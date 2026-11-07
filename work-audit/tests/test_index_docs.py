"""The skill's doc pointers resolve and the 21-index list stays complete."""

import re
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\]\((references/[^)#]+)\)")


def test_every_references_link_in_skill_md_exists():
    links = LINK.findall((SKILL / "SKILL.md").read_text(encoding="utf-8"))
    assert "references/empty-catch-gate.md" in links
    assert "references/indices.md" in links
    assert not (SKILL / "references" / "index-map.md").exists()
    for l in links:
        assert (SKILL / l).is_file(), l


def test_no_ref_dir_left_behind():
    assert not (SKILL / "ref").exists()


def test_indices_md_lists_all_21_in_order():
    text = (SKILL / "references" / "indices.md").read_text(encoding="utf-8")
    section = text.split("\n## Definitions", 1)[1].split("\n## ", 1)[0]
    assert [int(n) for n in re.findall(r"^(\d+)\. ", section, re.M)] == list(
        range(1, 22)
    )
