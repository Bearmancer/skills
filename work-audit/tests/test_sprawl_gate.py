"""Tests for scripts/sprawl-gate.py: every verdict in references/sprawl-gate.md.

Every case drives the script as a subprocess with SPRAWL_GATE_* pointed at a
fabricated home and a fabricated user-exception file, never the real ones:
`check` lists violations, `hook` (JSON on stdin) denies a write that would
create plan sprawl, and `explain` prints the verdict with the mechanism that
decided it (base rule, omo runtime need, user exception or out of scope).
"""

import json
import os
import subprocess
from pathlib import Path

import pytest
from conftest import PY_RUNNER, SCRIPT_TIMEOUT

SPRAWL_GATE = Path(__file__).resolve().parent.parent / "scripts" / "sprawl-gate.py"


def gate(home: Path, *args, payload=None, extra_env=None):
    env = dict(os.environ)
    env.update(extra_env or {})
    env.update(
        SPRAWL_GATE_HOME=str(home),
        SPRAWL_GATE_PLAN_HOME=str(home / "plans"),
        SPRAWL_GATE_DEV=str(home / "Dev"),
        SPRAWL_GATE_EXCEPTIONS_FILE=str(home / "exceptions.toml"),
    )
    return subprocess.run(
        [*PY_RUNNER, str(SPRAWL_GATE), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        input=json.dumps(payload) if payload is not None else None,
        timeout=SCRIPT_TIMEOUT,
    )


def hooked_write(home: Path, path: Path):
    return gate(home, "hook", payload={"tool_input": {"file_path": str(path), "content": "x"}})


def deny_reason(result) -> str | None:
    assert result.returncode == 0
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecisionReason"]


def explain(home: Path, path: Path) -> str:
    result = gate(home, "explain", str(path))
    assert result.returncode == 0
    return result.stdout.strip()


def test_empty_plan_home_is_clean(tmp_path):
    (tmp_path / "plans").mkdir()
    clean = gate(tmp_path, "check")
    assert (clean.returncode, clean.stdout.strip()) == (0, "sprawl-gate: clean")


TRACKED = "# loom: plan\n\nTracker: https://github.com/Bearmancer/loom/issues/7\n"

# Stand-in for `gh issue view N -R repo --json number`: issue 7 exists, every other number does not.
FAKE_GH = """import json, sys
n = sys.argv[3]
if n == "7":
    print(json.dumps({"number": 7}))
else:
    sys.exit(1)
"""


def drain(home: Path):
    fake = home / "fake_gh.py"
    fake.write_text(FAKE_GH, encoding="utf-8")
    return gate(home, "drain", extra_env={"SPRAWL_GATE_GH": str(fake)})


@pytest.mark.parametrize("rel", ["loom.md", "notes.txt", "drafts/note.md", ".omo/waves/boulder.json"])
def test_check_fails_on_a_plan_home_file_that_is_not_live(tmp_path, rel):
    # `.omo` included: the executor-state allowance is gone since #174.
    f = tmp_path / "plans" / rel
    f.parent.mkdir(parents=True)
    f.write_text("# loom: plan\n", encoding="utf-8")
    dirty = gate(tmp_path, "check")
    assert (dirty.returncode, dirty.stdout.strip()) == (
        1,
        f"[plan-not-live] file this plan as a tracker issue, add a 'Tracker: <issue url>' line, then run drain: {f}",
    )


def test_check_fails_on_a_live_plan_copy_until_drained(tmp_path):
    f = tmp_path / "plans" / "loom.md"
    f.parent.mkdir()
    f.write_text(TRACKED, encoding="utf-8")
    dirty = gate(tmp_path, "check")
    assert (dirty.returncode, dirty.stdout.strip()) == (
        1,
        f"[plan-live-undrained] Bearmancer/loom#7 is the record; run drain to delete this copy: {f}",
    )


def test_empty_folders_in_the_plan_home_are_clean(tmp_path):
    (tmp_path / "plans" / "drafts").mkdir(parents=True)
    clean = gate(tmp_path, "check")
    assert (clean.returncode, clean.stdout.strip()) == (0, "sprawl-gate: clean")


@pytest.mark.parametrize("rel", ["loom.md", "drafts/note.md", ".omo/waves/boulder.json"])
def test_hook_allows_writes_into_the_plan_home(tmp_path, rel):
    # Plan mode saves its file here; check and drain keep the tracker the one source of truth.
    target = tmp_path / "plans" / rel
    assert deny_reason(hooked_write(tmp_path, target)) is None
    assert explain(tmp_path, target).startswith("allow  [base rule plan-home-live]")


def test_drain_deletes_only_plans_whose_issue_exists(tmp_path):
    plans = tmp_path / "plans"
    plans.mkdir()
    live = plans / "live.md"
    live.write_text(TRACKED, encoding="utf-8")
    untracked = plans / "draft.md"
    untracked.write_text("# draft\n", encoding="utf-8")
    missing = plans / "gone.md"
    missing.write_text("Tracker: https://github.com/Bearmancer/loom/issues/9\n", encoding="utf-8")

    result = drain(tmp_path)
    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        f"kept, not live (no Tracker line): {untracked}",
        f"kept, Bearmancer/loom#9 not found: {missing}",
        f"deleted, live as Bearmancer/loom#7: {live}",
    ]
    assert not live.exists() and untracked.exists() and missing.exists()


