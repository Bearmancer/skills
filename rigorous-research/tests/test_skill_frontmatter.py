from pathlib import Path

import pytest
import yaml

SKILLS = sorted(Path(__file__).resolve().parents[2].glob("*/SKILL.md"))


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_frontmatter_is_valid_yaml_with_a_string_description(path):
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert text.startswith("---\n")
    data = yaml.safe_load(text.split("\n---", 1)[0][4:])
    assert isinstance(data["description"], str) and data["name"] == path.parent.name
