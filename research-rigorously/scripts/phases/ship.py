import hashlib
import json
import re
import shutil
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

from .. import agents, footnotes, ledger, lesson, registry, site, workspace
from ..driver import GateFailed, NeedsAgent, PhaseResult
from ..publish import HOME_INDEX, PublishResult, rendered_files
from . import common, write


def _rel(ctx, path):
    return path.relative_to(ctx.site_root).as_posix()


def default_live_fetch(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "research-rigorously-live-check/1",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except Exception:
        return 0, b""


# One policy for publish and remove (ADR 0039): 12 attempts, 20 s apart.
LIVE_ATTEMPTS = 12
LIVE_DELAY = 20.0


def live_problems(fetch, base, expected, removed=()):
    """Compare live bytes with the committed files; every removed path must 404."""
    problems = []
    for rel, want in expected.items():
        code, body = fetch(f"{base}/{rel}")
        if code != 200:
            problems.append(f"{rel}: HTTP {code}")
        elif site.lf(body) != want:
            problems.append(f"{rel}: live bytes differ from the published file")
    for rel in removed:
        code, _ = fetch(f"{base}/{rel}")
        if code != 404:
            problems.append(f"{rel}: HTTP {code}, want 404")
    return problems


def live_check_until(fetch, base, expected, removed=(), sleep=None):
    """The one retry loop; returns (problems, attempts)."""
    import time

    sleep = sleep or time.sleep
    attempts = 0
    for attempt in range(LIVE_ATTEMPTS):
        attempts = attempt + 1
        problems = live_problems(fetch, base, expected, removed)
        if not problems or attempt == LIVE_ATTEMPTS - 1:
            return problems, attempts
        sleep(LIVE_DELAY)
    return [], attempts


def render_pages(ctx, d):
    ctx.ledger.save()
    claims_doc, sources_doc = ctx.ledger.claims_doc, ctx.ledger.sources_doc
    site.sync_assets(ctx.site_root)
    record = {
        "answered_by": list(d.state.context.get("answered_by") or []),
        "date": ctx.stamp(),
    }
    pages = []
    if d.state.mode == "verify":
        ctx_state = d.state.context
        ctx_state.setdefault("verify_date", record["date"][:10])
        skipped = ctx_state.get("skipped", {})
        first = ctx.ledger.source(ctx_state["inputs"][0])
        meta = {
            "title": write.topic_title(ctx),
            "slug": ctx.topic,
            "date": ctx_state["verify_date"],
            "skipped": skipped.get("opinions", 0) + skipped.get("predictions", 0),
            "input_ref": "pasted text"
            if first["url"].startswith("text:")
            else first["url"],
        }
        pages.append(
            _rel(
                ctx,
                site.write_verify(
                    ctx.site_root, claims_doc, sources_doc, meta, record=record
                ),
            )
        )
    else:
        published_kind = site.read_course_kind(ctx.main_root / ctx.topic)
        published_subject = site.read_course_subject(ctx.main_root / ctx.topic)
        d.state.context.setdefault("kind_before", published_kind)
        topic_dir = ctx.site_root / ctx.topic
        published_index = ctx.main_root / ctx.topic / "index.html"
        if (
            d.state.mode == "learn"
            and published_index.is_file()
            and not (topic_dir / "index.html").exists()
        ):
            # Seed the staged index from what is published so its preserved extras survive.
            topic_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(published_index, topic_dir / "index.html")
        for ch in d.state.context["chapters"]:
            doc = lesson.load(write.lessons_dir(ctx) / f"ch{ch['n']}.yaml")
            if d.state.mode in site.SINGLE_MODES:
                path = site.write_single(
                    ctx.site_root, doc, claims_doc, sources_doc, record=record
                )
            else:
                path = site.write_lesson(
                    ctx.site_root,
                    doc,
                    claims_doc,
                    sources_doc,
                    topic_title=write.topic_title(ctx),
                    kind=d.state.context.get("course_kind") or published_kind,
                    subject=doc.get("subject") or published_subject,
                    record=record,
                )
            pages.append(_rel(ctx, path))
    d.state.context["pages"] = pages
    return PhaseResult(data={"pages": pages})


def _verifier_rows(ctx, claims):
    by_id = ctx.ledger.sources_by_id()
    out = []
    for c in claims:
        out.append(f"- {c['id']} [{c['status']}] {c['text']}")
        for ev in c["evidence"]:
            s = by_id.get(ev["source"], {})
            out.append(
                f'    evidence {ev["source"]} ({s.get("publisher")}, {s.get("tier")}, {s.get("url")}) {ev["stance"]} at {ev["locator"]}: "{ev["quote"]}"'
            )
        for p in c.get("positions", []):
            out.append(f"    position: {p['text']} (sources {', '.join(p['sources'])})")
    return "\n".join(out)


def _gate_call(ctx, claims, step):
    data = agents.call(
        ctx.runner,
        "verifier",
        "gate",
        _verifier_rows(ctx, claims) + "\n",
        step,
        required=("verdicts",),
    )
    return {
        str(v.get("claim")): v for v in data["verdicts"] or [] if isinstance(v, dict)
    }


def verifier_problems(ctx):
    # `unchecked` claims assert nothing, so there is no verdict to give them.
    claims = [c for c in ctx.ledger.claims if c["status"] != "unchecked"]
    verdicts, asks = {}, []
    for i in range(0, len(claims), ctx.cfg.gate_batch):
        batch = claims[i : i + ctx.cfg.gate_batch]
        step = f"gate.b{i // ctx.cfg.gate_batch + 1}"
        try:
            verdicts.update(_gate_call(ctx, batch, step))
        except NeedsAgent as exc:
            asks.extend(exc.asks)
    if asks:
        # Every missing batch ask goes out in one wave: one resume answers the lot.
        raise NeedsAgent(asks)
    disputed = [
        c for c in claims if (verdicts.get(c["id"]) or {}).get("verdict") != "agree"
    ]
    asks = []
    for c in disputed:
        try:
            verdicts.update(_gate_call(ctx, [c], f"gate.{c['id']}.recheck"))
        except NeedsAgent as exc:
            asks.extend(exc.asks)
    if asks:
        raise NeedsAgent(asks)
    problems = []
    agree = 0
    for c in claims:
        v = verdicts.get(c["id"])
        if v is None:
            problems.append(f"verifier gave no verdict for {c['id']}")
        elif v.get("verdict") != "agree":
            problems.append(
                f"verifier disagrees on {c['id']} ({c['status']}): {v.get('note') or 'no note'}"
            )
        else:
            agree += 1
    return problems, {
        "checked": len(claims),
        "agree": agree,
        "rechecked": len(disputed),
    }


def page_problems(ctx, d):
    problems = []
    verify = d.state.mode == "verify"
    source_ids = set(ctx.ledger.sources_by_id())
    for rel in d.state.context.get("pages", []):
        path = ctx.site_root / rel
        if not path.exists():
            problems.append(f"{rel}: page was not written")
            continue
        text = path.read_text(encoding="utf-8")
        if 'class="appendix"' not in text:
            problems.append(f"{rel}: no appendix")
        if "Sources failed to grab" not in text:
            problems.append(f"{rel}: appendix lacks the failed-sources list")
        if 'href="' + "../" * rel.count("/") + 'assets/lesson.css"' not in text:
            problems.append(f"{rel}: does not link the shared theme")
        if verify and '<meta name="robots" content="noindex">' not in text:
            problems.append(f"{rel}: verify page lacks noindex")
        if not verify and 'content="noindex"' in text:
            problems.append(f"{rel}: listed page is marked noindex")
        problems += [f"{rel}: {p}" for p in footnotes.problems(text, source_ids)]
    index = ctx.main_root / "index.html"
    if (
        verify
        and index.exists()
        and "answers/verify-" in index.read_text(encoding="utf-8")
    ):
        problems.append("home index lists a verify page")
    return problems


CAST_LINK = re.compile(r'href="[^"]*cast-map')


def course_problems(ctx, d):
    problems = []
    scan = [ctx.site_root / rel for rel in d.state.context.get("pages", [])]
    kind = "explainer"
    if d.state.mode == "learn":
        topic_dir = ctx.site_root / ctx.topic
        kind = site.read_course_kind(topic_dir)
        index = topic_dir / "index.html"
        text = index.read_text(encoding="utf-8") if index.exists() else ""
        if kind not in site.KINDS:
            problems.append(
                f"{ctx.topic}: index.html does not declare its course kind "
                "(a course-kind meta must hold narrative or explainer)"
            )
        elif (
            d.state.context.get("kind_before") == "narrative"
            and kind == "explainer"
            and not d.state.context.get("allow_kind_downgrade")
        ):
            problems.append(
                f"{ctx.topic}: course kind dropped from narrative to explainer (start with --kind explainer --allow-kind-downgrade to do that)"
            )
        if 'class="hub-table numbered"' not in text or 'class="index-rows"' in text:
            problems.append(
                f"{ctx.topic}/index.html: topic index is not the numbered hub-table"
            )
        scan += [index, *sorted((topic_dir / "reference").glob("*.html"))]
        if not site.read_course_subject(topic_dir):
            problems.append(f"{ctx.topic}: index.html has no subject meta")
    elif d.state.mode != "verify":
        for path in scan:
            if path.exists() and not site.read_page_subject(path):
                problems.append(
                    f"{path.relative_to(ctx.site_root).as_posix()}: page has no subject meta"
                )
    if kind == "explainer":
        if (ctx.site_root / ctx.topic / "reference" / "cast-map.html").exists():
            problems.append(f"{ctx.topic}: explainer has reference/cast-map.html")
        for path in scan:
            if path.exists() and CAST_LINK.search(path.read_text(encoding="utf-8")):
                problems.append(
                    f"{path.relative_to(ctx.site_root).as_posix()}: explainer links a Cast page"
                )
    return problems


def url_problems(ctx):
    return (
        []
        if ctx.cfg.site_url
        else [
            "no site_url configured: the live-bytes check cannot run (pass --site-url)"
        ]
    )


def lesson_problems(ctx, d):
    problems = []
    if d.state.mode == "verify":
        return problems
    for ch in d.state.context.get("chapters", []):
        doc = lesson.load(write.lessons_dir(ctx) / f"ch{ch['n']}.yaml")
        problems += [f"ch{ch['n']} {p}" for p in lesson.validate(doc)]
        problems += [
            f"ch{ch['n']} {v}"
            for v in lesson.sentence_violations(doc, ctx.ledger.claims_doc)
            if v.severity == "error"
        ]
    return problems


def mcp_fetch_tools(reg):
    """Every fetch-ladder surface's MCP tools, in ladder order."""
    surfaces = registry.surfaces(reg)
    out = []
    for sid in reg["fetch_ladder"]:
        surf = surfaces.get(sid)
        if surf is None:
            continue
        for name in surf.routes.get("mcp", ()):
            tool = registry.mcp_tool(surf.server, name)
            if tool not in out:
                out.append(tool)
    return out


def recheck_url(ctx, url):
    """A blocked cited URL's second chance: every non-MCP route, then one MCP ask.

    Returns (ok, routes) where routes records what was tried.
    """
    routes = []
    result = None
    if ctx.fetcher is not None:
        try:
            result = ctx.fetcher.read_url(url, ctx, allow_mcp=False)
        except Exception as exc:  # a vendor failure is a failed route, not a crash
            result = None
            routes.append({"route": "ladder-nonmcp", "status": "error", "code": str(exc)[:120]})
        if result is not None:
            routes.append(
                {
                    "route": "ladder-nonmcp",
                    "status": "ok" if result.ok else "error",
                    "code": (result.error or "")[:200],
                    "tried": list(result.tried),
                }
            )
        if result is not None and result.ok:
            return True, routes
    tools = mcp_fetch_tools(ctx.reg)
    if tools and ctx.runner is not None:
        step = "gate.urlaudit." + hashlib.sha256(url.encode()).hexdigest()[:10]
        dest = ctx.drop_dir / f"{step}.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            f"url: {url}\nmcp fetch tools (try each until one returns the page):\n"
            + "\n".join(f"- {tool}" for tool in tools)
            + f"\nsave the page text to: {dest}\n"
        )
        try:
            data = agents.call(
                ctx.runner, "discovery", "fetch", payload, step, required=("ok",)
            )
        except agents.Unanswerable as exc:
            routes.append({"route": "mcp", "status": "error", "code": f"unanswerable: {exc.reason}"})
            data = None
        if data is not None and data.get("ok") and dest.exists() and dest.read_text(
            encoding="utf-8", errors="replace"
        ).strip():
            dest.unlink(missing_ok=True)
            routes.append({"route": "mcp", "status": "ok", "tools": tools})
            return True, routes
        dest.unlink(missing_ok=True)
        if data is not None:
            routes.append(
                {
                    "route": "mcp",
                    "status": "error",
                    "code": str((data.get("error") or {}).get("code") or "ok: false"),
                    "tools": tools,
                }
            )
    return False, routes


