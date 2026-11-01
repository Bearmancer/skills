"""Rigor tests: Windows paths, CRLF, idempotence, concurrency, no-sleep/timeout audit.

Every repo fixture is a throwaway real git repo under pytest tmp_path with
WORK_AUDIT_STATE_DIR isolated there. All spawned work is bounded by timeouts;
no test sleeps, polls, or retries.
"""

import ast
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from conftest import (
    audit_brief,
    cli_brief,
    commit_all,
    run_record,
    run_state_report,
    write_cli,
)

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent / "scripts"
STATE_SUBDIR = ".work-audit-state"


def state_records():
    return Path(os.environ["WORK_AUDIT_STATE_DIR"]) / STATE_SUBDIR / "records"


def snapshot_records():
    """Map every file under the isolated records dir to its sha256."""
    base = state_records()
    out = {}
    for p in sorted(base.rglob("*")):
        if p.is_file():
            out[p.relative_to(base).as_posix()] = hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
    return out


def without_header(stdout):
    """Drop the state-report header line: it carries the run timestamp."""
    lines = stdout.splitlines()
    assert lines and lines[0].startswith("state-report ")
    return lines[1:]


def make_demo_repo(make_repo, name=None, extra_files=None):
    files = {
        "README.md": "# Demo\n\nUse `--fast-mode` here.\n",
        "app.py": 'parser.add_argument("--fast-mode")\nx = 1\n',
    }
    files.update(extra_files or {})
    repo = make_repo(name=name, files=files)
    commit_all(repo)
    (repo / "app.py").write_text('parser.add_argument("--fast-mode")\nx = 2\n')
    return repo


def build_record_for(repo, brief, idx):
    import sys as _sys

    spec = brief["required"][idx]
    rec = {
        "index": idx,
        "repo": repo.name,
        "files_read": spec["required_files"],
        "findings": [],
        "samples": [],
        "verdict": "pass",
    }
    status = {
        "claim": "ok",
        "ref": "placeholder",
        "pair": "distinct",
        "file": "conforms",
    }
    for s in spec["samples"]:
        if s["kind"] == "claim":
            ev = next(
                f"{p.relative_to(repo).as_posix()}:{n}"
                for p in sorted(repo.rglob("*"))
                if p.is_file() and ".git" not in p.parts and p != repo / s["doc"]
                for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                if s["token"] in line
            )
        elif s["kind"] == "ref":
            ev = f"{s['doc']}:{s['line']}"
        elif s["kind"] == "pair":

            def _line(rel):
                return next(
                    n
                    for n, line in enumerate(
                        (repo / rel).read_text(encoding="utf-8").splitlines(), 1
                    )
                    if s["token"] in line
                )

            ev = f"{s['a']}:{_line(s['a'])}; {s['b']}:{_line(s['b'])}"
        else:
            ev = f"{s['file']}:1"
        rec["samples"].append(
            {"id": s["id"], "status": status[s["kind"]], "evidence": ev}
        )
    if idx == "21":
        rec["rules"] = [
            f"{line}@{doc}:{n}"
            for doc in spec["style_docs"]
            for n, line in enumerate(
                (repo / doc).read_text(encoding="utf-8").splitlines(), 1
            )
            if len(line) >= 8 and "@" not in line
        ][: len(spec["style_docs"])]
    if idx == "verify":
        # Test commands run through uv; sys.executable only when uv is unavailable inside the sandbox.
        _uv = shutil.which("uv")
        cmd = (
            f'"{_uv}" run --no-project python -c "import sys; sys.exit(0)"'
            if _uv
            else f'"{_sys.executable}" -c "import sys; sys.exit(0)"'
        )
        rec["evidence"] = [
            {"file": f, "kind": "test", "cmd": cmd, "exit": 0}
            for f in spec["required_files"]
        ]
        rec["tests_identified"] = [cmd]
        rec["open_questions"] = 0
    return rec


# Windows paths ---------------------------------------------------------------


def test_repo_path_with_spaces(make_repo):
    repo = make_repo(
        name="my repo (1)",
        files={"README.md": "# Spaced\n", "app.py": "# TODO spaced\n"},
    )
    commit_all(repo)
    r = run_state_report("--roots", repo, "--json")
    assert r.returncode == 1  # TODO hit still drives unfinished exit
    assert str(repo) in r.stdout
    assert f"{repo.name}/app.py:1" in r.stdout


def test_repo_path_with_unicode(make_repo):
    repo = make_repo(
        name="repo-ünicode-日本語",
        files={"README.md": "# Uni\n", "app.py": "# TODO uni\n"},
    )
    commit_all(repo)
    r = run_state_report("--roots", repo, "--json")
    assert r.returncode == 1  # TODO hit still drives unfinished exit
    assert str(repo) in r.stdout
    assert f"{repo.name}/app.py:1" in r.stdout
    reports = {}
    for f in state_records().glob("*/*/report.json"):
        doc = json.loads(f.read_text(encoding="utf-8"))
        reports[doc["repo"]] = doc
    assert reports[repo.name]["repo"] == repo.name
    assert reports[repo.name]["indices"]["1"]["status"]


