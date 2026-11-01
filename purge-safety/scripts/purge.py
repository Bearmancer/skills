# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Purge engine. One job: enumerate what should not exist, prove the counts, delete it, and prove it is gone.

Modes
  --scan    build a manifest from the rule table, delete nothing
  default   plan: read a manifest (or re-scan), run every guard, print counts, delete nothing
  --apply   delete the manifest entries that pass the guards, journal each one, then rescan

The script terminates itself, it does not rely on the operator:
  - a second instance refuses to start while the lock is held by a live process;
  - the time budget (--max-minutes) and failure ceiling (--max-failures) abort mid-run, journalled;
  - a manifest larger than --max-paths is refused before any delete;
  - every exit path flushes the journal, releases the lock, and exits with an explicit code.

Deletion is the only destructive path: it needs --apply plus a manifest whose verdict is PURGE or OWNER.
A protected path is refused unless listed in --override. A reparse point is unlinked, never walked.
"""

import argparse
import fnmatch
import json
import os
import re
import stat
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

FILE_ATTRIBUTE_READONLY = 0x1
FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
WORKERS = 16

PROTECTED_PATTERNS = [
    r"(?i)\\\.omo\\memory(\\|$)",
    r"(?i)\\\.omo\\agent\\(sessions|projects|skills|extensions|runtime)(\\|$)",
    r"(?i)\\\.omo\\binary-runtime(\\|$)",
    r"(?i)\\\.omo\\omo\.jsonc$",
    r"(?i)\\\.senpi\\agent\\(auth\.json|migrations-state\.json|extensions|runtime)(\\|$)",
    r"(?i)\\\.claude\\(settings\.json|projects)(\\|$)",
    r"(?i)\\\.claude\\plans(\\|$)",
    r"(?i)\\\.claude\.json$",
    r"(?i)\\\.codegraph(\\|$)",
    r"(?i)\\(\.ssh|\.gnupg|\.secrets|\.aws|\.oci)(\\|$)",
    r"(?i)\\\.azure\\(commands|logs|telemetry)(\\|$)",
    r"(?i)\\\.config(\\|$)",
    r"(?i)\\\.local\\bin(\\|$)",
    r"(?i)\\Desktop\\Desktop(\\|$)",
    r"(?i)\\(Documents|Downloads|Desktop)(\\|$)",
    r"(?i)\\OneDrive[^\\\\]*(\\|$)",
    r"(?i)\\Documents\\(PowerShell|WindowsPowerShell)(\\|$)",
    r"(?i)\\(Pictures|Videos|Music|OneDrive|Favorites|Contacts|Saved Games|Searches|Links)(\\|$)",
    r"(?i)\\AppData\\Roaming\\(Emby-Server|Code[^\\]*|Claude|Spotify|Vivaldi|JetBrains|Mozilla|discord)(\\|$)",
    r"(?i)\\AppData\\Local\\(Packages|Programs|Microsoft|Google\\Chrome|Vivaldi|Spotify|JetBrains)(\\|$)",
    r"(?i)\\AppData\\Local\\Personal\\(Bitwarden[^\\]*)(\\|$)",
    r"(?i)\\wizards(\\|$)",
]
PROTECTED = [(p, re.compile(p)) for p in PROTECTED_PATTERNS]

CACHE_NAMES = {n.upper() for n in ("node_modules", ".cache", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".venv", "venv", ".parcel-cache", ".turbo", ".next")}
BUILD_NAMES = {n.upper() for n in ("bin", "obj", "artifacts", "dist", "build", "out", "coverage", "TestResults")}
BUILD_MARKERS = ("*.csproj", "*.sln", "*.slnx", "package.json", "Cargo.toml", "go.mod", "pyproject.toml")
BACKUP_NAME = re.compile(r"(?i)(\.bak$|\.old$|\.orig$|~$|\.backup\.\d+$)")
ORPHAN_PARENT = re.compile(r"(?i)\\\.omo\\agent\\(projects|sessions)\\")
DRIVE_ROOT = re.compile(r"(?i)^[A-Za-z]:\\?$")
TOOLCHAIN_LINE = re.compile(r'(?i)^default_toolchain\s*=\s*"(.+)"')


class BudgetExceeded(Exception):
    """The time budget ran out: the run aborts with exit 4."""


class Fatal(Exception):
    """A guard or usage error: the run aborts with exit 1."""


# --- filesystem primitives -------------------------------------------------------------------


def long_path(path):
    if path.startswith("\\\\?\\"):
        return path
    if len(path) > 240:
        return "\\\\?\\" + path
    return path


def attrs_of(st):
    a = getattr(st, "st_file_attributes", None)
    if a is not None:
        return a
    a = FILE_ATTRIBUTE_DIRECTORY if stat.S_ISDIR(st.st_mode) else 0
    if stat.S_ISLNK(st.st_mode):
        a |= FILE_ATTRIBUTE_REPARSE_POINT
    return a


def lstat(path):
    """The entry's own stat (links are not followed), or None when it does not exist."""
    try:
        return os.lstat(long_path(path))
    except (OSError, ValueError):
        return None


