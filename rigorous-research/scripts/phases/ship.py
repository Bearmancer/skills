import re
import urllib.error
import urllib.request
from collections import Counter

from .. import agents, footnotes, ledger, lesson, site
from ..driver import GateFailed, PhaseResult
from ..publish import PublishResult
from . import common, write


def _rel(ctx, path):
    return path.relative_to(ctx.site_root).as_posix()


def default_live_fetch(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "rigorous-research-live-check/1",
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


def render_pages(ctx, d):
    ctx.ledger.save()
    claims_doc, sources_doc = ctx.ledger.claims_doc, ctx.ledger.sources_doc
    site.sync_assets(ctx.site_root)
    pages = []
    if d.state.mode == "verify":
        ctx_state = d.state.context
        ctx_state.setdefault("verify_date", ctx.stamp()[:10])
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
            _rel(ctx, site.write_verify(ctx.site_root, claims_doc, sources_doc, meta))
        )
    else:
        d.state.context.setdefault(
            "kind_before", site.read_course_kind(ctx.site_root / ctx.topic)
        )
        for ch in d.state.context["chapters"]:
            doc = lesson.load(write.lessons_dir(ctx) / f"ch{ch['n']}.yaml")
            if d.state.mode in site.SINGLE_MODES:
                path = site.write_single(ctx.site_root, doc, claims_doc, sources_doc)
            else:
                path = site.write_lesson(
                    ctx.site_root,
                    doc,
                    claims_doc,
                    sources_doc,
                    topic_title=write.topic_title(ctx),
                    kind=d.state.context.get("course_kind"),
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
    claims = ctx.ledger.claims
    verdicts = {}
    for i in range(0, len(claims), ctx.cfg.gate_batch):
        batch = claims[i : i + ctx.cfg.gate_batch]
        verdicts.update(_gate_call(ctx, batch, f"gate.b{i // ctx.cfg.gate_batch + 1}"))
    disputed = [
        c for c in claims if (verdicts.get(c["id"]) or {}).get("verdict") != "agree"
    ]
    for c in disputed:
        verdicts.update(_gate_call(ctx, [c], f"gate.{c['id']}.recheck"))
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
    index = ctx.site_root / "index.html"
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
                f"{ctx.topic}: course kind is undeclared (course.json must hold narrative or explainer)"
            )
        elif (
            d.state.context.get("kind_before") == "narrative"
            and kind == "explainer"
            and not d.state.context.get("allow_kind_downgrade")
        ):
            problems.append(
                f"{ctx.topic}: course kind dropped from narrative to explainer (start with --kind explainer --allow-kind-downgrade to do that)"
            )
        elif f'<meta name="course-kind" content="{kind}">' not in text:
            problems.append(
                f"{ctx.topic}/index.html: course-kind meta does not match course.json ({kind})"
            )
        if 'class="hub-table numbered"' not in text or 'class="index-rows"' in text:
            problems.append(
                f"{ctx.topic}/index.html: topic index is not the numbered hub-table"
            )
        scan += [index, *sorted((topic_dir / "reference").glob("*.html"))]
        if not site.read_course_subject(topic_dir):
            problems.append(f"{ctx.topic}: course.json has no subject")
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
    bad = [r for r in ctx.audit_urls(urls) if not r.ok]
    return [
        f"url audit: {r.flag} {r.url} (HTTP {r.code})" for r in bad
    ], f"{len(urls) - len(bad)}/{len(urls)} ok"


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


def publish(ctx, d):
    if "pre_publish_base" not in d.state.context:
        d.state.context["pre_publish_base"] = ctx.publisher.head()
        d.save()
    d.state.context["record"] = build_record(ctx, d)
    d.write_record(status="published")
    d.save_finished()
    try:
        ctx.publisher.commit(f"Publish {d.state.mode} {ctx.topic} ({d.state.run_id})")
        result = ctx.publisher.publish(regen=site.regenerate_index)
    except BaseException:
        d.save()
        raise
    before = d.state.context.get("pre_publish_base")
    if result.sha and result.sha == result.base and before and before != result.sha:
        result = result._replace(base=before)
    d.state.context["published"] = result._asdict()
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
    names = [
        *d.state.context.get("pages", []),
        *(f"assets/{n}" for n in site.THEME_FILES),
    ]
    problems = []
    for attempt in range(ctx.cfg.live_attempts):
        problems = []
        for rel in names:
            want = site.lf((ctx.site_root / rel).read_bytes())
            code, body = fetch(f"{base}/{rel}")
            if code != 200:
                problems.append(f"{rel}: HTTP {code}")
            elif site.lf(body) != want:
                problems.append(f"{rel}: live bytes differ from the published file")
        if not problems:
            return PhaseResult(data={"checked": names, "attempts": attempt + 1})
        ctx.sleep(ctx.cfg.live_delay)
    published = (
        PublishResult(**d.state.context["published"])
        if d.state.context.get("published")
        else PublishResult()
    )
    ctx.publisher.revert(published)
    d.state.context["reverted"] = True
    raise GateFailed("live-check", [*problems, "the publish was reverted on main"])
