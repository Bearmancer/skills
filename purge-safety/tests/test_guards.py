"""#281: the probe harness (`purge-guards.py`) proves the engine and catches the negative control.

The engine must come back with 17 PASS and exit 0; the lax fixture, which speaks the manifest
contract and skips every guard, must come back with the FAILs a harness that works produces. Each
run drives real deletions, but only inside its own fabricated workspace.
"""

import json
import os
import subprocess
import sys

import scenarios as sc

HARNESS = sc.SCRIPTS / "purge-guards.py"
LAX = sc.SCRIPTS / "fixtures" / "lax-purge.py"
PROBES = [
    "contract-declared", "script-parses", "plan-refuses-traps", "plan-deletes-nothing", "apply-clean-exit",
    "protected-survives", "protected-refused", "keep-survives", "junction-unlinked", "cascade-pruned",
    "read-only-removed", "journal-write-ahead", "residue-zero", "junction-ancestor-refused",
    "missing-verdict-refused", "budget-aborts", "live-lock-refuses",
]


def harness(tmp_path, script, *extra):
    home = sc.empty_home(tmp_path)
    env = {**os.environ, **sc.env_for(home)}
    proc = subprocess.run([sys.executable, str(HARNESS), "--script", str(script), "--workspace", str(tmp_path / "ws"), "--json", *extra],
                          capture_output=True, text=True, encoding="utf-8", timeout=600, env=env)
    states = {r["invariant"]: r["state"] for r in json.loads(proc.stdout)} if proc.stdout.strip() else {}
    return proc.returncode, states, proc.stderr


def test_engine_passes_every_probe(tmp_path):
    code, states, err = harness(tmp_path, sc.ENGINE_PY, "--apply-probes")
    assert (code, err) == (0, "")
    assert states == dict.fromkeys(PROBES, "PASS")


def test_negative_control_fails(tmp_path):
    code, states, _ = harness(tmp_path, LAX, "--apply-probes")
    assert code == 2
    fails = {k for k, v in states.items() if v == "FAIL"}
    assert {"plan-refuses-traps", "protected-refused", "journal-write-ahead", "junction-ancestor-refused",
            "missing-verdict-refused"} <= fails
    assert states["budget-aborts"] == states["live-lock-refuses"] == "UNSUPPORTED"


def test_plan_probes_only_without_apply_probes(tmp_path):
    code, states, _ = harness(tmp_path, sc.ENGINE_PY)
    assert code == 0
    assert states == {"contract-declared": "PASS", "script-parses": "PASS", "plan-refuses-traps": "PASS",
                      "plan-deletes-nothing": "PASS", "apply-probes": "UNSUPPORTED"}


def test_script_without_contract_is_never_run(tmp_path):
    script = sc.write(tmp_path / "rogue.py", "import shutil, os\nshutil.rmtree(os.path.expanduser('~/nothing-here'))\n")
    code, states, _ = harness(tmp_path, script, "--apply-probes")
    assert code == 2
    assert states == {"contract-declared": "FAIL", "plan-refuses-traps": "UNSUPPORTED", "apply-probes": "UNSUPPORTED"}


def test_script_that_does_not_parse_is_never_run(tmp_path):
    script = sc.write(tmp_path / "broken.py", "# --root --manifest\ndef (:\n")
    code, states, _ = harness(tmp_path, script, "--apply-probes")
    assert code == 2
    assert states == {"contract-declared": "PASS", "script-parses": "FAIL"}


def test_unknown_interpreter_is_refused(tmp_path):
    script = sc.write(tmp_path / "purge.sh", "rm -rf --root --manifest\n")
    code, states, err = harness(tmp_path, script)
    assert code == 1 and states == {} and "drive it by hand" in err
