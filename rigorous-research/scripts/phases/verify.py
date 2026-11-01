import re
import threading

from .. import agents, domains, driver, ledger, registry
from ..driver import GateFailed, PhaseResult
from . import common, discover

CREDIBLE = ledger.CREDIBLE_TIERS
ROUND_FAILURE_LIMIT = 3
_NUM_RE = re.compile(r"\d[\d,]*\.?\d*")


def reopen_not_found(ctx, d):
    if d.state.context.get("reopened"):
        return 0
    opened = 0
    for c in ctx.ledger.claims:
        if c["status"] == "not-found":
            c.update(status="open", rounds=0, paradigms_tried=[], round_log=[])
            ctx.ledger.archive_attempts(c["id"])
            opened += 1
    d.state.context["reopened"] = True
    ctx.ledger.save()
    d.save()
    return opened


def round_attempts(ctx, cid, n):
    return [
        a
        for a in ctx.ledger.attempts()
        if a["claim"] == cid and int(a["round"]) == n and a.get("ladder") == "discovery"
    ]


def _payload(
    ctx,
    claim,
    n,
    paradigms,
    variant,
    surfaces,
):
    lines = "\n".join(
        f"- {s.id} (cost {s.cost}) "
        + "; ".join(f"{kind}: {', '.join(names)}" for kind, names in s.routes.items())
        for s in surfaces
    )
    return (
        f"claim: {claim['id']}\nclaim text: {claim['text']}\nround: {n}\nquery_variant: {variant}\nparadigm: {', '.join(paradigms)}\n"
        f"inbox: {ctx.inbox}\nsource kinds: {', '.join(common.source_kinds(ctx.reg))}\n"
        f"{domains.prompt_block(ctx.step_data.get('domain', 'general'))}\n"
        f"surfaces of this paradigm (use only these):\n{lines}\n"
        f"{discover.ATTEMPTS_INSTRUCTION}\n"
    )


def _check_quotes(data):
    for ev in data.get("evidence") or []:
        q = str(ev.get("quote", ""))
        if "..." in q or "\u2026" in q:
            raise agents.AgentReplyError(f"spliced quote: {q[:40]!r}")


def _numeric_tokens(text):
    return [m.replace(",", "").rstrip(".") for m in _NUM_RE.findall(text)]


def _add_evidence(ctx, claim, row, text, step):
    added = 0
    visual = common.is_visual(row)
    ocr = common.ocr_text(ctx, row) if visual else ""
    for i, piece in enumerate(common.chunks(text, ctx.cfg.max_source_chars), 1):
        payload = f"claim: {claim['text']}\nsource: {row['url']}\n{agents.source_block(piece)}"
        data = agents.call(
            ctx.runner,
            "extractor",
            "evidence",
            payload,
            f"{step}.k{i}",
            required=("evidence",),
            strict=True,
            check=_check_quotes,
        )
        if data.get("_flags"):
            with ctx.ledger.lock:
                claim.setdefault("reply_flags", []).append(
                    {"source": row["id"], "piece": i, "reason": data["_flags"][0]}
                )
        if data.get("ignored_instructions"):
            ctx.step_data.setdefault("ignored", []).extend(
                {"source": row["id"], "text": str(t)[:200]}
                for t in data["ignored_instructions"]
            )
        for ev in data["evidence"] or []:
            quote = " ".join(str(ev.get("quote", "")).split())
            locator = str(ev.get("locator") or "").strip()
            if (
                ev.get("stance") not in ("supports", "contradicts")
                or not locator
                or not quote
                or len(quote.split()) > common.MAX_QUOTE_WORDS
                or not ctx.raw.contains(piece, quote)
            ):
                continue
            extra = {}
            if visual:
                extra = {
                    "read_by": "media",
                    "text_corroboration": bool(ocr) and ctx.raw.contains(ocr, quote),
                }
            if ctx.ledger.add_evidence(
                claim["id"], row["id"], ev["stance"], locator, quote, **extra
            ):
                added += 1
                if visual:
                    with ctx.ledger.lock:
                        if "visual-read" not in claim.setdefault("tags", []):
                            claim["tags"].append("visual-read")
    if added == 0:
        tokens = _numeric_tokens(claim["text"])
        normed = re.sub(r"\s+", " ", text.lower())
        if tokens and all(t.lower() in normed for t in tokens):
            with ctx.ledger.lock:
                if row["id"] not in claim.get("suspect_empty", []):
                    claim.setdefault("suspect_empty", []).append(row["id"])
    return added


