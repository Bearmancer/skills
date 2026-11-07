"""Failing-first tests for lessons L1-L7 (work-audit refactor).

Each group fails on the untouched scripts and passes after the refactor.
Every repo fixture is a throwaway git repo under pytest tmp_path with
WORK_AUDIT_STATE_DIR isolated there (see conftest.py). All spawned work is
bounded by timeouts; no test blocks without a deadline.
"""

import concurrent.futures
import json
import os
import shlex
import sys
from pathlib import Path

import pytest

from conftest import (
    RECORD,
    STATE_REPORT,
    STOP_GUARD,
    commit_all,
    load_reports,
    run_record,
    run_state_report,
    run_stop_guard,
    fresh_script_module,
    cli_brief,
)

NO_GH = {"WORK_AUDIT_NO_GH": "1"}
NO_ROOTS = {"WORK_AUDIT_ROOTS": ""}
BASE_ENV = {**NO_GH, **NO_ROOTS}
_IS_WINDOWS = sys.platform == "win32"


def _write_stub(bindir, name, bat_lines, sh_lines):
    """Write a fake tool that shutil.which will find: a .bat on Windows, an
    executable #!/bin/sh script elsewhere. Both must behave the same."""
    if _IS_WINDOWS:
        (Path(bindir) / f"{name}.bat").write_bytes(
            ("\r\n".join(bat_lines) + "\r\n").encode("utf-8")
        )
        return
    stub = Path(bindir) / name
    stub.write_text("\n".join(sh_lines) + "\n", encoding="utf-8", newline="\n")
    stub.chmod(0o755)


def load_script(name):
    return fresh_script_module(name)


def state_records_base():
    return Path(os.environ["WORK_AUDIT_STATE_DIR"]) / ".work-audit-state" / "records"


# L1: bounded scanning ----------------------------------------------------


def test_l1_scan_bounds_exposed_with_defaults():
    sr = load_script(STATE_REPORT)
    assert set(sr.SKIP_DIRS) >= {"node_modules", ".git", "__pycache__", ".venv"}
    assert sr.MAX_FILES == 20000
    assert sr.INDEX_TIMEOUT == 20


def test_l1_skips_unlisted_ignored_dirs(make_repo):
    repo = make_repo(files={"app.py": "# TODO visible\n"})
    (repo / "node_modules" / "pkg").mkdir(parents=True)
    (repo / "node_modules" / "pkg" / "index.js").write_text("# TODO hidden\n")
    (repo / "node_modules" / "empty-sub").mkdir(parents=True)
    commit_all(repo)
    r = run_state_report("--roots", repo, "--json", extra_env=BASE_ENV)
    assert r.returncode == 1  # the visible TODO still drives unfinished exit
    assert "node_modules" not in r.stdout
    reports = load_reports(None)
    blob = json.dumps(reports[repo.name]["indices"])
    assert "node_modules" not in blob


def test_l1_file_count_cap_reports_truncation(make_repo):
    files = {f"f{i:03d}.txt": "x\n" for i in range(60)}
    files["app.py"] = "x = 1\n"
    repo = make_repo(files=files)
    commit_all(repo)
    env = {**BASE_ENV, "WORK_AUDIT_MAX_FILES": "50"}
    r = run_state_report("--roots", repo, "--json", extra_env=env)
    # #213: a cap hit stops the scan at once and names the narrowing command.
    assert r.returncode == 3
    assert "stopped early" in r.stderr and "--roots" in r.stderr
    reports = load_reports(None)
    assert "truncat" in json.dumps(reports[repo.name]["indices"]).lower()


def test_l1_per_index_timeout_reports_truncation_never_hangs(clean_repo):
    env = {**BASE_ENV, "WORK_AUDIT_INDEX_TIMEOUT": "0"}
    r = run_state_report("--roots", clean_repo, "--json", extra_env=env)
    assert r.returncode == 3  # #213: fail fast instead of a doomed partial scan
    assert "truncated" in r.stderr and "Traceback" not in r.stderr
    assert load_reports(None)[clean_repo.name]["truncated"] is True


def test_l1_linked_dir_cycle_never_followed(make_repo, tmp_path):
    import time  # noqa: PLC0415

    parent = tmp_path / "cycparent"
    repo = make_repo(
        name="cycparent/repo",
        files={
            "real/a.txt": "x" * 300,
            "app.py": "x = 1\n",
            ".gitignore": "out/\n",
        },
    )
    commit_all(repo)
    (repo / "out").mkdir()
    link = repo / "out" / "link"
    try:
        import subprocess  # noqa: PLC0415

        r = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(repo)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        kind = "junction" if r.returncode == 0 and link.is_dir() else None
    except OSError:
        kind = None
    if kind is None:
        try:
            os.symlink(str(repo), str(link), target_is_directory=True)
            kind = "symlink"
        except OSError as e:
            pytest.fail(
                f"platform refused both junction and symlink for a directory cycle: {e}"
            )
    assert kind in ("junction", "symlink")
    old = time.time() - 3 * 86400
    os.utime(repo / "out", (old, old))
    start = time.monotonic()
    r = run_state_report("--roots", parent, "--json", extra_env=BASE_ENV)
    assert (
        time.monotonic() - start < 60
    )  # a followed cycle never ends; under load a pass takes ~10 s
    assert r.returncode == 0
    assert "truncat" not in r.stdout.lower()  # skipped, not timed out mid-cycle
    reports = load_reports(None)
    idx = reports[repo.name]["indices"]
    assert any("out" in p for p in idx["4"].get("ignored_untracked_old", []))
    assert (
        idx["4"]["safety"][f"{repo.name}/out"]["files"] == 0
    )  # linked contents never counted


