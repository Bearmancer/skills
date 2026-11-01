"""#281: engine behaviour the goldens do not pin on their own.

Sizes round half-to-even like .NET, the protected list refuses what it names, accepted rows print
largest first, long and non-ASCII paths are deleted, and a dead lock owner does not block a run.
"""

import json
import os
import subprocess
import sys
from datetime import timezone

import pytest

import scenarios as sc

purge = sc.load("purge_engine", sc.ENGINE_PY)


@pytest.mark.parametrize(("size", "text"), [
    (0, "0 B"), (1023, "1023 B"), (1024, "1 KB"), (2560, "2 KB"), (3584, "4 KB"),
    (1048576, "1.0 MB"), (1572864, "1.5 MB"), (1073741824, "1.00 GB"), (1084479242, "1.01 GB"),
])
def test_sizes_round_half_to_even_like_dotnet(size, text):
    assert purge.format_size(size) == text


@pytest.mark.parametrize("path", [
    r"C:\Users\u\.omo\memory", r"C:\Users\u\.omo\memory\x.md", r"C:\Users\u\.OMO\Agent\Sessions\s",
    r"C:\Users\u\.omo\binary-runtime", r"C:\Users\u\.omo\omo.jsonc", r"C:\Users\u\.claude\settings.json",
    r"C:\Users\u\.claude\plans\p.md", r"C:\Users\u\.claude.json", r"C:\Users\u\.ssh\id", r"C:\Users\u\.config",
    r"C:\Users\u\Documents\a", r"C:\Users\u\OneDrive - Work\b", r"C:\Users\u\AppData\Roaming\Code - Insiders",
    r"C:\Users\u\AppData\Local\Google\Chrome", r"C:\Users\u\wizards\w",
])
def test_protected_list_names_these(path):
    assert purge.Engine.protected(path)


@pytest.mark.parametrize("path", [
    r"C:\Users\u\.omo\logs", r"C:\Users\u\.omo\omo.jsonc.bak", r"C:\Users\u\.omo\evidence\e.md",
    r"C:\Users\u\.claude\file-history", r"C:\Users\u\Dev\repo\node_modules", r"C:\Users\u\.configs",
])
def test_protected_list_leaves_these(path):
    assert purge.Engine.protected(path) is None


def test_manifest_stamp_parses_dotnet_and_python_forms():
    a = purge.parse_iso("2026-01-01T00:00:00.1234567+00:00")
    b = purge.parse_iso("2026-01-01T11:00:00.123456+11:00")
    assert a.tzinfo == timezone.utc and abs((a - b).total_seconds()) < 1e-3
    assert purge.parse_iso("not a date") is None and purge.parse_iso(None) is None


def run(args, home, cwd):
    env = {**os.environ, **sc.env_for(home)}
    return subprocess.run([sys.executable, str(sc.ENGINE_PY), *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", env=env, cwd=cwd, timeout=120)


def test_plan_lists_largest_first(tmp_path):
    r = tmp_path / "r"
    sc.write(r / "small/a", "1")
    for i in range(3):
        sc.write(r / f"big/f{i}", "1")
    sc.write(r / "mid/a", "1")
    sc.write(r / "mid/b", "1")
    m = sc.manifest(tmp_path / "m.json", [sc.row(r, "small"), sc.row(r, "big"), sc.row(r, "mid")], r)
    proc = run(["--root", r, "--manifest", m, "--lock-file", tmp_path / "p.lock"], sc.empty_home(tmp_path), tmp_path)
    order = [line.rsplit("\\", 1)[1] for line in proc.stdout.splitlines() if line.startswith("PURGE")]
    assert (proc.returncode, order) == (0, ["big", "mid", "small"])


def test_long_and_non_ascii_paths_are_deleted(tmp_path):
    r = tmp_path / "r"
    deep = r / "x" / ("a" * 120) / ("b" * 120)
    sc.write(deep / "f.bak", "long")
    sc.write(r / "naïve-日本.bak", "uni")
    rows = [sc.row(r, "x"), sc.row(r, "naïve-日本.bak")]
    m = sc.manifest(tmp_path / "m.json", rows, r)
    proc = run(["--root", r, "--manifest", m, "--apply", "--out-dir", tmp_path / "out", "--lock-file", tmp_path / "p.lock"],
               sc.empty_home(tmp_path), tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not os.path.lexists(sc.lp(r / "x")) and not (r / "naïve-日本.bak").exists()
    journal = next((tmp_path / "out").glob("*.jsonl")).read_text(encoding="utf-8")
    assert "naïve-日本.bak" in journal


def test_dead_lock_owner_is_reclaimed_and_released(tmp_path):
    r = tmp_path / "r"
    sc.write(r / "a.bak", "x")
    lock = sc.write(tmp_path / "p.lock", json.dumps({"pid": 4294967, "started": "yesterday"}))
    m = sc.manifest(tmp_path / "m.json", [sc.row(r, "a.bak")], r)
    proc = run(["--root", r, "--manifest", m, "--apply", "--out-dir", tmp_path / "out", "--lock-file", lock],
               sc.empty_home(tmp_path), tmp_path)
    assert proc.returncode == 0 and not lock.exists() and not (r / "a.bak").exists()


def test_live_pid_check():
    assert purge.pid_alive(os.getpid())
    assert not purge.pid_alive(4294967)


def test_override_accepts_several_paths(tmp_path):
    r = tmp_path / "r"
    sc.write(r / "a.bak", "x")
    sc.write(r / "b.bak", "x")
    m = sc.manifest(tmp_path / "m.json", [sc.row(r, "a.bak", "OWNER"), sc.row(r, "b.bak", "OWNER")], r)
    proc = run(["--root", r, "--manifest", m, "--override", r / "a.bak", r / "b.bak", "--lock-file", tmp_path / "p.lock"],
               sc.empty_home(tmp_path), tmp_path)
    assert proc.returncode == 0 and "refused=0" in proc.stdout


def test_usage_errors_exit_1_not_2(tmp_path):
    proc = run(["--no-such-flag"], sc.empty_home(tmp_path), tmp_path)
    assert proc.returncode == 1 and proc.stderr.startswith("purge: ")
