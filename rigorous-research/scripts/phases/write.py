import re
from pathlib import Path

import yaml

from .. import agents, domains, ledger, lesson, render, site
from ..driver import GateFailed, PhaseResult
from ..workspace import normalize_url

PUBLISHABLE = ("true", "interpretive", "untrue")
SINGLE_PAGE_MODES = ("rules", "answer", "recommend")
COMPOSING = re.compile(r"\b(composed|wrote|written|composer)\b", re.I)
LAYOUTS_MD = Path(__file__).resolve().parent.parent.parent / "references" / "layouts.md"


def drafts_dir(ctx):
    return ctx.topic_dir / "drafts"


def lessons_dir(ctx):
    return ctx.topic_dir / "lessons"


def publishable(ctx):
    return [c for c in ctx.ledger.claims if c["status"] in PUBLISHABLE]


def topic_title(ctx):
    return ctx.topic.replace("-", " ").title()


def claim_sources(ctx, claim):
    by_id = ctx.ledger.sources_by_id()
    ids = [e["source"] for e in claim["evidence"]] + [
        s for p in claim.get("positions", []) for s in p["sources"]
    ]
    return [
        by_id[i]
        for i in dict.fromkeys(ids)
        if i in by_id
        and by_id[i]["status"] == "read"
        and re.match(r"https?://", by_id[i]["url"])
    ]


def _pick_chapters(ctx, d):
    by_cluster = {}
    for c in ctx.ledger.claims:
        by_cluster.setdefault(c.get("cluster") or "General", []).append(c)
    keep = []
    dropped = []
    for name, claims in by_cluster.items():
        bad = sorted(
            {c["status"] for c in claims if c["status"] not in ("true", "interpretive")}
        )
        composer = " ".join(
            [name, *(c["text"] for c in claims if COMPOSING.search(c["text"]))]
        )
        banned = domains.banned_composer(composer, d.state.prompt)
        era = domains.banned_era(" ".join([name, *(c["text"] for c in claims)]))
        if banned:
            dropped.append(
                {"cluster": name, "reason": f"composer on the ban list: {banned}"}
            )
        elif era:
            dropped.append({"cluster": name, "reason": f"era ban: {era}"})
        elif bad:
            dropped.append(
                {"cluster": name, "reason": "a fact of this pick is " + ", ".join(bad)}
            )
        else:
            keep.append(name)
    d.state.context["dropped_picks"] = dropped
    if not keep:
        raise GateFailed(
            "write",
            ["no pick survived the checks"]
            + [f"{x['cluster']}: {x['reason']}" for x in dropped],
        )
    return [{"n": 1, "title": topic_title(ctx), "clusters": keep}]


def _media_chapters(ctx, d):
    ok = {c["id"]: c for c in publishable(ctx)}
    chapters = [
        {"title": m["title"], "claim_ids": [i for i in m["claim_ids"] if i in ok]}
        for m in d.state.context["media_chapters"]
    ]
    chapters = [ch for ch in chapters if ch["claim_ids"]]
    placed = {i for ch in chapters for i in ch["claim_ids"]}
    for cid, claim in ok.items():
        if cid in placed or not chapters:
            continue
        cluster = claim.get("cluster")
        best = max(
            chapters,
            key=lambda ch: sum(
                1 for i in ch["claim_ids"] if ok[i].get("cluster") == cluster
            ),
        )
        best["claim_ids"].append(cid)
    return [
        {"n": i, "title": ch["title"], "clusters": [], "claim_ids": ch["claim_ids"]}
        for i, ch in enumerate(chapters, 1)
    ]


def _title_chapters(ctx, d):
    if d.state.mode == "recommend":
        return _pick_chapters(ctx, d)
    if (
        d.state.mode == "learn"
        and len(
            media := _media_chapters(ctx, d)
            if d.state.context.get("media_chapters")
            else []
        )
        > 1
    ):
        return media
    by_cluster = {}
    for c in publishable(ctx):
        by_cluster.setdefault(c.get("cluster") or "General", []).append(c)
    if not by_cluster:
        raise GateFailed(
            "write", ["no claim reached true, interpretive or untrue; nothing to write"]
        )
    clusters = list(by_cluster)
    if d.state.mode in SINGLE_PAGE_MODES or len(clusters) == 1:
        return [{"n": 1, "title": topic_title(ctx), "clusters": clusters}]
    rows = "\n".join(
        f"- {name}: " + "; ".join(f"{c['id']} {c['text']}" for c in by_cluster[name])
        for name in clusters
    )
    data = agents.call(
        ctx.runner,
        "author",
        "course",
        f"topic: {d.state.prompt}\nconcept clusters with their verified claims:\n{rows}\n",
        "course",
        required=("chapters",),
    )
    seen = set()
    chapters = []
    for ch in data["chapters"] or []:
        picked = [
            c for c in (ch.get("clusters") or []) if c in by_cluster and c not in seen
        ]
        seen.update(picked)
        if picked:
            chapters.append(
                {
                    "title": " ".join(str(ch.get("title") or picked[0]).split()),
                    "clusters": picked,
                }
            )
    left = [c for c in clusters if c not in seen]
    if left:
        if chapters:
            chapters[-1]["clusters"] += left
        else:
            chapters.append({"title": topic_title(ctx), "clusters": left})
    return [{"n": i, **ch} for i, ch in enumerate(chapters, 1)]