def record_link_failure(ctx, url, routes):
    layout = workspace.Layout(ctx.cfg.state_root, ctx.topic)
    layout.link_failures.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "url": url,
        "topic": ctx.topic,
        "date": ctx.stamp(),
        "routes": routes,
    }
    with layout.link_failures.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=True) + "\n")


def audit_problems(ctx):
    if not ctx.cfg.url_audit:
        return [], "off"
    if ctx.audit_urls is None:
        return [], "skipped: no auditor configured"
    by_id = ctx.ledger.sources_by_id()
    urls = list(
        dict.fromkeys(
            by_id[ev["source"]]["url"]
            for c in ctx.ledger.claims
            if c["status"] in write.PUBLISHABLE
            for ev in c["evidence"]
            if ev["source"] in by_id
            and by_id[ev["source"]]["url"].startswith(("http://", "https://"))
        )
    )
    bad = []
    for r in ctx.audit_urls(urls):
        if r.ok:
            continue
        passed, routes = recheck_url(ctx, r.url)
        if passed:
            continue
        record_link_failure(ctx, r.url, routes)
        bad.append(f"url audit: {r.flag} {r.url} (HTTP {r.code})")
    return bad, f"{len(urls) - len(bad)}/{len(urls)} ok"


def gates(ctx, d):
    common.guard_pools(ctx)
    ctx.ledger.save()
    verdicts = {}
    problems = []
    found = ledger.check(
        ctx.ledger.claims_doc,
        ctx.ledger.sources_doc,
        ctx.ledger.attempts(),
        publish=True,
        round_order=ctx.reg["round_order"],
    )
    errors = [str(v) for v in found if v.severity == "error"]
    verdicts["ledger_check"] = {
        "errors": len(errors),
        "warnings": len(found) - len(errors),
    }
    problems += errors
    v_problems, v_counts = verifier_problems(ctx)
    verdicts["verifier"] = {**v_counts, "disagreements": len(v_problems)}
    problems += v_problems
    l_problems = lesson_problems(ctx, d)
    verdicts["lessons"] = {"problems": len(l_problems)}
    problems += l_problems
    p_problems = page_problems(ctx, d)
    verdicts["pages"] = {"problems": len(p_problems)}
    problems += p_problems
    c_problems = course_problems(ctx, d) + url_problems(ctx)
    verdicts["course"] = {"problems": len(c_problems)}
    problems += c_problems
    a_problems, summary = audit_problems(ctx)
    verdicts["url_audit"] = {"result": summary, "problems": len(a_problems)}
    problems += a_problems
    d.state.context["gates"] = verdicts
    if problems:
        raise GateFailed("gates", problems)
    return PhaseResult(data=verdicts)