# L2: atomic incremental output --------------------------------------------


def test_l2_report_carries_complete_flag(make_repo):
    repo = make_repo(files={"app.py": "x = 1\n"})
    commit_all(repo)
    r = run_state_report("--roots", repo, "--json", extra_env=BASE_ENV)
    assert r.returncode == 0
    reports = load_reports(None)
    assert reports[repo.name]["indices"]["complete"] is True


def test_l2_check_fails_on_incomplete_report(make_repo, tmp_path):
    # bench: solo 5.1s -> 4.7s, xdist 17.6s -> 12.6s; git-heavy write/check flow (NO_GH, threaded tr/ch)
    from test_record import build_record  # noqa: PLC0415

    repo = make_repo(
        files={
            "README.md": "# Demo\n\nUse `--fast-mode` here.\n",
            "app.py": 'parser.add_argument("--fast-mode")\n',
        }
    )
    commit_all(repo)
    (repo / "app.py").write_text('parser.add_argument("--fast-mode")\nx = 1\n')
    brief = cli_brief(repo, "demo-record")
    for idx in ("19", "20", "21", "verify"):
        rec = build_record(repo, brief, idx)
        p = tmp_path / f"inc-{idx}.json"
        p.write_text(json.dumps(rec))
        w = run_record("write", p, repo)
        assert w.returncode == 0, w.stdout
    r = run_record("check", repo)
    assert r.returncode == 0
    assert "pairs not ok: 0" in r.stdout
    # flip the report to incomplete: check must now fail
    from conftest import find_report  # noqa: PLC0415

    repof = find_report(repo.name)
    doc = json.loads(repof.read_text(encoding="utf-8"))
    doc["indices"]["complete"] = False
    repof.write_text(json.dumps(doc), encoding="utf-8")
    r2 = run_record("check", repo)
    assert r2.returncode == 1
    assert "incomplete" in r2.stdout.lower()


def test_l2_atomic_write_helper_roundtrip(tmp_path):
    sr = load_script(STATE_REPORT)
    sub = tmp_path / "sub"
    sub.mkdir()
    target = sub / "report.json"
    sr.atomic_write_json(target, {"a": 1, "complete": False})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1, "complete": False}
    sr.atomic_write_json(target, {"a": 2, "complete": True})
    assert json.loads(target.read_text(encoding="utf-8"))["complete"] is True
    assert list(sub.iterdir()) == [target]  # no temp files left behind


def test_l2_parallel_reports_never_corrupt(make_repo):
    repo = make_repo(files={"app.py": "x = 1\n"})
    commit_all(repo)
    # End to end through real subprocesses via the resolved interpreter:
    # cross-process atomicity needs real processes, not the uv launcher.
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futs = [
            pool.submit(
                run_state_report, "--roots", repo, "--json", extra_env=BASE_ENV, uv=True
            )
            for _ in range(4)
        ]
        results = [f.result(timeout=300) for f in futs]
    assert [r.returncode for r in results] == [0, 0, 0, 0]
    found = list(state_records_base().glob("*/*/report.json"))
    assert len(found) == 1
    doc = json.loads(found[0].read_text(encoding="utf-8"))
    assert doc["indices"]["complete"] is True


# L3: own-repo end-state facts ----------------------------------------------


def test_l3_roots_cover_every_nested_repo(make_repo, tmp_path):
    parent = tmp_path / "roots"
    (parent / "nested").mkdir(parents=True)
    ra = make_repo(name="roots/child-a", files={"a.py": "1\n"})
    rb = make_repo(name="roots/nested/child-b", files={"b.py": "2\n"})
    commit_all(ra)
    commit_all(rb)
    env = {**NO_GH, "WORK_AUDIT_ROOTS": str(parent)}
    r = run_state_report("--roots", parent, extra_env=env)
    assert r.returncode == 0
    assert "child-a" in r.stdout
    assert "child-b" in r.stdout  # nested repos are covered, not just children


def test_l3_third_party_and_duplicate_clones(make_repo, tmp_path):
    parent = tmp_path / "clones"
    parent.mkdir()
    ra = make_repo(name="clones/alpha", files={"a.py": "1\n"})
    rb = make_repo(name="clones/beta", files={"b.py": "2\n"})
    commit_all(ra)
    commit_all(rb)
    url = "https://github.com/someone-else/sample.git"
    import subprocess  # noqa: PLC0415

    for repo in (ra, rb):
        subprocess.run(
            ["git", "-C", str(repo), "remote", "add", "origin", url],
            check=True,
            timeout=60,
        )
    env = {**NO_GH, "WORK_AUDIT_ROOTS": str(parent), "WORK_AUDIT_OWNERS": "TestOwner"}
    r = run_state_report("--roots", parent, "--json", extra_env=env)
    assert r.returncode == 0
    assert "third-part" in r.stdout.lower()
    assert "duplicate" in r.stdout.lower()
    reports = load_reports(None)
    idx2 = reports["alpha"]["indices"]["2"]
    assert idx2["third_party"] is True
    assert "beta" in json.dumps(idx2.get("duplicate_origin", []))


def test_l3_plan_files_classified_executed_open(make_repo):
    repo = make_repo(
        files={
            "plans/done.md": "# Plan\n\n- [x] a\n- [x] b\n\nRemaining items: 0\n",
            "plans/open.md": "# Plan\n\n- [x] a\n- [ ] b\n",
            "app.py": "x = 1\n",
        }
    )
    commit_all(repo)
    r = run_state_report("--roots", repo, extra_env=BASE_ENV)
    assert r.returncode == 1  # the open plan's unchecked box is unfinished work
    line3 = next(l for l in r.stdout.splitlines() if l.startswith("3. plan files:"))
    assert "executed 1" in line3 and "open 1" in line3


