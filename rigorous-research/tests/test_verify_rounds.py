from types import SimpleNamespace

from scripts import registry
from scripts.phases import common, verify

from .conftest import ScriptedRunner, add_claim_with

DISCOVERY = "```yaml\nsources: []\nattempts: []\n```"
NO_EVIDENCE = "```yaml\nevidence: []\nignored_instructions: []\n```"
ROW = {
    "id": "s1",
    "url": "https://x.test/1",
    "kind": "web",
    "status": "read",
    "tier": "T2",
    "publisher": "X",
}


def _wire(ctx, tmp_path, monkeypatch, rows):
    ctx.keys = None
    ctx.inbox = tmp_path / "inbox"
    ctx.raw = SimpleNamespace(contains=lambda text, quote: True)
    ctx.runner = ScriptedRunner(
        lambda role, step, prompt: NO_EVIDENCE if ".evidence." in step else DISCOVERY
    )
    monkeypatch.setattr(common, "take_sources", lambda c, reply: rows)
    monkeypatch.setattr(common, "log_reply_attempts", lambda *a, **k: [])
    monkeypatch.setattr(
        verify,
        "round_attempts",
        lambda c, cid, n: [{"paradigm": registry.round_paradigms(ctx.reg, n)[0]}],
    )


def _rounds(ctx, cid, count):
    for _ in range(count):
        verify._do_round(ctx, cid, [])
    return ctx.ledger.claim(cid)


def test_barren_claim_stops_before_the_cap(ledger_ctx, tmp_path, monkeypatch):
    _wire(ledger_ctx, tmp_path, monkeypatch, [])
    claim, _ = ledger_ctx.ledger.add_claim("Nothing public", origin="discovered")
    after_two = _rounds(ledger_ctx, claim["id"], 2)
    assert after_two["status"] == "open"
    after_three = _rounds(ledger_ctx, claim["id"], 1)
    assert after_three["status"] == "not-found"
    assert after_three["rounds"] == 3
    assert after_three["not_found_reason"] == "no-public-record-after-3-rounds"


def test_claim_with_sources_keeps_going(ledger_ctx, tmp_path, monkeypatch):
    _wire(ledger_ctx, tmp_path, monkeypatch, [(ROW, "page text")])
    claim, _ = ledger_ctx.ledger.add_claim(
        "Sourced but unextracted", origin="discovered"
    )
    claim = _rounds(ledger_ctx, claim["id"], 4)
    assert claim["status"] == "open"
    assert claim["rounds"] == 4


def test_claim_with_evidence_keeps_going(ledger_ctx, tmp_path, monkeypatch):
    _wire(ledger_ctx, tmp_path, monkeypatch, [])
    claim = add_claim_with(
        ledger_ctx, "One weak source", [("T3", "Blog", "supports")], rounds=0
    )
    claim = _rounds(ledger_ctx, claim["id"], 4)
    assert claim["status"] == "open"


def test_round_log_counts_each_source_once(ledger_ctx, tmp_path, monkeypatch):
    _wire(ledger_ctx, tmp_path, monkeypatch, [(ROW, "page text")])
    claim, _ = ledger_ctx.ledger.add_claim("Same page twice", origin="discovered")
    claim = _rounds(ledger_ctx, claim["id"], 2)
    assert [r["round"] for r in claim["round_log"]] == [1, 2]
    assert [r["new_read_sources"] for r in claim["round_log"]] == [1, 0]


def test_template_replies_across_claims_do_not_count_as_genuine(
    ledger_ctx, tmp_path, monkeypatch
):
    _wire(ledger_ctx, tmp_path, monkeypatch, [])
    ids = [
        ledger_ctx.ledger.add_claim(f"Claim {i}", origin="discovered")[0]["id"]
        for i in range(3)
    ]
    for _ in range(3):
        for cid in ids:
            verify._do_round(ledger_ctx, cid, [])
    assert [ledger_ctx.ledger.claim(c)["status"] for c in ids] == ["open"] * 3