def _evidence_rows(claim, sources, pairs):
    return "\n".join(
        f"- source {ev['source']} ({sources[ev['source']]['publisher']}, {src['tier']}, {src['url']}): {ev['stance']}, {ev['locator']}: {ev['quote']}"
        for ev, src in pairs
    )


def _independent(ctx, claim, pairs, n):
    if not pairs:
        return False
    if any(src["tier"] == "T1" for _, src in pairs):
        return True
    credible = [(ev, src) for ev, src in pairs if src["tier"] in CREDIBLE]
    if len({src["publisher"].strip().lower() for _, src in credible}) < 2:
        return False
    if ledger.meets_bar(pairs):
        return True
    signature = sorted(ev["source"] for ev, _ in credible)
    asked = ctx.step_data.setdefault("independence", {})
    memo = f"{claim['id']}|{','.join(signature)}"
    if memo in asked:
        return False
    asked[memo] = True
    sources = ctx.ledger.sources_by_id()
    payload = f"claim: {claim['text']}\nsupporting T1/T2 evidence from distinct publishers:\n{_evidence_rows(claim, sources, credible)}\n"
    data = agents.call(
        ctx.runner,
        "verifier",
        "independence",
        payload,
        f"verify.{claim['id']}.r{n}.independence",
        required=("independent",),
    )
    rationale = " ".join(str(data.get("rationale") or "").split())
    if data["independent"] is True and rationale:
        with ctx.ledger.lock:
            credible[0][0]["independence_rationale"] = rationale
        return True
    return False


def _positions(ctx, claim, n):
    sources = ctx.ledger.sources_by_id()
    pairs = [
        (ev, sources[ev["source"]])
        for ev in claim["evidence"]
        if ev["source"] in sources
        and sources[ev["source"]]["tier"] in CREDIBLE
        and sources[ev["source"]]["status"] == "read"
    ]
    allowed = {ev["source"] for ev, _ in pairs}
    payload = f"claim: {claim['text']}\ncredible supporting and contradicting evidence:\n{_evidence_rows(claim, sources, pairs)}\n"
    data = agents.call(
        ctx.runner,
        "verifier",
        "positions",
        payload,
        f"verify.{claim['id']}.r{n}.positions",
        required=("positions",),
    )
    out = []
    for p in data["positions"] or []:
        text = " ".join(str(p.get("text") or "").split())
        srcs = [s for s in (p.get("sources") or []) if s in allowed]
        if text and srcs:
            out.append(
                {
                    "text": text,
                    "holders": [str(h) for h in (p.get("holders") or [])],
                    "sources": srcs,
                }
            )
    if len(out) >= 2:
        return out
    fallback = []
    for stance, label in (
        ("supports", "Sources that support the claim"),
        ("contradicts", "Sources that contradict the claim"),
    ):
        group = [(ev, src) for ev, src in pairs if ev["stance"] == stance]
        if group:
            fallback.append(
                {
                    "text": f"{label}: {claim['text']}",
                    "holders": sorted({src["publisher"] for _, src in group}),
                    "sources": sorted({ev["source"] for ev, _ in group}),
                }
            )
    return fallback


def settle(ctx, cid, n):
    claim = ctx.ledger.claim(cid)
    sources = ctx.ledger.sources_by_id()
    sup, con = ledger.supporting(claim, sources), ledger.contradicting(claim, sources)
    sup_c, con_c = (
        ledger.supporting(claim, sources, CREDIBLE),
        ledger.contradicting(claim, sources, CREDIBLE),
    )
    last = n >= ctx.reg["max_rounds"]
    if sup_c and con_c:
        if last or (
            _independent(ctx, claim, sup, n) and _independent(ctx, claim, con, n)
        ):
            positions = _positions(ctx, claim, n)
            with ctx.ledger.lock:
                claim["positions"] = positions
            return "interpretive"
        return None
    if _independent(ctx, claim, sup, n):
        if n >= ctx.cfg.min_rounds_true or last:
            return "true"
    elif _independent(ctx, claim, con, n):
        return "untrue"
    return "not-found" if last else None


