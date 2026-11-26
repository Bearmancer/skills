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
ASPECTS_PER_PASS = 8


def discovery_surface_lines(ctx):
    rows = []
    for paradigm in ctx.reg["paradigms"]:
        for s in registry.discovery_surfaces(ctx.reg, paradigm):
            routes = "; ".join(
                f"{kind}: "
                + ", ".join(
                    registry.mcp_tool(s.server, name) if kind == "mcp" else name
                    for name in names
                )
                for kind, names in s.routes.items()
            )
            rows.append(f"- {s.id} ({paradigm}, cost {s.cost}) {routes}")
    return "\n".join(rows)


ATTEMPTS_INSTRUCTION = (
    "report every attempt, any route, in `attempts` (the driver logs them): "
    "{surface: <surface id>, route: <mcp|cli|post|http|local>, url: <url>, status: <ok|error|blocked|empty>, "
    "error_class: <bad_key|out_of_credit|blocked|rate_limit|unknown, only with error or blocked>, "
    "query_variant: <supporting|opposing|primary|other-language>}"
)


def _wave_payload(ctx, d, wave, kind, text):
    label = "aspect" if kind == "wave" else "cluster"
    return (
        f"topic: {d.state.prompt}\nmode: {d.state.mode}\nclaim: wave{wave}\nround: 1\n{label}: {text}\n"
        f"sources dir: {ctx.drop_dir} (save each page's text there as <name>.txt; the driver files it as sN.txt)\nsource kinds: {', '.join(common.source_kinds(ctx.reg))}\n"
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
    max_new,
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
                {"sources": str(ctx.drop_dir)},
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
            if claims >= max_new:
                break
            got = common.extract_claims(
                ctx,
                row,
                origin="misconception" if kind == "mis" else "discovered",
                step=f"{step}.{row['id']}",
                evidence=kind != "mis",
                max_new=max_new - claims,
            )
            claims += got.new
        return {"claims": claims, "rejected_attempts": rejected}
    except driver.PoolExhausted as exc:
        exhausted.append(exc)
        raise


def _aspects(ctx, d, wave):
    n = ASPECTS_PER_PASS
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
        d, "discover", {"pass": 0, "mis_done": [], "inputs_done": False}
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
    while len(ctx.ledger.claims) < ctx.cfg.max_claims:
        wave = st["pass"] + 1
        plan = st.setdefault("plans", {}).get(str(wave))
        if plan is None:
            aspects = _aspects(ctx, d, wave)
            last_new = set(st.get("last_new", []))
            fresh = [
                c
                for c in ctx.ledger.clusters()
                if ledger.normalize_text(c) in last_new
                and ledger.normalize_text(c) not in st["mis_done"]
            ][: ctx.cfg.max_mis_tasks]
            mis = [d.state.prompt] if wave == 1 else fresh
            plan = {f"a{i}": ["wave", a] for i, a in enumerate(aspects, 1)}
            plan.update({f"m{i}": ["mis", m] for i, m in enumerate(mis, 1)})
            st["plans"][str(wave)] = plan
        tasks = {name: tuple(task) for name, task in plan.items()}
        aspect_names = [name for name in tasks if tasks[name][0] == "wave"]
        # Every aspect gets an equal share of the cap, so no part of the prompt
        # crowds the others out (ADR 0037).
        share = st.setdefault("shares", {}).get(str(wave))
        if share is None:
            share = max(1, -(-ctx.cfg.max_claims // max(len(aspect_names), 1)))
            st["shares"][str(wave)] = share
        tasks = {
            name: (*task, share) if len(task) == 2 else task
            for name, task in tasks.items()
        }
        if not tasks and wave > 1:
            break
        before_clusters = _cluster_keys(ctx)
        before_claims = len(ctx.ledger.claims)
        exhausted = []
        results, _size = driver.run_wave(
            {name: name for name in tasks},
            lambda name, w=wave: _task(ctx, d, w, name, *tasks[name], exhausted),
            timeout=ctx.cfg.wave_timeout,
        )
        common.raise_exhausted(exhausted)
        st["claims"] = len(ctx.ledger.claims)
        if asks := driver.waiting(results):
            ctx.ledger.save()
            raise asks
        for name in tasks:
            if tasks[name][0] == "mis" and results[name].ok:
                st["mis_done"].append(ledger.normalize_text(tasks[name][1]))
        ctx.ledger.save()
        new = _cluster_keys(ctx) - before_clusters
        st["last_new"] = sorted(new)
        st["pass"] = wave
        d.save()
        if aspect_names and all(
            results[name].ok
            and (results[name].value or {}).get("claims", 0) >= share
            for name in aspect_names
        ):
            break  # every aspect reached its share
        if len(ctx.ledger.claims) <= before_claims:
            break  # a pass that adds no new claim ends discovery
    if not ctx.ledger.claims:
        raise RuntimeError("discovery produced no claims")
    return PhaseResult(
        data={
            "passes": st["pass"],
            "clusters": len(ctx.ledger.clusters()),
            "claims": len(ctx.ledger.claims),
            "claim_budget_hit": len(ctx.ledger.claims) >= ctx.cfg.max_claims,
        }
    )
