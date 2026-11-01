from types import SimpleNamespace

import pytest

from scripts import registry
from scripts.workspace import Config, Ledger


class ScriptedRunner:
    def __init__(self, answer):
        self.answer = answer
        self.steps = []

    def run(self, role, prompt, step="", context=None):
        self.steps.append(step)
        return self.answer(role, step, prompt)


@pytest.fixture
def reg():
    return registry.load()


@pytest.fixture
def ledger_ctx(tmp_path, reg):
    led = Ledger(tmp_path / "topic")
    return SimpleNamespace(
        ledger=led,
        reg=reg,
        cfg=Config(),
        step_data={},
        runner=ScriptedRunner(lambda *a: "verdicts: []"),
    )


def add_claim_with(ctx, text, evidence, rounds=1):
    claim, _ = ctx.ledger.add_claim(text, origin="discovered")
    for i, (tier, publisher, stance) in enumerate(evidence, 1):
        src = ctx.ledger.add_source(
            f"https://example.org/{publisher}/{i}",
            kind="web",
            tier=tier,
            publisher=publisher,
        )
        ctx.ledger.add_evidence(claim["id"], src["id"], stance, f"p{i}", f"quote {i}")
    claim["rounds"] = rounds
    return claim