def test_l3_config_roots_allowlist(make_repo, tmp_path):
    home = tmp_path / "fakehome"
    cfg = home / ".testcfg-a"
    cfg.mkdir(parents=True)
    (cfg / "keep1.txt").write_text("keep\n")
    (cfg / "drop.txt").write_text("drop\n")
    toml = tmp_path / "work-audit.toml"
    toml.write_text('config_roots = [".testcfg-a"]\nallow = ["drop.txt"]\n')
    repo = make_repo(files={"app.py": "x = 1\n"})
    commit_all(repo)
    env = {
        **BASE_ENV,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "WORK_AUDIT_CONFIG_FILE": str(toml),
    }
    r = run_state_report("--roots", repo, "--json", extra_env=env)
    assert r.returncode == 0
    assert "keep1.txt" in r.stdout
    assert "drop.txt" not in r.stdout
    reports = load_reports(None)
    blob = json.dumps(reports[repo.name]["indices"]["4"])
    assert "keep1.txt" in blob and "drop.txt" not in blob


def test_l3_default_config_roots_from_shipped_toml(make_repo, tmp_path):
    home = tmp_path / "defhome"
    (home / ".claude").mkdir(parents=True)
    (home / ".omo").mkdir(parents=True)
    (home / ".claude" / "entry-a.txt").write_text("a\n")
    (home / ".omo" / "entry-b.txt").write_text("b\n")
    import shutil  # noqa: PLC0415

    toml = tmp_path / "shipped.toml"
    shutil.copyfile(STATE_REPORT.parent / "work-audit.toml", toml)
    repo = make_repo(files={"app.py": "x = 1\n"})
    commit_all(repo)
    env = {
        **BASE_ENV,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "WORK_AUDIT_CONFIG_FILE": str(toml),
    }
    r = run_state_report("--roots", repo, "--json", extra_env=env)
    assert r.returncode == 0
    assert "entry-a.txt" in r.stdout and "entry-b.txt" in r.stdout
    reports = load_reports(None)
    blob = json.dumps(reports[repo.name]["indices"]["4"])
    assert "entry-a.txt" in blob and "entry-b.txt" in blob


def test_l3_no_hardcoded_config_dir_names_in_scripts():
    # The home-config scan (load_config/config_entries in state-report.py)
    # must read its roots from work-audit.toml, never literals in code.
    # (record.py has a pre-existing STYLE_GLOBS entry for plan specs that
    # is out of scope here and stays untouched.)
    text = STATE_REPORT.read_text(encoding="utf-8")
    assert ".claude" not in text
    assert ".omo" not in text
    assert "work-audit.toml" in text


def test_l3_index11_gh_unavailable_when_no_gh(clean_repo):
    r = run_state_report("--roots", clean_repo, "--json", extra_env=BASE_ENV)
    assert r.returncode == 0
    assert "gh unavailable" in r.stdout
    reports = load_reports(None)
    assert reports[clean_repo.name]["indices"]["11"]["gh_status"] == "unavailable"


# L4: deletion-safety facts --------------------------------------------------


def test_l4_stale_findings_carry_safety_facts(make_repo):
    repo = make_repo(
        name="safety facts-ünicode",
        files={
            "README.md": "# Demo\n",
            "app.py": "x = 1\n",
            "empty.txt": "",
            "scratch.tmp": "s\n",
            "one.txt": "x" * 300,
            "two.txt": "x" * 300,
        },
    )
    commit_all(repo)
    (repo / "app.py").write_text("x = 2\n")  # uncommitted change for counts
    (repo / "emptydir").mkdir()
    r = run_state_report("--roots", repo, "--json", extra_env=BASE_ENV)
    assert r.returncode == 0
    idx = load_reports(None)[repo.name]["indices"]
    for key in ("4", "15", "16"):
        assert "safety" in idx[key], f"index {key} lacks safety facts"
    for rel, facts in idx["4"]["safety"].items():
        assert {"files", "newest_mtime", "branch", "uncommitted", "unpushed"} <= set(
            facts
        ), rel
        assert isinstance(facts["files"], int) and facts["files"] >= 1
        assert isinstance(facts["uncommitted"], int) and facts["uncommitted"] >= 1
        assert isinstance(facts["branch"], str) and facts["branch"]


# L5: quiet repeats ------------------------------------------------------------


def test_l5_quiet_repeat_prints_single_line(make_repo):
    # bench: solo 6.8s -> 6.5s, xdist 16.0s; three full audits, dotnet/i6 cost cached per worker
    repo = make_repo(files={"app.py": "x = 1\n"})
    commit_all(repo)
    args = ("--roots", repo, "--json", "--quiet-if-unchanged")
    first = run_state_report(*args, extra_env=BASE_ENV)
    assert first.returncode == 0
    assert "3. plan files:" in first.stdout  # full report the first time
    second = run_state_report(*args, extra_env=BASE_ENV)
    assert second.returncode == 0
    lines = [l for l in second.stdout.splitlines() if l.strip()]
    assert len(lines) == 1
    assert lines[0].startswith("unchanged since ")
    third = run_state_report(*args, extra_env=BASE_ENV)
    assert third.stdout == second.stdout  # quiet repeats are idempotent


# L6: no unbounded subprocess -----------------------------------------------------


