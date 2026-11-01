"""Tests for scripts/test-audit.py: each check fires on a fixture smell and stays quiet on clean code.

Fixture sources carry `# test-audit: accept` trailing markers (outside the
string) so a self-run skips them; the runtime fixture text stays clean so the
finding still fires. The one wait-call fixture is built with a replace trick
because the rigor no-wait scan forbids the literal.
"""

from pathlib import Path

from conftest import fresh_script_module

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
TEST_AUDIT = SCRIPTS / "test-audit.py"


def load_audit():
    return fresh_script_module(TEST_AUDIT)


def write_tmp_files(tmp_path, files):
    root = tmp_path / "audit-fixture"
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def audit_source(mod, tmp_path, files, **kw):
    root = write_tmp_files(tmp_path, files)
    return mod.audit_repo(root, **kw)


SMELL_T1 = (
    "from conftest import make_repo, run_state_report\n"  # test-audit: accept fixture target
    "def test_heavy(make_repo):\n"  # test-audit: accept fixture target
    '    repo = make_repo(files={"a.py": "x = 1\\n"})\n'  # test-audit: accept fixture target
    '    r = run_state_report("--roots", repo, "--json")\n'  # test-audit: accept fixture target
    "    assert r.returncode == 0\n"  # test-audit: accept fixture target
)
CLEAN_T1 = 'def test_light(clean_repo):\n    assert (clean_repo / "app.py").is_file()\n'


def test_t1_flags_per_test_build_and_audit(tmp_path):
    mod = load_audit()
    findings, _by, _notes = audit_source(mod, tmp_path, {"tests/test_h.py": SMELL_T1})
    assert any(f["check"] == "T1" and "template" in f["claim"] for f in findings)
    findings, _by, _notes = audit_source(mod, tmp_path, {"tests/test_h.py": CLEAN_T1})
    assert [f for f in findings if f["check"] == "T1"] == []


SMELL_T2 = (
    "import subprocess\n"  # test-audit: accept fixture target
    "def test_probe():\n"  # test-audit: accept fixture target
    '    r = subprocess.run(["gh", "api", "user"], capture_output=True, timeout=30)\n'  # test-audit: accept fixture target
    "    assert r.returncode == 0\n"  # test-audit: accept fixture target
)
CLEAN_T2 = (
    "import subprocess\n"
    "def test_mocked(monkeypatch):\n"
    '    monkeypatch.setenv("WORK_AUDIT_NO_GH", "1")\n'
    '    r = subprocess.run(["gh", "api", "user"], capture_output=True, timeout=30)\n'  # test-audit: accept fixture target, body is mocked
    "    assert r.returncode == 0\n"
)


def test_t2_flags_unmocked_probe(tmp_path):
    mod = load_audit()
    findings, _by, _notes = audit_source(mod, tmp_path, {"tests/test_h.py": SMELL_T2})
    assert any(f["check"] == "T2" for f in findings)
    findings, _by, _notes = audit_source(mod, tmp_path, {"tests/test_h.py": CLEAN_T2})
    assert [f for f in findings if f["check"] == "T2"] == []


def test_t2_ignores_message_constants(tmp_path):
    mod = load_audit()
    src = (
        'GH_MSG = "error: not logged in to github.com; run gh auth login"\n'  # test-audit: accept fixture target
        "def test_x():\n    assert GH_MSG\n"
    )
    findings, _by, _notes = audit_source(mod, tmp_path, {"tests/test_h.py": src})
    assert [f for f in findings if f["check"] == "T2"] == []


def test_t3_flags_wait_call_and_honors_accept(tmp_path):
    mod = load_audit()
    smell = "import time\ndef test_w():\n" + "    time.WAIT(0.1)\n".replace(
        "WAIT", "sleep"
    )
    findings, _by, _notes = audit_source(mod, tmp_path, {"tests/test_h.py": smell})
    assert any(f["check"] == "T3" for f in findings)
    marked = smell.replace("0.1)", "0.1)  # test-audit: accept bound verified")
    findings, _by, _notes = audit_source(mod, tmp_path, {"tests/test_h.py": marked})
    assert [f for f in findings if f["check"] == "T3"] == []