def test_drain_of_only_live_plans_exits_clean(tmp_path):
    plans = tmp_path / "plans"
    plans.mkdir()
    (plans / "live.md").write_text(TRACKED, encoding="utf-8")
    assert drain(tmp_path).returncode == 0
    clean = gate(tmp_path, "check")
    assert (clean.returncode, clean.stdout.strip()) == (0, "sprawl-gate: clean")


def test_omo_home_plans_dir_is_denied_as_a_stray_plan_dir(tmp_path):
    # Owner ruling on #247: plans are tracker issues, so omo home's plans dir gets no exemption.
    target = tmp_path / ".omo" / "plans" / "omo-plan.md"
    reason = deny_reason(hooked_write(tmp_path, target))
    assert reason.startswith("sprawl-gate [base rule stray-plan-dir]: a plan is a tracker issue body")
    assert explain(tmp_path, target).startswith("deny   [base rule stray-plan-dir]")


def test_omo_home_outside_plans_is_out_of_scope(tmp_path):
    for sub in ("drafts", "evidence", "ulw-loop"):
        target = tmp_path / ".omo" / sub / "note.md"
        assert deny_reason(hooked_write(tmp_path, target)) is None
        assert explain(tmp_path, target).startswith("allow  [out of scope]")


@pytest.mark.parametrize("stray", [".omo/plans", ".mo/plans", ".claude/plans", ".omc/plans"])
def test_repo_plan_dirs_are_denied_by_hook_and_reported_by_check(tmp_path, stray):
    target = tmp_path / "Dev" / "repo" / stray / "x.md"
    assert "[base rule stray-plan-dir]" in deny_reason(hooked_write(tmp_path, target))

    target.parent.mkdir(parents=True)
    target.write_text("# x\n", encoding="utf-8")
    dirty = gate(tmp_path, "check")
    assert (dirty.returncode, dirty.stdout.strip()) == (1, f"[stray-plan-dir] stray plan file: {target}")


def test_user_exception_with_reason_and_date_allows_and_check_skips_it(tmp_path):
    (tmp_path / "exceptions.toml").write_text(
        '[[exception]]\npath = "~/Dev/repo/.omc/plans"\nreason = "owner keeps omc drafts here"\ngranted = "2026-10-25"\n',
        encoding="utf-8",
    )
    target = tmp_path / "Dev" / "repo" / ".omc" / "plans" / "x.md"
    assert deny_reason(hooked_write(tmp_path, target)) is None
    line = explain(tmp_path, target)
    assert line.startswith("allow  [user exception]")
    assert "owner keeps omc drafts here (granted 2026-10-25)" in line

    target.parent.mkdir(parents=True)
    target.write_text("# x\n", encoding="utf-8")
    clean = gate(tmp_path, "check")
    assert (clean.returncode, clean.stdout.strip()) == (0, "sprawl-gate: clean")


def test_user_exception_without_reason_or_date_is_reported_and_not_applied(tmp_path):
    exceptions = tmp_path / "exceptions.toml"
    exceptions.write_text('[[exception]]\npath = "~/Dev/repo/.omc/plans"\n', encoding="utf-8")
    target = tmp_path / "Dev" / "repo" / ".omc" / "plans" / "x.md"
    assert "[base rule stray-plan-dir]" in deny_reason(hooked_write(tmp_path, target))

    dirty = gate(tmp_path, "check")
    assert (dirty.returncode, dirty.stdout.strip()) == (1, f"user exception #1 in {exceptions} lacks reason, granted; not applied")


def test_unreadable_user_exception_file_applies_nothing_and_check_says_so(tmp_path):
    (tmp_path / "exceptions.toml").write_text("[[exception]\n", encoding="utf-8")
    target = tmp_path / "Dev" / "repo" / ".omc" / "plans" / "x.md"
    assert "[base rule stray-plan-dir]" in deny_reason(hooked_write(tmp_path, target))

    dirty = gate(tmp_path, "check")
    assert dirty.returncode == 1
    assert dirty.stdout.startswith("user exception file unreadable, no exception applied:")


def test_missing_plan_home_dev_and_exception_file_are_clean(tmp_path):
    clean = gate(tmp_path, "check")
    assert (clean.returncode, clean.stdout.strip()) == (0, "sprawl-gate: clean")
