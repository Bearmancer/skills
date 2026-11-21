# /// script
# requires-python = ">=3.12"
# ///
"""Diff scope and repo audit for rigorous-review. Read-only: never edits, checks out or deletes."""
import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

MARKER = re.compile(r"(#|//|<!--|/\*|--)\s*(TODO|FIXME|XXX|HACK)\b|\b(TODO|FIXME|XXX|HACK)[:(]|raise NotImplementedError")
BOX = re.compile(r"^\s*[-*] \[ \]")
SKIP = re.compile(r"\.skip\(|\.only\(|@pytest\.mark\.(skip|xfail)|\bx(it|describe)\(|\bit\.todo\(|@Disabled|@Ignore\b")
TEST = re.compile(r"(^|/)(tests?|__tests__)/|(^|/)test_[^/]+$|[._]test\.[^/]+$|\.spec\.[^/]+$", re.I)
CLUTTER = re.compile(r"\.(tmp|bak|orig|rej|swp)$|~$|(^|/)(__pycache__|\.pytest_cache)(/|$)", re.I)
DRAFT = re.compile(r"(^|/)[^/]*(handoff|draft|scratch|wip)[^/]*\.(md|txt)$", re.I)
TICK = re.compile(r"`([\w.-]+(?:/[\w.-]+)+\.\w+)`|\]\(([^)\s#]+)")
STANDARDS = ("AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "CODING_STANDARDS.md", "STYLE_GUIDE.md", ".editorconfig")
EMPTY_BLOB = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
WALK_SKIP = {".git", "node_modules", ".venv", "venv"}


def git(root, *args):
    r = subprocess.run(["git", "-c", "core.quotePath=false", "-C", str(root), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else ""


def rows(s):
    return [l for l in s.splitlines() if l.strip()]


def resolve_base(root, base):
    if base:
        if not git(root, "rev-parse", "--verify", "-q", f"{base}^{{commit}}").strip():
            sys.exit(f"base does not resolve in {root}: {base}")
        return base, "given"
    for ref in ("@{upstream}", "origin/HEAD"):
        if mb := git(root, "merge-base", ref, "HEAD").strip():
            return mb, ref
    return "HEAD", "no upstream"


def added_lines(root, base, untracked):
    out, path, n = [], None, 0
    for l in git(root, "diff", "-U0", "--no-color", "--no-ext-diff", base).splitlines():
        if l.startswith("+++ "):
            path = l[6:] if l.startswith("+++ b/") else None
        elif l.startswith("@@"):
            n = int(re.search(r"\+(\d+)", l)[1])
        elif l.startswith("+") and path:
            out.append((path, n, l[1:]))
            n += 1
    for u in untracked:
        p = root / u
        if p.is_file() and p.stat().st_size < 1_000_000:
            out += [(u, i, l) for i, l in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1)]
    return out


def resolves(md, target, root, tick):
    target = target.split("#")[0]
    if not target or re.match(r"[a-z][\w+.-]*:", target) or target.startswith(("/", "~", "\\")) or any(c in target for c in "<>{}*$|\\"):
        return True
    ancestors = [md.parent, *[d for d in md.parent.parents if d.is_relative_to(root)]]
    if tick and not any((d / target.split("/")[0]).exists() for d in ancestors):
        return True
    return any((d / target).exists() for d in ancestors)


def scope(root, base, how):
    commits = rows(git(root, "log", "--oneline", f"{base}..HEAD")) if base != "HEAD" else []
    num = [l.split("\t") for l in rows(git(root, "diff", "--numstat", base))]
    untracked = rows(git(root, "ls-files", "-o", "--exclude-standard"))
    size = sum(int(a) + int(d) for a, d, _ in num if a != "-")
    cls = "small" if size <= 100 else "ok" if size <= 300 else "large, consider a split" if size < 1000 else "too large to review whole: split it"
    std = [s for s in STANDARDS if (root / s).exists()] + ["~/.agents/AGENTS.md"]
    specs = [p.parent.relative_to(root).as_posix() for p in (root / "openspec" / "changes").glob("*/proposal.md") if p.parent.name != "archive"]
    refs = sorted({r for c in commits for r in re.findall(r"#\d+", c)})
    print(f"repo {root}  branch {git(root, 'branch', '--show-current').strip() or '(detached)'}  base {base[:9]} ({how})")
    print(f"DIFF {len(commits)} commits, {len(num)} files, {size} lines ({cls}), untracked {len(untracked)}")
    print(f"  standards: {', '.join(std)}")
    print(f"  spec: {', '.join(specs) or 'none found: use the user request'}{'; issue refs ' + ' '.join(refs) if refs else ''}")
    return [f for *_, f in num] + untracked, untracked


def audit(root, base, changed, untracked):
    found, names = defaultdict(list), set()
    dirty = rows(git(root, "status", "--porcelain"))
    unpushed = git(root, "rev-list", "--count", "@{upstream}..HEAD").strip()
    stashes = rows(git(root, "stash", "list"))
    trees = [l[9:] for l in git(root, "worktree", "list", "--porcelain").splitlines() if l.startswith("worktree ")][1:]
    cur = git(root, "branch", "--show-current").strip()
    if dirty:
        found["state"].append(f"{len(dirty)} uncommitted: {', '.join(l[3:] for l in dirty[:8])}")
        names |= {l[3:] for l in dirty}
    if unpushed not in ("", "0"):
        found["state"].append(f"{unpushed} unpushed commit(s) on {cur}")
    elif not unpushed and cur:
        found["state"].append(f"{cur} has no upstream")
    for s in stashes:
        found["state"].append(f"stash: {s}")
        names |= set(re.findall(r"On ([^:]+):", s))
    for t in trees:
        found["state"].append(f"extra worktree: {t}")
        names.add(Path(t).name)
    for l in rows(git(root, "for-each-ref", "--format=%(refname:short)\t%(upstream:short)\t%(upstream:track)", "refs/heads")):
        b, up, track = (l.split("\t") + ["", ""])[:3]
        if b != cur and (not up or "gone" in track or "ahead" in track):
            found["state"].append(f"local branch {b}: {track or 'no upstream'}")
            names.add(b)

    tracked = rows(git(root, "ls-files"))
    ignored = rows(git(root, "ls-files", "-o", "-i", "--exclude-standard", "--directory"))
    found["clutter"] += [p for p in tracked + untracked + ignored if CLUTTER.search(p.rstrip("/"))]
    found["drafts"] += [p for p in tracked + untracked if DRAFT.search(p)]
    skip = {root / x.rstrip("/") for x in ignored if x.endswith("/")}
    for d, dirs, files in root.walk():
        dirs[:] = [x for x in dirs if x not in WALK_SKIP and d / x not in skip]
        if not dirs and not files:
            found["empty dirs"].append(d.relative_to(root).as_posix())
    blobs = defaultdict(list)
    for l in rows(git(root, "ls-files", "-s")):
        meta, path = l.split("\t", 1)
        if (blob := meta.split()[1]) != EMPTY_BLOB:
            blobs[blob].append(path)
    found["duplicates"] += [" = ".join(g) for g in blobs.values() if len(g) > 1]

    for path, n, text in added_lines(root, base, untracked):
        where = f"{path}:{n}"
        if "re.compile(" in text:
            continue
        if MARKER.search(text):
            found["unfinished"].append(f"{where} marker: {text.strip()[:80]}")
        if path.endswith(".md") and not path.endswith("tasks.md") and BOX.match(text):
            found["unfinished"].append(f"{where} unchecked: {text.strip()[:80]}")
        if SKIP.search(text):
            found["unfinished"].append(f"{where} skipped test: {text.strip()[:80]}")
    deleted = rows(git(root, "diff", "--name-only", "--diff-filter=D", base))
    found["unfinished"] += [f"test deleted: {p}" for p in deleted if TEST.search(p)]
    for tasks in (root / "openspec" / "changes").glob("*/tasks.md"):
        if (open_ := sum(1 for l in tasks.read_text(encoding="utf-8").splitlines() if BOX.match(l))):
            found["unfinished"].append(f"{tasks.relative_to(root).as_posix()}: {open_} unchecked task(s)")

    gone = {p.split("/")[0] for p in deleted if not (root / p.split("/")[0]).exists()}
    names |= gone | set(deleted)
    for rel in sorted({p for p in changed if p.endswith(".md") and not p.startswith("openspec/") and (root / p).is_file()}):
        md = root / rel
        for i, l in enumerate(md.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in TICK.finditer(l):
                if not resolves(md, m[1] or m[2], root, bool(m[1])):
                    found["links"].append(f"{rel}:{i} -> {m[1] or m[2]}")
    for name in sorted(gone):
        for hit in rows(git(root, "grep", "-n", "-w", "-F", name, "--", "*.md", ":!LEDGER.md", ":!openspec/"))[:10]:
            found["links"].append(f"names deleted {name}: {hit[:140]}")

    for epic in (Path.home() / ".agents" / "EPICs").glob("*/EPIC.md"):
        text = epic.read_text(encoding="utf-8", errors="replace")
        if epic.parent.name.lower() != root.name.lower() and str(root) not in text:
            continue
        items = [l for l in text.splitlines() if l.startswith("- [ ]")]
        hits = [l for l in items if any(n and n in l for n in names)]
        found["epic"] += [f"{epic.parent.name}: {l[:160]}" for l in hits]
        print(f"  epic {epic}: {len(items)} open item(s)")
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repos", nargs="*", default=["."])
    ap.add_argument("--base", help="review from this ref (when the session's work is already pushed)")
    a = ap.parse_args()
    total = 0
    for r in a.repos:
        root = Path(git(Path(r), "rev-parse", "--show-toplevel").strip() or sys.exit(f"not a git repo: {r}")).resolve()
        base, how = resolve_base(root, a.base)
        changed, untracked = scope(root, base, how)
        found = audit(root, base, changed, untracked)
        print("AUDIT")
        for cat in ("state", "clutter", "drafts", "empty dirs", "duplicates", "unfinished", "links", "epic"):
            items = found.get(cat, [])
            total += len(items)
            print(f"  {cat}: {len(items) or 'none'}")
            for it in items[:15]:
                print(f"    - {it}")
            if len(items) > 15:
                print(f"    ... {len(items) - 15} more")
        print()
    print(f"RESULT {total} audit finding(s)")
    sys.exit(1 if total else 0)


main()
