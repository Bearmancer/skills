# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Review records for work-audit: content fingerprint per repo, seeded briefs, schema- and line-checked records, pair status.

Commands: brief [repo...] | write <record.json> [repo...] | check [repo...] | --selftest. Optional --transcript <file.jsonl>.
Without repo arguments the scope is derived: cwd, git roots found in the transcript's tool inputs, and WORK_AUDIT_ROOTS.
Structure only: hashes, schema, file existence, token-on-line checks."""

import fnmatch
import functools
import hashlib
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


def rmtree(p):
    shutil.rmtree(p, onexc=lambda fn, path, exc: (Path(path).chmod(0o700), fn(path)))


STATE = (
    Path(
        os.environ.get("WORK_AUDIT_STATE_DIR")
        or (os.environ.get("USERPROFILE") or os.environ.get("HOME") or ".")
    )
    / ".work-audit-state"
)
SKILL = Path(__file__).resolve().parent.parent
RECORDS = STATE / "records"
SCOPE = []
WINDOW = "24 hours ago"
INDICES = ("19", "20", "21", "verify")
SCHEME = 2
STYLE_GLOBS = (
    "claude.md",
    "agents.md",
    "context.md",
    "readme*",
    "contributing*",
    ".github/contributing*",
    "docs/standards*",
    ".claude/plans/specs/*",
)
DOC_EXT = {".md", ".txt"}
STATUS = {
    "claim": {"ok", "traced", "missing", "mismatch", "unverifiable"},
    "ref": {"broken", "placeholder", "runtime-created", "other-repo", "unverifiable"},
    "pair": {"duplicate", "distinct", "unverifiable"},
    "file": {"conforms", "violates", "unverifiable"},
}
BAD = {"missing", "mismatch", "broken", "duplicate", "violates"}
FINDING_KEYS = {
    "path": str,
    "claim": str,
    "evidence": str,
    "severity": str,
    "fixed": bool,
}
CLAIM_PATTERNS = [
    re.compile(p)
    for p in (
        r"^--?[A-Za-z][\w-]{2,}$",
        r"^[A-Z][A-Z0-9]*_[A-Z0-9_]+$",
        r"^[A-Za-z_]\w*\(\)$",
        r"^[a-z]+(?:[A-Z]\w*)+$",
        r"^[A-Za-z]\w*_\w+$",
        r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$",
    )
]
FILE_EXT = re.compile(r"\.(md|py|json|jsonc|ya?ml|toml|txt|ps1|sh|ts|js|cs)$", re.I)
SUBPROCESS_TIMEOUT = 30
SKIP_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        ".pytest_cache",
        ".cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
    }
)


def _env_timeout(default=SUBPROCESS_TIMEOUT):
    try:
        return float(os.environ.get("WORK_AUDIT_SUBPROCESS_TIMEOUT", default))
    except ValueError:
        return float(default)


def kill_tree(pid):
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                timeout=15,
            )
        else:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
    except Exception:
        pass


def proc_run(cmd, cwd=None, env=None, timeout=None, shell=False):
    """Run cmd with a bounded timeout; on timeout kill the whole process tree.
    Returns (returncode|None, stdout, stderr, timed_out)."""
    limit = _env_timeout() if timeout is None else timeout
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=(sys.platform != "win32"),
        )
    except OSError as e:
        return None, "", str(e), False
    try:
        out, err = proc.communicate(timeout=limit)
        return proc.returncode, out, err, False
    except subprocess.TimeoutExpired as e:
        kill_tree(proc.pid)
        try:
            out, err = proc.communicate(timeout=15)
        except Exception:
            out, err = e.stdout or "", e.stderr or ""
        return None, out or "", err or f"timed out after {limit:g}s", True


@functools.lru_cache(maxsize=None)
def git_bin():
    return shutil.which("git")


def dir_is_link(p):
    try:
        if p.is_symlink():
            return True
        return p.is_dir() and p.is_junction()
    except OSError:
        return False


def git(repo, *a, env=None, timeout=None):
    gb = git_bin()
    rc, out, _err, _timed_out = proc_run(
        [(gb or "git"), "-c", "core.quotepath=off", "-C", str(repo), *a],
        env=env,
        timeout=timeout,
    )
    return out if rc == 0 else None


def toplevel(p):
    try:
        p = Path(p).expanduser()
        while not p.is_dir():
            if p.parent == p:
                return None
            p = p.parent
        out = git(p, "rev-parse", "--show-toplevel")
        return Path(out.strip()).resolve() if out and out.strip() else None
    except (OSError, ValueError):
        return None


def main_repo(root):
    out = git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if out and out.strip():
        c = Path(out.strip())
        if c.name == ".git" and c.parent.resolve() != Path(root).resolve():
            return c.parent.resolve()
    return None


def atomic_replace(tmp, path, tries=200):
    for n in range(tries):
        try:
            os.replace(tmp, path)
            return path
        except PermissionError:
            if n == tries - 1:
                tmp.unlink(missing_ok=True)
                raise
    return path


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    return atomic_replace(tmp, path)


# Trees below a walk root that discovery passes over, for the report to name.
NOT_SCANNED = set()


def _not_scanned_dirs():
    """System temp: purge-safety's purge.py clears it by age, so its throwaway clones are never walked."""
    t = tempfile.gettempdir()
    return {os.path.normcase(t), os.path.normcase(os.path.realpath(t))}


def _list_dir(path, skip):
    """(path, []) when path is a repo, else (None, child dirs to walk)."""
    try:
        with os.scandir(path) as it:
            children = list(it)
    except OSError:
        return None, []
    if any(c.name == ".git" for c in children):
        return (
            path,
            [],
        )  # a repo is a leaf: vendored clones and linked worktrees inside it are not walked
    subs = []
    for c in children:
        try:
            # DirEntry type bits come with the listing: one syscall per directory, not per entry
            if (
                c.name in SKIP_DIR_NAMES
                or c.is_symlink()
                or c.is_junction()
                or not c.is_dir()
            ):
                continue
        except OSError:
            continue
        if os.path.normcase(c.path) in skip:
            NOT_SCANNED.add(c.path)
            continue
        subs.append(c.path)
    return None, subs


