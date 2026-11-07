"""references/indices.md groups the 21 indices under the display phases state-report.py prints."""

import re
from pathlib import Path

from conftest import STATE_REPORT, fresh_script_module, clean_repo, shared_run  # noqa: F401

INDICES_MD = Path(__file__).resolve().parent.parent / "references" / "indices.md"


def doc_phases():
    text = INDICES_MD.read_text(encoding="utf-8")
    section = text.split("\n## The 21 indices", 1)[1].split("\n## ", 1)[0]
    phases = []
    for line in section.splitlines():
        if line.startswith("### "):
            phases.append((line[4:], []))
        elif m := re.match(r"(\d+)\. (.+?)(?:  `\[.*\]`)?$", line):
            phases[-1][1].append((int(m[1]), m[2]))
    return phases


def test_doc_groups_match_the_script_phases_and_names():
    mod = fresh_script_module(STATE_REPORT)
    names = dict(enumerate((n for n, _ in mod.INDICES), 1))
    assert [(title, [i for i, _ in items]) for title, items in doc_phases()] == [
        (title, list(members)) for title, members in mod.PHASES
    ]
    for _, items in doc_phases():
        for i, name in items:
            assert name == names[i], i


def test_phases_partition_the_21_indices_into_six():
    mod = fresh_script_module(STATE_REPORT)
    assert len(mod.PHASES) == 6
    assert sorted(i for _, m in mod.PHASES for i in m) == list(range(1, 22))


def test_report_prints_each_index_under_its_phase_heading(clean_repo):
    mod = fresh_script_module(STATE_REPORT)
    lines = shared_run("clean", "--brief").stdout.splitlines()
    expected = []
    for title, members in mod.PHASES:
        expected.append(f"== {title} ==")
        expected += [
            f"{i}. {dict(enumerate((n for n, _ in mod.INDICES), 1))[i]}:"
            for i in members
        ]
    got = [l for l in lines if l.startswith("== ") or re.match(r"\d+\. ", l)]
    assert len(got) == len(expected)
    for g, e in zip(got, expected):
        assert g.startswith(e)
