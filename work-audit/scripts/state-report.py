# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
import argparse
import fnmatch
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SELF = Path(__file__).resolve()


def load_record():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("record", SELF.with_name("record.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


RC = load_record()
SUBPROCESS_TIMEOUT = 30
SKIP_DIRS = RC.SKIP_DIR_NAMES
MAX_FILES = _env_int("WORK_AUDIT_MAX_FILES", 20000)
INDEX_TIMEOUT = _env_float("WORK_AUDIT_INDEX_TIMEOUT", 20)
SCAN_TRUNCATED = []
SUBPROCESS_TIMEOUTS = []
_CTX = {}
_DELETED = {}
_LS = {}
_DEADLINE = None


class _Truncated(Exception):
    pass


def _subprocess_timeout():
    return _env_float("WORK_AUDIT_SUBPROCESS_TIMEOUT", SUBPROCESS_TIMEOUT)


WORKERS = max(1, _env_int("WORK_AUDIT_WORKERS", 16))
# Unset caps grow with scope so a large legitimate scope completes instead of truncating.
INDEX_TIMEOUT_PER_REPO = 1.0
MAX_FILES_PER_REPO = 4000
FAIL_FAST_EXIT = 3


def index_timeout():
    if "WORK_AUDIT_INDEX_TIMEOUT" in os.environ:
        return INDEX_TIMEOUT
    return INDEX_TIMEOUT + INDEX_TIMEOUT_PER_REPO * len(REPOS)


def max_files():
    if "WORK_AUDIT_MAX_FILES" in os.environ:
        return MAX_FILES
    return max(MAX_FILES, MAX_FILES_PER_REPO * len(REPOS))


def pmap(fn, items):
    """fn over items on a thread pool, results in order: process spawn and hashing dominate, so independent items overlap."""
    items = list(items)
    if len(items) < 2 or WORKERS < 2:
        return [fn(x) for x in items]
    with ThreadPoolExecutor(min(WORKERS, len(items))) as ex:
        return list(ex.map(fn, items))


def check_deadline():
    if _DEADLINE is not None and time.time() >= _DEADLINE:
        raise _Truncated("wall-clock cap exceeded")


SECRET = re.compile(
    r"^\.env(?!\.(example|sample|template)$)|^auth\.json$|credential|\.pem$|\.key$|^mcp-auth\.json$|^\.npmrc$|^\.netrc$|^id_(rsa|ed25519)$",
    re.I,
)
TEST = re.compile(
    r"(^|/)(tests?|__tests__)/|(^|/)test_[^/]*\.py$|\.test\.|_test\.|\.spec\."
)
DOC_EXT = {".md", ".yaml", ".yml", ".txt", ".json", ".jsonc"}
CODE_EXT = {
    ".py",
    ".ps1",
    ".psm1",
    ".md",
    ".ts",
    ".tsx",
    ".js",
    ".cs",
    ".sh",
    ".yml",
    ".yaml",
    ".toml",
}
PLAN = re.compile(
    r"(^|[^a-z])(plan|spec|todo|handoff|roadmap|backlog|progress\.ya?ml)", re.I
)
UNCHECKED = re.compile(r"^\s*[-*]\s*\[ \]", re.M)

REPOS, FILES, DIRS, CACHES = [], [], [], []
REPOS_SET = set()
IGN = {}
RPT = defaultdict(lambda: defaultdict(dict))
FBR = defaultdict(list)
PLAN_STATS = {}
SINCE = timedelta(hours=24)
SINCE_GIT = "24 hours ago"


def _limit(base=None, deadline=None):
    limit = _subprocess_timeout() if base is None else base
    deadline = _DEADLINE if deadline is None else deadline
    if deadline is not None:
        limit = min(limit, max(0.01, deadline - time.time()))
    return limit


def proc(cmd, cwd=None, timeout=None, deadline=None):
    """RC.proc_run under the per-index deadline (or an explicit one); a timeout is recorded."""
    rc, out, err, timed_out = RC.proc_run(
        cmd, cwd=cwd, timeout=_limit(timeout, deadline)
    )
    if timed_out:
        SUBPROCESS_TIMEOUTS.append(
            {"cmd": [str(c) for c in cmd], "cwd": str(cwd) if cwd is not None else None}
        )
    return rc, out, err, timed_out


def run(cmd, cwd=None, timeout=None, deadline=None):
    rc, out, _err, timed_out = proc(cmd, cwd, timeout, deadline)
    if timed_out:
        return 1, ""
    return (rc if rc is not None else 1), out


def git(repo, *a):
    rc, out = run(
        [(RC.git_bin() or "git"), "-c", "core.quotepath=off", "-C", str(repo), *a]
    )
    return [l for l in out.splitlines() if l.strip()] if rc == 0 else []


def rec(repo, idx, key, val):
    if repo is not None:
        RPT[repo][str(idx)][key] = val


def acc(repo, idx, key, *vals):
    if repo is not None:
        RPT[repo][str(idx)].setdefault(key, []).extend(vals)


@lru_cache(maxsize=None)
def gh_bin():
    return shutil.which("gh")


@lru_cache(maxsize=None)
def gh_ok():
    if os.environ.get("WORK_AUDIT_NO_GH"):
        return False
    gb = gh_bin()
    return bool(gb) and run([gb, "auth", "status"])[0] == 0


@lru_cache(maxsize=None)
def gh_auth_error():
    if gh_ok():
        return ""
    if os.environ.get("WORK_AUDIT_NO_GH"):
        return "gh disabled via WORK_AUDIT_NO_GH"
    gb = gh_bin()
    if not gb:
        return "gh not found on PATH"
    rc, out, err, timed_out = proc([gb, "auth", "status"])
    if timed_out:
        return f"gh auth status timed out after {_subprocess_timeout():g}s"
    return (
        (err or "") + (out or "")
    ).strip() or f"gh auth status exited {rc} with no error text"


# The gh list calls indices 11 and 14 make, started when collect() begins so their
# network wait overlaps the git-bound indices instead of following them (#128).
GH_LISTS = (
    ("issue", "list", "--state", "open", "--json", "number", "--limit", "100"),
    ("pr", "list", "--state", "open", "--json", "number", "--limit", "100"),
    ("pr", "list", "--state", "merged", "--limit", "100", "--json", "mergeCommit"),
)
_GH_PREFETCH = {}


def prefetch_gh(ex):
    if not gh_ok():
        return
    for r in REPOS:
        for a in GH_LISTS:
            _GH_PREFETCH[(r, a)] = ex.submit(
                lambda r=r, a=a: _gh_call(r, a, math.inf) if origin_url(r) else None
            )


def gh_run(repo, *a):
    fut = _GH_PREFETCH.pop((repo, a), None)
    if fut is not None and (res := fut.result()) is not None:
        return res
    return _gh_call(repo, a)


def _gh_call(repo, a, deadline=None):
    gb = gh_bin()
    if not gb:
        return 1, "", "gh not found on PATH"
    cmd = [gb, *a]
    rc, out, err, timed_out = proc(cmd, repo, deadline=deadline)
    if timed_out:
        return 1, out, f"gh timed out after {_subprocess_timeout():g}s"
    if rc is None:
        return 1, out, err or "gh failed to start"
    return rc, out, err


def gh_json(repo, *a):
    if not gh_ok():
        return None
    rc, out, _err = gh_run(repo, *a)
    try:
        return json.loads(out) if rc == 0 else None
    except ValueError:
        return None


@lru_cache(maxsize=None)
def st(p):
    try:
        return p.stat()
    except OSError:
        return None


@lru_cache(maxsize=None)
def txt(p):
    """File text, read once per run: several indices scan the same files."""
    check_deadline()
    s = st(p)
    if not s or s.st_size > 1_000_000:
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def mt(p):
    s = st(p)
    return datetime.fromtimestamp(s.st_mtime).strftime("%Y-%m-%d %H:%M") if s else "?"


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f}{u}" if u == "B" else f"{n:.1f}{u}"
        n /= 1024


def du(p):
    if p.is_file():
        s = st(p)
        return s.st_size if s else 0
    total = 0
    for dp, _, fns, _ in BoundedScan(p).walk():
        check_deadline()
        for f in fns:
            s = st(dp / f)
            total += s.st_size if s else 0
    return total


def under(p, base):
    """p's path below base in posix form, or None; string work, pathlib's relative_to is slow at 10k+ files."""
    s, b = str(p), str(base)
    if s.startswith(b) and s[len(b) : len(b) + 1] in (os.sep, "/"):
        return s[len(b) + 1 :].replace(os.sep, "/")
    return None


def rel(p):
    for base in REPOS:
        r = under(p, base.parent)
        if r is not None:
            return r
    return str(p)


def repo_of(p):
    for a in p.parents:
        if a in REPOS_SET:
            return a
    return None


def sample(items, n=4):
    items = list(items)
    return [*items[:n]] + ([f"(+{len(items) - n} more)"] if len(items) > n else [])


def atomic_write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    return RC.atomic_replace(tmp, path)


class BoundedScan:
    """Top-down walk: skips SKIP_DIRS and caller skips, never follows symlinked dirs,
    stops at the file-count cap by raising _Truncated."""

    def __init__(self, root, skip=(), prune_git=False):
        self.root = Path(root)
        self.skip = {Path(s) for s in skip}
        self.prune_git = prune_git
        self.files = 0

    def walk(self):
        stack = [self.root]
        while stack:
            check_deadline()
            dp = stack.pop()
            try:
                children = sorted(dp.iterdir())
            except OSError:
                continue
            dns, fns, skipped = [], [], 0
            for e in children:
                if e.name in SKIP_DIRS or e in self.skip:
                    skipped += 1
                    continue
                try:
                    link, isdir = RC.dir_is_link(e), e.is_dir()
                except OSError:
                    continue
                if link and isdir:
                    continue
                (dns if isdir else fns).append(e.name)
                if not isdir:
                    self.files += 1
                    if self.files > max_files():
                        raise _Truncated(
                            f"file-count cap {max_files()} exceeded at {dp}"
                        )
            yield dp, dns, fns, skipped
            for d in reversed(dns):
                if self.prune_git and (dp / d / ".git").exists():
                    continue
                stack.append(dp / d)


def reset_scan_state():
    del SCAN_TRUNCATED[:]
    _GH_PREFETCH.clear()
    RC.NOT_SCANNED.clear()
    del SUBPROCESS_TIMEOUTS[:]
    _CTX.clear()
    _DELETED.clear()
    _LS.clear()
    global _DEADLINE
    _DEADLINE = None
    for f in (
        st,
        sha,
        txt,
        adrs,
        gh_ok,
        gh_bin,
        gh_auth_error,
        owners,
        extra_root_repos,
    ):
        f.cache_clear()


def setup(repos):
    for c in (REPOS, FILES, DIRS, CACHES):
        c.clear()
    for c in (REPOS_SET, PLAN_STATS, IGN, RPT, FBR):
        c.clear()
    for f in (
        st,
        sha,
        txt,
        adrs,
        gh_ok,
        gh_bin,
        gh_auth_error,
        owners,
        extra_root_repos,
    ):
        f.cache_clear()
    del SCAN_TRUNCATED[:]
    _CTX.clear()
    _DELETED.clear()
    _LS.clear()
    REPOS[:] = sorted(repos)
    REPOS_SET.update(REPOS)
    dirs = set()
    listed = pmap(
        lambda r: (
            git(r, "ls-files", "-o", "-i", "--exclude-standard", "--directory"),
            git(r, "ls-files", "-co", "--exclude-standard"),
        ),
        REPOS,
    )
    links = {}
    for r, (ignored, tracked) in zip(REPOS, listed):
        IGN[r] = [r / x.rstrip("/") for x in ignored]
        CACHES.extend(d for d in IGN[r] if d.name == ".pytest_cache")
        _LS[r] = tracked
        for name in dict.fromkeys(_LS[r]):
            check_deadline()
            p = r / name
            rel_parts = p.relative_to(r).parts
            if any(part in SKIP_DIRS for part in rel_parts[:-1]):
                continue
            cand, linked = r, False
            for part in rel_parts[:-1]:
                cand = cand / part
                if cand not in links:
                    links[cand] = RC.dir_is_link(cand)
                if links[cand]:
                    linked = True
                    break
            if linked:
                continue
            if len(FILES) >= max_files():
                SCAN_TRUNCATED.append(
                    f"file-count cap {max_files()} exceeded while listing {r.name}"
                )
                break
            if SECRET.search(p.name) or not p.is_file():
                continue
            FILES.append(p)
            FBR[r].append(p)
            dirs.update(a for a in (p.parent, *p.parents) if a == r or r in a.parents)
    DIRS[:] = sorted(dirs)
    # Warm the text cache concurrently: reads (and AV scans on open) overlap across threads.
    pmap(txt, [f for f in FILES if f.suffix.lower() in CODE_EXT | DOC_EXT])


def default_branch(r):
    for b in ("master", "main"):
        if git(r, "rev-parse", "--verify", "-q", b):
            return b


def md_files():
    return [
        f
        for f in FILES
        if f.suffix.lower() == ".md" and "fixtures" not in f.as_posix().lower()
    ]


@lru_cache(maxsize=None)
def extra_root_repos():
    if "WORK_AUDIT_ROOTS" in os.environ:
        roots = [Path(x) for x in os.environ["WORK_AUDIT_ROOTS"].split(os.pathsep) if x]
    else:
        roots = [Path.home() / "Dev"]
    out = []
    for rt in roots:
        try:
            if not rt.is_dir():
                continue
        except OSError:
            continue
        for c in RC.discover_repos(rt):
            if c not in REPOS_SET and c not in out:
                out.append(c)
    return out


OWNERS_ERROR = ""


@lru_cache(maxsize=None)
def owners():
    global OWNERS_ERROR
    if "WORK_AUDIT_OWNERS" in os.environ:
        OWNERS_ERROR = ""
        return [x for x in re.split(r"[;:]", os.environ["WORK_AUDIT_OWNERS"]) if x]
    if gh_ok():
        rc, out, err = gh_run(None, "api", "user", "--jq", ".login")
        if rc == 0 and out.strip():
            OWNERS_ERROR = ""
            return [out.strip().splitlines()[0]]
        OWNERS_ERROR = (
            (err or "") + (out or "")
        ).strip() or "gh api user failed with no error text"
        return []
    OWNERS_ERROR = gh_auth_error() or "gh unavailable"
    return []


def origin_url(r):
    ctx = _CTX.get(r) or {}
    if "origin" not in ctx:
        o = git(r, "remote", "get-url", "origin")
        ctx = {**ctx, "origin": o[0].strip() if o else ""}
        _CTX[r] = ctx
    return ctx["origin"]


def origin_owner(url):
    m = re.search(r"github\.com[:/]([^/\s]+)/", url or "", re.I)
    return m.group(1) if m else None


def normalize_origin(url):
    u = (url or "").strip()
    m = re.match(
        r"(?:git@|ssh://git@|https?://)?([^/:\s]+)[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$",
        u,
        re.I,
    )
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}".lower()
    return re.sub(r"\.git$", "", u.rstrip("/"), flags=re.I).lower() or ""