def discover_repos(root):
    """Every outermost git repo at or under root: skips cache/vendor dirs, symlinked dirs and the
    system temp dir below root, stops at each repo root. Directories are listed on a thread pool."""
    root = Path(root)
    try:
        if not root.is_dir():
            return []
    except OSError:
        return []
    skip, found = _not_scanned_dirs(), []
    repo, level = _list_dir(
        str(root), skip
    )  # root itself is never skipped, only what is below it
    if repo is not None:
        return [root.resolve()]
    # Level by level: each level's listings run concurrently, total work stays linear.
    with ThreadPoolExecutor(16) as ex:
        while level:
            nxt = []
            for repo, subs in ex.map(lambda d: _list_dir(d, skip), level):
                if repo is not None:
                    found.append(Path(repo).resolve())
                nxt += subs
            level = nxt
    if not found and (root / ".git").exists():
        return [root.resolve()]
    return sorted(found, key=lambda p: [x.casefold() for x in p.parts])


CD_RE = re.compile(
    r"""(?:^|[;&|(\s])cd\s+(?:/d\s+)?(?:"([^"]+)"|'([^']+)'|([^\s;&|)]+))"""
)
C_RE = re.compile(r"""\s-C\s+(?:"([^"]+)"|'([^']+)'|([^\s;&|)]+))""")
PATH_KEYS = ("file_path", "path", "cwd", "workdir", "notebook_path")


def native(s):
    m = re.fullmatch(r"/([A-Za-z])(/.*)?", s)
    return f"{m[1].upper()}:{m[2] or '/'}" if m and sys.platform == "win32" else s


def transcript_paths(lines, cwd=None):
    out = []
    for l in lines:
        try:
            e = json.loads(l)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        base = e.get("cwd") or cwd
        if e.get("cwd"):
            out.append(Path(e["cwd"]))
        c = (
            (e.get("message") or {}).get("content")
            if isinstance(e.get("message"), dict)
            else None
        )
        for u in c if isinstance(c, list) else []:
            if (
                not isinstance(u, dict)
                or u.get("type") != "tool_use"
                or not isinstance(u.get("input"), dict)
            ):
                continue
            inp, found = u["input"], []
            found += [
                inp[k] for k in PATH_KEYS if isinstance(inp.get(k), str) and inp[k]
            ]
            cmd = inp.get("command")
            if isinstance(cmd, str):
                found += [
                    next(g for g in m.groups() if g)
                    for m in (*CD_RE.finditer(cmd), *C_RE.finditer(cmd))
                ]
            for s in found:
                p = Path(native(s)).expanduser()
                out.append(p if p.is_absolute() or not base else Path(base) / p)
    return out


def scope(cwd=None, lines=(), roots=(), env=True):
    cands = [Path(cwd)] if cwd else []
    cands += transcript_paths(lines, cwd)
    explicit = [Path(r) for r in roots]
    if env:
        explicit += [
            Path(x)
            for x in os.environ.get("WORK_AUDIT_ROOTS", "").split(
                (";" if sys.platform == "win32" else ":")
            )
            if x
        ]
    out, memo = [], {}

    def add(p):
        top = memo.get(p) if p in memo else memo.setdefault(p, toplevel(p))
        if top is None and (p / ".git").exists():
            top = p.resolve()
            memo[p] = top
        for r in (top, main_repo(top) if top else None):
            if r and r not in out:
                out.append(r)
        return top

    for p in cands:
        add(p.parent if p.is_file() else p)
    for p in explicit:
        if not add(p) and p.is_dir():
            for c in discover_repos(p):
                add(c)
    return out


def repos():
    return SCOPE


def find_repo(name):
    if name and Path(name).exists() and (top := toplevel(Path(name))):
        return top
    return next((r for r in SCOPE if r.name == name), Path(name))


def head(repo):
    return (git(repo, "rev-parse", "HEAD") or "").strip()


def tree(repo):
    """Tree fingerprint; one transient git failure (spawn storm) gets one retry before ''."""
    return _tree_once(repo) or _tree_once(repo)


def _tree_once(repo):
    gd = Path((git(repo, "rev-parse", "--git-dir") or ".git").strip())
    gd = gd if gd.is_absolute() else Path(repo) / gd
    idx = gd / f"work-audit.{uuid.uuid4().hex}.idx"
    try:
        git(repo, "status", "--porcelain")
        if (gd / "index").exists():
            shutil.copyfile(gd / "index", idx)
        env = {**os.environ, "GIT_INDEX_FILE": str(idx)}
        if git(repo, "add", "-A", env=env) is None:
            return ""
        return (git(repo, "write-tree", env=env) or "").strip()
    finally:
        idx.unlink(missing_ok=True)


def tree_cached(repo, cache):
    key = hashlib.sha256(
        f"{head(repo)}\0{git(repo, 'status', '--porcelain') or ''}".encode()
    ).hexdigest()
    c = cache.get(str(repo))
    if not c or c.get("key") != key or not c.get("tree"):
        c = cache[str(repo)] = {"key": key, "tree": tree(repo)}
    return c["tree"]


def rec_dir(repo, base=None):
    name = Path(repo).name
    digest = hashlib.sha256(str(Path(repo).resolve()).encode("utf-8")).hexdigest()[:8]
    return (base if base is not None else RECORDS) / f"{name}-{digest}"


class ReportError(ValueError):
    pass


def baseline(repo):
    f = rec_dir(repo) / "baseline"
    return f.read_text().strip() if f.is_file() else ""


