import shlex
import sys
import threading
from types import SimpleNamespace

import pytest

from scripts import cli, driver
from scripts.phases import _infer, common, ship, verify

from .conftest import ScriptedRunner, add_claim_with


def test_wave_halves_batch_on_rate_limit_then_succeeds():
    calls = {}

    def fn(x):
        calls[x] = calls.get(x, 0) + 1
        if x == "a" and calls[x] == 1:
            raise driver.RateLimited()
        return x.upper()

    results, size = driver.run_wave({k: k for k in "abcd"}, fn, size=4)
    assert size == 2
    assert all(r.ok for r in results.values())
    assert results["a"].value == "A"


def test_wave_retries_an_error_once_then_reports_failure():
    def boom(_):
        raise ValueError("nope")

    results, _ = driver.run_wave({"a": 1}, boom, retries=1)
    assert not results["a"].ok and results["a"].attempts == 2


def test_wave_never_reruns_a_task_that_is_still_running():
    release, started = threading.Event(), []

    def slow(_):
        started.append(1)
        release.wait(2)
        return "late"

    results, _ = driver.run_wave({"a": 1}, slow, timeout=0.1, retries=1)
    release.set()
    assert not results["a"].ok and "still running" in results["a"].error
    assert len(started) == 1


def _gate_runner(first_disagrees, stays_wrong):
    def answer(role, step, prompt):
        if step.startswith("gate.b"):
            v = "disagree" if first_disagrees else "agree"
            return f"verdicts:\n  - {{claim: c1, verdict: {v}, note: stray}}\n  - {{claim: c2, verdict: agree}}"
        v = "disagree" if stays_wrong else "agree"
        return f"verdicts:\n  - {{claim: c1, verdict: {v}, note: still}}"

    return ScriptedRunner(answer)


def _two_claims(ledger_ctx):
    add_claim_with(ledger_ctx, "Claim one", [("T1", "gov", "supports")])
    add_claim_with(ledger_ctx, "Claim two", [("T1", "edu", "supports")])
    for c in ledger_ctx.ledger.claims:
        c["status"] = "true"
    return ledger_ctx


def test_verifier_gate_clears_a_stray_disagree_but_blocks_a_confirmed_one(ledger_ctx):
    ctx = _two_claims(ledger_ctx)
    ctx.runner = _gate_runner(True, False)
    problems, counts = ship.verifier_problems(ctx)
    assert problems == [] and counts["rechecked"] == 1
    assert "gate.c1.recheck" in ctx.runner.steps
    ctx.runner = _gate_runner(True, True)
    problems, _ = ship.verifier_problems(ctx)
    assert len(problems) == 1 and "c1" in problems[0]


def _surface(reg, paradigm=None, not_paradigm=None):
    from scripts import registry

    for p in reg["paradigms"]:
        if paradigm and p != paradigm:
            continue
        if not_paradigm and p == not_paradigm:
            continue
        for s in registry.discovery_surfaces(reg, p):
            route = next(iter(s.routes))
            return p, {
                "surface": s.id,
                "route": route,
                "url": "https://x.test/",
                "status": "ok",
            }
    raise AssertionError("no surface")


def test_attempt_log_rejects_other_rounds_and_repeated_paradigms(ledger_ctx, reg):
    ok_p, ok = _surface(reg)
    _, other = _surface(reg, not_paradigm=ok_p)
    assert ledger_ctx.ledger.attempts() == []
    problems = common.log_reply_attempts(
        ledger_ctx, {"attempts": [ok, other]}, "c1", 1, allowed={ok_p}
    )
    logged = ledger_ctx.ledger.attempts()
    assert [a["paradigm"] for a in logged] == [ok_p]
    assert len(problems) == 1 and "outside this round" in problems[0]
    problems = common.log_reply_attempts(
        ledger_ctx, {"attempts": [ok]}, "c1", 2, allowed={ok_p}, earlier={ok_p}
    )
    assert ledger_ctx.ledger.attempts() == logged and "earlier round" in problems[0]


def test_declared_mode_beats_inference():
    d = SimpleNamespace(
        state=SimpleNamespace(
            prompt="is it true that X", context={"mode_override": "learn"}
        )
    )
    assert _infer(None, d).mode == "learn"