def current_branch(repo):
    b = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    return b[0].strip() if b else ""


def repo_ctx(repo):
    ctx = _CTX.get(repo) or {}
    if "branch" not in ctx:
        ctx = {
            **ctx,
            "branch": current_branch(repo),
            "uncommitted": len(git(repo, "status", "--short")),
            "unpushed": len(
                git(repo, "log", "--branches", "--not", "--remotes", "--oneline")
            ),
        }
        _CTX[repo] = ctx
    return ctx


def path_facts(p):
    p = Path(p)
    facts = {"files": 1, "newest_mtime": mt(p)}
    if p.is_dir():
        n, newest = 0, 0.0
        for dp, _, fns, _ in BoundedScan(p).walk():
            n += len(fns)
            for f in fns:
                s = st(dp / f)
                if s and s.st_mtime > newest:
                    newest = s.st_mtime
        facts["files"] = n
        facts["newest_mtime"] = (
            datetime.fromtimestamp(newest).strftime("%Y-%m-%d %H:%M")
            if newest
            else mt(p)
        )
    repo = repo_of(p)
    if repo is None:
        try:
            repo = RC.toplevel(p)
        except (OSError, ValueError):
            repo = None
    if repo is not None:
        facts.update(repo_ctx(repo))
    else:
        facts.update({"branch": None, "uncommitted": None, "unpushed": None})
    return facts


def load_config():
    path = Path(
        os.environ.get("WORK_AUDIT_CONFIG_FILE") or (SELF.parent / "work-audit.toml")
    )
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, ValueError):
        return [], set()
    return [str(x) for x in data.get("config_roots", []) or []], set(
        data.get("allow", []) or []
    )