def parse_name_status(out):
    ch = {}
    for l in (out or "").splitlines():
        parts = l.split("\t")
        if len(parts) >= 2 and parts[0]:
            ch[parts[-1]] = parts[0][0]
    return ch


def changed(repo, cur):
    base = baseline(repo)
    if base and git(repo, "cat-file", "-e", base) is not None:
        return parse_name_status(
            git(repo, "diff-tree", "-r", "--name-status", base, cur)
        )
    ch = parse_name_status(
        git(
            repo,
            "log",
            "--branches",
            f"--since={WINDOW}",
            "--name-status",
            "--pretty=format:",
        )
    )
    for l in (git(repo, "status", "--porcelain", "-uall") or "").splitlines():
        xy, path = l[:2], l[3:].split(" -> ")[-1].strip('"')
        ch[path] = (
            "A" if xy == "??" else "D" if "D" in xy else "R" if "R" in xy else "M"
        )
    return ch


def required(ch):
    paths = list(ch)
    out = []
    if any(p.endswith(".md") for p in paths) or any(s in "DR" for s in ch.values()):
        out.append("19")
    if any(p.endswith(".md") for p in paths):
        out.append("20")
    if paths:
        out.append("21")
    if any(Path(p).suffix.lower() not in DOC_EXT for p in paths):
        out.append("verify")
    return out


def lines_of(repo, rel):
    try:
        return (
            (Path(repo) / rel).read_text(encoding="utf-8", errors="ignore").splitlines()
        )
    except OSError:
        return []


def existing(repo, ch, only=None):
    return sorted(
        p
        for p, s in ch.items()
        if s != "D" and (Path(repo) / p).is_file() and (only is None or only(p))
    )


def read_report(repo, tr):
    f = rec_dir(repo) / tr / "report.json"
    if not f.is_file():
        raise ValueError(
            f"report.json missing for tree {tr[:10]}: run state-report.py --json {RECORDS}"
        )
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except ValueError as x:
        raise ReportError(f"report.json unreadable for tree {tr[:10]}: {x}")
    if not isinstance(doc, dict) or not isinstance(doc.get("indices"), dict):
        raise ReportError(
            f"report.json wrong shape for tree {tr[:10]} (need object with indices map): rerun state-report.py --json {RECORDS}"
        )
    return doc


def load_report(repo, tr):
    doc = read_report(repo, tr)
    if doc.get("truncated") is True and not os.environ.get(
        "WORK_AUDIT_ALLOW_TRUNCATED"
    ):
        raise ValueError(
            f"report.json partial scan for tree {tr[:10]}: rerun state-report.py --json {RECORDS}"
        )
    if doc.get("indices", {}).get("complete") is not True:
        raise ValueError(
            f"report.json incomplete for tree {tr[:10]}: rerun state-report.py --json {RECORDS}"
        )
    return doc.get("indices", {})


def claim_pool(repo, mds):
    pool = {}
    for md in mds:
        fence = False
        for n, l in enumerate(lines_of(repo, md), 1):
            if l.lstrip().startswith("```"):
                fence = not fence
            if fence:
                continue
            for tok in re.findall(r"`([^`\n]+)`", l):
                if any(p.match(tok) for p in CLAIM_PATTERNS) and not FILE_EXT.search(
                    tok
                ):
                    pool.setdefault((md, tok.removesuffix("()")), n)
    return pool


SHARED_BLOCK = re.compile(r"<!-- SHARED:START -->.*?<!-- SHARED:END -->", re.S)


def h2_pairs(repo, n):
    tracked = (git(repo, "ls-files", "-co", "--exclude-standard") or "").splitlines()
    heads = {}
    for f in (
        t
        for t in tracked
        if t.endswith(".md")
        and "fixtures" not in t.lower()
        and (Path(repo) / t).is_file()
    ):
        for h in {
            m.strip()
            for m in re.findall(
                r"(?m)^##\s+(.+)$", SHARED_BLOCK.sub("", "\n".join(lines_of(repo, f)))
            )
        }:
            heads.setdefault(h, []).append(f)
    score = {}
    for h, fs in heads.items():
        for i, a in enumerate(sorted(fs)):
            for b in sorted(fs)[i + 1 :]:
                score.setdefault((a, b), []).append(h)
    ranked = sorted(score.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:n]
    return [
        {"id": f"p{i}", "kind": "pair", "a": a, "b": b, "token": sorted(hs)[0]}
        for i, ((a, b), hs) in enumerate(ranked, 1)
    ]


def spec(repo, tr, ch, idx):
    rng = random.Random(f"{tr}:{idx}")
    ex = existing(repo, ch)
    mds = [p for p in ex if p.endswith(".md")]
    match idx:
        case "19":
            rp = load_report(repo, tr).get("19", {})
            refs = sorted(
                {(b["doc"], b["ref"]) for b in rp.get("bad_refs", [])}
                | {(b["doc"], b["adr"]) for b in rp.get("adr", [])}
            )
            samples = []
            for i, (doc, tok) in enumerate(refs, 1):
                n = next(
                    (k for k, l in enumerate(lines_of(repo, doc), 1) if tok in l), 0
                )
                samples.append(
                    {"id": f"r{i}", "kind": "ref", "doc": doc, "line": n, "token": tok}
                )
            pool = sorted(claim_pool(repo, mds).items())
            for i, ((doc, tok), n) in enumerate(
                rng.sample(pool, min(len(pool), min(10, 2 + len(mds)))), 1
            ):
                samples.append(
                    {
                        "id": f"c{i}",
                        "kind": "claim",
                        "doc": doc,
                        "line": n,
                        "token": tok,
                    }
                )
            files = sorted(
                {
                    *mds,
                    *(s["doc"] for s in samples if (Path(repo) / s["doc"]).is_file()),
                }
            )
            return {
                "required_files": files,
                "samples": samples,
                "inputs": {"report_19": rp},
            }
        case "20":
            rp = load_report(repo, tr).get("20", {})
            return {
                "required_files": mds,
                "samples": h2_pairs(repo, 5),
                "inputs": {"report_20": rp, "changed_md": mds},
            }
        case "21":
            tracked = (
                git(repo, "ls-files", "-co", "--exclude-standard") or ""
            ).splitlines()
            styles = sorted(
                t
                for t in tracked
                if (Path(repo) / t).is_file()
                and any(fnmatch.fnmatchcase(t.lower(), g) for g in STYLE_GLOBS)
            )
            files = [p for p in ex if p not in styles]
            picks = rng.sample(files, min(10, len(files)))
            return {
                "required_files": sorted({*styles, *files}),
                "style_docs": styles,
                "samples": [
                    {"id": f"f{i}", "kind": "file", "file": p}
                    for i, p in enumerate(sorted(picks), 1)
                ],
                "inputs": {"changed_files": files},
            }
        case _:
            files = existing(repo, ch, lambda p: Path(p).suffix.lower() not in DOC_EXT)
            return {
                "required_files": files,
                "samples": [],
                "inputs": {"changed_non_doc_files": files},
            }