def test_crlf_files_audited(make_repo, tmp_path):
    # bench: solo 7.3s -> 4.0s, xdist 18.1s -> 12.6s; audit+brief+write flow (NO_GH, cached tools)
    repo = make_repo(name="crlf-repo")
    (repo / "README.md").write_bytes(b"# Demo\r\n\r\nUse `--fast-mode` here.\r\n")
    (repo / "app.py").write_bytes(
        b'parser.add_argument("--fast-mode")\r\n# TODO first\r\nx = 1\r\n'
    )
    commit_all(repo)
    r = run_state_report("--roots", repo, "--json")
    assert r.returncode == 1
    assert f"{repo.name}/app.py:2" in r.stdout  # line number pins CRLF handling
    b = audit_brief(repo)
    rec = build_record_for(repo, b, "19")
    assert write_cli(repo, rec, tmp_path, "crlf-19").returncode == 0


def test_deeply_nested_long_path(make_repo, tmp_path):
    # Size the nesting so the full path stays under the Windows MAX_PATH limit
    # (paths past 260 need machine-level long-path opt-ins outside repo scope).
    base_len = len(str(tmp_path / "repo-lp"))
    seg, parts = "directory-with-a-quite-long-name", []
    while base_len + 1 + sum(len(p) + 1 for p in parts) + len("deep.py") < 210:
        parts.append(f"{seg}-{len(parts):02d}")
    nested = "/".join(parts)
    rel = f"{nested}/deep.py"
    assert len(rel) >= 100
    repo = make_repo(
        name="repo-lp", files={"README.md": "# Deep\n", rel: "# TODO deep\n"}
    )
    assert len(str(repo / rel)) < 260
    commit_all(repo)
    r = run_state_report("--roots", repo, "--json")
    assert r.returncode == 1
    assert f"{repo.name}/{rel}:1" in r.stdout


# Idempotence -------------------------------------------------------------------


def test_state_report_idempotent(make_repo):
    repo = make_demo_repo(make_repo)
    first = run_state_report("--roots", repo, "--json")
    assert first.returncode == 0
    snap1, out1 = snapshot_records(), without_header(first.stdout)
    second = run_state_report("--roots", repo, "--json")
    assert second.returncode == 0
    assert snapshot_records() == snap1
    assert without_header(second.stdout) == out1


def test_brief_idempotent(make_repo):
    repo = make_demo_repo(make_repo)
    assert cli_brief(repo, "demo-rigor") == cli_brief(repo, "demo-rigor")


def test_check_idempotent_after_advance(make_repo, tmp_path):
    repo = make_demo_repo(make_repo)
    b = cli_brief(repo, "demo-rigor")
    for idx in ("19", "20", "21", "verify"):
        assert (
            write_cli(
                repo, build_record_for(repo, b, idx), tmp_path, f"idem-{idx}"
            ).returncode
            == 0
        )
    first = run_record("check", repo)
    assert first.returncode == 0
    assert "pairs not ok: 0" in first.stdout
    snap1 = snapshot_records()
    second = run_record("check", repo)
    assert second.returncode == 0
    assert "pairs not ok: 0" in second.stdout
    assert snapshot_records() == snap1


# Concurrency ---------------------------------------------------------------------


def test_parallel_reports_stay_valid(make_repo):
    repo = make_demo_repo(make_repo)
    # End to end through real subprocesses via the resolved interpreter:
    # concurrent reads and writes need real processes, not the uv launcher.
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(run_state_report, "--roots", repo, "--json", py=True)
            for _ in range(4)
        ]
        results = [f.result(timeout=300) for f in futures]
    assert [r.returncode for r in results] == [0, 0, 0, 0]
    found = list(state_records().glob("*/*/report.json"))
    assert len(found) == 1  # same content tree: one report file
    doc = json.loads(found[0].read_text(encoding="utf-8"))
    assert doc["repo"] == repo.name
    assert set(doc) == {"repo", "tree", "head", "since", "truncated", "indices"}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        # The first brief is record's one real-uv launch; the rest use the
        # resolved interpreter (same output contract, no uv resolve cost).
        briefs = [
            pool.submit(run_record, "brief", repo, uv=(i == 0), py=(i > 0))
            for i in range(4)
        ]
        outs = [f.result(timeout=300).stdout for f in briefs]
    assert len(set(outs)) == 1  # concurrent reads agree byte for byte


# No sleeps; bounded waits ----------------------------------------------------------

SLEEP_RE = re.compile(r"\bsleep\s*\(")


def test_no_sleep_calls_in_tests_and_scripts():
    offenders = [
        f"{p.name}:{n}"
        for p in (*TESTS_DIR.glob("*.py"), *SCRIPTS_DIR.glob("*.py"))
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if SLEEP_RE.search(line)
    ]
    assert offenders == []


def test_bounded_subprocess_and_future_calls():
    violations = []
    for p in TESTS_DIR.glob("*.py"):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if (
                isinstance(f, ast.Attribute)
                and isinstance(f.value, ast.Name)
                and f.value.id == "subprocess"
                and f.attr in ("run", "Popen", "call", "check_call", "check_output")
            ):
                if not any(k.arg == "timeout" for k in node.keywords):
                    violations.append(
                        f"{p.name}:{node.lineno} subprocess.{f.attr} without timeout"
                    )
            if isinstance(f, ast.Attribute) and f.attr in ("result", "as_completed"):
                if not any(k.arg == "timeout" for k in node.keywords):
                    violations.append(
                        f"{p.name}:{node.lineno} future.{f.attr} without timeout"
                    )
    assert violations == []