def attrs(path):
    st = lstat(path)
    return None if st is None else attrs_of(st)


def is_dir(path):
    a = attrs(path)
    return a is not None and bool(a & FILE_ATTRIBUTE_DIRECTORY)


def is_file(path):
    a = attrs(path)
    return a is not None and not a & FILE_ATTRIBUTE_DIRECTORY


def exists(path):
    return attrs(path) is not None


def is_reparse(path):
    a = attrs(path)
    return a is not None and bool(a & FILE_ATTRIBUTE_REPARSE_POINT)


def entry_attrs(entry):
    return attrs_of(entry.stat(follow_symlinks=False))


def list_dir(path):
    """Every entry of a directory; raises OSError when the directory cannot be listed."""
    with os.scandir(long_path(path)) as it:
        return list(it)


def full_path(path):
    return os.path.abspath(path)


def parent_of(path):
    parent = os.path.dirname(path.rstrip("\\"))
    return "" if parent == path else parent


def same(a, b):
    return a.upper() == b.upper()


def under(path, base):
    """path sits strictly below base (case-insensitive, the way Windows compares paths)."""
    return path.upper().startswith(base.rstrip("\\").upper() + "\\")


def clear_readonly(path, a):
    if a & FILE_ATTRIBUTE_READONLY:
        os.chmod(path, stat.S_IWRITE)


def format_size(n):
    # n / scale is exact in binary, and Python rounds that exact value half-to-even, as .NET does.
    for unit, scale, places in (("GB", 1 << 30, 2), ("MB", 1 << 20, 1), ("KB", 1 << 10, 0)):
        if n >= scale:
            return f"{n / scale:,.{places}f} {unit}"
    return f"{n} B"


def now_iso():
    return datetime.now().astimezone().isoformat()


def parse_iso(text):
    """A manifest `generated` stamp as an aware UTC datetime, or None. Accepts .NET's 7-digit fractions."""
    if not isinstance(text, str):
        return None
    try:
        value = datetime.fromisoformat(text.strip())
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.astimezone()
    return value.astimezone(timezone.utc)