def build_record(ctx, d):
    st = d.state.context
    claims = ctx.ledger.claims
    baseline = st.get("baseline", {})
    sources = ctx.ledger.sources
    return {
        "answered_by": st.get("answered_by", []),
        "claims": dict(Counter(c["status"] for c in claims)),
        "surfaces": dict(Counter(a["surface"] for a in ctx.ledger.attempts())),
        "sources_read": [
            s["url"]
            for s in sources
            if s["status"] == "read" and s.get("kind") != "input"
        ],
        "sources_failed": [
            {"url": s["url"], "reason": s.get("fail_reason")}
            for s in sources
            if s["status"] == "failed"
        ],
        "gates": st.get("gates", {}),
        "skipped": st.get("skipped"),
        "layouts": st.get("layouts"),
        "media_split": st.get("media_split"),
        "ignored_instructions": ctx.step_data.get("ignored", []),
        "diff_vs_previous": {
            "new": [c["id"] for c in claims if c["id"] not in baseline],
            "status_changed": {
                c["id"]: [baseline[c["id"]]["status"], c["status"]]
                for c in claims
                if c["id"] in baseline and baseline[c["id"]]["status"] != c["status"]
            },
            "unchanged": sum(
                1
                for c in claims
                if c["id"] in baseline and baseline[c["id"]]["status"] == c["status"]
            ),
        },
    }