def config_entries():
    roots, allow = load_config()
    out = []
    for name in roots:
        d = Path(name)
        if not d.is_absolute():
            d = Path.home() / name
        if not d.is_dir():
            continue
        try:
            ents = sorted(e.name for e in d.iterdir())
        except OSError:
            continue
        out.append({"root": str(d), "entries": [e for e in ents if e not in allow]})
    return out


def i1():
    out, dirty = [], 0

    def status(r):
        check_deadline()
        return (
            git(r, "status", "--short", "--branch"),
            len(git(r, "ls-files", "--others", "--exclude-standard")),
        )

    for r, (l, unt) in zip(REPOS, pmap(status, REPOS)):
        n = max(len(l) - 1, 0)
        dirty += n > 0
        rec(r, 1, "status", l)
        rec(r, 1, "counts", {"dirty": n, "untracked": unt})
        out.append(f"{r.name}: {l[0] if l else '?'} ({n} changes, {unt} untracked)")
        if SCAN_TRUNCATED:
            rec(r, 1, "scan_truncated", list(SCAN_TRUNCATED))
    extras = extra_root_repos()
    check_deadline()

    def extra_line(r):
        check_deadline()
        l = git(r, "status", "--short", "--branch")
        n = max(len(l) - 1, 0)
        unt = len(git(r, "ls-files", "--others", "--exclude-standard"))
        return f"{r.name}: {l[0] if l else '?'} ({n} changes, {unt} untracked)"

    out.extend(pmap(extra_line, extras))
    extra = f"; roots: {len(extras)} repos" if extras else ""
    if RC.NOT_SCANNED:
        skipped = sorted(RC.NOT_SCANNED)
        for r in REPOS:
            rec(r, 1, "not_scanned", skipped)
        extra += f"; not scanned: {', '.join(skipped)} (system temp, cleared by purge-safety)"
    trunc = f"; truncated: {'; '.join(SCAN_TRUNCATED)}" if SCAN_TRUNCATED else ""
    return f"{len(REPOS)} repos, {dirty} dirty{extra}{trunc}", out, 0


def i2():
    out, tot = [], [0, 0, 0, 0]
    own = owners() if "WORK_AUDIT_OWNERS" in os.environ else None

    def facts(r):
        check_deadline()
        d = default_branch(r)
        origin_url(r)
        return (
            git(r, "branch", "-a"),
            git(r, "worktree", "list"),
            git(r, "stash", "list"),
            git(r, "log", "--branches", "--not", "--remotes", "--oneline"),
            d,
            git(r, "branch", "--merged", d) if d else [],
        )

    for r, (br, wt, stash, up, d, merged_raw) in zip(REPOS, pmap(facts, REPOS)):
        loc = [b for b in br if "remotes/" not in b]
        merged = [
            b.strip() for b in merged_raw if not b.startswith("*") and b.strip() != d
        ]
        for i, v in enumerate((len(wt) - 1, len(stash), len(up), len(merged))):
            tot[i] += v
        url = origin_url(r)
        owner = origin_owner(url)
        if url and own is None:
            own = owners()
        lowered = {o.lower() for o in (own or [])}
        third = bool(url and owner and owner.lower() not in lowered)
        rec(r, 2, "origin", url)
        rec(r, 2, "owner", owner)
        rec(r, 2, "third_party", third)
        nondef = sorted(
            {b.strip().lstrip("* ").strip() for b in br if "remotes/" not in b}
            - {d or "", ""}
        )
        rec(r, 2, "non_default_branches", nondef)
        for k, v in (
            ("branches", br),
            ("worktrees", wt),
            ("stashes", stash),
            ("unpushed", up),
            ("merged_undeleted", merged),
        ):
            rec(r, 2, k, v)
        tag = " (third-party)" if third else ""
        out.append(
            f"{r.name}: local {len(loc)}, remote {len(br) - len(loc)}, worktrees {len(wt)}, stashes {len(stash)}, unpushed {len(up)}, merged-undeleted {merged or 0}"
            + tag
        )
    seen = {}
    pmap(origin_url, extra_root_repos())
    for r in (*REPOS, *extra_root_repos()):
        u = normalize_origin(origin_url(r))
        if u:
            seen.setdefault(u, []).append(r)
    dups = {u: rs for u, rs in seen.items() if len(rs) > 1}
    for u, rs in dups.items():
        for r in rs:
            if r in REPOS_SET:
                rec(r, 2, "duplicate_origin", [str(x) for x in rs if x != r])
        out.append(f"duplicate origin {u}: " + ", ".join(str(x) for x in rs))
    t = sum(1 for r in REPOS if RPT[r].get("2", {}).get("third_party"))
    suffix = (f", third-party clones {t}" if t else "") + (
        f", duplicate-origin groups {len(dups)}" if dups else ""
    )
    return (
        f"extra worktrees {tot[0]}, stashes {tot[1]}, unpushed commits {tot[2]}, merged-undeleted branches {tot[3]}{suffix}",
        out,
        0,
    )


def is_plan(p):
    s = "/" + p.as_posix().lower()
    return p.suffix.lower() in DOC_EXT and (PLAN.search(p.name) or "/plans/" in s)


def plan_stats():
    if not PLAN_STATS:
        for p in FILES:
            if is_plan(p):
                t = txt(p)
                PLAN_STATS[p] = (
                    len(UNCHECKED.findall(t)),
                    len(re.findall(r"^\s*\W*status\b", t, re.I | re.M)),
                )
    return PLAN_STATS


REMAINING_ZERO = re.compile(r"Remaining items:\s*0\b")
DONE_STATUS = re.compile(r"status\s*:\s*(done|complete)\b", re.I)
CHECKED = re.compile(r"^\s*[-*]\s*\[[xX]\]", re.M)


def classify_plan(t):
    boxes = len(UNCHECKED.findall(t))
    if (
        REMAINING_ZERO.search(t)
        or (boxes == 0 and CHECKED.search(t))
        or DONE_STATUS.search(t)
    ):
        return "executed"
    if boxes or PLAN_STATUS.search(t):
        return "open"
    return "unknown"


def i3():
    ps = plan_stats()
    states = {}
    for p in ps:
        check_deadline()
        state = classify_plan(txt(p))
        states[state] = states.get(state, 0) + 1
        r = repo_of(p)
        if r is not None:
            RPT[r]["3"].setdefault("plans", []).append({"file": rel(p), "state": state})
    top = sorted(ps, key=lambda p: -(st(p).st_mtime if st(p) else 0))
    out = [
        f"{rel(p)} (mtime {mt(p)}, unchecked {ps[p][0]}, status lines {ps[p][1]})"
        for p in top[:6]
    ]
    cls = ", ".join(f"{k} {states.get(k, 0)}" for k in ("executed", "open", "unknown"))
    return (
        f"{len(ps)} plan-like files ({cls}), {sum(v[0] for v in ps.values())} unchecked boxes, {sum(v[1] for v in ps.values())} status lines",
        out,
        0,
    )


ZERO_OK = {"__init__.py", ".gitkeep", ".keep", "py.typed"}
JUNK = re.compile(r"\.(tmp|bak|orig)$", re.I)


