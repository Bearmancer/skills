import re
from pathlib import Path
from urllib.parse import urlparse

from .. import agents, domains, driver, ledger, log_attempt, registry, urlaudit
from ..fetch import FetchResult, MEDIA_SUFFIXES, TEXT_SUFFIXES
from ..workspace import source_kinds, tier_for

INPUT_SUFFIXES = (".pdf", *TEXT_SUFFIXES, *MEDIA_SUFFIXES)
PATH_TOKEN = re.compile(r"\"([^\"]+)\"|'([^']+)'|(\S+)")
VARIANTS = ("supporting", "opposing", "primary", "other-language")
MAX_QUOTE_WORDS = ledger.MAX_QUOTE_WORDS


def find_inputs(prompt):
    found = list(urlaudit.extract_urls(prompt))
    for m in PATH_TOKEN.finditer(prompt):
        token = (m[1] or m[2] or m[3]).strip(",;()")
        if token.lower().endswith(INPUT_SUFFIXES) and not re.match(r"https?://", token):
            path = Path(token).expanduser()
            if path.exists() and str(path) not in found:
                found.append(str(path))
    return found


def bind_domain(ctx, d):
    ctx.step_data.setdefault(
        "domain", domains.domain_for(d.state.mode or "learn", d.state.prompt)
    )


def host_of(url):
    return re.sub(r"^www\.", "", urlparse(url).netloc.lower()) or "unknown"


def chunks(text, limit):
    out = []
    cur = ""
    for para in re.split(r"\n\s*\n", text):
        while len(para) > limit:
            if cur:
                out.append(cur)
                cur = ""
            out.append(para[:limit])
            para = para[limit:]
        if cur and len(cur) + len(para) + 2 > limit:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n\n{para}" if cur else para
    if cur.strip():
        out.append(cur)
    return out or [text]


def is_visual(row):
    return str(row.get("raw_path", "")).endswith("-visual.txt")


def store_source(
    ctx,
    url,
    res,
    *,
    kind,
    publisher,
    language=None,
    authority=None,
):
    tier = tier_for(ctx.reg, kind, url)
    with ctx.ledger.lock:
        if not res.ok:
            return ctx.ledger.add_source(
                url,
                kind=kind,
                tier=tier,
                publisher=publisher,
                status="failed",
                fail_reason=res.error or "unspecified",
            )
        row = ctx.ledger.add_source(
            url,
            kind=kind,
            tier=tier,
            publisher=publisher,
            language=language,
            authority=authority,
            retrieved_at=ctx.stamp(),
        )
        if row.get("raw_path") and ctx.raw.get(row["raw_path"]) is not None:
            return row
        name = f"{row['id']}-visual" if res.visual else row["id"]
        row["raw_path"], row["content_hash"] = ctx.raw.put(name, res.text)
        if res.visual:
            ctx.raw.put(f"{row['id']}-ocr", res.ocr_text)
        row.setdefault("retrieved_at", ctx.stamp())
        return row


def source_text(ctx, row):
    return ctx.raw.get(row.get("raw_path")) or ""


def ocr_text(ctx, row):
    if not is_visual(row):
        return ""
    return ctx.raw.get(row["raw_path"].replace("-visual.txt", "-ocr.txt")) or ""


class Extracted:
    def __init__(self):
        self.claims = []
        self.opinions = 0
        self.predictions = 0
        self.dropped = 0
        self.ignored = []


def _count(value):
    return value if isinstance(value, int) and value >= 0 else 0


def extract_claims(
    ctx,
    row,
    *,
    origin,
    step,
    evidence,
    text=None,
):
    out = Extracted()
    text = source_text(ctx, row) if text is None else text
    for i, piece in enumerate(chunks(text, ctx.cfg.max_source_chars), 1):
        data = agents.call(
            ctx.runner,
            "extractor",
            "claims",
            agents.source_block(piece),
            f"{step}.k{i}",
            required=("claims",),
        )
        skipped = data.get("skipped") or {}
        out.opinions += _count(skipped.get("opinions"))
        out.predictions += _count(skipped.get("predictions"))
        out.ignored += [str(x) for x in (data.get("ignored_instructions") or [])]
        for item in data["claims"] or []:
            if not isinstance(item, dict):
                out.dropped += 1
                continue
            claim_text = " ".join(str(item.get("text", "")).split())
            quote = " ".join(str(item.get("quote", "")).split())
            locator = str(item.get("locator") or "").strip()
            if (
                not claim_text
                or len(claim_text.split()) > ctx.cfg.max_claim_words
                or not quote
                or len(quote.split()) > MAX_QUOTE_WORDS
                or not ctx.raw.contains(piece, quote)
            ):
                out.dropped += 1
                continue
            cluster = " ".join(str(item.get("cluster") or "").split()) or "General"
            claim, created = ctx.ledger.add_claim(
                claim_text, origin, cluster, [locator] if locator else None
            )
            if evidence and locator:
                ctx.ledger.add_evidence(
                    claim["id"], row["id"], "supports", locator, quote
                )
            out.claims.append(claim)
    if out.ignored:
        ctx.step_data.setdefault("ignored", []).extend(
            {"source": row["id"], "text": t[:200]} for t in out.ignored
        )
    return out