def _topic_footprint(site_root, topic):
    """A topic's published files, shared with `rr remove` (never another topic's)."""
    from ..remove import resolve_footprint

    return resolve_footprint(site_root, topic)


DATE_META = re.compile(r'<meta name="research-rigorously-date" content="[^"]*">')


def _prune_topic(ctx, keep):
    """Delete clone files this topic owns but this run did not render; return their paths."""
    from ..publish import _ok

    deleted = []
    for path in _topic_footprint(ctx.main_root, ctx.topic):
        rel = path.relative_to(ctx.main_root).as_posix()
        if rel in keep:
            continue
        path.unlink(missing_ok=True)
        # Only a tracked file can be staged as a deletion; an untracked leftover
        # is gone from the clone but has no commit path.
        if _ok(ctx.main_root, "ls-files", "--error-unmatch", "--", rel):
            deleted.append(rel)
    return deleted


def _stamp_date(root, paths, stamp):
    """Set the run-date meta on the pages about to be committed (ADR 0039)."""
    for rel in paths:
        if not rel.endswith(".html"):
            continue
        path = Path(root) / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        new = DATE_META.sub(
            f'<meta name="research-rigorously-date" content="{stamp}">', text
        )
        if new != text:
            site.write_text(path, new)


def publish(ctx, d):
    d.state.context["record"] = build_record(ctx, d)
    d.save()
    staged = rendered_files(ctx.layout.site)
    # The home index is rebuilt from the clone: a render dir holds only this
    # topic, so copying its index would drop every other topic (ADR 0039).
    pages = [rel for rel in staged if rel not in HOME_INDEX]
    if not pages:
        raise RuntimeError("render wrote no pages to the run's site dir")
    deleted = []

    def after():
        # Under the publish lock, after the pull and the copy: drop this topic's
        # stale files, stamp the publish time on the committed pages, rebuild the
        # home index from the whole clone.
        deleted.extend(_prune_topic(ctx, {*pages, *HOME_INDEX}))
        _stamp_date(ctx.main_root, pages, ctx.stamp())
        site.regenerate_index(ctx.main_root)
        return deleted

    message = f"Publish {d.state.mode} {ctx.topic} ({d.state.run_id})"
    result = ctx.publisher.publish(
        pages,
        ctx.layout.site,
        message,
        generated=HOME_INDEX,
        after=after,
    )
    d.state.context["published"] = result._asdict()
    d.state.context["published_deleted"] = deleted
    d.write_record(status="published")
    d.save_finished()
    return PhaseResult(
        data={
            "sha": result.sha,
            "pushed": result.pushed,
            "pages": d.state.context.get("pages", []),
        }
    )


