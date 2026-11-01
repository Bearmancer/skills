from .. import infer_mode
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


def make_handlers(ctx):
    return {name: (lambda d, fn=fn: fn(ctx, d)) for name, fn in PHASE_FUNCTIONS.items()}
