#!/usr/bin/env python3
"""Mirror personal skills from ~/.agents/skills into this repository.

`personal-skills.json` is the only list of skills that belong here. Everything
else in the source directory is a vendor or third-party skill and is never
copied. The mirror is exact: files removed from a personal skill are removed
from the repo as well.

Usage:
    uv run --no-dev --project . python scripts/sync-skills.py
    uv run --no-dev --project . python scripts/sync-skills.py --check
    uv run --no-dev --project . python scripts/sync-skills.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKILL_FILE = "SKILL.md"
MANIFEST_FILE = "personal-skills.json"

JUNK_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".codegraph",
    "node_modules",
}
JUNK_FILES = {".DS_Store", "Thumbs.db"}
TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".js",
    ".mjs",
    ".cjs",
    ".json",
    ".jsonc",
    ".yaml",
    ".yml",
    ".toml",
    ".txt",
    ".sh",
    ".ps1",
    ".psm1",
    ".css",
    ".html",
    ".htm",
    ".xml",
    ".csv",
    ".ts",
    ".tsx",
    ".jsx",
    ".kt",
    ".kts",
    ".gradle",
    ".properties",
    ".ini",
    ".cfg",
    ".conf",
    ".lock",
}
TEXT_NAMES = {".gitignore", ".gitattributes", ".editorconfig"}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def fail(message: str, code: int = 2) -> "NoReturn":
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def load_manifest(repo: Path) -> tuple[Path, list[str]]:
    manifest = repo / MANIFEST_FILE
    if not manifest.is_file():
        fail(f"missing manifest: {manifest}")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{manifest}: invalid JSON: {exc}")
    if not isinstance(data, dict):
        fail(f"{manifest}: expected a JSON object")

    source_raw = data.get("source", "~/.agents/skills")
    if not isinstance(source_raw, str) or not source_raw.strip():
        fail(f"{manifest}: 'source' must be a non-empty string")
    source = Path(os.path.expandvars(os.path.expanduser(source_raw)))

    skills = data.get("skills")
    if not isinstance(skills, list) or not all(isinstance(item, str) for item in skills):
        fail(f"{manifest}: 'skills' must be a list of strings")
    if not skills:
        fail(f"{manifest}: 'skills' is empty")

    seen: set[str] = set()
    for name in skills:
        if not NAME_RE.fullmatch(name):
            fail(f"{manifest}: invalid skill name {name!r}")
        if name in seen:
            fail(f"{manifest}: duplicate skill {name!r}")
        seen.add(name)
    return source, skills


def is_junk(rel: Path) -> bool:
    return (
        any(part in JUNK_DIRS for part in rel.parts)
        or rel.name in JUNK_FILES
        or rel.suffix == ".pyc"
    )


def iter_files(root: Path) -> dict[Path, Path]:
    files: dict[Path, Path] = {}
    if not root.is_dir():
        return files
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if not is_junk(rel):
            files[rel] = path
    return files


def front_matter_name(skill_md: Path) -> str | None:
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    match = re.search(r"^name:\s*(.+?)\s*$", text[3:end], re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    return value


def normalized(path: Path) -> bytes:
    """Return bytes with line endings normalized so LF/CRLF is not drift."""
    data = path.read_bytes()
    if b"\0" in data[:8192]:
        return data
    suffix = path.suffix.lower()
    if suffix not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
        return data
    text = data.decode("utf-8", errors="surrogateescape")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.encode("utf-8", errors="surrogateescape")


def diff_skill(source: Path, repo_skill: Path, name: str) -> list[str]:
    problems: list[str] = []
    if not source.is_dir():
        return [f"{name}: missing source directory {source}"]
    skill_md = source / SKILL_FILE
    if not skill_md.is_file():
        return [f"{name}: source has no {SKILL_FILE}"]

    actual = front_matter_name(skill_md)
    if actual != name:
        problems.append(f"{name}: {SKILL_FILE} name is {actual!r}, expected {name!r}")

    source_files = iter_files(source)
    repo_files = iter_files(repo_skill)
    for rel in sorted(set(source_files) - set(repo_files)):
        problems.append(f"{name}: missing in repo: {rel.as_posix()}")
    for rel in sorted(set(repo_files) - set(source_files)):
        problems.append(f"{name}: extra in repo: {rel.as_posix()}")
    for rel in sorted(set(source_files) & set(repo_files)):
        if normalized(source_files[rel]) != normalized(repo_files[rel]):
            problems.append(f"{name}: differs: {rel.as_posix()}")
    return problems


def mirror_skill(source: Path, repo_skill: Path, name: str, dry_run: bool) -> list[str]:
    if not source.is_dir():
        fail(f"{name}: missing source directory {source}")
    skill_md = source / SKILL_FILE
    if not skill_md.is_file():
        fail(f"{name}: source has no {SKILL_FILE}")

    actual = front_matter_name(skill_md)
    if actual != name:
        fail(f"{name}: {SKILL_FILE} name is {actual!r}, expected {name!r}")

    changes: list[str] = []
    source_files = iter_files(source)
    repo_files = iter_files(repo_skill)

    for rel in sorted(set(repo_files) - set(source_files)):
        changes.append(f"{name}: remove {rel.as_posix()}")
        if not dry_run:
            repo_files[rel].unlink()

    for rel in sorted(source_files):
        data = normalized(source_files[rel])
        target = repo_skill / rel
        if rel in repo_files and normalized(repo_files[rel]) == data:
            continue
        changes.append(f"{name}: write {rel.as_posix()}")
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    if not dry_run:
        for directory in sorted(
            (path for path in repo_skill.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            if directory == repo_skill:
                continue
            try:
                directory.rmdir()
            except OSError:
                pass

    return changes


def unmanaged_skills(repo: Path, skills: set[str]) -> list[Path]:
    found: list[Path] = []
    for child in sorted(repo.iterdir()):
        if not child.is_dir() or child.name.startswith(".") or child.name in skills:
            continue
        if (child / SKILL_FILE).is_file():
            found.append(child)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report drift without writing")
    parser.add_argument("--dry-run", action="store_true", help="show changes without writing")
    parser.add_argument("--source", type=Path, help="override the source skills directory")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: parent of scripts/)",
    )
    parser.add_argument("--quiet", action="store_true", help="only print problems and the summary")
    args = parser.parse_args()

    repo = args.repo.resolve()
    source, skills = load_manifest(repo)
    if args.source:
        source = args.source.resolve()
    if not source.is_dir():
        fail(f"source directory does not exist: {source}")

    problems: list[str] = []
    for child in unmanaged_skills(repo, set(skills)):
        problems.append(
            f"unmanaged skill directory: {child.name} "
            f"(add it to {MANIFEST_FILE} or remove it)"
        )

    if args.check or args.dry_run:
        for name in skills:
            problems.extend(diff_skill(source / name, repo / name, name))
        if args.dry_run:
            for name in skills:
                for change in mirror_skill(source / name, repo / name, name, dry_run=True):
                    print(change)
    else:
        for name in skills:
            for change in mirror_skill(source / name, repo / name, name, dry_run=False):
                if not args.quiet:
                    print(change)

    if problems:
        for problem in problems:
            print(f"drift: {problem}", file=sys.stderr)
        print(
            f"{len(problems)} problem(s); run without --check to mirror",
            file=sys.stderr,
        )
        return 1

    if not args.quiet:
        print(f"ok: {len(skills)} personal skill(s) in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