def install_fake_git_hang(bindir, real, flag):
    """Fake git hangs once, on setup's unique `ls-files --directory` call only;
    every other call delegates to the real git."""
    _write_stub(
        bindir,
        "git",
        [
            "@echo off",
            'echo %* | findstr /C:"--directory" >nul',
            "if errorlevel 1 goto real",
            f'if exist "{flag}" goto real',
            f'echo. > "{flag}"',
            "ping -n 6 127.0.0.1 >nul",  # test-audit: accept single real-timeout hang; later calls delegate
            "exit /b 0",
            ":real",
            f'"{real}" %*',
        ],
        [
            "#!/bin/sh",
            'case "$*" in',
            "*--directory*)",
            f'  if [ -e {shlex.quote(str(flag))} ]; then exec {shlex.quote(real)} "$@"; fi',
            f"  : > {shlex.quote(str(flag))}",
            "  sleep 5",
            "  exit 0",
            "  ;;",
            "esac",
            f'exec {shlex.quote(real)} "$@"',
        ],
    )


def test_l6_subprocess_timeout_is_30_and_named():
    for script in (STATE_REPORT, RECORD):
        text = script.read_text(encoding="utf-8")
        assert "timeout=60" not in text, f"{script.name} still has timeout=60"
        assert "timeout=120" not in text, f"{script.name} still has timeout=120"
        assert "timeout=25" not in text, f"{script.name} still has timeout=25"
    sr, rc = load_script(STATE_REPORT), load_script(RECORD)
    assert sr.SUBPROCESS_TIMEOUT == 30
    assert rc.SUBPROCESS_TIMEOUT == 30


def test_l6_timeout_becomes_finding_never_hang_or_crash(
    clean_repo, tmp_path, monkeypatch
):
    # bench: solo 8.5s -> 4.3s, xdist 9.7s; one real timeout via single-hang fake git (was ~60 taskkills at timeout 0)
    import shutil  # noqa: PLC0415
    import time  # noqa: PLC0415

    real = shutil.which("git")
    assert real, "git must be on PATH: this test exercises a real timeout"
    flag = tmp_path / "hung-once"
    bindir = tmp_path / "slowgit"
    bindir.mkdir(exist_ok=True)
    install_fake_git_hang(bindir, real, flag)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    env = {**BASE_ENV, "WORK_AUDIT_SUBPROCESS_TIMEOUT": "1"}
    start = time.monotonic()
    r = run_state_report("--roots", clean_repo, "--json", extra_env=env)
    assert (
        time.monotonic() - start < 90
    )  # bounded, not fast: every spawn here waits out its 1 s cap
    assert r.returncode == 0
    assert "subprocess timeouts" in r.stdout.lower()


# L7: no block loops ---------------------------------------------------------------


def _guard_lines(tmp_path):
    user = json.dumps({"type": "user", "message": {"content": "fix"}})
    edit = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Edit", "input": {"file_path": "a"}}
                ]
            },
        }
    )
    return [user, edit]


def test_l7_decide_blocks_twice_then_allows(tmp_path):
    sg = load_script(STOP_GUARD)
    lines = _guard_lines(tmp_path)
    pairs = [("19", "r1", "missing", "")]
    blocks, unresolved = {}, []
    first = sg.decide(lines, "fp", "stamp", pairs, blocks, unresolved)
    assert first[0] is not None and first[0].startswith("Required review records")
    second = sg.decide(lines, "fp", "stamp", pairs, blocks, unresolved)
    assert second[0] is not None
    third = sg.decide(lines, "fp", "stamp", pairs, blocks, unresolved)
    assert third == (None, None)  # allowed on the third identical block
    assert unresolved and "19@r1" in unresolved[0]


# D3: executed plans do not count as unfinished --------------------------------------------


def test_d3_executed_plans_excluded_from_unfinished(make_repo):
    repo = make_repo(
        files={
            "plans/done.md": "# Plan\n\n- [x] a\n- [ ] b\n\nRemaining items: 0\n",
            "plans/open.md": "# Plan\n\n- [x] a\n- [ ] b\n",
            "app.py": "x = 1\n",
        }
    )
    commit_all(repo)
    r = run_state_report("--roots", repo, extra_env=BASE_ENV)
    assert r.returncode == 1  # the open plan's box is unfinished work
    line17 = next(l for l in r.stdout.splitlines() if l.startswith("17. unfinished:"))
    assert "1 unchecked plan boxes" in line17
    line3 = next(l for l in r.stdout.splitlines() if l.startswith("3. plan files:"))
    assert "executed 1" in line3 and "open 1" in line3


# D4: canonical origins, case-insensitive owners -------------------------------------------


def test_d4_normalize_origin_canonical():
    sr = load_script(STATE_REPORT)
    cases = {
        "git@github.com:Someone/Sample.git": "github.com/someone/sample",
        "ssh://git@github.com/Someone/Sample": "github.com/someone/sample",
        "https://github.com/Someone/Sample.git/": "github.com/someone/sample",
        "https://github.com/someone/sample": "github.com/someone/sample",
        "github.com/Someone/Sample": "github.com/someone/sample",
        "": "",
    }
    for raw, want in cases.items():
        assert sr.normalize_origin(raw) == want, raw


def test_d4_duplicates_group_canonical_and_owners_match_case_insensitive(
    make_repo, tmp_path
):
    parent = tmp_path / "d4roots"
    parent.mkdir()
    ra = make_repo(name="d4roots/aaa", files={"a.py": "1\n"})
    rb = make_repo(name="d4roots/bbb", files={"b.py": "2\n"})
    commit_all(ra)
    commit_all(rb)
    import subprocess  # noqa: PLC0415

    subprocess.run(
        [
            "git",
            "-C",
            str(ra),
            "remote",
            "add",
            "origin",
            "git@github.com:TestOwner/Sample.git",
        ],
        check=True,
        timeout=60,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(rb),
            "remote",
            "add",
            "origin",
            "https://github.com/testowner/sample/",
        ],
        check=True,
        timeout=60,
    )
    env = {**NO_GH, "WORK_AUDIT_ROOTS": str(parent), "WORK_AUDIT_OWNERS": "testowner"}
    r = run_state_report("--roots", parent, "--json", extra_env=env)
    assert r.returncode == 0
    assert "duplicate" in r.stdout.lower()
    reports = load_reports(None)
    idx = reports["aaa"]["indices"]["2"]
    assert idx["third_party"] is False
    assert any("bbb" in s for s in idx.get("duplicate_origin", []))