class Engine:
    def __init__(self, args):
        self.args = args
        self.root = args.root
        self.json = args.json
        self.start = time.monotonic()
        self.user_home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        self.local = os.environ.get("LOCALAPPDATA") or os.path.join(self.user_home, "AppData", "Local")
        self.roaming = os.environ.get("APPDATA") or os.path.join(self.user_home, "AppData", "Roaming")
        self.exit = 0
        self.stamp = datetime.now().strftime("%Y-%m-%d %H%M%S")
        lock_dir = os.path.join(os.environ["LOCALAPPDATA"], "Temp") if os.environ.get("LOCALAPPDATA") else tempfile.gettempdir()
        if not os.path.isdir(lock_dir):
            lock_dir = tempfile.gettempdir()
        self.lock_path = full_path(args.lock_file) if args.lock_file else os.path.join(lock_dir, "Purge.lock")
        self.lock_held = False
        self.manifest_generated = None
        self.out_dir = args.out_dir or os.path.join(self.user_home, ".omo", "reports")

    # --- output ---------------------------------------------------------------------------------

    def line(self, text):
        if not self.json:
            print(text, flush=True)

    def budget(self, where):
        if (time.monotonic() - self.start) / 60 >= self.args.max_minutes:
            raise BudgetExceeded(f"time budget {self.args.max_minutes}m exhausted at {where}")

    # --- lock -----------------------------------------------------------------------------------

    def enter_lock(self):
        if os.path.isfile(self.lock_path):
            owner = None
            try:
                with open(self.lock_path, encoding="utf-8-sig") as f:
                    owner = json.load(f)
            except (OSError, ValueError):
                owner = None
            if isinstance(owner, dict) and owner.get("pid"):
                try:
                    pid = int(owner["pid"])
                except (TypeError, ValueError):
                    pid = 0
                if pid and pid_alive(pid):
                    raise Fatal(f"another purge is running (pid {owner['pid']}, started {owner.get('started')})")
        body = {"pid": os.getpid(), "started": now_iso(), "mode": "apply", "root": self.root}
        with open(self.lock_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(body, separators=(",", ":"), ensure_ascii=False) + "\n")
        self.lock_held = True

    def exit_lock(self):
        if self.lock_held and os.path.isfile(self.lock_path):
            try:
                os.remove(self.lock_path)
            except OSError:
                pass
            self.lock_held = False

    # --- guards ---------------------------------------------------------------------------------

    @staticmethod
    def protected(path):
        for text, rx in PROTECTED:
            if rx.search(path):
                return text
        return None

    def overridden(self, path):
        for item in self.args.override:
            full = full_path(item)
            if same(path, full) or under(path, full):
                return True
        return False

    def test_entry(self, entry):
        """The refusal reason for a manifest row, or None when it may be deleted."""
        raw = entry["path"]
        if raw is None or not str(raw).strip():
            return "empty path"
        raw = str(raw)
        if re.search(r"[*?]", raw):
            return "wildcard in manifest path"
        resolved = full_path(raw)
        if same(resolved.rstrip("\\"), self.root.rstrip("\\")):
            return "target is the root itself"
        if DRIVE_ROOT.match(resolved):
            return "target is a drive root"
        root_full = full_path(self.root).rstrip("\\")
        if not under(resolved, root_full):
            return "outside root"
        # A target reached through a junction would delete outside the root: check every ancestor.
        cursor = parent_of(resolved)
        while cursor and len(cursor) > len(root_full):
            if is_reparse(cursor):
                return f"path crosses a reparse point ({cursor})"
            cursor = parent_of(cursor)
        verdict = verdict_of(entry)
        if verdict == "MISSING":
            return "manifest row has no verdict"
        if verdict not in ("PURGE", "OWNER"):
            return "verdict is not PURGE"
        pattern = self.protected(resolved)
        if pattern and not self.overridden(resolved):
            return f"protected path ({pattern})"
        if verdict == "OWNER" and not self.overridden(resolved):
            return "owner verdict, needs --override"
        return None

    # --- measuring ------------------------------------------------------------------------------

    def measure(self, path):
        r = {"Files": 0, "Dirs": 0, "Bytes": 0, "EmptyDirs": 0, "ZeroFiles": 0, "Reparse": 0, "Errors": 0, "Exists": False}
        st = lstat(path)
        if st is None:
            return r
        r["Exists"] = True
        a = attrs_of(st)
        if not a & FILE_ATTRIBUTE_DIRECTORY:
            r["Files"] = 1
            r["Bytes"] = st.st_size
            if st.st_size == 0:
                r["ZeroFiles"] = 1
            return r
        if a & FILE_ATTRIBUTE_REPARSE_POINT:
            r["Reparse"] = 1
            return r
        stack = [path]
        while stack:
            self.budget("measure")
            d = stack.pop()
            try:
                items = list_dir(d)
            except OSError:
                r["Errors"] += 1
                continue
            for item in items:
                try:
                    st = item.stat(follow_symlinks=False)
                except OSError:
                    r["Errors"] += 1
                    continue
                ia = attrs_of(st)
                if ia & FILE_ATTRIBUTE_REPARSE_POINT:
                    r["Reparse"] += 1
                elif ia & FILE_ATTRIBUTE_DIRECTORY:
                    r["Dirs"] += 1
                    stack.append(item.path)
                else:
                    r["Files"] += 1
                    r["Bytes"] += st.st_size
                    if st.st_size == 0:
                        r["ZeroFiles"] += 1
            if not items and d != path:
                r["EmptyDirs"] += 1
        return r

    def new_entry(self, path, category, verdict, reason, m=None):
        m = m or self.measure(path)
        return {
            "path": path, "category": category, "verdict": verdict, "reason": reason,
            "files": m["Files"], "dirs": m["Dirs"], "bytes": m["Bytes"], "emptyDirs": m["EmptyDirs"],
            "zeroFiles": m["ZeroFiles"], "reparse": m["Reparse"], "measured": True,
        }

    # --- deleting -------------------------------------------------------------------------------

    def remove_tree(self, path):
        """Delete a directory tree children first; links are unlinked, never walked. Returns the failure count."""
        if is_reparse(path):
            os.rmdir(long_path(path))
            return 0
        failures = 0
        dirs = []
        stack = [long_path(path)]
        while stack:
            self.budget("delete")
            d = stack.pop()
            try:
                items = list_dir(d)
            except OSError:
                failures += 1
                continue
            for item in items:
                try:
                    a = entry_attrs(item)
                    if a & FILE_ATTRIBUTE_REPARSE_POINT:
                        if a & FILE_ATTRIBUTE_DIRECTORY:
                            os.rmdir(item.path)
                        else:
                            os.unlink(item.path)
                    elif a & FILE_ATTRIBUTE_DIRECTORY:
                        stack.append(item.path)
                    else:
                        # git marks its object files read-only, which a plain unlink refuses.
                        clear_readonly(item.path, a)
                        os.unlink(item.path)
                except OSError:
                    failures += 1
            dirs.append(d)
        for d in reversed(dirs):
            try:
                os.rmdir(d)
            except OSError:
                failures += 1
        return failures

    def remove_empty_ancestors(self, path):
        removed = []
        root_full = self.root.rstrip("\\")
        d = parent_of(path)
        while d:
            d = d.rstrip("\\")
            if same(d, root_full) or not under(d, root_full):
                break
            if is_reparse(d) or self.protected(d):
                break
            try:
                if list_dir(d):
                    break
                os.rmdir(long_path(d))
            except OSError:
                break
            removed.append(d)
            d = parent_of(d)
        return removed

    # --- scanning -------------------------------------------------------------------------------

    def admit(self, entries, index, path):
        """The canonical path when it may join the entry list (exists, under the root, not already covered)."""
        if not exists(path):
            return None
        full = full_path(path)
        root_full = full_path(self.root).rstrip("\\")
        if not under(full, root_full):
            return None
        key = full.upper()
        cursor = key
        while cursor:
            if cursor in index:
                return None
            parent = os.path.dirname(cursor)
            if parent == cursor:
                break
            cursor = parent
        return full

    def add_target(self, entries, index, path, category, reason, verdict="PURGE"):
        full = self.admit(entries, index, path)
        if full is None:
            return
        entries.append(self.new_entry(full, category, verdict, reason))
        index.add(full.rstrip("\\").upper())

    def build_container(self, repo_path):
        # A build-output name is only trusted inside a repo carrying a project manifest,
        # and never when that repo is the scan root itself (root\bin is a tool directory).
        if not repo_path or same(repo_path.rstrip("\\"), self.root.rstrip("\\")):
            return False
        if not is_file(os.path.join(repo_path, ".git", "HEAD")):
            return False
        try:
            names = [e.name.upper() for e in list_dir(repo_path) if not entry_attrs(e) & FILE_ATTRIBUTE_DIRECTORY]
        except OSError:
            return False
        return any(fnmatch.fnmatchcase(name, marker.upper()) for marker in BUILD_MARKERS for name in names)

    def default_toolchain(self):
        settings = os.path.join(self.user_home, ".rustup", "settings.toml")
        if os.path.isfile(settings):
            try:
                with open(settings, encoding="utf-8-sig", errors="replace") as f:
                    for text in f:
                        m = TOOLCHAIN_LINE.match(text.rstrip("\r\n"))
                        if m:
                            return m[1]
            except OSError:
                pass
        return "stable-x86_64-pc-windows-msvc"

    def walk_dir(self, d, base, skip):
        """One directory of the scan walk: (child dirs to walk, candidate rows)."""
        self.budget("walk")
        if is_reparse(d):
            return [], []
        try:
            items = list_dir(d)
        except OSError:
            return [], []
        subs, rows = [], []
        for item in items:
            try:
                a = entry_attrs(item)
            except OSError:
                continue
            if a & FILE_ATTRIBUTE_REPARSE_POINT:
                continue
            name = item.name
            full = os.path.join(d, name)
            if a & FILE_ATTRIBUTE_DIRECTORY:
                upper = name.upper()
                if upper == ".GIT" or full.upper() in skip:
                    continue
                if upper in CACHE_NAMES:
                    rows.append((full, "cache-tree", "regenerable cache or dependency tree", "PURGE"))
                    continue
                if upper in BUILD_NAMES and self.build_container(d):
                    rows.append((full, "build-output", "build output inside a repo", "PURGE"))
                    continue
                if ORPHAN_PARENT.search(full) and self.measure(full)["Files"] == 0:
                    rows.append((full, "orphan-shell", "no files, no live task", "OWNER"))
                    continue
                subs.append(full)
                continue
            if BACKUP_NAME.search(name):
                rows.append((full, "backup", "backup of a live file", "PURGE"))
        if not items and not same(d, base):
            st = lstat(d)
            age = datetime.fromtimestamp(st.st_mtime) if st else datetime.now()
            if age < datetime.now() - timedelta(days=self.args.empty_age_days):
                rows.append((d, "empty-shell", "empty directory", "PURGE"))
        return subs, rows

    def scan_entries(self, base):
        entries, index = [], set()
        home, local, roaming = self.user_home, self.local, self.roaming
        explicit = [
            (os.path.join(local, "uv", "cache"), "cache-uv", "uv sync refills"),
            (os.path.join(local, "npm-cache"), "cache-npm", "next npm install refills"),
            (os.path.join(roaming, "npm", "node_modules"), "cache-npm-global", "global npm tree, reinstalls"),
            (os.path.join(home, ".cache", "opencode"), "cache-opencode", "opencode package cache"),
            (os.path.join(home, ".bun", "install", "cache"), "cache-bun", "bun install refills"),
            (os.path.join(home, "go", "pkg", "mod"), "cache-go", "go mod download refills"),
            (os.path.join(home, ".cargo", "registry"), "cache-cargo", "cargo fetch refills"),
            (os.path.join(home, ".cargo", "git"), "cache-cargo-git", "cargo refetches the checkout"),
            (os.path.join(home, ".nuget", "packages"), "cache-nuget", "dotnet restore refills"),
            (os.path.join(home, ".wox", "updates"), "cache-wox", "installer downloads"),
            (os.path.join(home, ".wox", "filesearch"), "cache-wox", "rebuilt index"),
            (os.path.join(home, ".wox", "log"), "log-wox", "logs"),
            (os.path.join(home, ".wox", "cache"), "cache-wox", "cache"),
            (os.path.join(home, ".wox", "backup"), "backup-wox", "old snapshots"),
            (os.path.join(home, ".claude", "plugins", "cache"), "cache-plugin", "plugin cache"),
            (os.path.join(home, ".claude", "plugins", "marketplaces"), "cache-plugin", "marketplace clones"),
            (os.path.join(home, ".vscode-insiders", "agent-plugins"), "cache-plugin", "extension clones"),
            (os.path.join(home, ".gemini", "antigravity-cli"), "log-cli", "CLI logs and scratch"),
            (os.path.join(home, ".omo", "agent", "logs"), "log-agent", "runtime logs"),
            (os.path.join(home, ".omo", "logs"), "log-agent", "runtime logs"),
            (os.path.join(home, ".local", "state", "fresh", "logs"), "log-tool", "tool logs"),
            (os.path.join(home, ".claude", "file-history"), "history", "per-file edit history"),
            (os.path.join(home, ".local", "backups"), "backup-snapshot", "dated snapshot, purpose served"),
        ]
        for path, category, reason in explicit:
            self.budget("explicit targets")
            self.add_target(entries, index, path, category, reason)

        versions = os.path.join(home, ".local", "share", "claude", "versions")
        if is_dir(versions):
            items = sorted(list_dir(versions), key=lambda e: e.stat(follow_symlinks=False).st_mtime, reverse=True)
            for item in items[1:]:
                self.add_target(entries, index, item.path, "version-superseded", "newer launcher build present")
        toolchains = os.path.join(home, ".rustup", "toolchains")
        if is_dir(toolchains):
            keep = self.default_toolchain()
            for item in list_dir(toolchains):
                if entry_attrs(item) & FILE_ATTRIBUTE_DIRECTORY and not same(item.name, keep):
                    self.add_target(entries, index, item.path, "version-superseded", f"active toolchain is {keep}")

        dev = os.path.join(home, "Dev")
        if is_dir(dev):
            try:
                children = list_dir(dev)
            except OSError:
                children = []
            for item in children:
                if entry_attrs(item) & FILE_ATTRIBUTE_DIRECTORY and item.name.upper().endswith("_TMP"):
                    self.add_target(entries, index, item.path, "scratch", "test fixtures and probe output")
            fixups = os.path.join(dev, "fixups")
            if is_dir(fixups):
                self.add_target(entries, index, fixups, "scratch", "third-party rebase scratch")

        temp = os.path.join(local, "Temp")
        if is_dir(temp):
            cutoff = (datetime.now() - timedelta(days=self.args.temp_age_days)).timestamp()
            try:
                children = list_dir(temp)
            except OSError:
                children = []
            for item in children:
                try:
                    old = item.stat(follow_symlinks=False).st_mtime < cutoff
                except OSError:
                    continue
                if old:
                    self.add_target(entries, index, item.path, "temp", f"older than {self.args.temp_age_days} days")

        # The walk: each level's listings run on a thread pool; a target is never descended into.
        skip = {e["path"].upper() for e in entries}
        rows = []
        level = [base]
        with ThreadPoolExecutor(WORKERS) as ex:
            while level:
                nxt = []
                for subs, found in ex.map(lambda d: self.walk_dir(d, base, skip), level):
                    nxt += subs
                    rows += found
                level = nxt
        rows.sort(key=lambda r: r[0].upper().split("\\"))
        admitted = []
        for path, category, reason, verdict in rows:
            full = self.admit(entries, index, path)
            if full is None:
                continue
            admitted.append((full, category, reason, verdict))
            index.add(full.rstrip("\\").upper())
        with ThreadPoolExecutor(WORKERS) as ex:
            measured = list(ex.map(lambda r: self.measure(r[0]), admitted))
        for (full, category, reason, verdict), m in zip(admitted, measured):
            entries.append(self.new_entry(full, category, verdict, reason, m))
        return entries

    # --- modes ----------------------------------------------------------------------------------

    @staticmethod
    def totals(entries):
        t = {"Paths": 0, "Files": 0, "Dirs": 0, "Bytes": 0, "EmptyDirs": 0, "ZeroFiles": 0}
        for e in entries:
            t["Paths"] += 1
            t["Files"] += e["files"]
            t["Dirs"] += e["dirs"]
            t["Bytes"] += e["bytes"]
            t["EmptyDirs"] += e["emptyDirs"]
            t["ZeroFiles"] += e["zeroFiles"]
        return t

    def split(self, entries):
        accepted, refused = [], []
        for e in entries:
            reason = self.test_entry(e)
            if reason:
                refused.append({"Entry": e, "Reason": reason})
            elif e.get("measured"):
                accepted.append(e)
            else:
                accepted.append(self.new_entry(str(e["path"]), e["category"], e["verdict"], e["reason"]))
        return accepted, refused

    def show(self, e, state):
        verdict = "" if e["verdict"] is None else e["verdict"]
        self.line(f"{state:<8} {e['files']:>9} {e['dirs']:>8} {format_size(e['bytes']):>10}  {verdict}  [{e['category']}] {e['path']}")

    def report(self, mode, accepted, refused, tail=""):
        t = self.totals(accepted)
        self.line("")
        self.line(
            f"{mode:<6} root={self.root}  paths={t['Paths']}  files={t['Files']:,}  dirs={t['Dirs']:,}  bytes={format_size(t['Bytes'])}"
            f"  emptyDirs={t['EmptyDirs']:,}  zeroFiles={t['ZeroFiles']:,}  refused={len(refused)}{tail}"
        )
        for e in sorted(accepted, key=lambda e: -e["files"]):
            self.show(e, "PURGE")
        for r in refused:
            self.show(r["Entry"], "REFUSED")
            self.line(f"         reason: {r['Reason']}")
        return t

    def scan_mode(self):
        accepted, refused = self.split(self.scan_entries(self.root))
        t = self.report("SCAN", accepted, refused)
        os.makedirs(self.out_dir, exist_ok=True)
        path = os.path.join(self.out_dir, f"Purge Manifest - {self.stamp}.json")
        doc = {"root": self.root, "generated": now_iso(), "totals": t, "entries": accepted, "refused": refused}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        self.line(f"manifest: {path}")
        if self.json:
            print(json.dumps(doc, indent=2, ensure_ascii=False))
        if refused:
            self.exit = 3

    def read_entries(self):
        if not self.args.manifest:
            return self.scan_entries(self.root)
        if not os.path.isfile(self.args.manifest):
            raise Fatal(f"manifest not found: {self.args.manifest}")
        with open(self.args.manifest, encoding="utf-8-sig") as f:
            doc = json.load(f)
        if isinstance(doc, dict) and "generated" in doc:
            self.manifest_generated = parse_iso(doc["generated"])
        rows = doc.get("entries") if isinstance(doc, dict) else None
        if rows is None:
            rows = []
        elif not isinstance(rows, list):
            rows = [rows]
        items = []
        for raw in rows:
            if raw is None:
                continue
            if not isinstance(raw, dict) or "path" not in raw:
                raise Fatal("manifest row has no path property")
            items.append({
                "path": raw["path"],
                "category": raw.get("category", "manifest"),
                "verdict": raw["verdict"] if "verdict" in raw else "MISSING",
                "reason": raw.get("reason", ""),
                "files": 0, "dirs": 0, "bytes": 0, "emptyDirs": 0, "zeroFiles": 0, "reparse": 0,
            })
        return items

    def plan_mode(self):
        accepted, refused = self.split(self.read_entries())
        t = self.report("PLAN", accepted, refused, "  apply=no")
        if self.json:
            print(json.dumps({"mode": "plan", "totals": t, "entries": accepted, "refused": refused}, indent=2, ensure_ascii=False))
        self.exit = 1 if refused else 0

    def apply_mode(self):
        entries = self.read_entries()
        os.makedirs(self.out_dir, exist_ok=True)
        journal = os.path.join(self.out_dir, f"Purge Journal - {self.stamp}.jsonl")

        def record(**event):
            with open(journal, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, separators=(",", ":"), ensure_ascii=False) + "\n")

        removed = refused = failures = 0
        done = set()
        before = {"Files": 0, "Dirs": 0, "Bytes": 0, "EmptyDirs": 0, "ZeroFiles": 0}
        abort = None

        self.enter_lock()
        record(event="start", root=self.root, pid=os.getpid(), utc=datetime.now(timezone.utc).isoformat(),
               entries=len(entries), budgetMinutes=self.args.max_minutes)
        try:
            accepted, refused_rows = self.split(entries)
            refused = len(refused_rows)
            for r in refused_rows:
                record(event="refused", path=r["Entry"]["path"], reason=r["Reason"])
                self.line(f"REFUSED {r['Entry']['path']} :: {r['Reason']}")
            if len(accepted) > self.args.max_paths and not self.args.force:
                raise Fatal(f"manifest holds {len(accepted)} paths, above --max-paths {self.args.max_paths} (raise it or pass --force)")

            for e in sorted(accepted, key=lambda e: -len(e["path"])):
                self.budget("apply")
                if failures >= self.args.max_failures:
                    raise Fatal(f"failure ceiling {self.args.max_failures} reached")
                path = e["path"]
                if path.upper() in done:
                    continue
                live = self.measure(path)
                if not live["Exists"]:
                    continue
                if not self.args.force and self.manifest_generated and exists(path):
                    newest = datetime.fromtimestamp(lstat(path).st_mtime, timezone.utc)
                    if newest > self.manifest_generated:
                        refused += 1
                        record(event="refused", path=path, reason="changed after the manifest was written")
                        self.line(f"REFUSED {path} :: changed after the manifest was written (pass --force to ignore)")
                        continue
                was_overridden = bool(self.protected(path) or verdict_of(e) == "OWNER")
                self.line(f"DELETE  files={live['Files']} dirs={live['Dirs']} {format_size(live['Bytes'])}  {'(override) ' if was_overridden else ''}{path}")
                record(event="delete", path=path, category=e["category"], verdict=e["verdict"], override=was_overridden,
                       files=live["Files"], dirs=live["Dirs"], bytes=live["Bytes"], emptyDirs=live["EmptyDirs"],
                       zeroFiles=live["ZeroFiles"], reparse=live["Reparse"])
                try:
                    a = attrs(path)
                    if a is not None and not a & FILE_ATTRIBUTE_DIRECTORY:
                        if not a & FILE_ATTRIBUTE_REPARSE_POINT:
                            clear_readonly(long_path(path), a)
                        os.unlink(long_path(path))
                    else:
                        bad = self.remove_tree(path)
                        if bad > 0:
                            raise OSError(f"{bad} entries could not be removed")
                    removed += 1
                    done.add(path.upper())
                    for k in before:
                        before[k] += live[k]
                    record(event="removed", path=path)
                    for gone in self.remove_empty_ancestors(path):
                        before["Dirs"] += 1
                        record(event="prune-empty-parent", path=gone)
                except Exception as error:  # every failure is counted and journalled, never swallowed
                    failures += 1
                    record(event="failed", path=path, error=str(error))
                    self.line(f"FAILED  {path} :: {error}")
        except BudgetExceeded as error:
            abort = str(error)
            self.exit = 4
        except Exception as error:
            abort = str(error)
            self.exit = 1
        finally:
            try:
                residual = self.scan_entries(self.root)
            except Exception:
                residual = []
            left, left_refused = [], 0
            for e in residual:
                if self.test_entry(e):
                    left_refused += 1
                else:
                    left.append(e)
            after = self.totals(left)
            summary = {
                "mode": "apply", "root": self.root, "journal": journal,
                "removed_paths": removed, "refused_paths": refused, "failed_paths": failures,
                "deleted_files": before["Files"], "deleted_dirs": before["Dirs"], "deleted_bytes": before["Bytes"],
                "deleted_empty_dirs": before["EmptyDirs"], "deleted_zero_files": before["ZeroFiles"],
                "residual_paths": after["Paths"], "residual_files": after["Files"], "residual_dirs": after["Dirs"],
                "aborted": bool(abort), "abort_reason": abort,
            }
            record(event="abort" if abort else "done", **summary)
            self.exit_lock()

            self.line("")
            if abort:
                self.line(f"ABORT  {abort}")
            self.line(f"APPLY  removed={removed}  refused={refused}  failed={failures}")
            self.line(f"       deleted files={before['Files']:,} dirs={before['Dirs']:,} bytes={format_size(before['Bytes'])} emptyDirs={before['EmptyDirs']:,} zeroFiles={before['ZeroFiles']:,}")
            self.line(f"       residue paths={after['Paths']} files={after['Files']:,} dirs={after['Dirs']:,} (refused candidates: {left_refused})")
            self.line(f"       journal: {journal}")
            if self.json:
                print(json.dumps(summary, indent=2, ensure_ascii=False))
            if not abort:
                if failures > 0 or refused > 0:
                    self.exit = 3
                elif after["Paths"] > 0:
                    self.exit = 2
                else:
                    self.exit = 0