def _notify_path(path):
    # notify splits with shlex.split(posix=False) on Windows, which keeps quotes,
    # so the token must reach CreateProcess bare: no quotes, no spaces (8.3 name).
    path = str(path)
    if sys.platform == "win32":
        import ctypes

        buf = ctypes.create_unicode_buffer(1024)
        ctypes.windll.kernel32.GetShortPathNameW(path, buf, len(buf))
        return buf.value or path
    return shlex.quote(path)


def test_notify_is_silent_when_unset_and_runs_the_command_when_set(tmp_path):
    assert cli.notify("hi", env={}) is False
    out = tmp_path / "out.txt"
    script = tmp_path / "n.py"
    script.write_text(
        f"import sys; from pathlib import Path; Path({str(out)!r}).write_text(sys.argv[1])"
    )
    command = f"{_notify_path(sys.executable)} {_notify_path(script)}"
    assert cli.notify("run failed", env={"DEEP_RESEARCH_NOTIFY": command}) is True
    assert out.read_text() == "run failed"


def test_doctor_names_a_missing_tool_without_working_around_it(tmp_path):
    rows = cli.doctor(
        tmp_path, which=lambda tool: None if tool == "git" else f"/bin/{tool}"
    )
    status = {name: ok for name, ok, _ in rows}
    assert status["git"] is False and status["uv"] is True
    assert "opencode" not in status
    assert status["site git repo"] is False


def test_audit_hardening(tmp_path):
    import argparse
    from scripts import cli, domains, fetch, remove

    assert cli.slug_type("bach-cantatas")
    for bad in ("", "../x", "A b", "/abs"):
        with pytest.raises(argparse.ArgumentTypeError):
            cli.slug_type(bad)
    assert fetch.default_http_get("file:///etc/passwd").error == "UnsupportedScheme"
    assert domains.banned_host("https://open.spotify.com:443/x", "music/classical")
    answers = tmp_path / "answers"
    answers.mkdir()
    for name in ("verify-bach-2026-10-07.html", "verify-bach-cantatas-2026-10-07.html"):
        (answers / name).write_text("x")
    assert [p.name for p in remove.resolve_footprint(tmp_path, "bach")] == [
        "verify-bach-2026-10-07.html"
    ]


def test_claim_hash_keeps_sign_and_decimal():
    from scripts import ledger

    assert ledger.claim_hash("growth was -5%") != ledger.claim_hash("growth was 5%")
    assert ledger.claim_hash("pi is 3.14") != ledger.claim_hash("pi is 314")
    assert ledger.claim_hash("Growth, was 5%!") == ledger.claim_hash("growth was 5%")


def test_domain_regex_ignores_php_composer_and_orchestration():
    from scripts import domains

    assert domains.domain_for("answer", "install PHP Composer packages") == "general"
    assert domains.domain_for("answer", "Kubernetes orchestration") == "general"
    assert (
        domains.domain_for("answer", "which composer wrote this symphony")
        == "music/classical"
    )


def test_attempts_log_tolerates_only_a_torn_last_line(tmp_path):
    from scripts import ledger

    p = tmp_path / "attempts.jsonl"
    p.write_text('{"a": 1}\n{"a": 2}\n{"a": ', encoding="utf-8")
    assert ledger.load_attempts(p) == [{"a": 1}, {"a": 2}]
    p.write_text('{"a": 1}\n{"a": \n{"a": 3}\n', encoding="utf-8")
    with pytest.raises(Exception):
        ledger.load_attempts(p)


def test_verify_round_never_runs_twice_for_one_claim():
    ctx = SimpleNamespace(ledger=object())
    started, release = threading.Event(), threading.Event()

    def slow(c, cid, fatal):
        started.set()
        release.wait(5)

    original = verify._do_round
    verify._do_round = slow
    try:
        t = threading.Thread(target=verify._guarded_round, args=(ctx, "c1", []))
        t.start()
        started.wait(5)
        with pytest.raises(RuntimeError):
            verify._guarded_round(ctx, "c1", [])
    finally:
        release.set()
        t.join()
        verify._do_round = original