def i4():
    cutoff = time.time() - 86400
    found = {
        "zero-byte": [],
        "tmp/bak/orig": [],
        "__pycache__": [],
        "ignored untracked >24h": [],
    }
    for r in REPOS:
        for p in FBR[r]:
            s = st(p)
            if s and s.st_size == 0 and p.name not in ZERO_OK:
                found["zero-byte"].append(p)
                acc(r, 4, "zero_byte", rel(p))
            if JUNK.search(p.name):
                found["tmp/bak/orig"].append(p)
                acc(r, 4, "tmp_bak_orig", rel(p))
        caches = {d for d in cache_dirs(r) if repo_of(d) == r} | {
            d for d in IGN[r] if d.name == "__pycache__"
        }
        found["__pycache__"] += sorted(caches)
        acc(r, 4, "pycache", *(rel(d) for d in caches))
        for d in IGN[r]:
            if (
                d.name not in ("__pycache__", "node_modules", ".git")
                and not SECRET.search(d.name)
                and st(d)
                and st(d).st_mtime < cutoff
            ):
                found["ignored untracked >24h"].append(d)
                acc(r, 4, "ignored_untracked_old", rel(d))
    allp = [p for v in found.values() for p in v]
    safety = {}
    for p in allp:
        check_deadline()
        safety[rel(p)] = path_facts(p)
    for p in allp:
        r = repo_of(p)
        if r is not None and safety:
            RPT[r]["4"].setdefault("safety", {})[rel(p)] = safety[rel(p)]

    def detail(p):
        f = safety[rel(p)]
        base = f"{rel(p)} ({human(du(p))}, {mt(p)})"
        if f.get("branch"):
            base += f" [{f['branch']} uncommitted {f['uncommitted']} unpushed {f['unpushed']}]"
        return base

    out = [detail(p) for p in sample(allp, 6) if isinstance(p, Path)]
    cfg = config_entries()
    if cfg and REPOS:
        RPT[REPOS[0]]["4"].setdefault("config_root_entries", []).extend(cfg)
    for c in cfg:
        check_deadline()
        ents = c["entries"]
        out.append(
            f"{c['root']}: "
            + (
                ", ".join(ents[:8]) + ("..." if len(ents) > 8 else "")
                if ents
                else "(empty)"
            )
        )
    cfg_n = sum(len(c["entries"]) for c in cfg)
    return (
        (
            "read-only candidates: "
            + ", ".join(f"{k} {len(v)}" for k, v in found.items())
            + f", {human(sum(du(p) for p in allp))} total"
            + (f", config-root entries {cfg_n}" if cfg else "")
        ),
        out,
        0,
    )


def i5():
    pat = re.compile(r"(handoff|wizard|runbook)", re.I)
    hits = [p for p in FILES if pat.match(p.name)]
    for p in hits:
        acc(repo_of(p), 5, "files", rel(p))
    return (
        f"handoff/wizard/runbook files {len(hits)}",
        [rel(p) for p in sample(hits, 6) if isinstance(p, Path)],
        0,
    )


TOOLS = [
    (["git", "--version"], "git"),
    (["gh", "--version"], "gh"),
    (["uv", "--version"], "uv"),
    (["node", "--version"], "node"),
    (["uv", "run", "--no-project", "python", "--version"], "python"),
    (["dotnet", "--version"], "dotnet"),
    (["cargo", "--version"], "cargo"),
    (["go", "version"], "go"),
    (["npm", "--version"], "npm"),
]
MANIFESTS = {
    "package.json": (
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "bun.lock",
        "bun.lockb",
    ),
    "pyproject.toml": ("uv.lock", "poetry.lock", "pdm.lock"),
    "Cargo.toml": ("Cargo.lock",),
    "go.mod": ("go.sum",),
}


_TOOL_VERSIONS = {}


def tool_version_lines():
    """One --version probe per tool, cached per process keyed by PATH.
    Tests run dozens of audits in one process with a fixed PATH; without
    this every audit respawns all nine tools (dotnet alone costs ~0.5 s)."""
    key = os.environ.get("PATH", "")
    hit = _TOOL_VERSIONS.get(key)
    if hit is None:

        def probe(tool):
            argv, name = tool
            check_deadline()
            rc, o = run(argv) if shutil.which(argv[0]) else (1, "")
            return f"{name} {o.strip().splitlines()[0] if rc == 0 and o.strip() else 'unavailable'}"

        hit = pmap(probe, TOOLS)
        _TOOL_VERSIONS[key] = hit
    return hit


def i6():
    out = list(tool_version_lines())
    avail = sum("unavailable" not in o for o in out)
    nolock = 0
    for r in REPOS:
        mans = [p for p in FBR[r] if p.name in MANIFESTS]
        miss = [
            rel(p)
            for p in mans
            if not any((p.parent / l).exists() for l in MANIFESTS[p.name])
        ]
        nolock += len(miss)
        rec(r, 6, "manifests", [rel(p) for p in mans])
        rec(r, 6, "manifests_without_lockfile", miss)
        out.append(f"{r.name}: manifests {len(mans)}, without lockfile {miss or 0}")
    if SUBPROCESS_TIMEOUTS:
        by_repo = {}
        for t in SUBPROCESS_TIMEOUTS:
            match = next(
                (r for r in REPOS if t["cwd"] and str(r) == t["cwd"]),
                REPOS[0] if REPOS else None,
            )
            by_repo.setdefault(match, []).append(t)
        for r, ts in by_repo.items():
            if r is not None:
                rec(r, 6, "subprocess_timeouts", ts)
        out.append(
            f"subprocess timeouts {len(SUBPROCESS_TIMEOUTS)}: "
            + ", ".join(sample([t["cmd"][0] for t in SUBPROCESS_TIMEOUTS], 3))
        )
    return (
        (
            f"{avail}/{len(TOOLS)} tools on PATH, {nolock} manifests without lockfile"
            + (
                f", subprocess timeouts {len(SUBPROCESS_TIMEOUTS)}"
                if SUBPROCESS_TIMEOUTS
                else ""
            )
        ),
        out,
        0,
    )


def i7():
    out, n = [], 0
    for r in REPOS:
        f = [p for p in FBR[r] if TEST.search(p.relative_to(r).as_posix())]
        d = [
            p
            for p in DIRS
            if p.name in ("tests", "test", "__tests__") and repo_of(p) == r
        ]
        n += len(f)
        out.append(f"{r.name}: {len(f)} test files, {len(d)} test dirs")
    return f"{n} test files across {len(REPOS)} repos", out, 0


def i8():
    out = []
    for r in REPOS:
        marks = [
            c / "v/cache" / n
            for c in CACHES
            if repo_of(c) == r
            for n in ("lastfailed", "nodeids")
        ]
        marks = [m for m in marks if m.exists()]
        out.append(
            f"{r.name}: "
            + (
                f"newest pytest record {max(mt(m) for m in marks)}"
                if marks
                else "no record"
            )
        )
    return (
        f"{sum('no record' not in o for o in out)} of {len(REPOS)} repos have a pytest cache record (tests are not run here)",
        out,
        0,
    )


def deleted(r):
    if r not in _DELETED:
        _DELETED[r] = git(
            r,
            "log",
            "--diff-filter=D",
            "--name-only",
            "--pretty=format:",
            f"--since={SINCE_GIT}",
        )
    return _DELETED[r]


def i9():
    out, n = [], 0
    for r in REPOS:
        d = [f for f in deleted(r) if TEST.search(f)]
        rec(r, 9, "deleted_tests", d)
        n += len(d)
        if d:
            out.append(f"{r.name}: {d}")
    return f"{n} test files deleted in tracked history since {SINCE_GIT}", out, 0


def i10():
    out, n = [], 0
    for r in REPOS:
        d = [f for f in deleted(r) if not TEST.search(f)]
        rec(r, 10, "deleted_other", d)
        n += len(d)
        if d:
            out.append(f"{r.name}: {len(d)}")
    return (
        f"{n} non-test files deleted since {SINCE_GIT} (tracked history only; untracked deletions are unknowable)",
        out,
        0,
    )


def gh_error_entry(r, url, command, error):
    entry = {"remote": url, "command": command, "error": error}
    RPT[r]["11"].setdefault("gh_errors", []).append(entry)
    return entry


