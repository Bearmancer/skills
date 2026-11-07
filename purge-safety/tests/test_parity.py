r"""#281: the Python engine and adapter reproduce the PowerShell engine's recorded behaviour.

Every golden in `goldens/` was captured from `Purge.ps1` / `From-WorkAuditReport.ps1` (removed
after this parity was shown; the capture script went with them, see #281): exit code, stdout, stderr, the manifest or journal written, and the tree
left behind. Each test rebuilds the same scenario under its own temp dir, runs the Python port and
compares the normalized record.

One difference is deliberate (`scan-long-path`): the PowerShell walk dropped every candidate whose
directory path passes 240 characters, because it listed them through a `\\?\` prefix that its
containment check then refused. The Python walk finds them; that test asserts the difference.
"""

import json

import pytest

import scenarios as sc

DELIBERATE = {"scan-long-path"}


def golden(name):
    return json.loads(sc.golden_path(name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(set(sc.ENGINE_SCENARIOS) - DELIBERATE))
def test_engine_matches_golden(name, tmp_path):
    actual = sc.normalize(sc.run("engine", tmp_path, sc.ENGINE_SCENARIOS[name]))
    assert actual == golden(name)


@pytest.mark.parametrize("name", sorted(sc.ADAPTER_SCENARIOS))
def test_adapter_matches_golden(name, tmp_path):
    actual = sc.normalize(sc.run("adapter", tmp_path, sc.ADAPTER_SCENARIOS[name]))
    assert actual == golden(name)


def test_long_path_candidates_are_found_where_powershell_missed_them(tmp_path):
    expected = golden("scan-long-path")
    assert expected["code"] == 0 and expected["outputs"][0]["doc"]["entries"] == []
    actual = sc.normalize(
        sc.run("engine", tmp_path, sc.ENGINE_SCENARIOS["scan-long-path"])
    )
    entries = actual["outputs"][0]["doc"]["entries"]
    assert actual["code"] == 0
    assert [(e["category"], e["path"].endswith("\\deep.bak")) for e in entries] == [
        ("backup", True)
    ]
