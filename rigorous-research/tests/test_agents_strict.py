import pytest

from scripts import agents
from .conftest import ScriptedRunner


def _call(answer, strict=False, check=None):
    runner = ScriptedRunner(lambda *a: answer)
    return agents.call(
        runner,
        "extractor",
        "evidence",
        "payload",
        "test.step",
        required=("evidence",),
        strict=strict,
        check=check,
    )


def test_strict_rejects_two_blocks():
    result = _call(
        "```yaml\nevidence: []\n```\n```yaml\nevidence: []\n```", strict=True
    )
    assert "_flags" in result


def test_strict_rejects_text_after_fence():
    result = _call("```yaml\nevidence: []\n```\nextra text", strict=True)
    assert "_flags" in result


def test_strict_accepts_clean_block():
    result = _call("```yaml\nevidence: []\nignored_instructions: []\n```", strict=True)
    assert "evidence" in result
    assert "_flags" not in result


def test_non_strict_still_raises():
    with pytest.raises(agents.AgentReplyError):
        _call("not yaml at all", strict=False)


def test_check_hook_called():
    called = []

    def check(data):
        called.append(data)

    _call("```yaml\nevidence: []\n```", check=check)
    assert called


def test_check_rejection_triggers_retry():
    def check(data):
        raise agents.AgentReplyError("bad")

    runner = ScriptedRunner(lambda *a: "```yaml\nevidence: []\n```")
    with pytest.raises(agents.AgentReplyError):
        agents.call(
            runner,
            "extractor",
            "evidence",
            "payload",
            "test.step",
            required=("evidence",),
            check=check,
        )
    assert any(".retry" in s for s in runner.steps)