# D6: truncated scans are flagged and refused -------------------------------------------------


def test_d6_truncated_report_flagged_and_refused(make_repo):
    files = {f"f{i:03d}.txt": "x\n" for i in range(60)}
    files["app.py"] = "x = 1\n"
    repo = make_repo(files=files)
    commit_all(repo)
    env = {**BASE_ENV, "WORK_AUDIT_MAX_FILES": "50"}
    r = run_state_report("--roots", repo, "--json", extra_env=env)
    assert r.returncode == 3
    doc = load_reports(None)[repo.name]
    assert doc["truncated"] is True
    for key in ("16", "19", "17"):
        assert "scan_truncated" in doc["indices"].get(key, {}), key
    r2 = run_record("check", repo, extra_env=env)
    assert r2.returncode != 0
    assert "partial scan" in r2.stdout.lower()
    r3 = run_record("brief", repo, extra_env=env)
    assert r3.returncode != 0
    assert "partial scan" in (r3.stdout + r3.stderr).lower()
    r4 = run_record("check", repo, extra_env={**env, "WORK_AUDIT_ALLOW_TRUNCATED": "1"})
    assert "partial scan" not in r4.stdout.lower()
    assert "incomplete" in r4.stdout  # #213: a scan stopped early is never consumable


# D5: same-basename repos never clobber each other ---------------------------------------


def test_d5_same_basename_repos_have_independent_state(make_repo, tmp_path):
    parent = tmp_path / "d5roots"
    alpha = make_repo(name="d5roots/alpha/app", files={"app.py": "x = 1\n"})
    beta = make_repo(name="d5roots/beta/app", files={"app.py": "x = 2\n"})
    commit_all(alpha)
    commit_all(beta)
    mod = load_script(RECORD)
    mod.RECORDS = (
        Path(os.environ["WORK_AUDIT_STATE_DIR"]) / ".work-audit-state" / "records"
    )
    assert mod.rec_dir(alpha) != mod.rec_dir(beta)
    assert mod.rec_dir(alpha).parent == mod.rec_dir(beta).parent
    assert (
        run_state_report("--roots", parent, "--json", extra_env=BASE_ENV).returncode
        == 0
    )
    docs = {}
    base = Path(os.environ["WORK_AUDIT_STATE_DIR"]) / ".work-audit-state" / "records"
    for f in base.glob("*/*/report.json"):
        doc = json.loads(f.read_text(encoding="utf-8"))
        if doc.get("repo") == "app":
            docs[str(f.parent)] = doc
    assert len(docs) == 2
    assert mod.baseline(alpha) == "" and mod.baseline(beta) == ""
    (mod.rec_dir(alpha) / "baseline").write_text("tree-alpha")
    assert mod.baseline(alpha) == "tree-alpha"
    assert mod.baseline(beta) == ""


# D8: Remaining-items lines complete the turn ---------------------------------------------------


def test_d8_completed_matches_remaining_items_unit():
    sg = load_script(STOP_GUARD)
    assert sg.completed("Result: done")
    assert sg.completed("Remaining items: 0")
    assert sg.completed("remaining items: 3")
    assert sg.completed("  REMAINING ITEMS: 0\nmore")
    assert not sg.completed("Done, finished")


def test_d8_remaining_items_message_allows_stop(make_repo, tmp_path):
    repo = make_repo(files={"f.txt": "0\n"})
    commit_all(repo)
    user = json.dumps({"type": "user", "message": {"content": "fix"}})
    first = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "uv run scripts/state-report.py --json"},
                    }
                ]
            },
        }
    )
    edit = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Edit",
                        "input": {"file_path": str(repo / "f.txt")},
                    }
                ]
            },
        }
    )
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(user + "\n" + first + "\n")
    payload = json.dumps(
        {
            "cwd": str(repo),
            "transcript_path": str(transcript),
            "last_assistant_message": "Remaining items: 0",
        }
    )
    assert run_stop_guard(stdin_text=payload, cwd=repo).stdout.strip() == ""
    transcript.write_text(user + "\n" + edit + "\n")
    r = run_stop_guard(stdin_text=payload, cwd=repo)
    assert r.returncode == 0
    assert r.stdout.strip() == ""
    stamp = (
        Path(os.environ["WORK_AUDIT_STATE_DIR"]) / ".work-audit-state" / "audited.json"
    )
    assert stamp.is_file() and json.loads(stamp.read_text())["fingerprint"]


# D9: clean one-line errors, real fingerprints, no duplicate unresolved -------------------------


def _write_repo_report(repo, text):
    from conftest import find_report  # noqa: PLC0415

    repof = find_report(repo.name)
    repof.write_text(text, encoding="utf-8")
    return repof