def extract_input(ctx, d, sid, *, origin, step, evidence):
    row = ctx.ledger.source(sid)
    chapters = [
        ch for ch in d.state.context.get("media_chapters", []) if ch["source"] == sid
    ]
    if not chapters:
        return extract_claims(ctx, row, origin=origin, step=step, evidence=evidence)
    total = Extracted()
    for ch in chapters:
        got = extract_claims(
            ctx,
            row,
            origin=origin,
            step=f"{step}.ch{ch['n']}",
            evidence=evidence,
            text=ctx.raw.get(ch["raw_path"]) or "",
        )
        ch["claim_ids"] = list(
            dict.fromkeys([*ch["claim_ids"], *(c["id"] for c in got.claims)])
        )
        total.claims += got.claims
        total.opinions += got.opinions
        total.predictions += got.predictions
        total.dropped += got.dropped
        total.ignored += got.ignored
    return total


def valid_inbox_path(ctx, value):
    try:
        path = Path(value).resolve()
        path.relative_to(ctx.inbox.resolve())
    except (ValueError, OSError):
        return None
    return path if path.is_file() else None


def take_sources(ctx, reply):
    kinds = set(source_kinds(ctx.reg))
    out = []
    for src in (reply.get("sources") or [])[: ctx.cfg.max_sources_per_round]:
        if not isinstance(src, dict):
            continue
        url = str(src.get("url") or "").strip()
        if not re.match(r"https?://", url):
            continue
        kind = src.get("kind") if src.get("kind") in kinds else "unknown"
        publisher = str(src.get("publisher") or host_of(url))
        authority = (
            src.get("authority")
            if src.get("authority") in ("designer", "publisher")
            else None
        )
        if domains.banned_host(url, ctx.step_data.get("domain", "general")):
            store_source(
                ctx,
                url,
                FetchResult(False, error="streaming service: banned on music runs"),
                kind="unknown",
                publisher=host_of(url),
            )
            continue
        text = ""
        if src.get("file"):
            path = valid_inbox_path(ctx, str(src["file"]))
            text = path.read_text(encoding="utf-8", errors="replace") if path else ""
        text = text or str(src.get("text") or "")
        res = ctx.fetcher.read(url, ctx)
        if not res.ok and len(text.strip()) >= ctx.cfg.min_text_chars:
            res, kind = FetchResult(True, text, "agent"), "unknown"
        row = store_source(
            ctx,
            url,
            res,
            kind=kind,
            publisher=publisher,
            language=src.get("language"),
            authority=authority,
        )
        if row["status"] == "read":
            out.append((row, source_text(ctx, row)))
    for bad in reply.get("failed") or []:
        if not isinstance(bad, dict):
            continue
        url = str(bad.get("url") or "").strip()
        if url:
            store_source(
                ctx,
                url,
                FetchResult(False, error=str(bad.get("reason") or "unspecified")),
                kind="unknown",
                publisher=host_of(url),
            )
    return out


def log_reply_attempts(
    ctx,
    reply,
    claim,
    round_no,
    allowed=None,
    earlier=frozenset(),
):
    problems = []
    seen = {_attempt_key(a) for a in ctx.ledger.attempts()}
    for item in reply.get("attempts") or []:
        if not isinstance(item, dict):
            problems.append(f"attempt entry is not a mapping: {str(item)[:80]}")
            continue
        try:
            record = log_attempt.build_record(
                ctx.reg,
                claim=claim,
                round_no=round_no,
                surface=str(item.get("surface") or ""),
                route=str(item.get("route") or ""),
                url=str(item.get("url") or ""),
                status=str(item.get("status") or ""),
                query_variant=str(item.get("query_variant") or "supporting"),
                error_class=str(item["error_class"])
                if item.get("error_class")
                else None,
            )
        except log_attempt.AttemptError as exc:
            problems.append(f"{item.get('surface') or '?'}: {exc}")
            continue
        if allowed is not None and record["paradigm"] not in allowed:
            problems.append(
                f"{record['surface']}: paradigm {record['paradigm']} is outside this round's {sorted(allowed)}"
            )
            continue
        if record["paradigm"] in earlier:
            problems.append(
                f"{record['surface']}: paradigm {record['paradigm']} was used in an earlier round"
            )
            continue
        if _attempt_key(record) in seen:
            continue
        seen.add(_attempt_key(record))
        ctx.ledger.append_attempt(record)
    return problems


def _attempt_key(a):
    return tuple(
        str(a.get(k))
        for k in (
            "claim",
            "round",
            "surface",
            "route",
            "url",
            "status",
            "query_variant",
        )
    )


def server_of(ctx, surface):
    surf = registry.surfaces(ctx.reg).get(surface)
    return surf.server if surf else None


def handle_errors(ctx, reply, generations):
    decisions = []
    if ctx.keys is None:
        return decisions
    for err in reply.get("errors") or []:
        server = server_of(ctx, str(err.get("surface") or ""))
        if server is None:
            continue
        srv = ctx.reg["servers"][server]
        shown = f"{err.get('code')} {err.get('status')}".lower()
        if any(str(p).lower() in shown for p in srv.get("empty_results", [])):
            continue
        pool = srv.get("pool")
        decisions.append(
            ctx.keys.on_failure(
                server,
                status=err.get("status"),
                code=err.get("code"),
                url=str(err.get("url") or ""),
                seen_generation=generations.get(pool, 0),
            )
        )
    return decisions


def pool_generations(ctx, surfaces):
    if ctx.keys is None:
        return {}
    return {s.pool: ctx.keys.generation(s.pool) for s in surfaces if s.pool}


def guard_pools(ctx):
    if ctx.keys is None:
        return
    for server, spec in ctx.reg["servers"].items():
        if spec.get("wired") and spec.get("keyed"):
            ctx.keys.guard(server)


def raise_exhausted(errors):
    for exc in errors:
        if isinstance(exc, driver.PoolExhausted):
            raise exc


def state_ctx(d, key, default):
    return d.state.context.setdefault(key, default)
