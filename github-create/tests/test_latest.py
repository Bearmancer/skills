import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("preflight", Path(__file__).parents[1] / "scripts" / "preflight.py")
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)

CURRENT = {
    ("gh", "--version"): "gh version 2.102.0 (2026-09-30)",
    ("gh", "api"): "v2.102.0",
    ("codegraph", "--version"): "1.6.2",
    ("npm", "view"): "1.6.2",
}


def fake(overrides=()):
    table = {**CURRENT, **dict(overrides)}
    return lambda argv, cwd=None: table[(argv[0], argv[1])]


def test_current_is_clean():
    assert pf.stale(fake()) == []


def test_old_gh_is_stale():
    assert any(p.startswith("gh:") for p in pf.stale(fake({("gh", "api"): "v2.103.0"}.items())))


def test_old_codegraph_is_stale():
    assert any(p.startswith("codegraph:") for p in pf.stale(fake({("npm", "view"): "1.7.0"}.items())))


def test_unanswerable_gh_probe_fails_closed():
    assert any(p.startswith("gh:") for p in pf.stale(fake({("gh", "api"): None}.items())))


def test_latest_refuses_with_exit_3(monkeypatch, capsys):
    monkeypatch.setattr(pf, "stale", lambda: ["gh: installed None vs latest None"])
    with pytest.raises(SystemExit) as e:
        pf.latest()
    assert e.value.code == 3
    assert "STALE: gh" in capsys.readouterr().err


def test_stale_names_repair_per_component():
    got = " ".join(pf.stale(fake({("gh", "api"): "v2.103.0", ("npm", "view"): "1.7.0"}.items())))
    assert "winget upgrade GitHub.cli" in got
    assert "npm i -g @colbymchenry/codegraph@latest" in got


def test_vtuple_compares_numerically():
    assert pf.vtuple("v2.9.0") < pf.vtuple("2.10.0")


def test_log_tail_keeps_the_failure_end_and_strips_prefixes():
    noise = "\n".join(f"build\tSet up job\t2026-10-20T10:00:00.000Z noise line {i} " + "x" * 80 for i in range(30))
    tail = noise + "\nbuild\ttest\t2026-10-20T10:01:00.000Z \x1b[31mAssertionError: boom\x1b[0m\nbuild\ttest\t2026-10-20T10:01:01.000Z Process completed with exit code 1."
    got = pf.log_tail(lambda argv, cwd=None: tail, "o/r", 1)
    assert got.endswith("Process completed with exit code 1.") and "AssertionError: boom" in got
    assert len(got) <= 900 and "\x1b" not in got and "2026-10-20T" not in got


def test_log_tail_ignores_timestamp_only_lines():
    blank = "\n".join("build\ttest\t2026-10-20T10:00:00.000Z " for _ in range(10))
    out = "build\ttest\t2026-10-20T10:00:00.000Z real failure\n" + blank + "\nbuild\ttest\t2026-10-20T10:00:01.000Z Process completed with exit code 1."
    assert pf.log_tail(lambda argv, cwd=None: out, "o/r", 1) == "real failure / Process completed with exit code 1."
