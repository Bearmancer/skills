from .. import agents, ledger, media
from ..driver import PhaseResult
from ..fetch import FetchResult, is_local
from ..workspace import normalize_url
from . import common

SKIP_KEYS = ("opinions", "predictions", "dropped")


def _snapshot(ctx, d):
    if "baseline" not in d.state.context:
        d.state.context["baseline"] = {
            c["id"]: {"hash": c["hash"], "status": c["status"]}
            for c in ctx.ledger.claims
        }


def _kind(d, source):
    if d.state.mode == "verify":
        return "input"
    if is_local(source):
        return (
            "rulebook"
            if d.state.mode == "rules" and source.lower().endswith(".pdf")
            else "original-document"
        )
    return "unknown"


def _split_media(ctx, d, row):
    if d.state.mode == "answer" or any(
        m["source"] == row["id"] for m in d.state.context.get("media_split", [])
    ):
        return
    text = common.source_text(ctx, row)
    info = row.get("media") or {}
    duration = media.duration_seconds(text, info.get("duration"))
    if not media.is_long(duration):
        return
    basis, reason = "metadata", "the recording's own chapters"
    chapters = media.plan(duration, info.get("chapters"))
    if not chapters and info.get("description"):
        basis, reason = "description", "chapter timestamps in the description"
        chapters = media.plan(
            duration, media.chapters_from_description(info["description"])
        )
    if not chapters:
        basis = "agent"
        payload = f"duration: {media.clock(duration)}\n{agents.source_block(media.outline(text))}\n"
        data = agents.call(
            ctx.runner,
            "extractor",
            "split",
            payload,
            f"ingest.split.{row['id']}",
            required=("split",),
        )
        reason = " ".join(str(data.get("reason") or "no reason given").split())
        if data.get("split") is True:
            chapters = media.from_decision(duration, data.get("chapters"))
            if not chapters:
                reason += " (the proposed chapters were unusable: no split)"
    d.state.context.setdefault("media_split", []).append(
        {
            "source": row["id"],
            "basis": basis,
            "reason": reason,
            "chapters": len(chapters),
        }
    )
    for ch in chapters:
        raw_path, _ = ctx.raw.put(
            f"{row['id']}-ch{ch['n']}", media.slice_text(text, ch["start"], ch["end"])
        )
        d.state.context.setdefault("media_chapters", []).append(
            {"source": row["id"], **ch, "raw_path": raw_path, "claim_ids": []}
        )


def pasted_url(prompt):
    return f"text:{ledger.claim_hash(prompt)[:8]}"


def ingest(ctx, d):
    _snapshot(ctx, d)
    common.guard_pools(ctx)
    wanted = common.find_inputs(d.state.prompt)
    pasted = d.state.mode == "verify" and not wanted
    if pasted:
        wanted = [pasted_url(d.state.prompt)]
    failed = []
    ids = []
    for source in wanted:
        key = normalize_url(source)
        row = next(
            (
                s
                for s in ctx.ledger.sources
                if normalize_url(s["url"]) == key
                and s["status"] == "read"
                and ctx.raw.get(s.get("raw_path")) is not None
            ),
            None,
        )
        if row is None:
            res = (
                FetchResult(True, d.state.prompt, "prompt")
                if pasted
                else ctx.fetcher.read(source, ctx)
            )
            local = pasted or is_local(source)
            row = common.store_source(
                ctx,
                source,
                res,
                kind=_kind(d, source),
                publisher="user-supplied" if local else common.host_of(source),
            )
            if row["status"] == "failed":
                failed.append({"source": source, "reason": res.error})
            elif not pasted and (
                info := {
                    k: v
                    for k, v in (
                        ("duration", res.duration),
                        ("chapters", res.chapters),
                        ("description", res.description),
                    )
                    if v
                }
            ):
                row["media"] = info
        if row["status"] == "read":
            ids.append(row["id"])
            _split_media(ctx, d, row)
    ctx.ledger.save()
    d.state.context["inputs"] = ids
    if (d.state.mode == "verify" or wanted) and not ids:
        raise RuntimeError(
            f"{d.state.mode} mode: no input could be read: "
            + "; ".join(f"{f['source']} ({f['reason']})" for f in failed)
        )
    return PhaseResult(data={"inputs": len(wanted), "read": len(ids), "failed": failed})


def extract(ctx, d):
    common.guard_pools(ctx)
    totals = {k: 0 for k in SKIP_KEYS}
    for sid in d.state.context.get("inputs", []):
        got = common.extract_input(
            ctx,
            d,
            sid,
            origin="extracted-from-input",
            step=f"extract.{sid}",
            evidence=False,
        )
        totals["opinions"] += got.opinions
        totals["predictions"] += got.predictions
        totals["dropped"] += got.dropped
    ctx.ledger.save()
    d.state.context["skipped"] = totals
    if not ctx.ledger.claims:
        raise RuntimeError(
            "verify mode: the extractor found no factual claims in the input"
        )
    return PhaseResult(data={"claims": len(ctx.ledger.claims), **totals})