def i11():
    out, tot = [], [0, 0, 0, 0, 0]
    ok_repos, err_repos = 0, 0
    own, auth_err = owners(), gh_auth_error()
    need_owner = False
    gh_up = gh_ok()

    def lists(r):
        check_deadline()
        if not (gh_up and RPT[r].get("2", {}).get("origin", "")):
            return None
        issue_args = (
            "issue",
            "list",
            "--state",
            "open",
            "--json",
            "number",
            "--limit",
            "100",
        )
        pr_args = (
            "pr",
            "list",
            "--state",
            "open",
            "--json",
            "number",
            "--limit",
            "100",
        )
        return gh_run(r, *issue_args), gh_run(r, *pr_args)

    fetched = dict(zip(REPOS, pmap(lists, REPOS)))
    for r in REPOS:
        check_deadline()
        # Indices 1 and 2 ran already (collect runs in order) on the same repo
        # state, so reuse their values instead of respawning the same git calls.
        up = len(RPT[r].get("2", {}).get("unpushed", []))
        dirty = RPT[r].get("1", {}).get("counts", {}).get("dirty", 0)
        unt = RPT[r].get("1", {}).get("counts", {}).get("untracked", 0)
        url = RPT[r].get("2", {}).get("origin", "")
        need_owner = need_owner or bool(origin_owner(url))
        iss = prs = None
        if not url:
            gh_error_entry(
                r,
                "",
                "issue list",
                f"remote does not resolve: {r.name} has no origin remote",
            )
        elif not gh_ok():
            gh_error_entry(r, url, "auth status", auth_err or "gh unavailable")
        else:
            (rc1, o1, e1), (rc2, o2, e2) = fetched[r]
            try:
                iss = json.loads(o1) if rc1 == 0 else None
            except ValueError:
                iss = None
            try:
                prs = json.loads(o2) if rc2 == 0 else None
            except ValueError:
                prs = None
            if iss is None:
                gh_error_entry(
                    r,
                    url,
                    "issue list",
                    ((e1 or "") + (o1 or "")).strip()
                    or "gh issue list failed with no error text",
                )
            if prs is None:
                gh_error_entry(
                    r,
                    url,
                    "pr list",
                    ((e2 or "") + (o2 or "")).strip()
                    or "gh pr list failed with no error text",
                )
        ok = iss is not None and prs is not None
        ok_repos += ok
        vals = (
            up,
            dirty,
            unt,
            len(iss) if iss is not None else None,
            len(prs) if prs is not None else None,
        )
        tot = [a + (b or 0) for a, b in zip(tot, vals)]
        rec(
            r,
            11,
            "counts",
            dict(
                zip(("unpushed", "dirty", "untracked", "open_issues", "open_prs"), vals)
            ),
        )
        rec(r, 11, "open_issues", iss)
        rec(r, 11, "open_prs", prs)
        rec(r, 11, "gh_status", "ok" if ok else "unavailable")
        out.append(
            f"{r.name}: unpushed {up}, dirty {dirty}, untracked {unt}, open issues {'n/a' if iss is None else len(iss)}, open PRs {'n/a' if prs is None else len(prs)}"
        )
        for e in RPT[r]["11"].get("gh_errors", []):
            out.append(
                f"{r.name}: gh {e['command']} failed for {e['remote'] or '(no remote)'}: {e['error']}"
            )
    err_repos = sum(1 for r in REPOS if RPT[r].get("11", {}).get("gh_errors"))
    if need_owner and not own and "WORK_AUDIT_OWNERS" not in os.environ:
        for r in REPOS:
            if origin_owner(origin_url(r)):
                gh_error_entry(
                    r,
                    origin_url(r),
                    "api user",
                    OWNERS_ERROR or "gh owner login unavailable",
                )
                out.append(
                    f"{r.name}: gh api user failed: {OWNERS_ERROR or 'gh owner login unavailable'}"
                )
        err_repos = sum(1 for r in REPOS if RPT[r].get("11", {}).get("gh_errors"))
    note = "" if gh_ok() else "; gh unavailable"
    scope = (
        ""
        if not err_repos
        else f", gh errors in {err_repos} repos (counts cover the {ok_repos} repos with working gh)"
    )
    return (
        f"proxy: unpushed {tot[0]}, dirty entries {tot[1]}, untracked {tot[2]}, open issues {tot[3]}, open PRs {tot[4]}{note}{scope} -> record verify required",
        out,
        0,
    )


SKIPS = re.compile(
    r"pytest\.skip|pytest\.mark\.(skip|skipif|xfail)|unittest\.skip|\bxfail\b|\.(skip|only)\b|\b(xit|xdescribe|fit|fdescribe)\(|\bSkip\s*="
)


def git_path_ok(name):
    if not name:
        return False
    return not any(part in SKIP_DIRS for part in Path(name).parts[:-1])


def fs_path_ok(root, name):
    if not name:
        return False
    parts = Path(name).parts
    if any(part in SKIP_DIRS for part in parts[:-1]):
        return False
    cand = Path(root)
    for part in parts[:-1]:
        cand = cand / part
        try:
            if RC.dir_is_link(cand):
                return False
        except OSError:
            return False
    return True


def cache_dirs(r):
    """__pycache__ dirs with listed files (tracked or untracked-not-ignored),
    excluding ones nested under other skipped dirs. Git-only, no content scan."""
    out = set()
    higher = SKIP_DIRS - {"__pycache__"}
    for args in (("ls-files",), ("ls-files", "-o", "--exclude-standard")):
        for name in git(r, *args):
            parts = Path(name).parts
            for i, part in enumerate(parts[:-1]):
                if part == "__pycache__" and not any(s in higher for s in parts[:i]):
                    out.add(r.joinpath(*parts[: i + 1]))
    return out


def changed_files(r):
    names = set(
        git(
            r,
            "log",
            "--branches",
            f"--since={SINCE_GIT}",
            "--name-only",
            "--pretty=format:",
        )
    )
    names |= {
        l[3:].split(" -> ")[-1].strip('"')
        for l in git(r, "status", "--porcelain", "-uall")
    }
    return sorted(n for n in names if git_path_ok(n) and fs_path_ok(r, n))


def i12():
    hits = []
    for r in REPOS:
        found = [
            f"{f}:{i}"
            for f in changed_files(r)
            if TEST.search(f) and (r / f).is_file()
            for i, l in enumerate(txt(r / f).splitlines(), 1)
            if SKIPS.search(l)
        ]
        rec(r, 12, "markers", found)
        hits += [f"{r.name}/{x}" for x in found]
    return (
        f"proxy: {len(hits)} skip/xfail/only markers in changed test files -> record verify required",
        sample(hits, 5),
        0,
    )


def commits(r):
    return git(r, "log", "--branches", f"--since={SINCE_GIT}", "--pretty=%h %s")


def i13():
    allc = {r: commits(r) for r in REPOS}
    for r, c in allc.items():
        rec(r, 13, "commits", c)
    out = [
        f"{r.name}: {len(c)} commits {sample([x[:70] for x in c], 3)}"
        for r, c in allc.items()
        if c
    ]
    return (
        f"proxy: {sum(map(len, allc.values()))} commits since {SINCE_GIT} (finished = verified record) -> record verify required",
        out,
        0,
    )


def i14():
    out, n_unrev, n_notest = [], 0, 0

    def evidence(r):
        check_deadline()
        if not RPT[r].get("13", {}).get("commits", []):
            return None, []
        prs = gh_json(
            r,
            "pr",
            "list",
            "--state",
            "merged",
            "--limit",
            "100",
            "--json",
            "mergeCommit",
        )
        log = git(
            r,
            "log",
            "--branches",
            f"--since={SINCE_GIT}",
            "--name-only",
            "--pretty=format:",
        )
        return prs, log

    for r, (prs, log) in zip(REPOS, pmap(evidence, REPOS)):
        # commits() already ran for index 13 (collect runs in order).
        c = RPT[r].get("13", {}).get("commits", [])
        if not c:
            continue
        merged = (
            {(p.get("mergeCommit") or {}).get("oid", "")[:7] for p in prs}
            if prs is not None
            else None
        )
        un = [x for x in c if merged is None or x[:7] not in merged]
        files = [f for f in log if git_path_ok(f) and fs_path_ok(r, f)]
        notest = bool(files) and not any(TEST.search(f) for f in files)
        rec(r, 14, "commits_without_pr", un)
        rec(r, 14, "files_changed", files)
        n_unrev += len(un)
        n_notest += len(files) if notest else 0
        out.append(
            f"{r.name}: {len(un)}/{len(c)} commits not on a merged PR{' (gh unavailable)' if merged is None else ''}; {len(files)} files changed, tests touched: {'no' if notest else 'yes'}"
        )
    return (
        f"proxy: {n_unrev} commits without PR evidence, {n_notest} files changed with no test touched (CI not queried) -> record verify required",
        out,
        0,
    )


def i15():
    empty = []
    for r in REPOS:
        skip = {*IGN[r], r / ".git"}
        for dp, dns, fns, skipped in BoundedScan(r, skip=skip, prune_git=True).walk():
            check_deadline()
            bare = not dns and not fns and not skipped
            dns[:] = [d for d in dns if dp / d not in skip]
            if bare and dp != r:
                empty.append(dp)
                acc(r, 15, "empty_dirs", rel(dp))
    safety = {}
    for dp in empty:
        check_deadline()
        safety[rel(dp)] = path_facts(dp)
        r = repo_of(dp)
        if r is not None:
            RPT[r]["15"].setdefault("safety", {})[rel(dp)] = safety[rel(dp)]

    def det(p):
        f = safety.get(rel(p), {})
        return rel(p) + (
            f" [{f.get('branch')} uncommitted {f.get('uncommitted')} unpushed {f.get('unpushed')}]"
            if f.get("branch")
            else ""
        )

    return (
        f"{len(empty)} empty dirs",
        [det(p) for p in sample(empty, 6) if isinstance(p, Path)],
        0,
    )