def test_t4_flags_duplicated_helper(tmp_path):
    mod = load_audit()
    helper = 'def build_thing(repo, x):\n    return {"a": x}\n'
    files = {
        "tests/test_a.py": helper + "def test_a():\n    assert build_thing(None, 1)\n",
        "tests/test_b.py": helper + "def test_b():\n    assert build_thing(None, 2)\n",
    }
    findings, _by, _notes = audit_source(mod, tmp_path, files)
    assert any(f["check"] == "T4" and "build_thing" in f["claim"] for f in findings)


JUNIT = (
    '<testsuite><testcase classname="test_m" name="test_slow_x" time="9.0"/>'
    '<testcase classname="test_m" name="test_fast_x" time="0.1"/></testsuite>'
)


def test_t5_flags_slow_test_without_bench_note(tmp_path):
    mod = load_audit()
    src = "def test_slow_x():\n    assert slow()\n"
    noted = "def test_slow_x():\n    # bench: 9.0s dominated by git spawns\n    assert slow()\n"
    xml = tmp_path / "r.xml"
    xml.write_text(JUNIT, encoding="utf-8")
    kw = {"junitxml": str(xml), "slow_over": 5.0}
    root = write_tmp_files(tmp_path, {"tests/test_m.py": src})
    findings, _by, _notes = mod.audit_repo(root, **kw)
    assert any(f["check"] == "T5" and "test_slow_x" in f["claim"] for f in findings)
    root = write_tmp_files(tmp_path, {"tests/test_m.py": noted})
    findings, _by, _notes = mod.audit_repo(root, **kw)
    assert [f for f in findings if f["check"] == "T5"] == []


def test_t6_flags_weak_and_missing_asserts(tmp_path):
    mod = load_audit()
    weak = (
        "def test_weak():\n"  # test-audit: accept fixture target
        "    assert value or OK\n".replace(
            "OK", "True"
        )  # test-audit: accept fixture target
    )
    bare = "def test_bare():\n    run_something()\n"
    findings, _by, _notes = audit_source(
        mod, tmp_path, {"tests/test_h.py": weak + bare}
    )
    assert any(f["check"] == "T6" and "weak" in f["claim"] for f in findings)
    assert any(f["check"] == "T6" and "no assert" in f["claim"] for f in findings)


def test_t7_count_agreement_and_drift(tmp_path):
    mod = load_audit()
    src = (
        "def test_a():\n    pass\n"
        "def test_b():\n    pass\n"
        "import pytest\n"
        '@pytest.mark.parametrize("n", ["a", "b", "c"])\n'
        "def test_c(n):\n    pass\n"
    )
    assert mod.predict_file(src) == 5
    named = "CASES = ['a', 'b']\nimport pytest\n@pytest.mark.parametrize('n', CASES)\ndef test_c(n):\n    pass\n"
    assert mod.predict_file(named) == 2  # module-level list resolves by name
    findings, _by, _notes = audit_source(
        mod, tmp_path, {"tests/test_h.py": src}, collected=5
    )
    assert [f for f in findings if f["check"] == "T7"] == []
    findings, _by, _notes = audit_source(
        mod, tmp_path, {"tests/test_h.py": src}, collected=6
    )
    assert any(f["check"] == "T7" for f in findings)


def test_t8_flags_shared_state(tmp_path):
    mod = load_audit()
    smell = (
        "X = []\n"  # test-audit: accept fixture target
        "def test_state():\n"  # test-audit: accept fixture target
        "    global X\n"  # test-audit: accept fixture target
        "    X.append(1)\n"  # test-audit: accept fixture target
    )
    findings, _by, _notes = audit_source(mod, tmp_path, {"tests/test_h.py": smell})
    assert any(f["check"] == "T8" and "global" in f["claim"] for f in findings)


def test_main_exit_codes(tmp_path):
    mod = load_audit()
    clean = write_tmp_files(tmp_path, {"tests/test_c.py": CLEAN_T1})
    assert mod.main([str(clean)]) == 0
    smell = write_tmp_files(tmp_path, {"tests/test_h.py": SMELL_T1})
    assert mod.main([str(smell)]) == 1
