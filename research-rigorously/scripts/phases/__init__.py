from .. import driver, infer_mode, ledger
from ..driver import PhaseResult
from . import discover, ingest, ship, verify, write


def _infer(ctx, d):
    declared = d.state.context.get("mode_override")
    if declared:
        return PhaseResult(data={"reason": "declared with --mode"}, mode=declared)
    mode, reason = infer_mode.infer_mode(d.state.prompt)
    return PhaseResult(data={"reason": reason}, mode=mode)


PHASE_FUNCTIONS = {
    "infer_mode": _infer,
    "ingest": ingest.ingest,
    "extract": ingest.extract,
    "discover": discover.discover,
    "verify": verify.verify,
    "write": write.write,
    "conformance": write.conformance,
    "layout": write.layout,
    "render": ship.render_pages,
    "gates": ship.gates,
    "publish": ship.publish,
    "live_check": ship.live_check,
}


def _settle_ask_budget(ctx, d):
    """At the ask ceiling: stop asking and settle the still-open claims for the gates.

    A claim that meets the ledger's own true rule keeps what it earned; every
    other open claim becomes `unchecked`, which asserts nothing about the
    evidence (ADR 0037).
    """
    sources = ctx.ledger.sources_by_id()
    attempts = ctx.ledger.attempts()
    settled_true = settled_unchecked = 0
    for c in ctx.ledger.claims:
        ledger.sync_rounds(c, attempts)
        if c["status"] != "open":
            continue
        if ledger.true_violations(c, sources):
            c["status"] = "unchecked"
            settled_unchecked += 1
        else:
            c["status"] = "true"
            settled_true += 1
    ctx.ledger.save()
    d.state.context["ask_budget_exhausted"] = True
    d.save()
    return PhaseResult(
        data={
            "ask_budget": "exhausted",
            "settled_true": settled_true,
            "settled_unchecked": settled_unchecked,
        }
    )


def make_handlers(ctx):
    def handler_for(name, fn):
        def handle(d):
            # Only the gathering phases are capped; entering one restores the
            # ceiling (it counts gathering asks only), and every other phase clears it.
            if ctx.runner is not None:
                ctx.runner.max_asks = (
                    ctx.cfg.max_asks if name in driver.CEILING_PHASES else None
                )
            try:
                return fn(ctx, d)
            except driver.AskBudgetExhausted:
                return _settle_ask_budget(ctx, d)

        return handle

    return {name: handler_for(name, fn) for name, fn in PHASE_FUNCTIONS.items()}
