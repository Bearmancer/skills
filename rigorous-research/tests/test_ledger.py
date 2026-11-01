from scripts import ledger
from scripts.phases import verify

from .conftest import add_claim_with


def test_publish_check_rejects_a_true_claim_without_evidence(ledger_ctx):
    claim, _ = ledger_ctx.ledger.add_claim(
        "Water boils at 100 C at sea level", origin="discovered"
    )
    claim["status"] = "true"
    claim["rounds"] = 2
    found = ledger.check(
        ledger_ctx.ledger.claims_doc,
        ledger_ctx.ledger.sources_doc,
        [],
        publish=True,
        round_order=ledger_ctx.reg["round_order"],
    )
    assert any(v.severity == "error" for v in found)


def test_publish_check_rejects_an_open_claim(ledger_ctx):
    ledger_ctx.ledger.add_claim("Still working on this", origin="discovered")
    found = ledger.check(
        ledger_ctx.ledger.claims_doc,
        ledger_ctx.ledger.sources_doc,
        [],
        publish=True,
        round_order=ledger_ctx.reg["round_order"],
    )
    assert any(v.severity == "error" for v in found)


def test_settle_rules(ledger_ctx):
    ledger_ctx.runner.run = lambda *a, **k: "positions: []"
    last = ledger_ctx.reg["max_rounds"]
    one = add_claim_with(
        ledger_ctx, "Primary-backed claim", [("T1", "gov", "supports")]
    )
    assert verify.settle(ledger_ctx, one["id"], 1) is None
    assert verify.settle(ledger_ctx, one["id"], 2) == "true"
    weaker = add_claim_with(
        ledger_ctx,
        "Contested claim",
        [("T1", "gov", "supports"), ("T2", "uni", "contradicts")],
        rounds=2,
    )
    assert verify.settle(ledger_ctx, weaker["id"], 2) is None
    assert verify.settle(ledger_ctx, weaker["id"], last) == "interpretive"
    both = add_claim_with(
        ledger_ctx,
        "Disputed claim",
        [("T1", "gov", "supports"), ("T1", "agency", "contradicts")],
        rounds=2,
    )
    assert verify.settle(ledger_ctx, both["id"], 2) == "interpretive"
    none = add_claim_with(ledger_ctx, "Nothing found", [], rounds=5)
    assert verify.settle(ledger_ctx, none["id"], last) == "not-found"
