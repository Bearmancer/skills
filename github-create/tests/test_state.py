import importlib.util
import json
import threading
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "preflight", Path(__file__).parents[1] / "scripts" / "preflight.py"
)
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)


def test_sh_default_timeout_is_short():
    assert pf.sh.__defaults__ == (None, 60)


def test_learn_concurrent_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_CREATE_STATE_DIR", str(tmp_path))
    threads = [
        threading.Thread(target=pf.learn, args=("o/r", f"note {i} -> x"))
        for i in range(2)
    ]
    [t.start() for t in threads]
    [t.join() for t in threads]
    text = pf.doc_path("o/r").read_text()
    assert "note 0" in text and "note 1" in text and text.count("## Learnings") == 1
    assert not pf.doc_path("o/r").with_name("o__r.md.lock").exists()


def test_concurrent_from_pr_records_each_check_once(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_CREATE_STATE_DIR", str(tmp_path))
    checks = json.dumps(
        [
            {
                "name": "t",
                "workflow": "CI",
                "state": "FAILURE",
                "bucket": "fail",
                "link": "",
            }
        ]
    )
    run = lambda argv, cwd=None: checks if argv[:3] == ["gh", "pr", "checks"] else ""  # noqa: E731
    threads = [
        threading.Thread(target=pf.learn, args=("o/r",), kwargs={"pr": 7, "run": run})
        for _ in range(4)
    ]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert pf.doc_path("o/r").read_text().count("CI failed: CI/t") == 1


def test_lock_removed_only_by_its_owner(tmp_path):
    path = tmp_path / "d.md"
    lock = tmp_path / "d.md.lock"
    with pf.locked(path):
        lock.write_text("someone else")
    assert lock.exists()


def test_held_lock_times_out_with_refusal(tmp_path):
    path = tmp_path / "d.md"
    (tmp_path / "d.md.lock").write_text("x")
    with pytest.raises(SystemExit) as e:
        with pf.locked(path, wait=0.1):
            pass
    assert e.value.code == 3


def test_learn_makes_no_external_call(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_CREATE_STATE_DIR", str(tmp_path))
    calls = []
    pf.learn("o/r", "a -> b", run=lambda argv, cwd=None: calls.append(argv))
    assert calls == []


def test_stale_lock_is_taken_over(tmp_path):
    import os

    path = tmp_path / "d.md"
    lock = tmp_path / "d.md.lock"
    lock.write_text("dead writer")
    old = lock.stat().st_mtime - 3600
    os.utime(lock, (old, old))
    with pf.locked(path, wait=1, stale_after=60):
        assert lock.read_text() != "dead writer"
    assert not lock.exists() and not list(tmp_path.glob("*.stale"))


def test_fresh_lock_is_not_taken_over(tmp_path):
    path = tmp_path / "d.md"
    lock = tmp_path / "d.md.lock"
    lock.write_text("live writer")
    with pytest.raises(SystemExit):
        with pf.locked(path, wait=0.1, stale_after=60):
            pass
    assert lock.read_text() == "live writer"