def verdict_of(entry):
    v = entry.get("verdict")
    return None if v is None else str(v).upper()


def pid_alive(pid):
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # access denied: the process exists
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class Parser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write(f"purge: {message}\n")
        sys.exit(1)


def parse_args(argv):
    p = Parser(prog="purge.py", description=__doc__.split("\n")[0], allow_abbrev=False)
    p.add_argument("--root", default=os.environ.get("USERPROFILE") or os.path.expanduser("~"))
    p.add_argument("--manifest")
    p.add_argument("--scan", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--override", action="extend", nargs="+", default=[])
    p.add_argument("--out-dir")
    p.add_argument("--temp-age-days", type=int, default=2)
    p.add_argument("--empty-age-days", type=int, default=1)
    p.add_argument("--max-minutes", type=int, default=60)
    p.add_argument("--max-paths", type=int, default=5000)
    p.add_argument("--max-failures", type=int, default=25)
    p.add_argument("--lock-file")
    p.add_argument("--force", action="store_true")
    p.add_argument("--json", action="store_true")
    return p.parse_args(argv)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = parse_args(argv)
    # An override that covers the root is not an override: it disables the deny list for everything.
    for item in args.override:
        if same(full_path(item).rstrip("\\"), full_path(args.root).rstrip("\\")):
            sys.stderr.write("purge: --override may name a path inside the root, never the root itself\n")
            return 1
    engine = None
    try:
        root = full_path(args.root)
        if not os.path.isdir(root):
            raise Fatal(f"root not found: {root}")
        if DRIVE_ROOT.match(root):
            raise Fatal("refusing to run against a drive root")
        args.root = root.rstrip("\\")
        if args.scan and args.apply:
            raise Fatal("choose one of --scan or --apply")
        if args.apply and not args.manifest:
            raise Fatal("--apply needs --manifest")
        engine = Engine(args)
        if args.scan:
            engine.scan_mode()
        elif args.apply:
            engine.apply_mode()
        else:
            engine.plan_mode()
    except BudgetExceeded as error:
        sys.stderr.write(f"purge: aborted, {error}\n")
        if engine:
            engine.exit_lock()
        return 4
    except Exception as error:
        sys.stderr.write(f"purge: {error}\n")
        if engine:
            engine.exit_lock()
        return 1
    return engine.exit


if __name__ == "__main__":
    sys.exit(main())