def previous(repo, idx, tr):
    best = None
    for f in rec_dir(repo).glob(f"*/{idx}.json"):
        if f.parent.name == tr:
            continue
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if (
            r.get("scheme") != SCHEME
        ):  # indices were renumbered: an older scheme's record names a different check
            continue
        if best is None or r.get("checked_at", "") > best.get("checked_at", ""):
            best = r
    return best


UNFINGERPRINTABLE = "unfingerprintable (git timed out)"


def brief(repo):
    repo = find_repo(repo)
    tr = tree(repo)
    if not tr:
        raise ValueError(
            f"{UNFINGERPRINTABLE}: cannot fingerprint {repo.name}, fix git and rerun state-report.py --json"
        )
    rf = rec_dir(repo) / tr / "report.json"
    if rf.is_file():
        rdoc = read_report(repo, tr)
        if rdoc.get("truncated") is True and not os.environ.get(
            "WORK_AUDIT_ALLOW_TRUNCATED"
        ):
            raise ValueError(
                f"report.json partial scan for tree {tr[:10]}: rerun state-report.py --json {RECORDS}"
            )
    ch = changed(repo, tr)
    out = {
        "repo": repo.name,
        "path": str(repo),
        "tree": tr,
        "head": head(repo),
        "baseline": baseline(repo) or None,
        "report": str(rec_dir(repo) / tr / "report.json"),
        "changed": ch,
        "required": {},
        "previous_findings": {},
    }
    for idx in required(ch):
        out["required"][idx] = spec(repo, tr, ch, idx)
        prev = previous(repo, idx, tr)
        out["previous_findings"][idx] = [
            f for f in (prev or {}).get("findings", []) if f.get("fixed") is False
        ]
    return out


def norm(p):
    return str(p).replace("\\", "/").removeprefix("./")


def resolve(repo, p):
    p = Path(p)
    return p if p.is_absolute() else Path(repo) / p


def check_ref(repo, ref, token=None, must=None):
    m = re.fullmatch(r"(.+):(\d+)", str(ref).strip())
    if not m:
        return f"evidence '{ref}' is not path:line"
    p, n = resolve(repo, m[1]), int(m[2])
    if not p.is_file():
        return f"evidence file missing: {m[1]}"
    if must is not None and p.resolve() != resolve(repo, must).resolve():
        return f"evidence {ref} must point into {must}"
    ls = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    if not 1 <= n <= len(ls):
        return f"evidence {ref}: line out of range"
    if token is not None and not token_in(token, ls[n - 1]):
        return f"evidence {ref}: line does not contain '{token}'"
    return None


def token_in(token, line):
    """The token is on the line; a PowerShell parameter `-Name` also matches its `$Name` declaration."""
    if token in line:
        return True
    m = re.fullmatch(r"-([A-Za-z_]\w*)", token)
    return bool(m) and re.search(rf"\${m[1]}\b", line, re.I) is not None


TEST_TIMEOUT = (
    900  # a whole suite, not one git call: the 30 s spawn cap killed 2-minute suites
)


def run_test(repo, cmd):
    """(exit code, timed out) of a recorded test command re-run in the repo."""
    limit = float(os.environ.get("WORK_AUDIT_TEST_TIMEOUT", TEST_TIMEOUT))
    rc, _out, _err, timed_out = proc_run(cmd, cwd=repo, timeout=limit, shell=True)
    return rc, timed_out


