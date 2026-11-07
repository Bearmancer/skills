"""Characterization of scripts/record.py: brief, validation rules, baseline movement."""

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from conftest import (
    RECORD,
    audit_brief,
    cli_brief,
    commit_all,
    run_record,
    run_state_report,
    write_cli,
)

DOC = {
    "repo",
    "path",
    "tree",
    "head",
    "baseline",
    "report",
    "changed",
    "required",
    "previous_findings",
}


@pytest.fixture()
def recmod(tmp_path, monkeypatch):
    """Fresh record module with RECORDS patched to the isolated state dir."""
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("record_under_test", str(RECORD))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(
        mod,
        "RECORDS",
        Path(os.environ["WORK_AUDIT_STATE_DIR"]) / ".work-audit-state" / "records",
    )
    return mod


def make_demo(make_repo, readme_extra=""):
    """Repo shaped like the script selftest demo: claim token in doc + code."""
    repo = make_repo(
        files={
            "README.md": "# Demo\n\nUse `--fast-mode` here.\n" + readme_extra,
            "app.py": 'parser.add_argument("--fast-mode")\n',
        }
    )
    commit_all(repo)
    (repo / "app.py").write_text('parser.add_argument("--fast-mode")\nx = 1\n')
    return repo


def find_line(repo, rel, token):
    for n, line in enumerate((repo / rel).read_text(encoding="utf-8").splitlines(), 1):
        if token in line:
            return n
    raise AssertionError(f"token {token!r} not found in {rel}")


def outside_doc_with_token(repo, token, doc):
    for p in sorted(repo.rglob("*")):
        if p.is_file() and ".git" not in p.parts and p.name != ".gitignore":
            try:
                text = p.read_text(encoding="utf-8")
            except OSError:
                continue
            if p != repo / doc:
                for n, line in enumerate(text.splitlines(), 1):
                    if token in line:
                        return p.relative_to(repo).as_posix(), n
    raise AssertionError(f"no outside-doc evidence for {token!r}")


def sample_evidence(repo, s):
    kind = s["kind"]
    if kind == "claim":
        rel, n = outside_doc_with_token(repo, s["token"], s["doc"])
        return f"{rel}:{n}"
    if kind == "ref":
        return f"{s['doc']}:{s['line']}"
    if kind == "pair":
        return f"{s['a']}:{find_line(repo, s['a'], s['token'])}; {s['b']}:{find_line(repo, s['b'], s['token'])}"
    if kind == "file":
        return f"{s['file']}:1"
    raise AssertionError(kind)


STATUS_FOR_KIND = {
    "claim": "ok",
    "ref": "placeholder",
    "pair": "distinct",
    "file": "conforms",
}


def build_record(repo, brief, idx, verdict="pass", findings=(), extra=None):
    spec = brief["required"][idx]
    rec = {
        "index": idx,
        "repo": repo.name,
        "files_read": spec["required_files"],
        "findings": list(findings),
        "samples": [],
        "verdict": verdict,
    }
    for s in spec["samples"]:
        rec["samples"].append(
            {
                "id": s["id"],
                "status": STATUS_FOR_KIND[s["kind"]],
                "evidence": sample_evidence(repo, s),
            }
        )
    if idx == "21":
        rules = []
        for doc in spec["style_docs"]:
            for n, line in enumerate(
                (repo / doc).read_text(encoding="utf-8").splitlines(), 1
            ):
                if len(line) >= 8 and "@" not in line:
                    rules.append(f"{line}@{doc}:{n}")
                    break
        rec["rules"] = rules
    if idx == "verify":
        # Test commands run through uv; sys.executable only when uv is unavailable inside the sandbox.
        _uv = shutil.which("uv")
        cmd = (
            f'"{_uv}" run --no-project python -c "import sys; sys.exit(0)"'
            if _uv
            else f'"{sys.executable}" -c "import sys; sys.exit(0)"'
        )
        rec["evidence"] = [
            {"file": f, "kind": "test", "cmd": cmd, "exit": 0}
            for f in spec["required_files"]
        ]
        rec["tests_identified"] = [cmd]
        rec["open_questions"] = 0
    if extra:
        rec.update(extra)
    return rec


