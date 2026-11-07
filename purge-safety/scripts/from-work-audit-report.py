# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Work-audit handoff.

Turns a work-audit report.json into a purge manifest, so the audit's indices 4 (stale artifacts)
and 15 (empty dirs) are resolved by the purge engine instead of ad-hoc deletes. One deletion
engine, one guard layer, one journal.

Reads only. Writes a manifest; apply it with purge.py --apply --manifest <file>.

Routing is 4, then 15, then 16, ascending: every row carries its index, entries sort by index
then path, and the order line is echoed (`order: 4 -> 15 -> 16`).

Usage:
  uv run from-work-audit-report.py --report "<records>\\<repo>-<hash>\\<tree>\\report.json" --repo "C:\\path\\to\\repo"
  uv run purge.py --manifest "<written manifest>"            # plan
  uv run purge.py --apply --manifest "<written manifest>"    # delete, journal, residue
"""

import argparse
import fnmatch
import importlib.util
import json
import os
import re
import stat
import sys
import time
from datetime import datetime
from itertools import groupby

# Generated omo state routed by --home-config (#216). Executor-adjacent dirs need an owner override.
HOME_PURGE = ("evidence", "drafts", "tmp", "reports")
HOME_OWNER = ("plans", "ulw-loop", "wayfinder")
HOME_LOOSE = re.compile(r"(?i)\.(bak|old)$")
ENGINE_FILES = (
    "Purge Manifest - *",
    "Purge Journal - *",
)  # the engine's own output under reports/
DRIVE_ROOT = re.compile(r"(?i)^[A-Za-z]:\\?$")
REPARSE = 0x400


def engine_protected():
    """The engine's protected-path check, loaded from purge.py so there is one list."""
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "purge_engine", os.path.join(here, "purge.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Engine.protected


class Parser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write(f"from-work-audit-report: {message}\n")
        sys.exit(1)


def text(value):
    """A report value spliced into a reason the way PowerShell concatenates it."""
    return "" if value is None else str(value)


def load_sections(report):
    with open(report, encoding="utf-8-sig") as f:
        doc = json.load(f)
    # work-audit report.json nests the per-index sections under "indices"; a hand-built
    # report may carry them at the top level. Both shapes are accepted.
    return doc.get("indices") if isinstance(doc.get("indices"), dict) else doc


def is_link(st):
    return stat.S_ISLNK(st.st_mode) or bool(
        getattr(st, "st_file_attributes", 0) & REPARSE
    )


def tree_facts(path):
    """(files, newest mtime) of a path; links count as themselves and are never followed."""
    st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode) or is_link(st):
        return (0 if stat.S_ISDIR(st.st_mode) else 1), st.st_mtime
    files, newest, stack = 0, st.st_mtime, [path]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                items = list(it)
        except OSError:
            continue
        for item in items:
            try:
                s = item.stat(follow_symlinks=False)
            except OSError:
                continue
            newest = max(newest, s.st_mtime)
            if stat.S_ISDIR(s.st_mode) and not is_link(s):
                stack.append(item.path)
            elif not stat.S_ISDIR(s.st_mode):
                files += 1
    return files, newest


