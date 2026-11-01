"""Characterization of scripts/state-report.py: flags, exit codes, 21 lines, report.json."""

import json
import os
import time
from pathlib import Path

import pytest

from conftest import (
    commit_all,
    load_reports,
    run_state_report,
    seeded_report,
    shared_run,
)

EXPECTED_NAMES = [
    "git status",
    "branches/worktrees/stashes",
    "plan files",
    "stale artifacts",
    "handoffs and wizards",
    "tool state",
    "tests present",
    "tests run",
    "tests deleted",
    "other files deleted",
    "left",
    "skipped",
    "finished",
    "not verified",
    "empty dirs",
    "duplicates",
    "unfinished",
    "small commits to squash",
    "doc mismatches",
    "doc sprawl",
    "repo sprawl vs style",
]


def test_help_lists_all_flags():
    # End to end through a real uv subprocess: proves the PEP 723 script boots under uv.
    r = run_state_report("--help", uv=True)
    assert r.returncode == 0
    for flag in (
        "--roots",
        "--transcript",
        "--since",
        "--brief",
        "--json",
        "--selftest",
    ):
        assert flag in r.stdout


def test_no_repo_in_scope_reports_and_exits_zero(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    r = run_state_report(cwd=plain)
    assert r.returncode == 0
    assert "no git repo in scope" in r.stdout


def test_21_index_lines_numbered_and_named(clean_repo):
    r = shared_run("clean")
    assert r.returncode == 0
    for i, name in enumerate(EXPECTED_NAMES, 1):
        assert f"{i}. {name}:" in r.stdout


def test_header_names_since_window_and_repos(clean_repo):
    r = shared_run("clean")
    assert "state-report" in r.stdout
    assert "since 24 hours ago" in r.stdout
    assert str(clean_repo) in r.stdout or clean_repo.name in r.stdout


def test_brief_omits_detail_lines_but_keeps_21_summaries(clean_repo):
    full = shared_run("clean")
    brief = shared_run("clean", "--brief")
    assert brief.returncode == 0
    brief_lines = brief.stdout.splitlines()
    assert not any(l.startswith("     - ") for l in brief_lines)
    for i, name in enumerate(EXPECTED_NAMES, 1):
        assert any(l.startswith(f"{i}. {name}:") for l in brief_lines)
    # full output carries at least the same summary lines
    for i, name in enumerate(EXPECTED_NAMES, 1):
        assert f"{i}. {name}:" in full.stdout


def test_clean_repo_exits_zero(clean_repo):
    r = shared_run("clean", "--json")
    assert r.returncode == 0


def test_todo_marker_is_unfinished_and_exits_one(make_repo):
    repo = make_repo(files={"app.py": "# TODO later\n"})
    commit_all(repo)
    r = run_state_report("--roots", repo)
    assert r.returncode == 1
    assert "17. unfinished:" in r.stdout
    assert "TODO" in r.stdout


def test_tracked_secret_is_hard_defect_and_exits_one(make_repo):
    repo = make_repo(files={"app.py": "x = 1\n", "server.pem": "secret\n"})
    commit_all(repo)
    r = run_state_report("--roots", repo, "--json")
    assert r.returncode == 1
    assert "tracked secret" in r.stdout
    reports = load_reports(None)
    indices = reports[repo.name]["indices"]
    assert indices["21"]["tracked_secrets"] == ["server.pem"]


def test_json_report_shape(clean_repo, state_dir):
    repo = clean_repo
    r = shared_run("clean", "--json")
    assert r.returncode == 0
    assert "report " in r.stdout
    reports = {repo.name: seeded_report(repo, "clean")}
    assert repo.name in reports
    doc = reports[repo.name]
    assert set(doc) == {"repo", "tree", "head", "since", "truncated", "indices"}
    assert doc["truncated"] is False
    assert doc["repo"] == repo.name
    assert len(doc["tree"]) == 40  # git tree hash
    assert len(doc["head"]) == 40  # git commit hash
    assert doc["since"] == "24 hours ago"
    assert isinstance(doc["indices"], dict)
    # indices dict is sparse by design: only indices with findings record keys.
    # index 3 (plan files) never writes; 7/8 never write.
    assert "1" in doc["indices"] and "2" in doc["indices"]
    assert "3" not in doc["indices"]
    assert doc["indices"]["1"]["status"]
    assert "branches" in doc["indices"]["2"]


def test_json_custom_dir_receives_report(make_repo, tmp_path):
    repo = make_repo(files={"app.py": "x = 1\n"})
    commit_all(repo)
    custom = tmp_path / "custom-records"
    r = run_state_report("--roots", repo, "--json", custom)
    assert r.returncode == 0
    found = list(custom.glob("*/*/report.json"))
    assert len(found) == 1
    doc = json.loads(found[0].read_text(encoding="utf-8"))
    assert doc["repo"] == repo.name


def _build_finding_repo(make_repo):
    repo = make_repo(
        files={
            "README.md": "# Demo\n\nSee `docs/guide.md` and `docs/missing.md`.\n",
            "docs/guide.md": "# Guide\n",
            "tests/test_a.py": "import pytest\n\n\n@pytest.mark.skip\ndef test_a():\n    pass\n",
            "app.py": "# TODO later\n",
            "handoff-notes.md": "# Handoff\n",
            "one.txt": "x" * 300,
            "two.txt": "x" * 300,
            "scratch.tmp": "",
            "empty.txt": "",
            ".gitignore": "out/\n",
        }
    )
    commit_all(repo)
    (repo / "app.py").write_text("# TODO later\nx = 1\n")
    (repo / "new.txt").write_text("new")
    (repo / "emptydir").mkdir()
    (repo / "pkg" / "__pycache__").mkdir(parents=True)
    (repo / "pkg" / "__pycache__" / "m.pyc").write_text("c")
    (repo / "out").mkdir(exist_ok=True)
    (repo / "out" / "build.bin").write_text("b")
    old = time.time() - 3 * 86400
    os.utime(repo / "out", (old, old))
    return repo


def test_index_findings_pinned(make_repo):
    repo = _build_finding_repo(make_repo)
    r = run_state_report("--roots", repo, "--json")
    assert r.returncode == 1  # TODO hit drives unfinished exit
    reports = load_reports(None)
    idx = reports[repo.name]["indices"]
    assert f"{repo.name}/handoff-notes.md" in idx["5"]["files"]
    assert idx["12"]["markers"] == ["tests/test_a.py:4"]
    assert idx["15"]["empty_dirs"] == [f"{repo.name}/emptydir"]
    assert idx["16"]["duplicates"] == [[f"{repo.name}/one.txt", f"{repo.name}/two.txt"]]
    assert [b["ref"] for b in idx["19"]["bad_refs"]] == ["docs/missing.md"]
    assert any(h.endswith("app.py:1") for h in idx["17"]["hits"])
    assert any("empty.txt" in z for z in idx["4"]["zero_byte"])
    assert any("scratch.tmp" in t for t in idx["4"]["tmp_bak_orig"])
    assert any("__pycache__" in p for p in idx["4"]["pycache"])
    assert any("out" in p for p in idx["4"]["ignored_untracked_old"])


def test_tracked_secret_content_never_indexed(make_repo):
    repo = make_repo(files={"server.pem": "S3CR3T\n", "app.py": "x=1\n"})
    commit_all(repo)
    r = run_state_report("--roots", repo, "--json")
    assert r.returncode == 1
    # the secret filename must not leak into duplicate/file scans as content
    assert "S3CR3T" not in r.stdout


def test_roots_folder_of_repos_audits_children(make_repo, tmp_path):
    parent = tmp_path / "parent"
    parent.mkdir()
    ra = make_repo(name="parent/repo-a", files={"a.py": "1\n"})
    rb = make_repo(name="parent/repo-b", files={"b.py": "2\n"})
    commit_all(ra)
    commit_all(rb)
    r = run_state_report("--roots", parent)
    assert r.returncode == 0
    assert "repo-a" in r.stdout and "repo-b" in r.stdout


def test_transcript_adds_touched_repo(make_repo, tmp_path):
    ra = make_repo(files={"a.py": "1\n"})
    rb = make_repo(files={"b.py": "2\n"})
    commit_all(ra)
    commit_all(rb)
    line = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Edit",
                        "input": {"file_path": str(rb / "b.py")},
                    }
                ]
            },
        }
    )
    t = tmp_path / "t.jsonl"
    t.write_text(line + "\n")
    r = run_state_report("--transcript", t, cwd=ra)
    assert ra.name in r.stdout or str(ra) in r.stdout
    assert rb.name in r.stdout or str(rb) in r.stdout


def test_since_flag_windows(make_repo):
    # bench: solo 4.5s, xdist 14.1s; three full audits (24h/7d/2w), per-audit git + dotnet dominate
    repo = make_repo(files={"app.py": "x = 1\n"})
    commit_all(repo)
    for flag in ("24h", "7d", "2w"):
        r = run_state_report("--roots", repo, "--since", flag)
        assert r.returncode == 0
        assert "repos:" in r.stdout


def test_since_invalid_value_fails_current_behavior(clean_repo):
    r = run_state_report("--roots", clean_repo, "--since", "bogus")
    assert r.returncode == 2
    assert "--since must look like 24h, 7d or 2w (got 'bogus')" in (r.stdout + r.stderr)
    assert "Traceback" not in (r.stdout + r.stderr)


def test_empty_dirs_and_duplicates_absent_when_clean(clean_repo):
    r = shared_run("clean", "--json")
    assert r.returncode == 0
    idx = seeded_report(clean_repo, "clean")["indices"]
    assert "15" not in idx
    assert "16" not in idx


def test_selftest_passes():
    r = run_state_report("--selftest")
    assert r.returncode == 0
    assert "FAIL" not in r.stdout