# CLI basics ---------------------------------------------------------------


def test_no_args_prints_usage_and_fails():
    r = run_record()
    assert r.returncode != 0


def test_unknown_command_prints_usage_and_fails(clean_repo):
    r = run_record("frobnicate", clean_repo)
    assert r.returncode != 0


def test_usage_boots_under_uv():
    # The one real-uv launch proving the record entry point boots under uv.
    r = run_record(uv=True)
    assert r.returncode != 0
    assert "brief" in (r.stdout + r.stderr)


def test_brief_non_repo_root_prints_empty_list(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    r = run_record("brief", plain)
    assert r.returncode == 0
    assert json.loads(r.stdout) == []


def test_run_selftest_passes():
    # bench: solo 7.7s -> 4.8s, xdist ~28s -> 22.9s; git-heavy selftest (mk hoists tr/ch, scope copies one template)
    r = run_record("--selftest")
    assert r.returncode == 0
    assert "FAIL" not in r.stdout


# brief --------------------------------------------------------------------


def test_brief_shape_and_required_for_code_and_doc_change(make_repo):
    repo = make_demo(make_repo)
    b = cli_brief(repo, "demo-record")
    assert DOC <= set(b)
    assert b["repo"] == repo.name
    assert b["path"] == str(repo)
    assert len(b["tree"]) == 40 and len(b["head"]) == 40
    assert b["baseline"] is None
    assert Path(b["report"]).is_file()  # report.json was generated
    assert set(b["changed"]) >= {"README.md", "app.py"}
    assert set(b["required"]) == {"19", "20", "21", "verify"}
    assert b["previous_findings"] == {i: [] for i in ("19", "20", "21", "verify")}


def test_required_rules_unit(recmod):
    assert recmod.required({"README.md": "M"}) == ["19", "20", "21"]
    assert recmod.required({"app.py": "M"}) == ["21", "verify"]
    assert recmod.required({"notes.txt": "M"}) == ["21"]
    assert recmod.required({"app.py": "D"}) == ["19", "21", "verify"]
    assert recmod.required({}) == []


def test_brief_is_deterministic_for_same_tree(make_repo):
    repo = make_demo(make_repo)
    b1 = cli_brief(repo, "demo-record")
    b2 = cli_brief(repo, "demo-record")
    assert b1["tree"] == b2["tree"]
    assert json.dumps(b1["required"]) == json.dumps(b2["required"])


def test_brief_fails_without_report_json(make_repo):
    repo = make_demo(make_repo)
    r = run_record("brief", repo)  # no state-report run: report.json missing
    assert r.returncode != 0
    assert "brief failed" in r.stdout or "brief failed" in r.stderr


# tree / changed ------------------------------------------------------------


def test_tree_stable_across_commit_and_moves_with_content(recmod, make_repo):
    repo = make_repo(files={"app.py": "x = 1\n"})
    t1 = recmod.tree(repo)
    commit_all(repo)
    assert recmod.tree(repo) == t1
    (repo / "app.py").write_text("x = 2\n")
    assert recmod.tree(repo) != t1


def test_tree_retries_once_after_a_transient_git_failure(
    recmod, make_repo, monkeypatch
):
    """One failed git call (spawn storm) must not turn a fingerprintable repo into tree ''."""
    repo = make_repo(files={"app.py": "x = 1\n"})
    expected = recmod.tree(repo)
    real, state = recmod.git, {"failed": False}

    def flaky(repo_, *args, env=None, timeout=None):
        if args[:2] == ("add", "-A") and not state["failed"]:
            state["failed"] = True
            return None
        return real(repo_, *args, env=env, timeout=timeout)

    monkeypatch.setattr(recmod, "git", flaky)
    assert recmod.tree(repo) == expected
    assert state["failed"] is True


def test_changed_first_run_is_window_plus_porcelain(recmod, make_repo):
    repo = make_repo(files={"app.py": "x = 1\n"})
    commit_all(repo)
    (repo / "app.py").write_text("x = 2\n")
    (repo / "new.txt").write_text("new\n")
    ch = recmod.changed(repo, recmod.tree(repo))
    assert ch["app.py"] == "M"
    assert ch["new.txt"] == "A"


# valid writes ---------------------------------------------------------------


@pytest.mark.parametrize("idx", ["19", "20", "21", "verify"])
def test_valid_records_write_and_stamp(make_repo, tmp_path, idx):
    repo = make_demo(make_repo)
    b = cli_brief(repo, "demo-record")
    rec = build_record(repo, b, idx)
    r = write_cli(repo, rec, tmp_path, f"valid-{idx}")
    assert r.returncode == 0, r.stdout
    assert r.stdout.startswith("written ")
    stored = json.loads(Path(r.stdout.removeprefix("written ").strip()).read_text())
    assert stored["tree"] == b["tree"] and stored["head"] == b["head"]
    assert stored["checked_at"]
    if idx == "verify":
        assert stored["counts"] == {
            "finished": 1,
            "not_verified": 0,
            "skipped": 0,
            "left": 0,
        }


def test_check_all_ok_advances_baseline_and_reports_counts(make_repo, tmp_path, recmod):
    repo = make_demo(make_repo)
    b = cli_brief(repo, "demo-record")
    for idx in ("19", "20", "21", "verify"):
        r = write_cli(repo, build_record(repo, b, idx), tmp_path, f"ok-{idx}")
        assert r.returncode == 0, r.stdout
    r = run_record("check", repo)
    assert r.returncode == 0, r.stdout
    assert "pairs not ok: 0" in r.stdout
    assert "'finished': 1" in r.stdout or '"finished": 1' in r.stdout
    base = recmod.rec_dir(repo) / "baseline"
    assert base.read_text().strip() == b["tree"]
    # editing after baseline requires records against the new tree only
    (repo / "app.py").write_text("y = 2\n")
    r = run_record("check", repo)
    assert r.returncode == 1
    assert "missing" in r.stdout


def test_older_tree_pruned_after_advance(make_repo, tmp_path, recmod):
    # bench: solo 9.3s -> 7.3s, xdist 20.8s -> 21.7s; git-heavy brief/write/check flow (NO_GH, cached tools, threaded tr/ch)
    repo = make_demo(make_repo)
    b1 = cli_brief(repo, "demo-record")
    for idx in ("19", "20", "21", "verify"):
        assert (
            write_cli(
                repo, build_record(repo, b1, idx), tmp_path, f"p-{idx}"
            ).returncode
            == 0
        )
    assert run_record("check", repo).returncode == 0
    (repo / "app.py").write_text("y = 9\n")
    b2 = audit_brief(repo)
    assert b2["tree"] != b1["tree"]
    # only app.py changed since the baseline, so 19/20 drop out of required
    assert set(b2["required"]) == {"21", "verify"}
    for idx in ("21", "verify"):
        assert (
            write_cli(
                repo, build_record(repo, b2, idx), tmp_path, f"q-{idx}"
            ).returncode
            == 0
        )
    assert run_record("check", repo).returncode == 0
    recdir = recmod.rec_dir(repo)
    trees = sorted(p.name for p in recdir.iterdir() if p.is_dir())
    assert trees == [b2["tree"]]


# verdict and finding rules ----------------------------------------------------


def test_fixed_false_forces_fail(make_repo, tmp_path):
    repo = make_demo(make_repo)
    b = cli_brief(repo, "demo-record")
    rec = build_record(
        repo,
        b,
        "19",
        verdict="pass",
        findings=[
            {
                "path": "README.md",
                "claim": "c",
                "evidence": "README.md:1",
                "severity": "low",
                "fixed": False,
            }
        ],
    )
    r = write_cli(repo, rec, tmp_path, "forces-fail")
    assert r.returncode == 1
    assert "forces verdict fail" in r.stdout


def test_fail_without_open_finding_rejected(make_repo, tmp_path):
    repo = make_demo(make_repo)
    b = cli_brief(repo, "demo-record")
    rec = build_record(repo, b, "19", verdict="fail")
    r = write_cli(repo, rec, tmp_path, "fail-no-finding")
    assert r.returncode == 1
    assert "needs a fixed:false finding" in r.stdout


def test_missing_required_file_rejected(make_repo, tmp_path):
    repo = make_demo(make_repo)
    b = cli_brief(repo, "demo-record")
    rec = build_record(repo, b, "19")
    rec["files_read"] = []
    r = write_cli(repo, rec, tmp_path, "missing-file")
    assert r.returncode == 1
    assert "files_read" in r.stdout


def test_bad_line_token_rejected(make_repo, tmp_path):
    repo = make_demo(make_repo)
    b = cli_brief(repo, "demo-record")
    rec = build_record(repo, b, "19")
    rec["samples"][0]["evidence"] = "app.py:2"  # line 2 has no claim token
    r = write_cli(repo, rec, tmp_path, "bad-token")
    assert r.returncode == 1
    assert "does not contain" in r.stdout


def test_claim_ok_in_own_doc_rejected(make_repo, tmp_path):
    repo = make_demo(make_repo)
    b = cli_brief(repo, "demo-record")
    rec = build_record(repo, b, "19")
    claim = next(s for s in b["required"]["19"]["samples"] if s["kind"] == "claim")
    i = next(i for i, s in enumerate(rec["samples"]) if s["id"] == claim["id"])
    rec["samples"][i]["evidence"] = f"{claim['doc']}:{claim['line']}"
    r = write_cli(repo, rec, tmp_path, "own-doc")
    assert r.returncode == 1
    assert "outside its own doc" in r.stdout


def test_index_not_required_rejected(make_repo, tmp_path):
    repo = make_repo(files={"app.py": "x = 1\n"})
    commit_all(repo)
    (repo / "app.py").write_text("x = 2\n")
    run_state_report("--roots", repo, "--json")
    r = run_record("brief", repo)
    assert r.returncode == 0
    b = json.loads(r.stdout)[0]
    assert "19" not in b["required"]
    rec = {
        "index": "19",
        "repo": repo.name,
        "files_read": ["app.py"],
        "findings": [],
        "samples": [],
        "verdict": "pass",
    }
    r = write_cli(repo, rec, tmp_path, "not-required")
    assert r.returncode == 1
    assert "not required" in r.stdout


def test_verify_rerun_mismatch_rejected(make_repo, tmp_path):
    repo = make_demo(make_repo)
    b = cli_brief(repo, "demo-record")
    rec = build_record(repo, b, "verify")
    rec["evidence"][0]["exit"] = 3  # command really exits 0
    r = write_cli(repo, rec, tmp_path, "rerun")
    assert r.returncode == 1
    assert "re-run" in r.stdout


def test_verify_pass_with_unverified_work_rejected(make_repo, tmp_path):
    repo = make_demo(make_repo)
    b = cli_brief(repo, "demo-record")
    rec = build_record(repo, b, "verify")
    rec["evidence"] = []  # nothing evidenced
    r = write_cli(repo, rec, tmp_path, "unverified")
    assert r.returncode == 1
    assert "unverified work" in r.stdout


def test_unverifiable_needs_reason_and_pass_rejects_it(make_repo, tmp_path):
    repo = make_demo(make_repo)
    b = cli_brief(repo, "demo-record")
    rec = build_record(repo, b, "19")
    rec["samples"][0]["status"] = "unverifiable"
    rec["samples"][0].pop("reason", None)
    r = write_cli(repo, rec, tmp_path, "unver-noreason")
    assert r.returncode == 1
    assert "needs a reason" in r.stdout
    rec["samples"][0]["reason"] = "upstream file, cannot fetch"
    rec["verdict"] = "pass"
    r = write_cli(repo, rec, tmp_path, "unver-pass")
    assert r.returncode == 1


def test_missing_style_rule_quote_rejected(make_repo, tmp_path):
    repo = make_demo(make_repo)
    b = cli_brief(repo, "demo-record")
    rec = build_record(repo, b, "21")
    rec["rules"] = []
    r = write_cli(repo, rec, tmp_path, "no-rules")
    assert r.returncode == 1
    assert "rules" in r.stdout


# fixed:true lifecycle ----------------------------------------------------------


def test_fixed_true_lifecycle(make_repo, tmp_path):
    # bench: solo 7.7s -> 5.8s, xdist 17.6s -> 11.3s; git-heavy lifecycle (NO_GH, cached tools, threaded tr/ch)
    repo = make_demo(make_repo)
    b1 = cli_brief(repo, "demo-record")
    finding = {
        "path": "app.py",
        "claim": "style",
        "evidence": "app.py:1",
        "severity": "low",
        "fixed": False,
    }
    rec = build_record(repo, b1, "21", verdict="fail", findings=[finding])
    assert write_cli(repo, rec, tmp_path, "open").returncode == 0
    r = run_record("check", repo)
    assert r.returncode == 1
    assert "fail" in r.stdout
    # fixed:true on the same tree without a matching previous fixed:false is rejected
    rec2 = build_record(
        repo, b1, "21", findings=[{**finding, "fixed": True, "rechecked": True}]
    )
    assert write_cli(repo, rec2, tmp_path, "early-fix").returncode == 1
    # new tree, same path+claim carried with rechecked:true is accepted
    (repo / "app.py").write_text("y = 3\n")
    b2 = audit_brief(repo)
    rec3 = build_record(
        repo, b2, "21", findings=[{**finding, "fixed": True, "rechecked": True}]
    )
    assert write_cli(repo, rec3, tmp_path, "fixed").returncode == 0
    # same but for a claim the previous record never held is rejected
    rec4 = build_record(
        repo,
        b2,
        "21",
        findings=[{**finding, "claim": "other", "fixed": True, "rechecked": True}],
    )
    r = write_cli(repo, rec4, tmp_path, "fixed-other")
    assert r.returncode == 1
    assert "fixed:true" in r.stdout
    # dropping the previous fixed:false finding is rejected
    rec5 = build_record(repo, b2, "21")
    r = write_cli(repo, rec5, tmp_path, "dropped")
    assert r.returncode == 1
    assert "dropped" in r.stdout


def test_check_missing_state_lists_missing(make_repo):
    repo = make_demo(make_repo)
    run_state_report("--roots", repo, "--json")
    r = run_record("check", repo)
    assert r.returncode == 1
    assert "missing" in r.stdout
    assert "pairs not ok:" in r.stdout


def test_discover_repos_stops_at_repo_roots_and_skips_cache_dirs(recmod, tmp_path):
    root = tmp_path / "ws"
    for rel in (
        "a/.git",
        "a/vendored/.git",
        "b/c/.git",
        "node_modules/x/.git",
        ".venv/y/.git",
    ):
        (root / rel).mkdir(parents=True)
    got = sorted(
        p.relative_to(root.resolve()).as_posix() for p in recmod.discover_repos(root)
    )
    assert got == ["a", "b/c"]


def test_previous_ignores_records_of_an_older_index_scheme(recmod, tmp_path):
    repo = tmp_path / "r"
    (recmod.rec_dir(repo) / "oldtree").mkdir(parents=True)
    (recmod.rec_dir(repo) / "newtree").mkdir(parents=True)
    (recmod.rec_dir(repo) / "oldtree" / "20.json").write_text(
        json.dumps({"checked_at": "2026-01-01", "findings": [{"fixed": False}]})
    )
    (recmod.rec_dir(repo) / "newtree" / "20.json").write_text(
        json.dumps(
            {"scheme": recmod.SCHEME, "checked_at": "2026-02-01", "findings": []}
        )
    )
    assert recmod.previous(repo, "20", "current")["findings"] == []
    (recmod.rec_dir(repo) / "newtree" / "20.json").unlink()
    assert recmod.previous(repo, "20", "current") is None


def test_check_counts_a_record_of_an_older_scheme_as_missing(
    make_repo, tmp_path, recmod
):
    repo = make_demo(make_repo)
    b = cli_brief(repo, "demo-record")
    for idx in ("19", "20", "21", "verify"):
        r = write_cli(repo, build_record(repo, b, idx), tmp_path, f"ok-{idx}")
        assert r.returncode == 0, r.stdout
    f = recmod.rec_dir(repo) / b["tree"] / "19.json"
    f.write_text(json.dumps({**json.loads(f.read_text()), "scheme": recmod.SCHEME - 1}))
    r = run_record("check", repo)
    assert r.returncode == 1
    assert "19" in r.stdout and "missing" in r.stdout


def _claim_sample(repo, tmp_path):
    b = cli_brief(repo, "demo-record")
    rec = build_record(repo, b, "19")
    claim = next(s for s in b["required"]["19"]["samples"] if s["kind"] == "claim")
    return rec, next(i for i, s in enumerate(rec["samples"]) if s["id"] == claim["id"])


def test_claim_traced_to_a_code_line_is_accepted(make_repo, tmp_path):
    # #135: a composed name (f"{P}_{n}_{d}.ris") is on no line verbatim; the line building it counts.
    repo = make_demo(make_repo)
    rec, i = _claim_sample(repo, tmp_path)
    rec["samples"][i].update(
        status="traced", evidence="app.py:1", reason="app.py:1 builds the name"
    )
    r = write_cli(repo, rec, tmp_path, "traced")
    assert r.returncode == 0, r.stdout


def test_claim_traced_needs_a_reason_and_a_non_doc_line(make_repo, tmp_path):
    repo = make_demo(make_repo)
    rec, i = _claim_sample(repo, tmp_path)
    rec["samples"][i].update(status="traced", evidence="app.py:1")
    r = write_cli(repo, rec, tmp_path, "traced-no-reason")
    assert r.returncode == 1 and "traced needs" in r.stdout
    doc = next(p for p in rec["files_read"] if p.endswith(".md"))
    rec["samples"][i].update(evidence=f"{doc}:1", reason="the doc says so")
    r = write_cli(repo, rec, tmp_path, "traced-doc")
    assert r.returncode == 1 and "traced needs" in r.stdout


def test_powershell_parameter_matches_its_declaration(recmod):
    rc = recmod
    assert rc.token_in("-TempAgeDays", "\t[int]$TempAgeDays = 2,")
    assert rc.token_in("-IncludeDuplicates", "[switch]$includeduplicates")
    assert not rc.token_in("-Temp", "[int]$TempAgeDays = 2,")
    assert not rc.token_in("TempAgeDays-", "$TempAgeDays")


def test_verify_rerun_timeout_is_named_not_a_wrong_exit(
    make_repo, tmp_path, monkeypatch
):
    # #135 review: a 2-minute suite died at the 30 s spawn cap and read as "exit differs".
    repo = make_demo(make_repo)
    b = cli_brief(repo, "demo-record")
    rec = build_record(repo, b, "verify")
    rec["evidence"][0]["cmd"] = (
        f'"{sys.executable}" -c "import threading; threading.Event().wait(5)"'
    )
    monkeypatch.setenv("WORK_AUDIT_TEST_TIMEOUT", "1")
    r = write_cli(repo, rec, tmp_path, "rerun-timeout")
    assert r.returncode == 1
    assert "timed out" in r.stdout and "exit differs" not in r.stdout