def validate(repo, rec, strict=True, pre=None):
    repo = Path(repo)
    e = []
    for k, t in (
        ("index", str),
        ("repo", str),
        ("files_read", list),
        ("findings", list),
        ("samples", list),
        ("verdict", str),
    ):
        if not isinstance(rec.get(k), t):
            e.append(f"field '{k}' missing or not {t.__name__}")
    if e:
        return e, {}
    idx, verdict = rec["index"], rec["verdict"]
    if (
        idx not in INDICES
        or rec["repo"] != repo.name
        or verdict not in ("pass", "fail", "unverifiable")
    ):
        return ["index, repo or verdict invalid"], {}
    tr = pre[0] if pre is not None else tree(repo)
    if rec.get("tree", tr) != tr:
        e.append("record tree differs from the current tree")
    ch = pre[1] if pre is not None else changed(repo, tr)
    if idx not in required(ch):
        return [f"index {idx} is not required for this repo"], {}
    try:
        sp = spec(repo, tr, ch, idx)
    except ValueError as x:
        return [str(x)], {}
    read = {norm(p) for p in rec["files_read"]}
    e += [
        f"required file not in files_read: {p}"
        for p in sp["required_files"]
        if p not in read
    ]
    e += [
        f"files_read entry does not exist: {p}"
        for p in sorted(read)
        if not resolve(repo, p).is_file()
    ]
    for f in rec["findings"]:
        if not isinstance(f, dict) or any(
            not isinstance(f.get(k), t) for k, t in FINDING_KEYS.items()
        ):
            e.append(f"finding malformed (needs {sorted(FINDING_KEYS)}): {f}")
        elif err := check_ref(repo, f["evidence"]):
            e.append(f"finding '{f['claim'][:40]}': {err}")
    want = {s["id"]: s for s in sp["samples"]}
    got = {s.get("id"): s for s in rec["samples"] if isinstance(s, dict)}
    e += [f"sample {i} missing" for i in want if i not in got] + [
        f"sample {i} not in brief" for i in got if i not in want
    ]
    unverifiable, bad = 0, 0
    for i, s in got.items():
        w = want.get(i)
        if not w:
            continue
        st = s.get("status")
        if st not in STATUS[w["kind"]]:
            e.append(f"sample {i}: status '{st}' not in {sorted(STATUS[w['kind']])}")
        elif st == "unverifiable":
            unverifiable += 1
            if not str(s.get("reason", "")).strip():
                e.append(f"sample {i}: unverifiable needs a reason")
        else:
            bad += st in BAD
            ev = str(s.get("evidence", ""))
            if w["kind"] == "pair":
                refs = [r.strip() for r in ev.split(";")]
                errs = (
                    [
                        check_ref(repo, r, w["token"], must=m)
                        for r, m in zip(refs, (w["a"], w["b"]))
                    ]
                    if len(refs) == 2
                    else ["pair needs 'a:line; b:line'"]
                )
                err = next((x for x in errs if x), None)
            elif w["kind"] == "file":
                err = check_ref(repo, ev, must=w["file"])
            elif st == "traced":
                # A composed name (f"{P}_{n}_{d}.ris") is on no line verbatim: the evidence is the
                # code line that builds it, outside any doc, with a reason saying how.
                err = check_ref(repo, ev)
                if not err and (
                    ev.rsplit(":", 1)[0].lower().endswith(".md")
                    or not str(s.get("reason", "")).strip()
                ):
                    err = "traced needs a non-doc path:line that builds the token and a reason"
            else:
                err = check_ref(repo, ev, w["token"])
                if (
                    not err
                    and w["kind"] == "claim"
                    and st == "ok"
                    and resolve(repo, ev.rsplit(":", 1)[0]).resolve()
                    == resolve(repo, w["doc"]).resolve()
                ):
                    err = "claim marked ok must be evidenced outside its own doc"
            if err:
                e.append(f"sample {i}: {err}")
    counts = {}
    if idx == "21":
        for d in sp["style_docs"]:
            if not any(
                str(r).rsplit("@", 1)[-1].startswith(d + ":")
                for r in rec.get("rules", [])
            ):
                e.append(f"rules: need at least one quote@{d}:line")
        for r in rec.get("rules", []):
            q, _, ref = str(r).rpartition("@")
            m = re.fullmatch(r"(.+):(\d+)", ref)
            ls = lines_of(repo, m[1]) if m else []
            if (
                not m
                or len(q) < 8
                or not 1 <= int(m[2]) <= len(ls)
                or " ".join(q.split()).lower()
                not in " ".join(ls[int(m[2]) - 1].split()).lower()
            ):
                e.append(f"rule not quoted verbatim at its line: {r}")
    if idx == "verify":
        evs = rec.get("evidence", [])
        if (
            not isinstance(evs, list)
            or not isinstance(rec.get("tests_identified", []), list)
            or not isinstance(rec.get("open_questions", 0), int)
        ):
            return e + [
                "verify needs evidence[], tests_identified[], open_questions:int"
            ], {}
        done, ran = set(), set()
        for v in evs:
            f, k = (
                (v.get("file"), v.get("kind")) if isinstance(v, dict) else (None, None)
            )
            if f not in sp["required_files"] or k not in (
                "test",
                "review",
                "unverifiable",
            ):
                e.append(f"evidence entry invalid or file not required: {v}")
            elif k == "test":
                ran.add(v.get("cmd"))
                rc, timed_out = (
                    run_test(repo, str(v.get("cmd")))
                    if strict
                    else (v.get("exit"), False)
                )
                if timed_out:
                    e.append(
                        f"test re-run timed out (WORK_AUDIT_TEST_TIMEOUT): {v.get('cmd')}"
                    )
                elif rc != v.get("exit"):
                    e.append(
                        f"test re-run exit differs from recorded exit: {v.get('cmd')}"
                    )
                done.add(f)
            elif k == "review":
                r = rec_dir(repo) / tr / f"{v.get('record')}.json"
                try:
                    ok = f in json.loads(r.read_text(encoding="utf-8")).get(
                        "files_read", []
                    ) and v.get("record") in ("19", "20", "21")
                except (OSError, ValueError):
                    ok = False
                if ok:
                    done.add(f)
                else:
                    e.append(
                        f"review evidence needs a stored record that read {f}: {v}"
                    )
            else:
                unverifiable += bool(str(v.get("reason", "")).strip())
                if not str(v.get("reason", "")).strip():
                    e.append(f"unverifiable evidence needs a reason: {v}")
        nv = [f for f in sp["required_files"] if f not in done]
        counts = {
            "finished": len(done),
            "not_verified": len(nv),
            "skipped": len(
                [c for c in rec.get("tests_identified", []) if c not in ran]
            ),
            "left": len(nv) + rec.get("open_questions", 0),
        }
        if verdict == "pass" and any(
            counts[k] for k in ("not_verified", "skipped", "left")
        ):
            e.append(f"verdict pass with unverified work: {counts}")
    open_f = [
        f for f in rec["findings"] if isinstance(f, dict) and f.get("fixed") is False
    ]
    if open_f and verdict != "fail":
        e.append("any fixed:false finding forces verdict fail")
    if verdict == "fail" and not open_f and idx != "verify":
        e.append("verdict fail needs a fixed:false finding")
    if verdict == "unverifiable" and not unverifiable:
        e.append(
            "verdict unverifiable needs a sample or evidence marked unverifiable with a reason"
        )
    if verdict == "pass" and unverifiable:
        e.append("verdict pass but a sample is unverifiable")
    if verdict == "pass" and bad and not rec["findings"]:
        e.append("verdict pass with bad sample statuses and no findings")
    if strict:
        prev = (previous(repo, idx, tr) or {}).get("findings", [])
        before = {(f["path"], f["claim"]) for f in prev if f.get("fixed") is False}
        now = {
            (f["path"], f["claim"]): f
            for f in rec["findings"]
            if isinstance(f, dict) and "path" in f and "claim" in f
        }
        e += [
            f"fixed:true needs the previous record to hold it fixed:false and rechecked:true: {k[0]} / {k[1][:40]}"
            for k, f in now.items()
            if f.get("fixed") is True
            and not (k in before and f.get("rechecked") is True)
        ]
        e += [
            f"previous fixed:false finding dropped: {k[0]} / {k[1][:40]}"
            for k in before
            if k not in now
        ]
    return e, counts