def citation_problems(ctx, sentence):
    by_id = {c["id"]: c for c in ctx.ledger.claims}
    allowed = {
        normalize_url(s["url"])
        for cid in sentence["claims"]
        if cid in by_id
        for s in claim_sources(ctx, by_id[cid])
    }
    return [
        f"{sentence['id']}: cites {m[2]} which is not a source of {sentence['claims']}"
        for m in render.LINK.finditer(sentence["text"])
        if normalize_url(m[2]) not in allowed
    ]


def _norm_sentence(item, block):
    item = item if isinstance(item, dict) else {}
    return {
        "text": " ".join(str(item.get("text") or "").split()),
        "claims": [str(c) for c in (item.get("claims") or [])],
        "block": block,
    }


def normalize_draft(data):
    answer = _norm_sentence(data.get("answer"), "plain")
    body, errata = [], []
    for item in data.get("sentences") or []:
        block = (
            item.get("block")
            if isinstance(item, dict)
            and item.get("block") in ("plain", "debate", "errata")
            else "plain"
        )
        (errata if block == "errata" else body).append(_norm_sentence(item, block))
    errata += [_norm_sentence(item, "errata") for item in data.get("errata") or []]
    n = 0
    out = {
        "title": " ".join(str(data.get("title") or "").split()),
        "answer": answer,
        "sentences": body,
        "errata": errata,
    }
    for s in [answer, *body, *errata]:
        n += 1
        s["id"] = f"s{n}"
    return out


def draft_sentences(draft):
    return [draft["answer"], *draft["sentences"], *draft["errata"]]


def draft_problems(ctx, draft, chapter_ids):
    problems = []
    if not draft["title"]:
        problems.append("draft has no title")
    for s in draft_sentences(draft):
        if not s["text"]:
            problems.append(f"{s['id']}: empty sentence")
        for cid in s["claims"]:
            if cid not in chapter_ids:
                problems.append(f"{s['id']}: claim {cid} is not in this chapter")
        problems += citation_problems(ctx, s)
    if not draft["sentences"] and not draft["errata"]:
        problems.append("draft has no sentences")
    problems += [
        str(v)
        for v in ledger.check_sentences(draft_sentences(draft), ctx.ledger.claims_doc)
    ]
    return problems


def _claim_rows(ctx, claims):
    rows = []
    for c in claims:
        srcs = (
            "; ".join(f"{s['publisher']} ({s['url']})" for s in claim_sources(ctx, c))
            or "none"
        )
        rows.append(f"- {c['id']} [{c['status']}] {c['text']} | sources: {srcs}")
    return "\n".join(rows)


def write(ctx, d):
    st = d.state.context
    if "chapters" not in st:
        st["chapters"] = _title_chapters(ctx, d)
        st["drafts_done"] = []
        for stale in (
            *drafts_dir(ctx).glob("ch*.yaml"),
            *lessons_dir(ctx).glob("ch*.yaml"),
        ):
            stale.unlink()
        d.save()
    drafts_dir(ctx).mkdir(parents=True, exist_ok=True)
    by_cluster = {}
    for c in publishable(ctx):
        by_cluster.setdefault(c.get("cluster") or "General", []).append(c)
    for ch in st["chapters"]:
        if ch["n"] in st["drafts_done"]:
            continue
        claims = (
            [c for c in publishable(ctx) if c["id"] in ch["claim_ids"]]
            if "claim_ids" in ch
            else [c for name in ch["clusters"] for c in by_cluster.get(name, [])]
        )
        if not claims:
            raise GateFailed("write", [f"chapter {ch['n']} has no publishable claims"])
        ids = {c["id"] for c in claims}
        problems = []
        draft = {}
        for attempt in range(2):
            note = (
                ""
                if not problems
                else "\nYour draft was rejected:\n"
                + "\n".join(f"- {p}" for p in problems)
                + "\nWrite it again.\n"
            )
            payload = f"topic: {d.state.prompt}\nmode: {d.state.mode}\nchapter: {ch['title']}\nclaims:\n{_claim_rows(ctx, claims)}\n{note}"
            data = agents.call(
                ctx.runner,
                "author",
                "draft",
                payload,
                f"draft.ch{ch['n']}" + ("" if attempt == 0 else ".again"),
                required=("answer",),
            )
            draft = normalize_draft(data)
            draft["title"] = draft["title"] or ch["title"]
            problems = draft_problems(ctx, draft, ids)
            if not problems:
                break
        if problems:
            raise GateFailed("write", [f"chapter {ch['n']}: {p}" for p in problems])
        (drafts_dir(ctx) / f"ch{ch['n']}.yaml").write_text(
            yaml.safe_dump(
                {"chapter": ch["n"], "topic": ctx.topic, "mode": d.state.mode, **draft},
                sort_keys=False,
                allow_unicode=True,
                width=100,
            ),
            encoding="utf-8",
        )
        st["drafts_done"].append(ch["n"])
        d.save()
    return PhaseResult(data={"chapters": len(st["chapters"])})


