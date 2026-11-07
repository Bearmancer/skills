# /// script
# requires-python = ">=3.12"
# ///
"""Offline audit: a read-only walk of the home folder's working trees and agent state.

Every git working tree under the roots (nested repos and linked worktrees included) is reported
with its dirty entries, stashes, local-only branches and unpushed commits; every plan, draft,
scratch or notes folder that git does not track (and that is not a skill) is reported with
its file count. A linked worktree reports its own dirty entries; branches and stashes are
reported once, on the main checkout. Items are ranked (most local-only state
first) and each names its owning ticket from --owners, or UNOWNED. Nothing is written.

  uv run offline-audit.py [--home DIR] [--roots NAME ...] [--depth N] [--owners FILE] [--json]

--owners is a JSON object mapping a home-relative path prefix to a ticket ("Dev/AI-Config": "#95");
the longest matching prefix wins. An item with no local state needs no owner and shows "-".
Exit 1 when any item with state is UNOWNED, else 0. Output is sorted, so
two runs on an unchanged machine print the same inventory.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOTS = (
    ".",
    "Dev",
    ".config",
    ".claude",
    ".omo",
    ".agents",
    ".senpi",
    ".gemini",
    ".omc-state",
)
SKIP = {
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".cache",
    "cache",
    "Cache",
    "site-packages",
    ".npm",
    ".pnpm-store",
    "plugins",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".codegraph",
}
NOTE_DIRS = {"plans", "drafts", "scratch", "notes", "wayfinder", "handoffs"}


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    return result.stdout if result.returncode == 0 else ""


def repo_facts(repo: Path) -> dict:
    dirty = len(
        [line for line in git(repo, "status", "--porcelain").splitlines() if line]
    )
    if (repo / ".git").is_file():
        # A linked worktree shares its main checkout's branches and stashes; report them there.
        branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
        return {
            "dirty": dirty,
            "stashes": 0,
            "local_only": [],
            "unpushed": 0,
            "worktree_of": branch,
        }
    stashes = len(git(repo, "stash", "list").splitlines())
    local_only, unpushed = [], 0
    refs = git(
        repo,
        "for-each-ref",
        "--format=%(refname:short)\t%(upstream:short)\t%(upstream:track)",
        "refs/heads",
    )
    for line in refs.splitlines():
        name, upstream, track = (line.split("\t") + ["", ""])[:3]
        if not upstream or "gone" in track:
            local_only.append(name)
        elif "ahead" in track:
            unpushed += int(track.split("ahead ")[1].split(",")[0].rstrip("]"))
    return {
        "dirty": dirty,
        "stashes": stashes,
        "local_only": sorted(local_only),
        "unpushed": unpushed,
    }


def tracked(path: Path) -> bool:
    """A notes folder whose files git tracks is repository content, not residue."""
    return bool(git(path, "ls-files", "--", ".").strip())


def walk(home: Path, roots: list[str], depth: int) -> list[dict]:
    items: dict[Path, dict] = {}

    def visit(path: Path, level: int) -> None:
        try:
            entries = sorted(os.scandir(path), key=lambda e: e.name)
        except OSError:
            return
        if any(e.name == ".git" for e in entries):
            items[path] = {"kind": "repo", **repo_facts(path)}
        if path.name in NOTE_DIRS and "skills" not in path.parts and not tracked(path):
            files = sum(len(f) for _, _, f in os.walk(path))
            items[path] = {"kind": "notes", "files": files, **items.get(path, {})}
        if level >= depth:
            return
        for entry in entries:
            if (
                entry.name in SKIP
                or entry.name == ".git"
                or not entry.is_dir(follow_symlinks=False)
            ):
                continue
            visit(Path(entry.path), level + 1)

    for root in roots:
        base = (home / root).resolve()
        if base.is_dir():
            visit(base, depth - 1 if root == "." else 0)
    return [{"path": p, **facts} for p, facts in items.items()]


def has_state(item: dict) -> bool:
    if item["kind"] == "repo":
        return bool(
            item["dirty"] or item["stashes"] or item["unpushed"] or item["local_only"]
        )
    return bool(item["files"])


def weight(item: dict) -> tuple:
    if item["kind"] == "repo":
        state = (
            item["dirty"] + item["stashes"] + item["unpushed"] + len(item["local_only"])
        )
        return (0 if state else 2, -state)
    return (1 if item["files"] else 3, -item["files"])


def owner_of(rel: str, owners: dict[str, str]) -> str:
    matches = [k for k in owners if rel == k or rel.startswith(k.rstrip("/") + "/")]
    return owners[max(matches, key=len)] if matches else "UNOWNED"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--home", type=Path, default=Path.home())
    ap.add_argument("--roots", nargs="+", default=list(ROOTS))
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--owners", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    home = args.home.resolve()
    owners = json.loads(args.owners.read_text(encoding="utf-8")) if args.owners else {}
    items = walk(home, args.roots, args.depth)
    for item in items:
        rel = (
            item["path"].relative_to(home).as_posix()
            if item["path"].is_relative_to(home)
            else str(item["path"])
        )
        item["path"] = rel
        item["owner"] = owner_of(rel, owners) if has_state(item) else "-"
    items.sort(key=lambda i: (*weight(i), i["path"]))
    if args.json:
        print(
            json.dumps(
                {"coverage": args.roots, "depth": args.depth, "items": items}, indent=1
            )
        )
    else:
        print(
            f"coverage: {', '.join(args.roots)} (depth {args.depth}); {len(items)} items"
        )
        for i in items:
            if i["kind"] == "repo":
                detail = f"dirty={i['dirty']} stashes={i['stashes']} unpushed={i['unpushed']} local-only={','.join(i['local_only']) or '-'}"
                if "worktree_of" in i:
                    detail = f"dirty={i['dirty']} worktree on {i['worktree_of']}"
            else:
                detail = f"files={i['files']}"
            print(f"{i['owner']:<10} {i['kind']:<5} {i['path']}  {detail}")
    return 1 if any(i["owner"] == "UNOWNED" for i in items) else 0


if __name__ == "__main__":
    sys.exit(main())