def write_record(path):
    rec = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rec, dict):
        raise ValueError(
            "record must be a JSON object with index, repo, files_read, findings, samples and verdict"
        )
    repo = find_repo(rec.get("repo", ""))
    if not (repo / ".git").exists() or not rec.get("repo"):
        return ["repo not found"], None
    tr = tree(repo)
    if not tr:
        return [
            f"{UNFINGERPRINTABLE}: cannot fingerprint {repo.name}, fix git and write again"
        ], None
    ch = changed(repo, tr)
    errs, counts = validate(repo, rec, pre=(tr, ch))
    if errs:
        return errs, None
    rec.update(
        scheme=SCHEME,
        tree=tr,
        head=head(repo),
        checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    if counts:
        rec["counts"] = counts
    out = rec_dir(repo) / tr / f"{rec['index']}.json"
    atomic_write(out, json.dumps(rec, indent=1))
    return [], out


def status(advance=False, cache=None):
    res = []
    for repo in repos():
        try:
            tr = tree_cached(repo, cache) if cache is not None else tree(repo)
            if not tr:
                res.append(
                    (
                        "?",
                        repo.name,
                        "invalid",
                        f"{UNFINGERPRINTABLE}: cannot fingerprint, fix git and rerun state-report.py --json",
                    )
                )
                continue
            rf = rec_dir(repo) / tr / "report.json"
            try:
                doc = json.loads(rf.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                doc = None
            if rf.is_file() and (
                not isinstance(doc, dict) or not isinstance(doc.get("indices"), dict)
            ):
                res.append(
                    (
                        "report",
                        repo.name,
                        "invalid",
                        f"report wrong shape for tree {tr[:10]}: rerun state-report.py --json",
                    )
                )
                continue
            if (
                rf.is_file()
                and doc.get("truncated") is True
                and not os.environ.get("WORK_AUDIT_ALLOW_TRUNCATED")
            ):
                res.append(
                    (
                        "report",
                        repo.name,
                        "invalid",
                        f"report partial scan for tree {tr[:10]}: rerun state-report.py --json",
                    )
                )
                continue
            complete = (
                isinstance(doc, dict) and doc.get("indices", {}).get("complete") is True
            )
            if rf.is_file() and not complete:
                res.append(
                    (
                        "report",
                        repo.name,
                        "invalid",
                        "report incomplete: rerun state-report.py --json",
                    )
                )
                continue
            ch = changed(repo, tr)
            rows = []
            for idx in required(ch):
                f = rec_dir(repo) / tr / f"{idx}.json"
                if not f.is_file():
                    rows.append((idx, repo.name, "missing", ""))
                    continue
                try:
                    rec = json.loads(f.read_text(encoding="utf-8"))
                    if (
                        rec.get("scheme") != SCHEME
                    ):  # an older scheme's record is no record
                        rows.append((idx, repo.name, "missing", ""))
                        continue
                    errs, _ = validate(repo, rec, strict=False, pre=(tr, ch))
                except ValueError as x:
                    errs = [str(x)]
                if rec.get("tree") != tr:
                    errs.append("tree differs")
                rows.append(
                    (
                        idx,
                        repo.name,
                        "invalid"
                        if errs
                        else {"pass": "ok"}.get(rec["verdict"], rec["verdict"]),
                        "; ".join(errs[:2]),
                    )
                )
            res += rows
            if advance and all(r[2] == "ok" for r in rows) and baseline(repo) != tr:
                d = rec_dir(repo)
                d.mkdir(parents=True, exist_ok=True)
                atomic_write(d / "baseline", tr)
                for old in (p for p in d.iterdir() if p.is_dir() and p.name != tr):
                    rmtree(old)
        except (OSError, ValueError, KeyError) as x:
            res.append(("?", repo.name, "invalid", f"{type(x).__name__}: {x}"))
    return res


def selftest_scope(base, case):
    root = base / "scope"
    root.mkdir()
    template = base / "scope-template"
    template.mkdir()
    for a in (("init", "-q"), ("commit", "-q", "--allow-empty", "-m", "i")):
        assert (
            git(template, "-c", "user.name=t", "-c", "user.email=t@t", *a) is not None
        ), f"selftest git failed: {a}"
    template = template.resolve()

    def mkrepo(name):
        # Copies of one template repo: identical shape, no git spawns.
        r = root / name
        shutil.copytree(template, r)
        return r.resolve()

    a, b, c, d, e = (
        mkrepo(n) for n in ("repo-a", "repo-b", "repo-c", "repo-d", "repo-e")
    )
    wt = (root / "wt-a").resolve()
    assert git(a, "worktree", "add", "-q", str(wt), "-b", "side") is not None
    plain = root / "plain"
    plain.mkdir()
    bash_b = (
        f"/{str(b)[0].lower()}{b.as_posix()[2:]}" if sys.platform == "win32" else str(b)
    )

    def tu(name, inp):
        return json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "tool_use", "name": name, "input": inp}]
                },
            }
        )

    lines = [
        tu("Edit", {"file_path": str(a / "gone" / "x.txt")}),
        tu("Bash", {"command": f'cd "{bash_b}" && ls'}),
        tu("Bash", {"command": f"git -C '{c}' status"}),
        json.dumps({"type": "user", "cwd": str(wt), "message": {"content": "hi"}}),
        "not json",
        tu("Grep", {"path": str(plain)}),
    ]
    got = set(scope(plain, lines, env=False))
    case(
        "scope: tool paths, cd, -C, entry cwd, worktree + main",
        got == {a, b, c, wt} and plain.resolve() not in got and e not in got,
    )
    case(
        "scope: no inputs = cwd repo only",
        scope(c / "sub-missing", [], env=False) == [c],
    )
    case("scope: cwd outside any repo = empty", scope(plain, [], env=False) == [])
    saved = os.environ.get("WORK_AUDIT_ROOTS")
    os.environ["WORK_AUDIT_ROOTS"] = (";" if sys.platform == "win32" else ":").join(
        [str(d), str(plain)]
    )
    try:
        case("scope: WORK_AUDIT_ROOTS adds repos", scope(plain, [], env=True) == [d])
    finally:
        os.environ.pop("WORK_AUDIT_ROOTS") if saved is None else os.environ.update(
            WORK_AUDIT_ROOTS=saved
        )
    case(
        "scope: explicit parent folder lists child repos",
        {*scope(roots=[root], env=False)} == {a, b, c, d, e, wt},
    )