def load_draft(ctx, n):
    return yaml.safe_load((drafts_dir(ctx) / f"ch{n}.yaml").read_text(encoding="utf-8"))


def conformance(ctx, d):
    by_id = {c["id"]: c for c in ctx.ledger.claims}
    problems = []
    for ch in d.state.context["chapters"]:
        draft = load_draft(ctx, ch["n"])
        sentences = draft_sentences(draft)
        mapped = sorted({cid for s in sentences for cid in s["claims"]})
        payload = (
            "final sentences:\n"
            + "\n".join(f"- {s['id']}: {s['text']}" for s in sentences)
            + "\nledger claims:\n"
            + "\n".join(
                f"- {cid}: {by_id[cid]['text']}" for cid in mapped if cid in by_id
            )
            + "\n"
        )
        data = agents.call(
            ctx.runner,
            "extractor",
            "conformance",
            payload,
            f"conformance.ch{ch['n']}",
            required=("sentences",),
        )
        seen = {}
        for item in data["sentences"] or []:
            if isinstance(item, dict) and item.get("id"):
                seen[str(item["id"])] = item
        for s in sentences:
            item = seen.get(s["id"])
            if item is None:
                problems.append(
                    f"ch{ch['n']} {s['id']}: the extractor returned no verdict for this sentence"
                )
                continue
            extra = [m for m in (item.get("matches") or []) if m not in s["claims"]]
            if extra:
                problems.append(
                    f"ch{ch['n']} {s['id']}: asserts {extra} but maps only {s['claims']}"
                )
            missing = ledger.prose_claims_missing(
                [str(t) for t in (item.get("new") or [])], ctx.ledger.claims_doc
            )
            problems += [
                f"ch{ch['n']} {s['id']}: assertion not in the ledger: {t}"
                for t in missing
            ]
    if problems:
        raise GateFailed("conformance", problems)
    return PhaseResult(data={"chapters": len(d.state.context["chapters"])})


def _signature(sentences):
    return {
        (s["id"], s["text"], tuple(s["claims"]), s.get("block", "plain"))
        for s in sentences
    }


def layout(ctx, d):
    lessons_dir(ctx).mkdir(parents=True, exist_ok=True)
    table = LAYOUTS_MD.read_text(encoding="utf-8")
    allowed = ", ".join(lesson.MODE_LAYOUTS[d.state.mode])
    chosen = {}
    for ch in d.state.context["chapters"]:
        draft = load_draft(ctx, ch["n"])
        want = _signature(draft_sentences(draft))
        problems = []
        doc = {}
        for attempt in range(2):
            note = (
                ""
                if not problems
                else "\nYour lesson source was rejected:\n"
                + "\n".join(f"- {p}" for p in problems)
                + "\nReply again.\n"
            )
            payload = (
                f"mode: {d.state.mode}\ntopic: {ctx.topic}\nchapter: {ch['n']}\nlayouts allowed in this mode: {allowed}\n{table}\n"
                f"existing subjects: {', '.join(site.existing_subjects(ctx.site_root)) or 'none'}\n"
                f"draft:\n{yaml.safe_dump({k: draft[k] for k in ('title', 'answer', 'sentences', 'errata')}, sort_keys=False, allow_unicode=True)}{note}"
            )
            doc = agents.call(
                ctx.runner,
                "author",
                "layout",
                payload,
                f"layout.ch{ch['n']}" + ("" if attempt == 0 else ".again"),
            )
            doc.update(schema=1, topic=ctx.topic, mode=d.state.mode)
            if d.state.context.get("subject"):
                doc["subject"] = d.state.context["subject"]
            doc.setdefault("title", draft["title"])
            if d.state.mode == "learn":
                doc["chapter"] = ch["n"]
            problems = lesson.validate(doc)
            if not problems:
                got = _signature(lesson.sentences(doc))
                problems = [
                    f"sentence changed or dropped: {x[0]}" for x in sorted(want - got)
                ] + [f"sentence added: {x[0]}" for x in sorted(got - want)]
            if not problems:
                break
        if problems:
            raise GateFailed("layout", [f"chapter {ch['n']}: {p}" for p in problems])
        (lessons_dir(ctx) / f"ch{ch['n']}.yaml").write_text(
            lesson.dump(doc), encoding="utf-8"
        )
        chosen[ch["n"]] = doc["layout"]
    d.state.context["layouts"] = chosen
    return PhaseResult(data={"layouts": chosen})