TEMPLATE_TWINS = 3


def _print(reply):
    attempts = sorted(
        (str(a.get("surface")), str(a.get("url")), str(a.get("status")))
        for a in reply.get("attempts") or []
        if isinstance(a, dict)
    )
    return f"{attempts}|{len(reply.get('sources') or [])}"


def _genuine(ctx, entry):
    twins = sum(
        1
        for c in ctx.ledger.claims
        for r in c.get("round_log", [])
        if r["round"] == entry["round"] and r["print"] == entry["print"]
    )
    return twins < TEMPLATE_TWINS


def _barren(ctx, claim):
    log = claim.get("round_log", [])
    return (
        len(log) >= 3
        and all(r["new_read_sources"] == 0 and _genuine(ctx, r) for r in log[-2:])
        and not any(r["sources"] for r in log)
        and not claim["evidence"]
        and not claim.get("suspect_empty")
    )


def _do_round(ctx, cid, fatal):
    try:
        claim = ctx.ledger.claim(cid)
        if claim["rounds"] >= ctx.reg["max_rounds"]:
            status = settle(ctx, cid, claim["rounds"])
            if status:
                with ctx.ledger.lock:
                    claim["status"] = status
            ctx.ledger.save()
            return status
        n = claim["rounds"] + 1
        paradigms = registry.round_paradigms(ctx.reg, n)
        variant = common.VARIANTS[(n - 1) % len(common.VARIANTS)]
        surfaces = [
            s for p in paradigms for s in registry.discovery_surfaces(ctx.reg, p)
        ]
        gens = common.pool_generations(ctx, surfaces)
        rows = {}
        rejected = []
        payload = _payload(ctx, claim, n, paradigms, variant, surfaces)
        earlier = {
            a["paradigm"]
            for a in ctx.ledger.attempts()
            if a["claim"] == cid
            and a.get("ladder") == "discovery"
            and int(a["round"]) < n
        }
        for attempt in range(2):
            note = (
                ""
                if attempt == 0
                else "\n\nThe previous pass reported no valid attempt for this round or hit a key rotation"
                + (f" (rejected: {'; '.join(rejected)[:600]})" if rejected else "")
                + ". Run the round again with only this round's surfaces and report every attempt.\n"
            )
            reply = agents.call(
                ctx.runner,
                "discovery",
                "discover-round",
                payload + note,
                f"verify.{cid}.r{n}.discover" + ("" if attempt == 0 else ".again"),
                {"inbox": str(ctx.inbox), "claim": cid, "round": n},
                required=("sources",),
            )
            rejected += common.log_reply_attempts(
                ctx, reply, cid, n, allowed=set(paradigms), earlier=earlier
            )
            decisions = common.handle_errors(ctx, reply, gens)
            for row, text in common.take_sources(ctx, reply):
                rows[row["id"]] = (row, text)
            if "rate_limited" in decisions and not rows:
                raise driver.RateLimited()
            if round_attempts(ctx, cid, n) and not (
                attempt == 0 and "retry" in decisions
            ):
                break
        logged = round_attempts(ctx, cid, n)
        if not logged:
            raise RuntimeError(
                f"{cid} round {n}: the discovery agent reported no valid attempt"
                + (f" ({'; '.join(rejected)})" if rejected else "")
            )
        used = {a["paradigm"] for a in logged}
        bad = [
            f"{cid} round {n}: paradigm {p} is outside {paradigms}"
            for p in sorted(used - set(paradigms))
        ] + [
            f"{cid} round {n}: paradigm {p} repeats an earlier round"
            for p in sorted(used & earlier)
        ]
        if bad:
            raise GateFailed("rotation", bad)
        asks = []
        for sid, (row, text) in rows.items():
            try:
                _add_evidence(
                    ctx, claim, row, text, f"verify.{cid}.r{n}.evidence.{sid}"
                )
            except driver.NeedsAgent as exc:
                asks += exc.asks
        if asks:
            raise driver.NeedsAgent(asks)
        with ctx.ledger.lock:
            claim["rounds"] = n
            claim["paradigms_tried"] = list(
                dict.fromkeys(
                    a["paradigm"]
                    for a in sorted(
                        ctx.ledger.attempts(), key=lambda a: int(a["round"])
                    )
                    if a["claim"] == cid and a.get("ladder") == "discovery"
                )
            )
        read_ids = sorted(
            sid for sid, (row, _) in rows.items() if row.get("status") == "read"
        )
        with ctx.ledger.lock:
            seen = {s for r in claim.get("round_log", []) for s in r["sources"]}
            claim.setdefault("round_log", []).append(
                {
                    "round": n,
                    "sources": read_ids,
                    "new_read_sources": len(set(read_ids) - seen),
                    "print": _print(reply),
                }
            )
        status = settle(ctx, cid, n)
        if status is None and _barren(ctx, claim):
            status = "not-found"
            with ctx.ledger.lock:
                claim["not_found_reason"] = f"no-public-record-after-{n}-rounds"
        if status:
            with ctx.ledger.lock:
                claim["status"] = status
        ctx.ledger.save()
        return status
    except (driver.PoolExhausted, GateFailed) as exc:
        fatal.append(exc)
        return None