def selftest():
    global RECORDS
    base = RECORDS / ".tmp" / "selftest"
    if base.exists():
        rmtree(base)
    saved = RECORDS, SCOPE[:]
    os.environ["GIT_CEILING_DIRECTORIES"] = str(base)
    RECORDS = base / "records"
    d = base / "work" / "demo"
    d.mkdir(parents=True)
    d = d.resolve()
    SCOPE[:] = [d]
    results = []

    def sh(*a):
        assert git(d, "-c", "user.name=t", "-c", "user.email=t@t", *a) is not None, (
            f"selftest git failed: {a}"
        )

    def case(name, ok):
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'} {name}")

    def mk(idx, tr, ch, **kw):
        # tr/ch are passed in: the demo content changes only three times, so
        # recomputing the fingerprint per record would respawn git for nothing.
        sp = spec(d, tr, ch, idx)
        rec = {
            "index": idx,
            "repo": "demo",
            "files_read": sp["required_files"],
            "findings": [],
            "samples": [],
            "verdict": "pass",
        }
        for s in sp["samples"]:
            ev = {
                "claim": "app.py:1",
                "file": f"{s.get('file')}:1",
                "pair": "",
                "ref": f"{s.get('doc')}:{s.get('line')}",
            }[s["kind"]]
            rec["samples"].append(
                {
                    "id": s["id"],
                    "status": {
                        "claim": "ok",
                        "file": "conforms",
                        "ref": "placeholder",
                        "pair": "distinct",
                    }[s["kind"]],
                    "evidence": ev,
                }
            )
        if idx == "21":
            rec["rules"] = [
                next(
                    f"{l}@{s}:{n}"
                    for n, l in enumerate(lines_of(d, s), 1)
                    if len(l) >= 8
                )
                for s in sp["style_docs"]
            ]
        rec.update(kw)
        p = base / f"{idx}.in.json"
        p.write_text(json.dumps(rec))
        return p, rec

    try:
        sh("init", "-q")
        (d / "README.md").write_text("# Demo\n\nUse `--fast-mode` here.\n")
        (d / "app.py").write_text('parser.add_argument("--fast-mode")\n')
        t1 = tree(d)
        sh("add", "-A")
        sh("commit", "-qm", "one")
        case("tree unchanged by commit", tree(d) == t1)
        (d / "app.py").write_text('parser.add_argument("--fast-mode")\nx = 1\n')
        case("tree changes with content", tree(d) != t1)
        ch = changed(d, tree(d))
        case("first run changed set = window files", set(ch) == {"README.md", "app.py"})
        case("required indices", required(ch) == ["19", "20", "21", "verify"])
        case(
            "diff-tree compares two tree hashes",
            parse_name_status(git(d, "diff-tree", "-r", "--name-status", t1, tree(d)))
            == {"app.py": "M"},
        )
        case(
            "brief is deterministic",
            json.dumps(spec(d, tree(d), ch, "21"))
            == json.dumps(spec(d, tree(d), ch, "21")),
        )
        tr = tree(d)
        (rec_dir(d) / tr).mkdir(parents=True)
        (rec_dir(d) / tr / "report.json").write_text(
            json.dumps(
                {
                    "indices": {
                        "complete": True,
                        "19": {"bad_refs": [], "adr": []},
                        "20": {},
                    }
                }
            )
        )
        chA = changed(d, tr)
        p, rec = mk("19", tr, chA)
        case("valid 19 record written", write_record(p)[0] == [])
        bad = dict(rec, files_read=[])
        p.write_text(json.dumps(bad))
        case(
            "missing required file rejected",
            any("files_read" in x for x in write_record(p)[0]),
        )
        bad = json.loads(json.dumps(rec))
        bad["samples"][0]["evidence"] = "app.py:2"
        p.write_text(json.dumps(bad))
        case(
            "bad line token rejected",
            any("does not contain" in x for x in write_record(p)[0]),
        )
        bad = json.loads(json.dumps(rec))
        bad["findings"] = [
            {
                "path": "README.md",
                "claim": "c",
                "evidence": "README.md:1",
                "severity": "low",
                "fixed": False,
            }
        ]
        p.write_text(json.dumps(bad))
        case(
            "fixed:false with pass rejected",
            any("forces verdict fail" in x for x in write_record(p)[0]),
        )
        bad = json.loads(json.dumps(rec))
        bad["samples"][0]["evidence"] = "README.md:3"
        p.write_text(json.dumps(bad))
        case(
            "claim ok evidenced only in its own doc rejected",
            any("outside its own doc" in x for x in write_record(p)[0]),
        )
        for idx in ("20", "21"):
            case(
                f"valid {idx} record written",
                write_record(mk(idx, tr, chA)[0])[0] == [],
            )
        pv, rv = mk(
            "verify",
            tr,
            chA,
            evidence=[{"file": "app.py", "kind": "test", "cmd": "exit 0", "exit": 0}],
            tests_identified=["exit 0"],
            open_questions=0,
        )
        case(
            "valid verify record written, counts derived",
            write_record(pv)[0] == []
            and json.loads((rec_dir(d) / tr / "verify.json").read_text())["counts"][
                "finished"
            ]
            == 1,
        )
        pv.write_text(
            json.dumps(
                dict(
                    rv,
                    evidence=[
                        {"file": "app.py", "kind": "test", "cmd": "exit 0", "exit": 1}
                    ],
                )
            )
        )
        case(
            "test re-run exit mismatch rejected",
            any("re-run" in x for x in write_record(pv)[0]),
        )
        case(
            "check: all pairs ok",
            all(s[2] == "ok" for s in status()) and len(status()) == 4,
        )
        status(advance=True)
        case(
            "baseline advanced, older trees pruned", baseline(d) == tr and not status()
        )
        (d / "app.py").write_text("y = 2\n")
        case(
            "edit after baseline requires 21+verify",
            [s[0] for s in status()] == ["21", "verify"],
        )
        trB = tree(d)
        chB = changed(d, trB)
        p, rec = mk(
            "21",
            trB,
            chB,
            verdict="fail",
            findings=[
                {
                    "path": "app.py",
                    "claim": "style",
                    "evidence": "app.py:1",
                    "severity": "low",
                    "fixed": False,
                }
            ],
        )
        case("fail record with open finding written", write_record(p)[0] == [])
        case(
            "check reports fail state",
            [s[2] for s in status() if s[0] == "21"] == ["fail"],
        )
        rec["findings"][0]["fixed"] = True
        p.write_text(json.dumps(rec))
        case(
            "fixed:true without rerun on a new tree rejected",
            any("fixed:true" in x for x in write_record(p)[0]),
        )
        (d / "app.py").write_text("y = 3\n")
        trC = tree(d)
        chC = changed(d, trC)
        p, rec = mk(
            "21",
            trC,
            chC,
            findings=[
                {
                    "path": "app.py",
                    "claim": "style",
                    "evidence": "app.py:1",
                    "severity": "low",
                    "fixed": True,
                    "rechecked": True,
                }
            ],
        )
        case(
            "fixed:true carried from previous fixed:false accepted",
            write_record(p)[0] == [],
        )
        p, rec = mk(
            "21",
            trC,
            chC,
            findings=[
                {
                    "path": "app.py",
                    "claim": "other",
                    "evidence": "app.py:1",
                    "severity": "low",
                    "fixed": True,
                    "rechecked": True,
                }
            ],
        )
        case(
            "fixed:true without a previous match rejected",
            any("fixed:true" in x for x in write_record(p)[0]),
        )
        case(
            "README is a style doc for index 21",
            spec(d, trC, chC, "21")["style_docs"] == ["README.md"],
        )
        selftest_scope(base, case)
    finally:
        RECORDS = saved[0]
        SCOPE[:] = saved[1]
        os.environ.pop("GIT_CEILING_DIRECTORIES", None)
        rmtree(base)
    return 0 if all(results) else 1