@lru_cache(maxsize=None)
def sha(p):
    h = hashlib.sha256()
    try:
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                check_deadline()
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def i16():
    by_size = defaultdict(list)
    for p in FILES:
        s = st(p)
        if s and 200 < s.st_size < 50_000_000:
            by_size[s.st_size].append(p)
    groups = defaultdict(list)
    pmap(sha, [p for ps in by_size.values() if len(ps) > 1 for p in ps])
    for sz, ps in by_size.items():
        if len(ps) > 1:
            for p in ps:
                groups[(sz, sha(p))].append(p)
    dups = [g for g in groups.values() if len(g) > 1]
    wasted = sum(st(g[0]).st_size * (len(g) - 1) for g in dups)
    names = defaultdict(list)
    for d in DIRS:
        names[d.name].append(d)
    cand = {d for ds in names.values() if len({x.parent for x in ds}) > 1 for d in ds}
    under = defaultdict(list)
    for p in FILES:
        for a in p.parents:
            if a in cand:
                under[a].append(p)
    sig = defaultdict(list)
    for d, fs in under.items():
        if 0 < len(fs) <= 200:
            sig[
                (
                    d.name,
                    tuple(
                        sorted(
                            (f.relative_to(d).as_posix(), st(f).st_size if st(f) else 0)
                            for f in fs
                        )
                    ),
                )
            ].append(d)
    dd = []
    for (name, _), ds in sig.items():
        if len(ds) > 1:
            hs = defaultdict(list)
            for d in ds:
                hs[
                    hashlib.sha256(
                        "".join(
                            f.relative_to(d).as_posix() + sha(f)
                            for f in sorted(under[d])
                        ).encode()
                    ).hexdigest()
                ].append(d)
            dd += [v for v in hs.values() if len(v) > 1]
    for g in dups:
        check_deadline()
        acc(repo_of(g[0]), 16, "duplicates", [rel(p) for p in g])
        r = repo_of(g[0])
        if r is not None:
            RPT[r]["16"].setdefault("safety", {}).update(
                {rel(p): path_facts(p) for p in g}
            )
    out = [
        " == ".join(rel(p) for p in g[:3])
        for g in sample(dups, 4)
        if isinstance(g, list)
    ]
    out += [
        "dir " + " == ".join(rel(p) for p in g[:3])
        for g in sample(dd, 3)
        if isinstance(g, list)
    ]
    return (
        f"{len(dups)} duplicate file groups ({human(wasted)} redundant), {len(dd)} identical same-name dir groups",
        out,
        0,
    )


def doc_roots(doc):
    scope = repo_of(doc) or doc.parent
    skill = next((a for a in doc.parents if (a / "SKILL.md").exists()), None)
    anc = [a for a in doc.parents if a == scope or scope in a.parents]
    return scope, skill, anc


@lru_cache(maxsize=None)
def adrs(scope):
    found = set()
    for f in md_files():
        if under(f, scope) is not None:
            found |= set(re.findall(r"(?m)^#+\s*ADR[- ]?(\d{4})", txt(f)))
            if f.parent.name == "adr" and (m := re.match(r"(\d{4})-", f.name)):
                found.add(m[1])
    return found


def i17():
    hits = []
    for p in FILES:
        if (
            p.suffix.lower() in CODE_EXT
            and ".min." not in p.name
            and not (p.name == SELF.name and p.resolve() == SELF)
        ):
            found = [
                f"{rel(p)}:{i}"
                for i, l in enumerate(txt(p).splitlines(), 1)
                if UNFIN.search(l)
            ]
            hits += found
            acc(repo_of(p), 17, "hits", *found)
    ps = plan_stats()
    live = {p: v for p, v in ps.items() if classify_plan(txt(p)) != "executed"}
    unchecked = sum(v[0] for v in live.values())
    pstat = [rel(p) for p in live if PLAN_STATUS.search(txt(p))]
    n = len(hits) + unchecked + len(pstat)
    return (
        f"{len(hits)} TODO/FIXME/XXX/NotImplemented/skip/only hits, {unchecked} unchecked plan boxes, {len(pstat)} plan files with pending/blocked/open status",
        sample(hits, 4) + sample(pstat, 3),
        n,
    )


ROOT_OK = re.compile(
    r"^(README|CLAUDE|AGENTS|CONTEXT|CONTRIBUTING|CHANGELOG|LICENSE)[^/]*$|^\.(gitignore|gitattributes|gitmodules|editorconfig|ignore)$|\.(json|jsonc|toml|ya?ml|lock|sln|props|csproj)$|lock|^(install|run|setup|build)[-\w]*\.(ps1|sh|py|cmd)$",
    re.I,
)
SECRET_TRACKED = re.compile(
    r"(^|/)(\.env(?!\.(example|sample|template)$)[^/]*|[^/]*\.pem|[^/]*\.key|auth\.json|credentials\.json|id_rsa|id_ed25519|\.npmrc|\.netrc)$"
)