_INFLIGHT = set()
_INFLIGHT_LOCK = threading.Lock()


def _guarded_round(ctx, cid, fatal):
    key = (id(ctx.ledger), cid)
    with _INFLIGHT_LOCK:
        if key in _INFLIGHT:
            raise RuntimeError(f"{cid}: the previous round is still running")
        _INFLIGHT.add(key)
    try:
        return _do_round(ctx, cid, fatal)
    finally:
        with _INFLIGHT_LOCK:
            _INFLIGHT.discard(key)


def verify(ctx, d):
    common.guard_pools(ctx)
    common.bind_domain(ctx, d)
    reopened = reopen_not_found(ctx, d)
    failures = d.state.context.setdefault("round_failures", {})
    size, wave = ctx.cfg.wave_size, 0
    while True:
        todo = [c["id"] for c in ctx.ledger.claims if c["status"] == "open"]
        if not todo:
            break
        wave += 1
        fatal = []
        before_sources = {s["id"] for s in ctx.ledger.sources}
        results, size = driver.run_wave(
            {cid: cid for cid in todo},
            lambda cid: _guarded_round(ctx, cid, fatal),
            size=size,
            timeout=ctx.cfg.wave_timeout,
        )
        for exc in fatal:
            raise exc
        for cid, res in results.items():
            if res.ok:
                failures.pop(cid, None)
                continue
            if res.waiting:
                continue
            if res.error == "rate limited":
                if not any(r.ok for r in results.values()):
                    raise driver.PoolExhausted(
                        "rate_limit", f"{cid}: rate limited across all wave retries"
                    )
                continue
            failures[cid] = failures.get(cid, 0) + 1
            if failures[cid] >= ROUND_FAILURE_LIMIT:
                raise RuntimeError(
                    f"{cid}: round failed {ROUND_FAILURE_LIMIT} times: {res.error}"
                )
        added = [s for s in ctx.ledger.sources if s["id"] not in before_sources]
        discover.log_wave(
            d,
            {
                "phase": "verify",
                "wave": wave,
                "claims": todo,
                "settled": {
                    cid: r.value for cid, r in results.items() if r.ok and r.value
                },
                "errors": {
                    cid: r.error
                    for cid, r in results.items()
                    if not r.ok and not r.waiting
                },
                "sources_read": [s["url"] for s in added if s["status"] == "read"],
                "sources_failed": [
                    {"url": s["url"], "reason": s.get("fail_reason")}
                    for s in added
                    if s["status"] == "failed"
                ],
                "batch_size": size,
            },
        )
        ctx.ledger.save()
        d.save()
        if asks := driver.waiting(results):
            raise asks
    counts = {}
    for c in ctx.ledger.claims:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    return PhaseResult(data={"waves": wave, "reopened": reopened, **counts})