def test_d9_brief_rejects_wrong_shape_report(make_repo, tmp_path):
    repo = make_repo(files={"app.py": "x = 1\n"})
    commit_all(repo)
    assert (
        run_state_report("--roots", repo, "--json", extra_env=BASE_ENV).returncode == 0
    )
    repof = _write_repo_report(repo, "[]")
    r = run_record("brief", repo, extra_env=BASE_ENV)
    assert r.returncode == 2
    assert "wrong shape" in (r.stdout + r.stderr).lower()
    assert "Traceback" not in (r.stdout + r.stderr)
    repof.write_text(
        json.dumps(
            {
                "repo": repo.name,
                "tree": "t",
                "head": "h",
                "since": "s",
                "truncated": False,
                "indices": None,
            }
        )
    )
    r = run_record("brief", repo, extra_env=BASE_ENV)
    assert r.returncode == 2
    assert "wrong shape" in (r.stdout + r.stderr).lower()


def test_d9_check_rejects_wrong_shape_report(make_repo):
    repo = make_repo(files={"app.py": "x = 1\n"})
    commit_all(repo)
    assert (
        run_state_report("--roots", repo, "--json", extra_env=BASE_ENV).returncode == 0
    )
    _write_repo_report(repo, "[]")
    r = run_record("check", repo, extra_env=BASE_ENV)
    assert r.returncode == 2
    assert "wrong shape" in r.stdout.lower()
    assert "Traceback" not in (r.stdout + r.stderr)


def test_d9_since_rejects_bad_values_with_format(make_repo):
    repo = make_repo(files={"app.py": "x = 1\n"})
    commit_all(repo)
    for flag in ("bogus", "24", "1.5h"):
        r = run_state_report("--roots", repo, "--since", flag, extra_env=BASE_ENV)
        assert r.returncode == 2
        assert "24h, 7d or 2w" in (r.stdout + r.stderr)
        assert "Traceback" not in (r.stdout + r.stderr)


def test_d9_write_rejects_bad_record_files(make_repo, tmp_path):
    repo = make_repo(files={"app.py": "x = 1\n"})
    commit_all(repo)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    r = run_record("write", bad, repo, extra_env=BASE_ENV)
    assert r.returncode == 2
    assert "bad record file" in (r.stdout + r.stderr).lower()
    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    r = run_record("write", empty, repo, extra_env=BASE_ENV)
    assert r.returncode == 2
    assert "Traceback" not in (r.stdout + r.stderr)
    r = run_record("write", tmp_path / "missing.json", repo, extra_env=BASE_ENV)
    assert r.returncode == 2
    assert "bad record file" in (r.stdout + r.stderr).lower()


def test_d9_fourth_identical_block_no_dup_real_fingerprint(make_repo, tmp_path):
    repo = make_repo(files={"f.txt": "0\n"})
    commit_all(repo)
    user = json.dumps({"type": "user", "message": {"content": "fix"}})
    edit = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Edit",
                        "input": {"file_path": str(repo / "f.txt")},
                    }
                ]
            },
        }
    )
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(user + "\n" + edit + "\n")
    payload = json.dumps(
        {
            "cwd": str(repo),
            "transcript_path": str(transcript),
            "last_assistant_message": "Result: done",
        }
    )
    assert (
        json.loads(run_stop_guard(stdin_text=payload, cwd=repo).stdout)["decision"]
        == "block"
    )
    assert (
        json.loads(run_stop_guard(stdin_text=payload, cwd=repo).stdout)["decision"]
        == "block"
    )
    assert run_stop_guard(stdin_text=payload, cwd=repo).stdout.strip() == ""
    fourth = run_stop_guard(stdin_text=payload, cwd=repo)
    assert fourth.stdout.strip() == ""
    stamp = json.loads(
        (
            Path(os.environ["WORK_AUDIT_STATE_DIR"])
            / ".work-audit-state"
            / "audited.json"
        ).read_text()
    )
    assert len(stamp.get("unresolved", [])) == 1
    assert stamp.get("fingerprint")


# D7: backtick paths with spaces are checked --------------------------------------------------


def test_d7_backtick_path_with_spaces_checked(make_repo):
    repo = make_repo(
        files={
            "README.md": "# Demo\n\nSee `docs/real file.md` and `docs/missing with space.md`.\n",
            "docs/guide.md": "# Guide\n",
            "app.py": "x = 1\n",
        }
    )
    (repo / "docs" / "real file.md").write_text("# Real\n")
    commit_all(repo)
    r = run_state_report("--roots", repo, "--json", extra_env=BASE_ENV)
    assert r.returncode == 0
    idx = load_reports(None)[repo.name]["indices"]
    assert [b["ref"] for b in idx["19"].get("bad_refs", [])] == [
        "docs/missing with space.md"
    ]


# D1: empty tree is invalid, never silently OK ------------------------------------------


def _path_without_git():
    """PATH minus every directory that holds git: launching git fails at once (OSError)
    instead of waiting out a zero timeout and running taskkill for each call."""
    keep = [
        p
        for p in os.environ.get("PATH", "").split(os.pathsep)
        if not any(
            os.path.exists(os.path.join(p, n))
            for n in ("git.exe", "git.bat", "git.cmd", "git")
        )
    ]
    return os.pathsep.join(keep)


def _no_git_env(**kw):
    env = {**NO_GH, **NO_ROOTS, "PATH": _path_without_git()}
    env.update(kw)
    return env


def test_d1_unfingerprintable_report_has_tree_error(make_repo):
    repo = make_repo(files={"app.py": "x = 1\n"})
    commit_all(repo)
    r = run_state_report("--roots", repo, "--json", extra_env=_no_git_env())
    assert r.returncode == 0
    reports = load_reports(None)
    doc = reports[repo.name]
    assert "unfingerprintable" in json.dumps(doc["indices"].get("tree_error", ""))
    assert doc["indices"].get("complete") is not True


def test_d1_check_rejects_unfingerprintable(make_repo):
    repo = make_repo(files={"app.py": "x = 1\n"})
    commit_all(repo)
    assert (
        run_state_report("--roots", repo, "--json", extra_env=_no_git_env()).returncode
        == 0
    )
    r = run_record("check", repo, extra_env=_no_git_env())
    assert r.returncode != 0
    assert "unfingerprintable" in r.stdout.lower()


