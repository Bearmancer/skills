"""Characterization of scripts/stop-guard.py: block/allow decisions, fingerprint, hook main."""

import json
import os
from pathlib import Path

import pytest

from conftest import RECORD, STOP_GUARD, commit_all, fresh_script_module, run_stop_guard


@pytest.fixture()
def sg():
    return fresh_script_module(STOP_GUARD)


@pytest.fixture()
def rc():
    return fresh_script_module(RECORD)


def tu(name, **inp):
    return json.dumps(
        {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]},
        }
    )


def msg(role, text):
    return json.dumps(
        {"type": role, "message": {"content": [{"type": "text", "text": text}]}}
    )


def edit_lines(path="a"):
    return [msg("user", "fix"), tu("Edit", file_path=path)]


# completed / helpers ----------------------------------------------------------


def test_completed_needs_result_prefix(sg):
    assert sg.completed("Result: done")
    assert sg.completed("  result: ok\nmore")
    assert not sg.completed("Done, finished")
    assert not sg.completed("")
    assert not sg.completed(None)


def test_ran_report_matches_bash_state_report_command(sg):
    uses = [{"name": "Bash", "input": {"command": "uv run x/state-report.py --json"}}]
    assert sg.ran_report(uses)
    assert not sg.ran_report([{"name": "Bash", "input": {"command": "uv run pytest"}}])
    assert not sg.ran_report([{"name": "Read", "input": {"file_path": "x"}}])


def test_asked_detects_question_tool(sg):
    assert sg.asked([{"name": "AskUserQuestion", "input": {"q": "x"}}])
    assert not sg.asked([{"name": "Edit", "input": {}}])


def test_last_turn_resets_at_plain_user_text(sg):
    lines = [
        tu("Edit", file_path="old"),
        msg("user", "new task"),
        tu("Read", file_path="new"),
    ]
    assert sg.last_turn_tool_uses(lines) == [
        {"type": "tool_use", "name": "Read", "input": {"file_path": "new"}}
    ]


def test_last_turn_ignores_tool_result_user_entries(sg):
    tool_result = json.dumps(
        {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": "out"}]},
        }
    )
    lines = [tu("Edit", file_path="a"), tool_result, tu("Read", file_path="b")]
    names = [u["name"] for u in sg.last_turn_tool_uses(lines)]
    assert names == ["Edit", "Read"]


def test_last_turn_drops_non_tool_use_items(sg):
    lines = [
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "hi"}]},
            }
        )
    ]
    assert sg.last_turn_tool_uses(lines) == []


# decide matrix ------------------------------------------------------------------


def test_no_tools_state_changed_passes(sg):
    lines = [msg("user", "why?"), msg("assistant", "Because X.")]
    assert sg.decide(lines, "b", "a", ()) == (None, None)


def test_tools_changed_no_audit_blocks(sg):
    reason, stamp = sg.decide(edit_lines(), "b", "a", ())
    assert stamp is None
    assert reason.startswith("State changed since the last audit")


def test_tools_unchanged_passes(sg):
    lines = [msg("user", "look"), tu("Read", file_path="a")]
    assert sg.decide(lines, "a", "a", ()) == (None, None)


def test_ran_state_report_passes_and_stamps(sg):
    lines = [msg("user", "fix"), tu("Bash", command="uv run x/state-report.py")]
    assert sg.decide(lines, "b", "a", ()) == (None, "b")


def test_missing_pair_blocks_even_after_report(sg):
    lines = [msg("user", "x"), tu("Bash", command="state-report.py")]
    reason, stamp = sg.decide(lines, "b", "a", [("21", "r2", "invalid", "")])
    assert stamp is None
    assert reason.startswith("Required review records missing or invalid: 21@r2")


def test_invalid_pair_lists_index_and_repo(sg):
    reason, _ = sg.decide(edit_lines(), "a", "a", [("19", "r1", "missing", "")])
    assert "19@r1" in reason