def home_config(sections, age_days, now=None):
    """Rows for the generated state under the report's omo config root (#216).

    Returns (root, rows, held, notes). Rows are children of the generated subdirs (the subdirs stay)
    plus loose backups at the omo root. A row inside the age gate, or on a protected path, is held:
    listed for plan review, never written to the manifest. The root is never the home folder.
    """
    now = time.time() if now is None else now
    cutoff = now - age_days * 86400
    four = sections.get("4") if isinstance(sections.get("4"), dict) else {}
    home = os.path.abspath(
        os.environ.get("USERPROFILE") or os.path.expanduser("~")
    ).rstrip("\\")
    protected = engine_protected()
    for item in four.get("config_root_entries") or []:
        root = (
            os.path.abspath(str(item.get("root") or "")).rstrip("\\")
            if isinstance(item, dict)
            else ""
        )
        if not root or os.path.basename(root).lower() != ".omo":
            continue
        if (
            root.upper() == home.upper()
            or DRIVE_ROOT.match(root)
            or not os.path.isdir(root)
            or is_link(os.lstat(root))
        ):
            return (
                None,
                [],
                [],
                [
                    f"home-config: refused root {root} (not an omo directory below the home folder)"
                ],
            )
        rows, held = [], []

        def consider(path, verdict, category, reason):
            try:
                files, newest = tree_facts(path)
            except OSError:
                return
            when = datetime.fromtimestamp(newest).strftime("%Y-%m-%d %H:%M")
            row = {
                "path": path,
                "verdict": verdict,
                "category": category,
                "reason": f"{reason} (files {files}, newest {when})",
                "index": 4,
            }
            pattern = protected(path)
            if pattern:
                held.append((row, f"protected path ({pattern})"))
            elif newest >= cutoff:
                held.append((row, f"inside the {age_days}-day age gate"))
            else:
                rows.append(row)

        for name in HOME_PURGE + HOME_OWNER:
            sub = os.path.join(root, name)
            try:
                if not stat.S_ISDIR(os.lstat(sub).st_mode) or is_link(os.lstat(sub)):
                    continue
                with os.scandir(sub) as it:
                    children = sorted(it, key=lambda e: e.name.casefold())
            except OSError:
                continue
            verdict = "OWNER" if name in HOME_OWNER else "PURGE"
            for child in children:
                if name == "reports" and any(
                    fnmatch.fnmatchcase(child.name, p) for p in ENGINE_FILES
                ):
                    continue
                consider(
                    child.path, verdict, f"home-config-{name}", f"omo generated {name}"
                )
        with os.scandir(root) as it:
            loose = sorted(
                (
                    e
                    for e in it
                    if e.is_file(follow_symlinks=False) and HOME_LOOSE.search(e.name)
                ),
                key=lambda e: e.name.casefold(),
            )
        for child in loose:
            consider(child.path, "PURGE", "home-config-backup", "omo backup file")
        return root, sorted(rows, key=lambda r: r["path"].casefold()), held, []
    return (
        None,
        [],
        [],
        [
            "home-config: the report lists no omo config root (index 4 config_root_entries)"
        ],
    )


def build(sections, repo, include_duplicates):

    def section(index, key):
        value = (
            (sections.get(index) or {}).get(key)
            if isinstance(sections.get(index), dict)
            else None
        )
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    def fact(index, rel):
        s = sections.get(index)
        safety = s.get("safety") if isinstance(s, dict) else None
        return safety.get(rel) if isinstance(safety, dict) else None

    entries, seen = [], set()
    parent = os.path.dirname(repo)
    prefix = repo.upper() + "\\"

    def add(rel, index, category, reason, verdict="PURGE"):
        if rel is None or not str(rel).strip():
            return
        rel = str(rel)
        # work-audit records rel paths against the repo's parent ("repo\dir\file"), so join
        # against the parent first; a repo-relative rel path falls through to the repo join.
        full = os.path.abspath(os.path.join(parent, rel))
        if not full.upper().startswith(prefix):
            full = os.path.abspath(os.path.join(repo, rel))
        if not full.upper().startswith(prefix):
            return
        if full.upper() in seen:
            return
        seen.add(full.upper())
        if not os.path.lexists(full):
            return
        f = fact(str(index), rel)
        if isinstance(f, dict) and f:
            bits = []
            if "files" in f:
                bits.append("files " + text(f["files"]))
            if "newest_mtime" in f:
                bits.append("newest " + text(f["newest_mtime"]))
            if f.get("branch"):
                bits.append(
                    f"branch {text(f['branch'])} uncommitted {text(f.get('uncommitted'))} unpushed {text(f.get('unpushed'))}"
                )
            if bits:
                reason = reason + " (" + ", ".join(bits) + ")"
        entries.append(
            {
                "path": full,
                "verdict": verdict,
                "category": category,
                "reason": reason,
                "index": index,
            }
        )

    for rel in section("4", "zero_byte"):
        add(rel, 4, "work-audit-4-zero-byte", "zero-byte file")
    for rel in section("4", "tmp_bak_orig"):
        add(rel, 4, "work-audit-4-junk", "tmp/bak/orig file")
    for rel in section("4", "pycache"):
        add(rel, 4, "work-audit-4-pycache", "python bytecode cache")
    for rel in section("4", "ignored_untracked_old"):
        add(rel, 4, "work-audit-4-ignored-old", "ignored untracked older than 24h")
    for rel in section("15", "empty_dirs"):
        add(rel, 15, "work-audit-15-empty-dir", "empty directory")
    if include_duplicates:
        for pair in section("16", "duplicates"):
            paths = pair if isinstance(pair, list) else [pair]
            if len(paths) < 2:
                continue
            add(
                text(paths[0]),
                16,
                "work-audit-16-duplicate",
                f"duplicate of {text(paths[1])}; keeper is the second path",
                "OWNER",
            )

    return sorted(entries, key=lambda e: (e["index"], e["path"].casefold()))