def test_d1_brief_rejects_unfingerprintable(make_repo):
    repo = make_repo(files={"app.py": "x = 1\n"})
    commit_all(repo)
    assert (
        run_state_report("--roots", repo, "--json", extra_env=_no_git_env()).returncode
        == 0
    )
    r = run_record("brief", repo, extra_env=_no_git_env())
    assert r.returncode != 0
    assert "unfingerprintable" in (r.stdout + r.stderr).lower()
    assert "incomplete for tree :" not in (r.stdout + r.stderr)


# D2: git timeout kills the tree and record honors the env var ---------------------


def _ping_pids():
    import subprocess  # noqa: PLC0415

    r = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq ping.exe", "/FO", "CSV"],
        capture_output=True,
        text=True,
        timeout=30,
        shell=True,
    )
    return {
        l.split(",")[1].strip('"')
        for l in r.stdout.splitlines()[1:]
        if l.startswith('"ping.exe"')
    }


def test_d2_git_timeout_kills_tree_and_honors_env(make_repo, tmp_path, monkeypatch):
    import time  # noqa: PLC0415

    bindir = tmp_path / "fakegit"
    bindir.mkdir(exist_ok=True)
    (bindir / "git.bat").write_bytes(
        (
            "\r\n".join(
                [
                    "@echo off",
                    'start "wa-orphan" ping -n 16 127.0.0.1 >nul',  # test-audit: accept hanging tree proves the kill
                    "ping -n 16 127.0.0.1 >nul",  # test-audit: accept hanging tree proves the kill
                ]
            )
            + "\r\n"
        ).encode("utf-8")
    )
    repo = make_repo(files={"app.py": "x = 1\n"})
    commit_all(repo)
    before = _ping_pids()
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("WORK_AUDIT_SUBPROCESS_TIMEOUT", "2")
    mod = load_script(RECORD)
    start = time.monotonic()
    assert mod.git(repo, "rev-parse", "x") is None
    assert time.monotonic() - start < 6
    assert _ping_pids() - before == set()


# L8: gh target resolution ------------------------------------------------------

GH_RESOLVE_MSG = (
    "GraphQL: Could not resolve to a Repository with the name 'someone-else/sample'"
)
GH_AUTH_MSG = "error: not logged in to github.com; run gh auth login to authenticate"
GH_REMOTE = "https://github.com/someone-else/sample.git"

GH_BAT_LINES = [
    "@echo off",
    'if "%1"=="auth" goto auth',
    'if "%1"=="issue" goto issue',
    'if "%1"=="pr" goto pr',
    "echo unsupported gh command %1 1>&2",
    "exit /b 1",
    ":auth",
    'if not "%GH_AUTH_ERR%"=="" echo %GH_AUTH_ERR% 1>&2',
    "exit /b %GH_AUTH_EXIT%",
    ":issue",
    'if not "%GH_ISSUE_ERR%"=="" echo %GH_ISSUE_ERR% 1>&2',
    'if not "%GH_ISSUE_OUT%"=="" echo %GH_ISSUE_OUT%',
    "exit /b %GH_ISSUE_EXIT%",
    ":pr",
    'if not "%GH_PR_ERR%"=="" echo %GH_PR_ERR% 1>&2',
    'if not "%GH_PR_OUT%"=="" echo %GH_PR_OUT%',
    "exit /b %GH_PR_EXIT%",
]


GH_SH_LINES = [
    "#!/bin/sh",
    'case "$1" in',
    "auth)",
    '  [ -z "$GH_AUTH_ERR" ] || printf "%s\\n" "$GH_AUTH_ERR" >&2',
    '  exit "${GH_AUTH_EXIT:-0}"',
    "  ;;",
    "issue)",
    '  [ -z "$GH_ISSUE_ERR" ] || printf "%s\\n" "$GH_ISSUE_ERR" >&2',
    '  [ -z "$GH_ISSUE_OUT" ] || printf "%s\\n" "$GH_ISSUE_OUT"',
    '  exit "${GH_ISSUE_EXIT:-0}"',
    "  ;;",
    "pr)",
    '  [ -z "$GH_PR_ERR" ] || printf "%s\\n" "$GH_PR_ERR" >&2',
    '  [ -z "$GH_PR_OUT" ] || printf "%s\\n" "$GH_PR_OUT"',
    '  exit "${GH_PR_EXIT:-0}"',
    "  ;;",
    "*)",
    '  printf "unsupported gh command %s\\n" "$1" >&2',
    "  exit 1",
    "  ;;",
    "esac",
]


def install_fake_gh(tmp_path):
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    _write_stub(bindir, "gh", GH_BAT_LINES, GH_SH_LINES)
    return str(bindir)


def gh_test_env(bindir, **kw):
    env = {
        "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
        "WORK_AUDIT_NO_GH": "",  # undo the conftest global: fake gh must run
        "WORK_AUDIT_ROOTS": "",
        "WORK_AUDIT_OWNERS": "TestOwner",
    }
    env.update(kw)
    return env


def test_l8_fake_gh_shim_shadows_real_gh(tmp_path):
    # A missing shim must fail here, not silently reach the real gh.
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    bindir = install_fake_gh(tmp_path)
    env = gh_test_env(bindir)
    found = shutil.which("gh", path=env["PATH"])
    assert found is not None, f"no fake gh shim on PATH under {bindir}"
    assert Path(found).parent == Path(bindir)
    r = subprocess.run(
        [found, "bogus"], capture_output=True, text=True, env=env, timeout=30
    )
    assert r.returncode == 1
    assert "unsupported gh command bogus" in r.stderr