def main():
    a = sys.argv[1:]
    if "--selftest" in a:
        sys.exit(selftest())
    lines = []
    if "--transcript" in a:
        i = a.index("--transcript")
        t = Path(a[i + 1]) if i + 1 < len(a) else Path()
        lines = (
            t.read_text(encoding="utf-8", errors="ignore").splitlines()
            if t.is_file()
            else []
        )
        del a[i : i + 2]
    if not a:
        sys.exit(__doc__)
    cmd, rest = a[0], a[1:]
    if cmd == "write":
        if not rest:
            sys.exit(__doc__)
        rec_path, rest = rest[0], rest[1:]
    SCOPE[:] = scope(roots=rest, env=False) if rest else scope(Path.cwd(), lines)
    match cmd:
        case "brief":
            try:
                print(json.dumps([brief(r) for r in SCOPE], indent=1))
            except ReportError as x:
                print(f"brief failed: {x}", file=sys.stderr)
                sys.exit(2)
            except (ValueError, OSError) as x:
                sys.exit(f"brief failed: {x}")
        case "write":
            try:
                errs, out = write_record(rec_path)
            except (ValueError, OSError) as x:
                print(f"record.py write: bad record file: {x}", file=sys.stderr)
                sys.exit(2)
            print("\n".join(errs) if errs else f"written {out}")
            sys.exit(1 if errs else 0)
        case "check":
            res = status(advance=True)
            for idx, repo, state, detail in res:
                print(f"{repo} {idx}: {state} {detail}".rstrip())
            for repo in repos():
                tr = tree(repo)
                f = rec_dir(repo) / tr / "verify.json" if tr else None
                if f is not None and f.is_file():
                    print(
                        f"{repo.name} counts: {json.loads(f.read_text(encoding='utf-8')).get('counts')}"
                    )
            print(f"pairs not ok: {sum(r[2] != 'ok' for r in res)}")
            if any(r[0] == "report" and "wrong shape" in r[3] for r in res):
                sys.exit(2)
            sys.exit(1 if any(r[2] != "ok" for r in res) else 0)
        case _:
            sys.exit(__doc__)


if __name__ == "__main__":
    main()