def main(argv=None):
    p = Parser(
        prog="from-work-audit-report.py",
        description=__doc__.split("\n")[0],
        allow_abbrev=False,
    )
    p.add_argument("--report", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--out-dir")
    p.add_argument("--include-duplicates", action="store_true")
    p.add_argument(
        "--home-config",
        action="store_true",
        help="also write a manifest for the generated state under the report's ~/.omo config root",
    )
    p.add_argument(
        "--home-age-days",
        type=int,
        default=7,
        help="age gate for --home-config rows (default 7)",
    )
    args = p.parse_args(argv)
    try:
        if not os.path.isfile(args.report):
            raise ValueError(f"report not found: {args.report}")
        if not os.path.isdir(args.repo):
            raise ValueError(f"repo not found: {args.repo}")
        repo = os.path.abspath(args.repo).rstrip("\\")
        out_dir = args.out_dir or os.path.dirname(os.path.abspath(args.report))
        sections = load_sections(args.report)
        entries = build(sections, repo, args.include_duplicates)
        stamp = datetime.now().strftime("%Y-%m-%d %H%M%S")
        generated = datetime.now().astimezone().isoformat()
        manifest = {
            "root": repo,
            "generated": generated,
            "source": args.report,
            "entries": entries,
        }
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "Purge Manifest - work-audit - " + stamp + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        home = None
        if args.home_config:
            home_root, home_rows, held, notes = home_config(
                sections, args.home_age_days
            )
            home_path = None
            if home_root:
                home_path = os.path.join(
                    out_dir,
                    "Purge Manifest - work-audit home-config - " + stamp + ".json",
                )
                doc = {
                    "root": home_root,
                    "generated": generated,
                    "source": args.report,
                    "entries": home_rows,
                }
                with open(home_path, "w", encoding="utf-8") as f:
                    json.dump(doc, f, indent=2, ensure_ascii=False)
            home = (home_root, home_rows, held, notes, home_path)
    except (OSError, ValueError) as error:
        sys.stderr.write(f"from-work-audit-report: {error}\n")
        return 1
    order = " -> ".join(str(k) for k, _ in groupby(e["index"] for e in entries))
    print(f"order: {order} (index asc, then path asc)")
    for category in sorted({e["category"] for e in entries}):
        print(
            f"{category:<28} {sum(e['category'] == category for e in entries):>5}  {repo}"
        )
    print(f"{'TOTAL':<28} {len(entries):>5}  {path}")
    if home:
        home_root, home_rows, held, notes, home_path = home
        for note in notes:
            print(note)
        if home_root:
            print(
                f"home-config root: {home_root} (plan and apply with --root {home_root})"
            )
            for category in sorted({r["category"] for r in home_rows}):
                print(
                    f"{category:<28} {sum(r['category'] == category for r in home_rows):>5}  {home_root}"
                )
            for row, why in held:
                print(f"held  {row['verdict']:<5} {row['path']} :: {why}")
            print(f"{'TOTAL':<28} {len(home_rows):>5}  {home_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
