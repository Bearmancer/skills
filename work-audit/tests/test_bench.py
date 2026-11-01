"""Tests for scripts/bench.py.

The fixture suite mirrors a real suite: a root with conftest.py and a tests/
subfolder holding a slow test, fast tests and a parametrized test. It uses a
busy loop, never a wait call, so the rigor no-wait audit stays green.
"""

import re
import sys
from pathlib import Path

from conftest import fresh_script_module

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
BENCH = SCRIPTS / "bench.py"

SLOW_BODY = (
    "import time\n"
    "def test_slow_deliberate():\n"
    "    end = time.perf_counter() + 1.2\n"
    "    while time.perf_counter() < end:\n"
    "        pass\n"
    "def test_slow_file_fast():\n"
    "    assert 1 + 1 == 2\n"
)
FAST_BODY = (
    "import pytest\n"
    "def test_fast_one():\n"
    "    assert True\n"
    "def test_fast_two():\n"
    "    assert [1, 2] == [1, 2]\n"
    '@pytest.mark.parametrize("n", ["p1", "p2", "p3"])\n'
    "def test_fast_param(n):\n"
    '    assert n.startswith("p")\n'
)

# A --collect-only -qq sample: per-file counts plus the summary line, no node ids.
QQ_SAMPLE = "tests/test_a.py: 2\ntests/test_b.py: 5\n7 tests collected in 0.10s\n"


def load_bench():
    return fresh_script_module(BENCH)


def make_fixture_suite(tmp_path):
    suite = tmp_path / "bench-fixture"
    (suite / "tests").mkdir(parents=True)
    (suite / "conftest.py").write_text("# fixture suite root\n", encoding="utf-8")
    (suite / "tests" / "test_slow.py").write_text(SLOW_BODY, encoding="utf-8")
    (suite / "tests" / "test_fast.py").write_text(FAST_BODY, encoding="utf-8")
    return suite


def _snapshot():
    # Full identity map: inner runs can OVERWRITE keys (fixture conftest.py
    # lands as top-level "conftest"), so a key diff alone never suffices.
    return dict(sys.modules), list(sys.path)


def _restore(snap):
    mods, path = snap
    for m in set(sys.modules) - set(mods):
        sys.modules.pop(m, None)
    for m, mod in mods.items():
        if sys.modules.get(m) is not mod:
            sys.modules[m] = mod
    sys.path[:] = path


def run_fixture(suite, xml):
    import pytest

    snap = _snapshot()
    try:
        rc = pytest.main(
            [
                str(suite),
                "-q",
                "-p",
                "no:cacheprovider",
                "--no-header",
                "--import-mode=importlib",
                f"--junitxml={xml}",
            ]
        )
    finally:
        _restore(snap)
    assert rc == 0


def collect_fixture(suite):
    import pytest

    snap = _snapshot()
    try:
        rc = pytest.main(
            [
                str(suite),
                "--collect-only",
                "-q",
                "-p",
                "no:cacheprovider",
                "--no-header",
                "--import-mode=importlib",
            ]
        )
    finally:
        _restore(snap)
    assert rc == 0


def test_bench_ranks_known_slow_test_first(tmp_path):
    bench = load_bench()
    suite = make_fixture_suite(tmp_path)
    xml = tmp_path / "bench.xml"
    run_fixture(suite, xml)
    per_file, tests, total = bench.parse_junit(str(xml))
    assert total > 1.0  # the busy loop dominates the fixture suite
    ranked = sorted(tests, reverse=True)
    assert ranked[0][1] == "test_slow.py"
    assert ranked[0][2] == "test_slow_deliberate"
    ranked_files = sorted(per_file.items(), key=lambda kv: -kv[1][1])
    assert ranked_files[0][0] == "test_slow.py"


def test_bench_nodeid_mapping_and_cause(tmp_path, monkeypatch, capsys):
    bench = load_bench()
    suite = make_fixture_suite(tmp_path)
    xml = tmp_path / "bench.xml"
    run_fixture(suite, xml)
    _, tests, _ = bench.parse_junit(str(xml))
    slow = next(t for t in tests if t[2] == "test_slow_deliberate")
    collect_fixture(suite)
    out = capsys.readouterr().out
    count, table = bench.parse_collect_output(out)
    assert count == 7  # 2 + 2 + 3 parametrized cases
    nid = bench.resolve_nodeid(table, slow[3], slow[1], slow[2], suite)
    assert nid is not None and "test_slow_deliberate" in nid
    cause = bench.classify(wall=slow[0], sub=0.0, git_calls=0, uv_spawns=0)
    assert isinstance(cause, str) and len(cause) > 10
    monkeypatch.chdir(suite)
    bench.spy_one(nid)
    out = capsys.readouterr().out
    assert re.search(r"^SPY .*test_slow_deliberate.*wall=\d", out, re.M)


def test_inner_runs_do_not_pollute_conftest(tmp_path):
    import conftest as real

    suite = make_fixture_suite(tmp_path)
    run_fixture(suite, tmp_path / "bench.xml")
    collect_fixture(suite)
    import conftest as after

    assert after is real  # inner runs must evict the fixture conftest
    assert hasattr(after, "run_stop_guard")


def test_bench_collect_count_and_table(tmp_path, capsys):
    bench = load_bench()
    suite = make_fixture_suite(tmp_path)
    collect_fixture(suite)
    out = capsys.readouterr().out
    count, table = bench.parse_collect_output(out)
    assert count == 7
    assert len(table) == 7
    assert any(n.endswith("[p1]") for (_, n) in table)


def test_bench_collect_qq_summary_count():
    bench = load_bench()
    count, table = bench.parse_collect_output(QQ_SAMPLE)
    assert count == 7  # the summary line is the count when -qq hides node ids
    assert table == {}


def test_bench_nodeid_from_file_attr_and_bare_classname(tmp_path):
    bench = load_bench()
    suite = tmp_path / "suite"
    (suite / "tests").mkdir(parents=True)
    (suite / "tests" / "test_master.py").write_text(
        "def test_x():\n    pass\n", encoding="utf-8"
    )
    via_file = bench.resolve_nodeid(
        {}, "tests/test_master.py", "test_master.py", "test_x", suite
    )
    assert via_file == "tests/test_master.py::test_x"
    bare = bench.resolve_nodeid({}, "", "test_master", "test_x", suite)
    assert bare == "tests/test_master.py::test_x"  # folder found by existence check
    missing = bench.resolve_nodeid({}, "", "test_ghost", "test_x", suite)
    assert missing is None


def test_bench_uv_base_includes_xdist():
    bench = load_bench()
    base = bench.uv_base([])
    assert "--with" in base and "pytest-xdist" in base  # -n needs the plugin in the env


def test_bench_failed_run_reported_not_timed(capsys):
    bench = load_bench()
    ok = bench.format_run_result(
        "xdist -n 8", 0.5, 4, "", "ERROR: unrecognized arguments: -n\n"
    )
    assert ok is False
    out = capsys.readouterr().out
    assert "FAILED" in out and "exit 4" in out
    assert "unrecognized arguments" in out
    assert "0.5s" not in out.split("FAILED")[0]  # a failed run is never a timing


def test_bench_help_text_for_every_option(capsys):
    import argparse

    bench = load_bench()
    ap = argparse.ArgumentParser()
    bench.add_options(ap)
    for action in ap._actions:
        if action.dest == "help":
            continue
        assert action.help, f"--{action.dest} has no help text"
    spy = next(a for a in ap._actions if a.dest == "spy")
    assert "internal" in spy.help.lower()