def test_failing_without_question_blocks(sg):
    reason, _ = sg.decide(edit_lines(), "a", "a", [("20", "r1", "fail", "")])
    assert reason.startswith("Review records not passing: 20@r1 fail")


def test_failing_with_question_passes(sg):
    lines = edit_lines() + [tu("AskUserQuestion", q="x")]
    assert sg.decide(lines, "a", "a", [("20", "r1", "unverifiable", "")]) == (
        None,
        None,
    )


def test_all_pairs_ok_passes(sg):
    assert sg.decide(edit_lines(), "a", "a", [("19", "r1", "ok", "")]) == (None, None)


# fingerprint / scope --------------------------------------------------------------


def test_fingerprint_scope_and_stability(sg, rc, make_repo):
    a = make_repo(name="sg-a", files={"f.txt": "0\n"})
    b = make_repo(name="sg-b", files={"g.txt": "0\n"})
    commit_all(a)
    commit_all(b)
    edit = tu("Edit", file_path=str(b / "f.txt"))
    rc.SCOPE[:] = rc.scope(a, [edit])
    try:
        assert len(rc.SCOPE) == 2  # cwd repo + transcript repo
        cache = {}
        fp1 = sg.fingerprint(rc, cache)
        assert sg.fingerprint(rc, cache) == fp1
        (b / "f.txt").write_text("x")
        assert sg.fingerprint(rc, cache) != fp1
        rc.SCOPE[:] = rc.scope(a, [])
        assert rc.SCOPE == [a]
        fp2 = sg.fingerprint(rc, cache)
        (b / "f.txt").write_text("y")
        assert sg.fingerprint(rc, cache) == fp2  # untouched repo ignored
    finally:
        rc.SCOPE[:] = []


# hook main --------------------------------------------------------------------------


def hook_input(repo, transcript, message="Result: done", extra=None):
    payload = {
        "cwd": str(repo),
        "transcript_path": str(transcript),
        "last_assistant_message": message,
    }
    payload.update(extra or {})
    return json.dumps(payload)


def test_empty_stdin_boots_under_uv():
    # The one real-uv launch proving the stop-guard entry point boots under uv.
    r = run_stop_guard(stdin_text="", uv=True)
    assert r.returncode == 0
    assert r.stdout.strip() == ""
    assert "stop-guard note" in r.stderr


def test_main_blocks_on_changed_state_and_writes_stamp(make_repo, tmp_path):
    repo = make_repo(files={"f.txt": "0\n"})
    commit_all(repo)
    t = tmp_path / "t.jsonl"
    t.write_text(
        msg("user", "fix") + "\n" + tu("Edit", file_path=str(repo / "f.txt")) + "\n"
    )
    r = run_stop_guard(stdin_text=hook_input(repo, t), cwd=repo)
    assert r.returncode == 0
    decision = json.loads(r.stdout)
    assert decision["decision"] == "block"
    assert decision["reason"].startswith("State changed since the last audit")
    stamp = json.loads(
        (
            Path(os.environ["WORK_AUDIT_STATE_DIR"])
            / ".work-audit-state"
            / "audited.json"
        ).read_text()
    )
    assert "fingerprint" in stamp and "repos" in stamp


def test_main_passes_after_state_report_in_last_turn(make_repo, tmp_path):
    repo = make_repo(files={"f.txt": "0\n"})
    commit_all(repo)
    t = tmp_path / "t.jsonl"
    t.write_text(
        msg("user", "fix")
        + "\n"
        + tu("Bash", command="uv run scripts/state-report.py --json")
        + "\n"
    )
    before = (repo / "f.txt").read_text()
    r = run_stop_guard(stdin_text=hook_input(repo, t), cwd=repo)
    assert r.stdout.strip() == ""  # allow: no block output
    stamp = json.loads(
        (
            Path(os.environ["WORK_AUDIT_STATE_DIR"])
            / ".work-audit-state"
            / "audited.json"
        ).read_text()
    )
    assert stamp["fingerprint"]
    assert before == "0\n"