def gh_repo(make_repo, name, remote=None):
    import subprocess  # noqa: PLC0415

    repo = make_repo(name=name, files={"app.py": "x = 1\n", "README.md": "# Demo\n"})
    commit_all(repo)
    if remote:
        subprocess.run(
            ["git", "-C", str(repo), "remote", "add", "origin", remote],
            check=True,
            timeout=60,
        )
    return repo


def gh_issue_env(bindir, exit_code, out="", err=""):
    return gh_test_env(
        bindir,
        GH_AUTH_EXIT="0",
        GH_AUTH_ERR="",
        GH_ISSUE_EXIT=exit_code,
        GH_ISSUE_OUT=out,
        GH_ISSUE_ERR=err,
        GH_PR_EXIT=exit_code,
        GH_PR_OUT=out,
        GH_PR_ERR=err,
    )


def test_l8_gh_resolve_error_is_quoted_finding(make_repo, tmp_path):
    bindir = install_fake_gh(tmp_path)
    repo = gh_repo(make_repo, "l8-resolve", remote=GH_REMOTE)
    env = gh_issue_env(bindir, "1", err=GH_RESOLVE_MSG)
    r = run_state_report("--roots", repo, "--json", extra_env=env, cwd=repo)
    assert r.returncode == 0
    assert "Could not resolve" in r.stdout
    assert "someone-else/sample" in r.stdout
    idx = load_reports(None)[repo.name]["indices"]
    errs = idx["11"]["gh_errors"]
    assert errs and any("Could not resolve" in e["error"] for e in errs)
    assert any(e["remote"] == GH_REMOTE for e in errs)
    assert idx["11"]["counts"]["open_issues"] is None
    assert idx["11"]["counts"]["open_prs"] is None


def test_l8_gh_empty_list_means_zero_without_finding(make_repo, tmp_path):
    bindir = install_fake_gh(tmp_path)
    repo = gh_repo(make_repo, "l8-empty", remote=GH_REMOTE)
    env = gh_issue_env(bindir, "0", out="[]")
    r = run_state_report("--roots", repo, "--json", extra_env=env, cwd=repo)
    assert r.returncode == 0
    idx = load_reports(None)[repo.name]["indices"]
    assert idx["11"].get("gh_errors", []) == []
    assert idx["11"]["counts"]["open_issues"] == 0
    assert idx["11"]["counts"]["open_prs"] == 0


def test_l8_gh_auth_failure_is_quoted_finding(make_repo, tmp_path):
    bindir = install_fake_gh(tmp_path)
    repo = gh_repo(make_repo, "l8-auth", remote=GH_REMOTE)
    env = {
        "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
        "WORK_AUDIT_NO_GH": "",  # undo the conftest global: fake gh must run
        "WORK_AUDIT_ROOTS": "",
        "GH_AUTH_EXIT": "1",
        "GH_AUTH_ERR": GH_AUTH_MSG,
        "GH_ISSUE_EXIT": "1",
        "GH_ISSUE_OUT": "",
        "GH_ISSUE_ERR": GH_RESOLVE_MSG,
        "GH_PR_EXIT": "1",
        "GH_PR_OUT": "",
        "GH_PR_ERR": GH_RESOLVE_MSG,
    }
    r = run_state_report("--roots", repo, "--json", extra_env=env, cwd=repo)
    assert r.returncode == 0
    assert "not logged in" in r.stdout
    idx = load_reports(None)[repo.name]["indices"]
    assert idx["11"]["gh_status"] == "unavailable"
    assert any("not logged in" in e["error"] for e in idx["11"]["gh_errors"])


def test_l8_repo_without_remote_is_own_finding(make_repo, tmp_path):
    install_fake_gh(tmp_path)
    repo = gh_repo(make_repo, "l8-noremote")
    env = {**NO_GH, **NO_ROOTS}
    r = run_state_report("--roots", repo, "--json", extra_env=env, cwd=repo)
    assert r.returncode == 0
    assert "remote does not resolve" in r.stdout
    idx = load_reports(None)[repo.name]["indices"]
    assert any("remote does not resolve" in e["error"] for e in idx["11"]["gh_errors"])


def test_l7_hook_allows_third_identical_block_and_records_unresolved(
    make_repo, tmp_path
):
    from conftest import run_stop_guard  # noqa: PLC0415

    repo = make_repo(files={"f.txt": "0\n"})
    commit_all(repo)
    user = json.dumps({"type": "user", "message": {"content": "fix"}})
    edit = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Edit",
                        "input": {"file_path": str(repo / "f.txt")},
                    }
                ]
            },
        }
    )
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(user + "\n" + edit + "\n")
    payload = json.dumps(
        {
            "cwd": str(repo),
            "transcript_path": str(transcript),
            "last_assistant_message": "Result: done",
        }
    )
    first = run_stop_guard(stdin_text=payload, cwd=repo)
    assert json.loads(first.stdout)["decision"] == "block"
    second = run_stop_guard(stdin_text=payload, cwd=repo)
    assert json.loads(second.stdout)["decision"] == "block"
    third = run_stop_guard(stdin_text=payload, cwd=repo)
    assert third.stdout.strip() == ""  # allowed: no block output
    stamp = json.loads(
        (
            Path(os.environ["WORK_AUDIT_STATE_DIR"])
            / ".work-audit-state"
            / "audited.json"
        ).read_text()
    )
    assert stamp.get("unresolved"), "third block must write the unresolved list"
    assert len(stamp.get("blocks", {})) == 1, (
        "third block went through the block counter in main()"
    )
