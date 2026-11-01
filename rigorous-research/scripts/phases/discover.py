import json
import re

from .. import agents, domains, driver, ledger, registry
from ..driver import PhaseResult
from . import common

RULES_AUTHORITY = (
    "Authority order for rules: publisher rulebook, then publisher rules or product page, then publisher or designer FAQ, "
    "then official errata (supersedes the printed rulebook; note its date), then designer or publisher forum posts. "
    "Player-to-player forum posts have kind `forum`. Public pages and the public XML API only; never log in."
)
RULES_STRATEGY = "easiest strategy to win (every claim in it is a matter of interpretation; attribute each to its holders)"
RULES_BASICS = "the essential rules a new player needs, nothing about setup or endgame scoring unless the strategy needs it"


def log_wave(d, entry):
    with (d.run_dir / "waves.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=True, sort_keys=True) + "\n")


def discovery_surface_lines(ctx):
    rows = []
    for paradigm in ctx.reg["paradigms"]:
        for s in registry.discovery_surfaces(ctx.reg, paradigm):
            routes = "; ".join(
                f"{kind}: {', '.join(names)}" for kind, names in s.routes.items()
            )
            rows.append(f"- {s.id} ({paradigm}, cost {s.cost}) {routes}")
    return "\n".join(rows)


ATTEMPTS_INSTRUCTION = (
    "report every attempt, any route, in `attempts` (the driver logs them): "
    "{surface: <surface id>, route: <mcp|cli|post|http>, url: <url>, status: <ok|error|blocked|empty>, "
    "error_class: <bad_key|out_of_credit|blocked|rate_limit|unknown, only with error or blocked>, "
    "query_variant: <supporting|opposing|primary|other-language>}"
)


def _wave_payload(ctx, d, wave, kind, text):
    label = "aspect" if kind == "wave" else "cluster"
    return (
        f"topic: {d.state.prompt}\nmode: {d.state.mode}\nclaim: wave{wave}\nround: 1\n{label}: {text}\n"
        f"inbox: {ctx.inbox}\nsource kinds: {', '.join(common.source_kinds(ctx.reg))}\n"
        f"{RULES_AUTHORITY if d.state.mode == 'rules' else ''}\n"
        f"{domains.prompt_block(ctx.step_data['domain'])}\n"
        f"surfaces (use several paradigms):\n{discovery_surface_lines(ctx)}\n"
        f"{ATTEMPTS_INSTRUCTION}\n"
    )


def _task(
    ctx,
    d,
    wave,
    name,
    kind,
    text,
    exhausted,
):
    step = f"discover.w{wave}.{name}"
    key = "discover-wave" if kind == "wave" else "discover-misconception"
    try:
        surfaces = [
            s
            for p in ctx.reg["paradigms"]
            for s in registry.discovery_surfaces(ctx.reg, p)
        ]
        gens = common.pool_generations(ctx, surfaces)
        reply = {}
        rejected = []
        for attempt in range(2):
            reply = agents.call(
                ctx.runner,
                "discovery",
                key,
                _wave_payload(ctx, d, wave, kind, text),
                step if attempt == 0 else f"{step}.rotated",
                {"inbox": str(ctx.inbox)},
                required=("sources",),
            )
            rejected += common.log_reply_attempts(ctx, reply, f"wave{wave}", 1)
            decisions = common.handle_errors(ctx, reply, gens)
            if "rate_limited" in decisions:
                raise driver.RateLimited()
            if "retry" not in decisions or attempt:
                break
        claims = 0
        for row, _text in common.take_sources(ctx, reply):
            got = common.extract_claims(
                ctx,
                row,
                origin="misconception" if kind == "mis" else "discovered",
                step=f"{step}.{row['id']}",
                evidence=kind != "mis",
            )
            claims += len(got.claims)
        return {"claims": claims, "rejected_attempts": rejected}
    except driver.PoolExhausted as exc:
        exhausted.append(exc)
        raise


def _aspects(ctx, d, wave):
    n = ctx.cfg.wave_size
    extra = (
        f"{RULES_AUTHORITY}\nCover: {RULES_BASICS}; and {RULES_STRATEGY}.\n"
        if d.state.mode == "rules" and wave == 1
        else ""
    )
    payload = f"topic: {d.state.prompt}\nmode: {d.state.mode}\nwave: {wave}\nconcept clusters so far: {'; '.join(ctx.ledger.clusters()) or 'none'}\nmax aspects: {n}\n{extra}"
    data = agents.call(
        ctx.runner,
        "author",
        "aspects",
        payload,
        f"aspects.w{wave}",
        required=("aspects",),
    )
    out = [" ".join(str(a).split()) for a in (data["aspects"] or []) if str(a).strip()][
        :n
    ]
    if (
        d.state.mode == "rules"
        and wave == 1
        and not any(re.search(r"strateg", a, re.I) for a in out)
    ):
        out = out[: max(n - 1, 0)] + [RULES_STRATEGY]
    return out


def _cluster_keys(ctx):
    return {ledger.normalize_text(c) for c in ctx.ledger.clusters()}


def discover(ctx, d):
    common.guard_pools(ctx)
    common.bind_domain(ctx, d)
    st = common.state_ctx(
        d, "discover", {"wave": 0, "quiet": 0, "mis_done": [], "inputs_done": False}
    )
    if not st["inputs_done"]:
        for sid in d.state.context.get("inputs", []):
            common.extract_input(
                ctx,
                d,
                sid,
                origin="discovered",
                step=f"discover.in.{sid}",
                evidence=True,
            )
        st["inputs_done"] = True
        ctx.ledger.save()
    size = ctx.cfg.wave_size
    while st["wave"] < ctx.cfg.max_waves and st["quiet"] < ctx.cfg.saturation_waves:
        wave = st["wave"] + 1
        plan = st.setdefault("plans", {}).get(str(wave))
        if plan is None:
            aspects = _aspects(ctx, d, wave)
            fresh = [
                c
                for c in ctx.ledger.clusters()
                if ledger.normalize_text(c) not in st["mis_done"]
            ]
            mis = [d.state.prompt] if wave == 1 else fresh
            plan = {f"a{i}": ["wave", a] for i, a in enumerate(aspects, 1)}
            plan.update({f"m{i}": ["mis", m] for i, m in enumerate(mis, 1)})
            st["plans"][str(wave)] = plan
        tasks = {name: tuple(task) for name, task in plan.items()}
        if not tasks and wave > 1:
            break
        before_clusters, before_sources = (
            _cluster_keys(ctx),
            {s["id"] for s in ctx.ledger.sources},
        )
        before_claims = len(ctx.ledger.claims)
        exhausted = []
        results, size = driver.run_wave(
            {name: name for name in tasks},
            lambda name, w=wave: _task(ctx, d, w, name, *tasks[name], exhausted),
            size=size,
            timeout=ctx.cfg.wave_timeout,
        )
        common.raise_exhausted(exhausted)
        if asks := driver.waiting(results):
            ctx.ledger.save()
            raise asks
        for name in tasks:
            if tasks[name][0] == "mis" and results[name].ok:
                st["mis_done"].append(ledger.normalize_text(tasks[name][1]))
        ctx.ledger.save()
        new = _cluster_keys(ctx) - before_clusters
        grown = len(ctx.ledger.claims) > before_claims
        failed_tasks = any(not r.ok for r in results.values())
        st["quiet"] = 0 if grown or failed_tasks else st["quiet"] + 1
        st["wave"] = wave
        added = [s for s in ctx.ledger.sources if s["id"] not in before_sources]
        log_wave(
            d,
            {
                "phase": "discover",
                "wave": wave,
                "tasks": len(tasks),
                "task_errors": {k: r.error for k, r in results.items() if not r.ok},
                "rejected_attempts": {
                    k: r.value["rejected_attempts"]
                    for k, r in results.items()
                    if r.ok and r.value["rejected_attempts"]
                },
                "sources_read": [s["url"] for s in added if s["status"] == "read"],
                "sources_failed": [
                    {"url": s["url"], "reason": s.get("fail_reason")}
                    for s in added
                    if s["status"] == "failed"
                ],
                "new_clusters": sorted(new),
                "claims": len(ctx.ledger.claims),
                "batch_size": size,
            },
        )
        d.save()
    if not ctx.ledger.claims:
        raise RuntimeError("discovery produced no claims")
    return PhaseResult(
        data={
            "waves": st["wave"],
            "clusters": len(ctx.ledger.clusters()),
            "claims": len(ctx.ledger.claims),
            "saturated": st["quiet"] >= ctx.cfg.saturation_waves,
        }
    )