def crashed_hook_result(repo, transcript, tmp_path, message="Result: done"):
    """Same hook input but with WORK_AUDIT_STATE_DIR pointing at a file: the run
    must reach the stamp stage and fail visibly (stderr note) yet silently."""
    statefile = tmp_path / "statefile"
    statefile.write_text("x")
    payload = hook_input(repo, transcript, message=message)
    r = run_stop_guard(
        stdin_text=payload, cwd=repo, extra_env={"WORK_AUDIT_STATE_DIR": str(statefile)}
    )
    assert r.returncode == 0
    assert r.stdout.strip() == ""
    assert "stop-guard note" in r.stderr
    return r


def test_main_crash_is_visible_and_silent(
    make_repo, tmp_path
):  # test-audit: accept asserts live in crashed_hook_result
    repo = make_repo(files={"f.txt": "0\n"})
    commit_all(repo)
    t = tmp_path / "t.jsonl"
    t.write_text(
        msg("user", "fix") + "\n" + tu("Edit", file_path=str(repo / "f.txt")) + "\n"
    )
    crashed_hook_result(repo, t, tmp_path)


def test_main_silent_without_completion(make_repo, tmp_path):
    repo = make_repo(files={"f.txt": "0\n"})
    commit_all(repo)
    t = tmp_path / "t.jsonl"
    t.write_text(tu("Edit", file_path=str(repo / "f.txt")) + "\n")
    r = run_stop_guard(
        stdin_text=hook_input(repo, t, message="still working"), cwd=repo
    )
    assert r.stdout.strip() == ""
    t2 = tmp_path / "t2.jsonl"
    t2.write_text(
        msg("user", "fix") + "\n" + tu("Edit", file_path=str(repo / "f.txt")) + "\n"
    )
    crashed_hook_result(repo, t2, tmp_path)


def test_main_silent_when_stop_hook_active(make_repo, tmp_path):
    repo = make_repo(files={"f.txt": "0\n"})
    commit_all(repo)
    t = tmp_path / "t.jsonl"
    t.write_text(tu("Edit", file_path=str(repo / "f.txt")) + "\n")
    payload = hook_input(repo, t, extra={"stop_hook_active": True})
    r = run_stop_guard(stdin_text=payload, cwd=repo)
    assert r.stdout.strip() == ""
    crashed_hook_result(repo, t, tmp_path)


def test_main_silent_with_missing_transcript(make_repo, tmp_path):
    repo = make_repo(files={"f.txt": "0\n"})
    commit_all(repo)
    payload = hook_input(repo, tmp_path / "nope.jsonl")
    r = run_stop_guard(stdin_text=payload, cwd=repo)
    assert r.stdout.strip() == ""
    t2 = tmp_path / "t2.jsonl"
    t2.write_text(
        msg("user", "fix") + "\n" + tu("Edit", file_path=str(repo / "f.txt")) + "\n"
    )
    crashed_hook_result(repo, t2, tmp_path)


def test_main_does_not_consult_record_pairs(make_repo, tmp_path):
    # Pinned current behavior: main() calls decide() without pairs, so a dirty
    # repo with state-report.py in the last turn passes even though no review
    # records exist (possible bug; reported, not fixed).
    repo = make_repo(files={"f.txt": "0\n"})
    commit_all(repo)
    (repo / "f.txt").write_text("dirty\n")
    t = tmp_path / "t.jsonl"
    t.write_text(msg("user", "x") + "\n" + tu("Bash", command="state-report.py") + "\n")
    r = run_stop_guard(stdin_text=hook_input(repo, t), cwd=repo)
    assert r.stdout.strip() == ""
    crashed_hook_result(repo, t, tmp_path)


def test_selftest_passes():
    r = run_stop_guard("--selftest")
    assert r.returncode == 0
    assert "FAIL" not in r.stdout