def i18():
    out, runs, pushed_small = [], 0, 0
    for r in REPOS:
        up = git(r, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        if not up:
            continue
        small = []
        for h in git(r, "log", "--reverse", "--pretty=%h", f"{up[0]}..HEAD"):
            body = "\n".join(git(r, "log", "-1", "--pretty=%B", h))
            stat = " ".join(git(r, "show", "--shortstat", "--pretty=", h))
            n = sum(int(x) for x in re.findall(r"(\d+) (?:insertion|deletion)", stat))
            small.append((h, n <= SMALL_LINES and not ISSUE_REF.search(body)))
        run_len = 0
        for _, ok in small + [("", False)]:
            if ok:
                run_len += 1
            else:
                if run_len >= 2:
                    runs += 1
                    acc(r, 18, "squashable_runs", run_len)
                    out.append(
                        f"{r.name}: {run_len} consecutive small (<= {SMALL_LINES} lines) unpushed commits with no issue reference; squash with `git reset --soft {up[0]}` then one commit"
                    )
                run_len = 0
    for r in REPOS:
        bodies = "\n".join(
            git(r, "log", f"--since={SINCE_GIT}", "--pretty=%B%x01", "--max-count=200")
        ).split("\x01")
        pushed_small += sum(
            1 for body in bodies if body.strip() and not ISSUE_REF.search(body)
        )
    return (
        f"{runs} squashable runs of unpushed small commits with no issue reference ({pushed_small} commits in the window carry no issue reference; pushed history is not rewritten)",
        out,
        runs,
    )


def i19():
    bad, adr_bad = [], []
    for doc in md_files():
        t = re.sub(r"(?s)```.*?```", "", txt(doc))
        scope, skill, anc = doc_roots(doc)
        bases = [*anc, *([skill] if skill else [])]

        def ok(tok):
            tok = re.sub(r"(:\d+(-\d+)?|#.*)$", "", tok).removeprefix("./")
            if tok.startswith("~/"):
                return (Path.home() / tok[2:]).exists()
            if re.match(r"^[A-Za-z]:[\\/]", tok) or tok.startswith("/"):
                return Path(tok).exists()
            return any((b / tok).exists() for b in bases)

        toks = []
        for m in re.findall(r"`([^`\n]+)`", t):
            if "/" not in m and not m.startswith(("scripts/", "references/")):
                continue
            if re.search(r"[*<>{}$|;=(),]|://|^[-@]", m):
                continue
            if re.search(r"\s", m) and not (
                "/" in m and re.search(r"\.\w{1,5}(:\d+)?$", m)
            ):
                continue
            toks.append(m)
        links = [
            m
            for m in re.findall(r"\]\(([^)\s]+)\)", t)
            if not re.match(r"(https?|mailto|#)", m) and not re.search(r"[<>{}$*]", m)
        ]
        for tok in {*toks, *links}:
            if not ok(tok):
                bad.append(f"{rel(doc)} -> {tok}")
                if repo_of(doc):
                    acc(
                        repo_of(doc),
                        19,
                        "bad_refs",
                        {"doc": doc.relative_to(repo_of(doc)).as_posix(), "ref": tok},
                    )
        known = adrs(skill or scope)
        for n in set(re.findall(r"ADR[- ]?(\d{4})", t)):
            if n not in known:
                adr_bad.append(f"{rel(doc)} ADR {n}")
                if repo_of(doc):
                    acc(
                        repo_of(doc),
                        19,
                        "adr",
                        {"doc": doc.relative_to(repo_of(doc)).as_posix(), "adr": n},
                    )
    return (
        f"proxy: {len(bad)} unresolved path/link refs, {len(adr_bad)} unresolved ADR citations in {len(md_files())} md files -> record 19 required",
        sample(bad, 4) + sample(adr_bad, 3),
        0,
    )


DOC_HOMES = re.compile(
    r"^(docs?/|\.[^/]+/|.*(^|/)README\.md$|(README|CLAUDE|AGENTS|CONTEXT|CONTRIBUTING|CHANGELOG|SECURITY|LICENSE)[^/]*$)",
    re.I,
)


def i20():
    out, titles = [], defaultdict(list)
    for r in REPOS:
        mds = [f for f in FBR[r] if f.suffix.lower() == ".md"]
        lines = {f: len(txt(f).splitlines()) for f in mds}
        outside = [f for f in mds if not DOC_HOMES.match(f.relative_to(r).as_posix())]
        for f in mds:
            m = re.search(r"(?m)^#\s+(.+)$", RC.SHARED_BLOCK.sub("", txt(f)))
            if m:
                titles[m[1].strip().lower()].append(f)
        big = [f for f, n in lines.items() if n > 300]
        rec(r, 20, "md_files", [f.relative_to(r).as_posix() for f in mds])
        rec(
            r,
            20,
            "outside_allowed_homes",
            [f.relative_to(r).as_posix() for f in outside],
        )
        rec(r, 20, "over_300_lines", [f.relative_to(r).as_posix() for f in big])
        out.append(
            f"{r.name}: {len(mds)} md, {sum(lines.values())} lines, >300 lines {len(big)}, outside allowed homes {len(outside)} {[f.relative_to(r).as_posix() for f in outside[:2]]}"
        )
    dup = {k: v for k, v in titles.items() if len(v) > 1}
    for k, v in dup.items():
        for r in {repo_of(f) for f in v} - {None}:
            acc(
                r,
                20,
                "duplicate_h1",
                {
                    "title": k,
                    "files": [
                        f.relative_to(r).as_posix() for f in v if repo_of(f) == r
                    ],
                },
            )
    return (
        f"proxy: {sum(len([f for f in FBR[r] if f.suffix.lower() == '.md']) for r in REPOS)} md files, {len(dup)} duplicate H1 titles -> record 20 required",
        out + [f"dup H1 '{k}': {len(v)} files" for k, v in list(dup.items())[:3]],
        0,
    )


UNFIN = re.compile(r"\b(TODO|FIXME|XXX|NotImplementedError)\b|\btest\.skip\b|\.only\(")
PLAN_STATUS = re.compile(
    r"\bBLOCKED\b|\bOPEN:|^\s*[-*]?\s*\**status\**\s*:\s*\**\s*(pending|blocked|open|in[- ]progress)",
    re.I | re.M,
)


STYLE_RE = re.compile("|".join(fnmatch.translate(g) for g in RC.STYLE_GLOBS))


def i21():
    out, hard = [], 0
    for r in REPOS:
        tracked = git(r, "ls-files")
        top = {t.split("/")[0] for t in _LS.get(r, []) if "/" not in t}
        stray = sorted(
            f
            for f in top
            if not ROOT_OK.search(f)
            and f not in SKIP_DIRS
            and not RC.dir_is_link(r / f)
        )
        secrets = [t for t in tracked if SECRET_TRACKED.search(t)]
        names = (under(f, r) for f in FBR[r])
        styles = [n for n in names if STYLE_RE.match(n.lower())]
        hard += len(secrets)
        rec(r, 21, "root_strays", stray)
        rec(r, 21, "style_docs", styles)
        rec(r, 21, "tracked_secrets", secrets)
        out.append(
            f"{r.name}: root strays {stray[:4]}{'+' if len(stray) > 4 else ''}, style docs {styles}, tracked secrets {secrets}"
        )
    return (
        f"proxy: {len(REPOS)} repos checked against generic rules; tracked secret-like files {hard} (hard) -> record 21 required",
        out,
        hard,
    )


SMALL_LINES = 60
ISSUE_REF = re.compile(r"#\d+|\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\b", re.I)


INDICES = [
    ("git status", i1),
    ("branches/worktrees/stashes", i2),
    ("plan files", i3),
    ("stale artifacts", i4),
    ("handoffs and wizards", i5),
    ("tool state", i6),
    ("tests present", i7),
    ("tests run", i8),
    ("tests deleted", i9),
    ("other files deleted", i10),
    ("left", i11),
    ("skipped", i12),
    ("finished", i13),
    ("not verified", i14),
    ("empty dirs", i15),
    ("duplicates", i16),
    ("unfinished", i17),
    ("small commits to squash", i18),
    ("doc mismatches", i19),
    ("doc sprawl", i20),
    ("repo sprawl vs style", i21),
]


PHASES = [
    ("Phase 1: repo state", (1, 2, 6)),
    ("Phase 2: clutter", (4, 5, 15, 16)),
    ("Phase 3: tests", (7, 8, 9, 12)),
    ("Phase 4: work status", (3, 10, 11, 13, 17)),
    ("Phase 5: verification", (14, 18)),
    ("Phase 6: docs and sprawl", (19, 20, 21)),
]

CONSUMING = {3, 4, 5, 6, 7, 15, 16, 17, 19, 20, 21}


STOPPED = []  # why collect(fail_fast=True) stopped early


def collect(on_index=None, fail_fast=False):
    """Run every index in order; with fail_fast, stop at the first cap hit (a partial
    report is refused by record.py anyway, so the remaining indices are wasted time)."""
    res = []
    del STOPPED[:]
    gx = ThreadPoolExecutor(min(WORKERS, 8))
    prefetch_gh(gx)
    try:
        res = _collect(res, on_index, fail_fast)
    finally:
        gx.shutdown(wait=False, cancel_futures=True)
        _GH_PREFETCH.clear()
    return res


def _collect(res, on_index, fail_fast):
    for i, (name, fn) in enumerate(INDICES, 1):
        global _DEADLINE
        cap = index_timeout()
        _DEADLINE = time.time() + cap
        try:
            check_deadline()
            summary, details, flag = fn()
            res.append((i, name, summary, details, flag, None))
        except _Truncated as t:
            reason = f"truncated: per-index cap {cap:g}s exceeded ({t})"
            for r in REPOS:
                rec(r, i, "truncated", reason)
            res.append((i, name, reason, [], 0, None))
            STOPPED.append(f"index {i} ({name}): {reason}")
        except Exception as e:
            res.append((i, name, f"ERROR {type(e).__name__}: {e}", [], 0, e))
        finally:
            _DEADLINE = None
        if SCAN_TRUNCATED:
            for r in REPOS:
                for j in sorted(CONSUMING):
                    RPT[r][str(j)].setdefault("scan_truncated", list(SCAN_TRUNCATED))
            if not STOPPED:
                STOPPED.append("; ".join(SCAN_TRUNCATED))
        if on_index is not None:
            on_index(i)
        if fail_fast and STOPPED:
            break
    return res


def selftest():
    reset_scan_state()
    base = RC.RECORDS / ".tmp" / "sr-selftest"
    if base.exists():
        RC.rmtree(base)
    repo = base / "repo"
    repo.mkdir(parents=True)
    repo = repo.resolve()
    os.environ["GIT_CEILING_DIRECTORIES"] = str(base)
    results = []

    def sh(*a):
        rc, _out = run(
            [
                (RC.git_bin() or "git"),
                "-C",
                str(repo),
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                *a,
            ]
        )
        assert rc == 0, f"selftest git failed: {a}"

    def case(name, ok):
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'} {name}")

    try:
        sh("init", "-q")
        (repo / "docs").mkdir()
        (repo / "tests").mkdir()
        (repo / "README.md").write_text(
            "# Demo\n\nSee `docs/guide.md` and `docs/missing.md`.\n"
        )
        (repo / "docs" / "guide.md").write_text("# Guide\n\n## Usage\n\nRun the app.\n")
        (repo / "tests" / "test_a.py").write_text(
            "import pytest\n\n\n@pytest.mark.skip\ndef test_a():\n    pass\n"
        )
        (repo / "app.py").write_text("# TODO later\n")
        (repo / "handoff-notes.md").write_text("# Handoff\n")
        (repo / "server.pem").write_text("")
        (repo / "one.txt").write_text("x" * 300)
        (repo / "two.txt").write_text("x" * 300)
        (repo / "scratch.tmp").write_text("")
        (repo / ".gitignore").write_text("out/\n")
        sh("add", "-A")
        sh("commit", "-qm", "one")
        (repo / "app.py").write_text("# TODO later\nx = 1\n")
        (repo / "new.txt").write_text("new")
        (repo / "emptydir").mkdir()
        (repo / "pkg" / "__pycache__").mkdir(parents=True)
        (repo / "pkg" / "__pycache__" / "m.pyc").write_text("c")
        (repo / "out").mkdir()
        (repo / "out" / "build.bin").write_text("b")
        old = time.time() - 3 * 86400
        os.utime(repo / "out", (old, old))
        setup(RC.scope(repo, env=False))
        case("scope from cwd = the repo", REPOS == [repo])
        res = collect()
        case("21 indices returned", [r[0] for r in res] == list(range(1, 22)))
        for i, name, summary, _, _, err in res:
            case(
                f"index {i} {name} returns without error",
                err is None and not summary.startswith("ERROR"),
            )
        rp = RPT[repo]
        case(
            "i4 finds zero-byte, tmp, pycache, old ignored dir",
            all(
                k in rp["4"]
                for k in (
                    "zero_byte",
                    "tmp_bak_orig",
                    "pycache",
                    "ignored_untracked_old",
                )
            ),
        )
        case("i5 finds handoff file", rp["5"].get("files") == ["repo/handoff-notes.md"])
        case(
            "i12 finds the pytest skip marker",
            rp["12"]["markers"] == ["tests/test_a.py:4"],
        )
        case("i15 finds the empty dir", rp["15"].get("empty_dirs") == ["repo/emptydir"])
        case(
            "i16 finds the duplicate pair",
            rp["16"].get("duplicates") == [["repo/one.txt", "repo/two.txt"]],
        )
        case(
            "i19 flags the missing doc ref only",
            [b["ref"] for b in rp["19"].get("bad_refs", [])] == ["docs/missing.md"],
        )
        case("i17 finds TODO", any(h.endswith("app.py:1") for h in rp["17"]["hits"]))
        case(
            "i21 flags the tracked secret as hard",
            rp["21"]["tracked_secrets"] == ["server.pem"] and res[20][4] == 1,
        )
        case(
            "tracked secret-like file content is never indexed",
            all(p.name != "server.pem" for p in FILES),
        )
    finally:
        os.environ.pop("GIT_CEILING_DIRECTORIES", None)
        RC.rmtree(base)
    return 0 if all(results) else 1


def main():
    global SINCE, SINCE_GIT
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--roots",
        nargs="*",
        type=Path,
        help="repos (or folders of repos) to audit instead of the cwd repo",
    )
    ap.add_argument(
        "--transcript",
        type=Path,
        help="session transcript (jsonl): add every git repo its tool inputs touched",
    )
    ap.add_argument("--since", default="24h", help="window such as 24h, 7d, 2w")
    ap.add_argument(
        "--brief", action="store_true", help="print only the 21 summary lines"
    )
    ap.add_argument(
        "--json",
        nargs="?",
        const=RC.RECORDS,
        type=Path,
        metavar="RECORDS_DIR",
        help="write every finding unsampled to <dir>/<repo>/<tree>/report.json (default: the shared state dir's records)",
    )
    ap.add_argument(
        "--quiet-if-unchanged",
        action="store_true",
        help="when tree hash and findings match the previous run, print one 'unchanged since' line instead of the full report",
    )
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    m = re.fullmatch(r"(\d+)([hdw])", a.since)
    if not m:
        print(
            f"state-report: --since must look like 24h, 7d or 2w (got '{a.since}')",
            file=sys.stderr,
        )
        sys.exit(2)
    n, u = m.groups()
    unit = {"h": "hours", "d": "days", "w": "weeks"}[u]
    SINCE = timedelta(**{unit: int(n)})
    SINCE_GIT = f"{n} {unit} ago"
    reset_scan_state()
    lines = (
        a.transcript.read_text(encoding="utf-8", errors="ignore").splitlines()
        if a.transcript and a.transcript.is_file()
        else []
    )
    setup(RC.scope(None if a.roots else Path.cwd(), lines, a.roots or ()))
    if not REPOS:
        print(
            f"state-report {datetime.now():%Y-%m-%d %H:%M:%S} since {SINCE_GIT} repos: none (mechanical + proxies)"
        )
        print(
            "no git repo in scope: run from inside a repo, or pass --roots / --transcript / WORK_AUDIT_ROOTS"
        )
        return
    trees = {r: RC.tree(r) for r in REPOS} if (a.json or a.quiet_if_unchanged) else {}
    heads = {r: RC.head(r) for r in REPOS} if (a.json or a.quiet_if_unchanged) else {}

    def dump(complete):
        if not a.json:
            return
        partial = bool(SCAN_TRUNCATED) or any(
            RPT[r].get(str(i), {}).get("truncated") for r in REPOS for i in range(1, 22)
        )
        for r in REPOS:
            ok = complete and bool(trees.get(r, ""))
            idx = dict(RPT[r])
            if not trees.get(r, ""):
                idx["tree_error"] = (
                    f"{RC.UNFINGERPRINTABLE}: cannot fingerprint {r.name}, fix git and rerun state-report.py --json"
                )
            atomic_write_json(
                RC.rec_dir(r, a.json)
                / (trees.get(r, "") or "__unfingerprinted__")
                / "report.json",
                {
                    "repo": r.name,
                    "tree": trees.get(r, ""),
                    "head": heads.get(r, ""),
                    "since": SINCE_GIT,
                    "truncated": partial,
                    "indices": {**idx, "complete": ok},
                },
            )

    dump(False)
    results = collect(on_index=lambda i: dump(False), fail_fast=True)
    if STOPPED:
        roots = " ".join(f'"{r}"' for r in REPOS[:2])
        print(
            f"state-report: stopped early, a scan cap was hit: {STOPPED[0]}\n"
            f"  scope was {len(REPOS)} repos; narrow it, e.g. state-report.py --roots {roots}\n"
            "  or raise WORK_AUDIT_INDEX_TIMEOUT / WORK_AUDIT_MAX_FILES; the partial report is marked truncated",
            file=sys.stderr,
        )
        sys.exit(FAIL_FAST_EXIT)
    dump(True)
    unfinished = hard = 0
    for i, name, summary, details, flag, _ in results:
        if i in (17, 18):
            unfinished += flag
        else:
            hard += flag
    code = 1 if unfinished or hard else 0
    if a.quiet_if_unchanged:
        sig = hashlib.sha256(
            json.dumps(
                {
                    "trees": {str(r): trees.get(r, "") for r in REPOS},
                    "indices": {str(r): RPT.get(r, {}) for r in REPOS},
                },
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()
        qf = RC.STATE / "last-quiet.json"
        try:
            prev = json.loads(qf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prev = {}
        if prev.get("sig") == sig and prev.get("repos") == sorted(
            str(r) for r in REPOS
        ):
            print(f"unchanged since {prev['time']}")
            sys.exit(code)
        qf.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            qf,
            {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "sig": sig,
                "repos": sorted(str(r) for r in REPOS),
            },
        )
    print(
        f"state-report {datetime.now():%Y-%m-%d %H:%M:%S} since {SINCE_GIT} repos: {', '.join(str(r) for r in REPOS) or 'none'} (mechanical + proxies)"
    )
    by_index = {r[0]: r for r in results}
    for title, members in PHASES:
        print(f"== {title} ==")
        for i in members:
            _, name, summary, details, _flag, _ = by_index[i]
            print(f"{i}. {name}: {summary}")
            if not a.brief:
                for d in details:
                    print(f"     - {d}")
    if a.json:
        for r in REPOS:
            print(
                f"report {RC.rec_dir(r, a.json) / (trees.get(r, '') or '__unfingerprinted__') / 'report.json'}"
            )
    sys.exit(code)


if __name__ == "__main__":
    t0 = time.time()
    try:
        main()
    finally:
        print(f"runtime {time.time() - t0:.1f}s", file=sys.stderr)