def live_check(ctx, d):
    if not ctx.cfg.site_url:
        raise GateFailed("live-check", url_problems(ctx))
    if d.state.context.get("reverted"):
        raise GateFailed(
            "live-check",
            [
                "the publish was reverted on main; a resume cannot re-publish, start a new run"
            ],
        )
    fetch = ctx.live_fetch or default_live_fetch
    base = ctx.cfg.site_url.rstrip("/")
    names = rendered_files(ctx.layout.site)
    # The clone holds the committed bytes: the home index it regenerated and the
    # pages stamped with the publish time (ADR 0039).
    expected = {rel: site.lf((ctx.main_root / rel).read_bytes()) for rel in names}
    for rel in HOME_INDEX:
        expected[rel] = site.lf((ctx.main_root / rel).read_bytes())
        if rel not in names:
            names.append(rel)
    removed = list(d.state.context.get("published_deleted") or [])
    problems, attempts = live_check_until(fetch, base, expected, removed, ctx.sleep)
    if not problems:
        return PhaseResult(
            data={"checked": names, "removed": removed, "attempts": attempts}
        )
    published = (
        PublishResult(**d.state.context["published"])
        if d.state.context.get("published")
        else PublishResult()
    )
    ctx.publisher.revert(published)
    d.state.context["reverted"] = True
    raise GateFailed("live-check", [*problems, "the publish was reverted on main"])
