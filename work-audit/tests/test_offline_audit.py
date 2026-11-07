"""Tests for scripts/offline-audit.py: a read-only, repeatable inventory of a fabricated home."""

import json
import os
import subprocess
from pathlib import Path

from conftest import PY_RUNNER, SCRIPT_TIMEOUT

AUDIT = Path(__file__).resolve().parent.parent / "scripts" / "offline-audit.py"


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        timeout=SCRIPT_TIMEOUT,
    )


def audit(home: Path, *args: str):
    return subprocess.run(
        [*PY_RUNNER, str(AUDIT), "--home", str(home), "--roots", "Dev", ".omo", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=SCRIPT_TIMEOUT,
        env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1"},
    )


def fabricated_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    repo = home / "Dev" / "proj"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    (repo / "a.txt").write_text("a")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-q", "-m", "seed")
    (repo / "dirty.txt").write_text("x")
    hidden = home / "Dev" / "proj" / "node_modules" / "dep"
    hidden.mkdir(parents=True)
    git(hidden, "init", "-q")
    clean = home / "Dev" / "clean"
    clean.mkdir()
    git(clean, "init", "-q", "-b", "main")
    plans = home / ".omo" / "plans"
    plans.mkdir(parents=True)
    (plans / "p.md").write_text("# p")
    return home


def test_inventory_ranks_items_skips_dependencies_and_repeats_exactly(tmp_path):
    home = fabricated_home(tmp_path)
    first = audit(home, "--json")
    assert first.returncode == 1  # nothing owned yet
    items = json.loads(first.stdout)["items"]
    assert [(i["path"], i["kind"]) for i in items] == [
        ("Dev/proj", "repo"),
        (".omo/plans", "notes"),
        ("Dev/clean", "repo"),
    ]
    assert items[0]["dirty"] == 2  # dirty.txt and the untracked node_modules/
    assert items[0]["local_only"] == ["main"] and items[0]["stashes"] == 0
    assert items[1]["files"] == 1
    assert [i["owner"] for i in items] == [
        "UNOWNED",
        "UNOWNED",
        "-",
    ]  # a clean repo needs no owner
    assert audit(home, "--json").stdout == first.stdout


def test_owners_map_names_each_item_and_clears_the_exit_code(tmp_path):
    home = fabricated_home(tmp_path)
    owners = tmp_path / "owners.json"
    owners.write_text(json.dumps({"Dev": "#1", "Dev/proj": "#2", ".omo": "#3"}))
    result = audit(home, "--owners", str(owners))
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert lines[0].startswith("coverage: Dev, .omo (depth 6); 3 items")
    assert lines[1].split()[:3] == ["#2", "repo", "Dev/proj"]
    assert lines[2].split()[:3] == ["#3", "notes", ".omo/plans"]
