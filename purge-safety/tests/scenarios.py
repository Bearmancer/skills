"""Golden scenarios for the parity tests.

Each scenario builds a fresh tree under a base directory, runs `purge.py` or
`from-work-audit-report.py` with logical options, and collects what the run left behind: exit code,
stdout, stderr, the manifest or journal it wrote, and the tree. `normalize` turns that into a
comparable record: the base path becomes `<B>`, and timestamps and process ids drop out.

The goldens were recorded from the PowerShell engine this port replaced (#281), with its flag names
already rewritten to the Python ones (`-MaxPaths` became `--max-paths`).
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
GOLDENS = Path(__file__).resolve().parent / "goldens"
ENGINE_PY = SCRIPTS / "purge.py"
ADAPTER_PY = SCRIPTS / "from-work-audit-report.py"
TIMEOUT = 300

STAMP = re.compile(r"\d{4}-\d{2}-\d{2} \d{6}")
OLD = datetime(2026, 1, 1).timestamp()
OLDER = datetime(2025, 12, 1).timestamp()
NEWER = datetime(2026, 2, 1).timestamp()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GUARDS = load("purge_guards", SCRIPTS / "purge-guards.py")


def lp(path):
    """A path the Win32 API accepts past MAX_PATH."""
    path = os.path.abspath(path)
    return path if len(path) < 240 or path.startswith("\\\\?\\") else "\\\\?\\" + path


def write(path, content="", mtime=None):
    path = Path(path)
    os.makedirs(lp(path.parent), exist_ok=True)
    data = content.encode("utf-8") if isinstance(content, str) else content
    with open(lp(path), "wb") as f:
        f.write(data)
    if mtime is not None:
        os.utime(lp(path), (mtime, mtime))
    return path


def mkdir(path, mtime=None):
    os.makedirs(lp(path), exist_ok=True)
    if mtime is not None:
        os.utime(lp(path), (mtime, mtime))


def empty_home(b):
    mkdir(b / "home" / "AppData" / "Local")
    return b / "home"


def env_for(home):
    home = Path(home)
    return {
        "USERPROFILE": str(home),
        "LOCALAPPDATA": str(home / "AppData" / "Local"),
        "APPDATA": str(home / "AppData" / "Roaming"),
    }


def manifest(path, rows, root, generated="now"):
    doc = {"root": str(root), "entries": rows}
    if generated == "now":
        # Written right after the tree; one second covers a filesystem clock that runs ahead of ours.
        doc["generated"] = (datetime.now() + timedelta(seconds=1)).astimezone().isoformat()
    elif generated:
        doc["generated"] = generated
    write(path, json.dumps(doc, indent=2))
    return path


def row(base, rel, verdict="PURGE", category="probe"):
    return {"path": str(Path(base) / rel), "verdict": verdict, "category": category, "reason": category}


# --- trees ------------------------------------------------------------------------------------


def build_home(home):
    """A fake home folder that exercises every scan rule, guard and size format."""
    h = Path(home)
    files = {
        "AppData/Local/uv/cache/big.bin": b"u" * 1572864,
        "AppData/Local/uv/cache/k.bin": b"k" * 2560,
        "AppData/Local/npm-cache/_cacache/x": "0123456789",
        "AppData/Roaming/npm/node_modules/x/index.js": "12345",
        ".cache/opencode/pkg.json": "{\"a\":1}",
        ".cache/other.txt": "zz",
        ".omo/logs/l.log": "logs",
        ".omo/agent/logs/a.log": "logs",
        ".omo/memory/note.md": "memory",
        ".omo/memory/note.md.bak": "memory",
        ".omo/agent/sessions/s1/f.txt": "s",
        ".omo/omo.jsonc": "{}",
        ".omo/omo.jsonc.bak": "{}",
        ".rustup/settings.toml": 'profile = "minimal"\ndefault_toolchain = "stable-x"\n',
        ".rustup/toolchains/stable-x/bin/rustc": "r",
        ".rustup/toolchains/nightly-y/lib/core": "n",
        "Dev/foo_tmp/x.txt": "tmp",
        "Dev/fixups/y": "f",
        "Dev/repo/.git/HEAD": "ref: refs/heads/main",
        "Dev/repo/package.json": "{}",
        "Dev/repo/dist/out.js": b"d" * 2048,
        "Dev/repo/dist/empty.txt": "",
        "Dev/repo/bin/tool": "t",
        "Dev/repo/src/__pycache__/m.pyc": "pyc!",
        "Dev/repo/src/app.py.orig": "o",
        "Dev/repo/src/notes.txt~": "n",
        "Dev/repo/src/cfg.backup.3": "c",
        "Dev/repo/src/main.py": "m",
        "Dev/norepo/bin/tool.exe": "e",
        "Dev/repo2/.git/HEAD": "ref: refs/heads/main",
        "Dev/repo2/App.CSPROJ": "<Project/>",
        "Dev/repo2/obj/x": "o",
        "Documents/x.bak": "b",
        ".git/HEAD": "ref: refs/heads/main",
        "package.json": "{}",
        "bin/tool.exe": "t",
    }
    for rel, content in files.items():
        write(h / rel, content, OLD)
    write(h / ".local/share/claude/versions/1.0", b"v" * 100, OLDER)
    write(h / ".local/share/claude/versions/2.0", b"v" * 100, NEWER)
    write(h / "AppData/Local/Temp/old.txt", "old", OLD)
    write(h / "AppData/Local/Temp/olddir/a.txt", "old", OLD)
    write(h / "AppData/Local/Temp/new.txt", "new")
    mkdir(h / ".omo/agent/projects/orphan")
    mkdir(h / "Dev/emptynew")
    mkdir(h / "deep/a/b/c")
    GUARDS.junction(h / "Dev/foo_tmp/j", h / "Documents")
    GUARDS.junction(h / "Dev/link", h / "Dev/repo")
    for rel in ("AppData/Local/Temp/olddir", ".omo/agent/projects/orphan", "deep/a/b/c", "deep/a/b"):
        mkdir(h / rel, OLD)
    mkdir(h / "Dev/emptyold", OLD)
    return h


# --- scenarios --------------------------------------------------------------------------------
# Each returns {"opts": {...}, "home": path, "hold": [open files], "cwd": path}.


def s_scan_home(b, json_mode=False):
    home = build_home(b / "home")
    opts = {"scan": True, "root": home, "out-dir": b / "out", "lock-file": b / "p.lock"}
    if json_mode:
        opts["json"] = True
    return {"opts": opts, "home": home}


def s_scan_long(b):
    home = empty_home(b)
    write(home / "Dev" / "long" / ("a" * 100) / ("b" * 100) / "deep.bak", "long", OLD)
    return {"opts": {"scan": True, "root": home, "out-dir": b / "out", "lock-file": b / "p.lock"}, "home": home}


def s_plan_rescan(b):
    home = build_home(b / "home")
    return {"opts": {"root": home, "out-dir": b / "out", "lock-file": b / "p.lock"}, "home": home}


def guard_tree(b):
    r = b / "r"
    GUARDS.new_fixture(r)
    empty_home(b)
    return r


def plan_trap_rows(b, r):
    drive = os.environ.get("SystemDrive", "C:")
    return [
        row(r, ".omo/memory", "PURGE", "trap-protected"),
        {"path": drive + "\\Windows\\Temp", "verdict": "PURGE", "category": "trap-outside", "reason": "outside root"},
        {"path": str(r / "cache") + "\\*", "verdict": "PURGE", "category": "trap-wildcard", "reason": "wildcard"},
        {"path": str(r / "cache") + "\\?x", "verdict": "PURGE", "category": "trap-wildcard", "reason": "wildcard"},
        {"path": str(r), "verdict": "PURGE", "category": "trap-root", "reason": "root itself"},
        {"path": str(r) + "\\", "verdict": "PURGE", "category": "trap-root", "reason": "root itself"},
        {"path": drive + "\\", "verdict": "PURGE", "category": "trap-drive", "reason": "drive root"},
        row(r, ".omo/agent/projects/orphan", "OWNER", "trap-owner"),
        row(r, "keep", "KEEP", "trap-keep"),
        {"path": str(r / "logs" / "keep.log"), "verdict": None, "category": "trap-null", "reason": "null verdict"},
        {"path": str(r / "logs" / "keep.log"), "category": "trap-missing", "reason": "no verdict"},
        {"path": "", "verdict": "PURGE", "category": "trap-empty", "reason": "empty"},
        {"path": "   ", "verdict": "PURGE", "category": "trap-blank", "reason": "blank"},
        {"path": str(r) + "\\..\\home", "verdict": "PURGE", "category": "trap-dotdot", "reason": "escapes"},
        {"path": str(r / "junctions" / "lock" / "important.txt"), "verdict": "PURGE", "category": "trap-hop", "reason": "through a junction"},
        row(r, "cache/node_modules", "PURGE", "cache-tree"),
        row(r, "proj/artifacts", "purge", "lowercase-verdict"),
        {"path": str(r / "logs" / "app.log.bak").replace("\\", "/"), "verdict": "PURGE"},
        row(r, "never/existed", "PURGE", "missing-target"),
        {"path": "r\\zero\\stub.txt", "verdict": "PURGE", "category": "relative", "reason": "relative to cwd"},
        None,
    ]


def s_plan_traps(b, json_mode=False):
    r = guard_tree(b)
    m = manifest(b / "m" / "traps.json", plan_trap_rows(b, r), r)
    opts = {"root": r, "manifest": m, "out-dir": b / "out", "lock-file": b / "p.lock"}
    if json_mode:
        opts["json"] = True
    return {"opts": opts, "home": b / "home"}


def s_plan_clean(b):
    r = guard_tree(b)
    m = manifest(b / "m" / "clean.json", [row(r, "cache/node_modules"), row(r, "logs/app.log.bak", category="backup")], r)
    return {"opts": {"root": r, "manifest": m, "out-dir": b / "out", "lock-file": b / "p.lock"}, "home": b / "home"}


def apply_opts(b, r, m, **extra):
    return {"root": r, "manifest": m, "apply": True, "out-dir": b / "out", "lock-file": b / "p.lock", **extra}


def s_apply_full(b, json_mode=False):
    r = guard_tree(b)
    rows = [
        row(r, "cache/node_modules", "PURGE", "cache-tree"),
        row(r, "proj/artifacts", "PURGE", "build-output"),
        row(r, "logs/app.log.bak", "PURGE", "backup"),
        row(r, "junctions/lock", "PURGE", "junction"),
        row(r, "cache/uploads/empty1", "PURGE", "empty-shell"),
        row(r, "cache/uploads/empty2/nested", "PURGE", "empty-shell"),
        row(r, ".omo/agent/projects/orphan", "OWNER", "owner-row"),
    ]
    m = manifest(b / "m" / "apply.json", rows, r)
    opts = apply_opts(b, r, m, override=r / ".omo/agent/projects/orphan")
    if json_mode:
        opts["json"] = True
    return {"opts": opts, "home": b / "home"}


def s_apply_protected(b):
    r = guard_tree(b)
    m = manifest(b / "m" / "prot.json", [row(r, ".omo/memory", "PURGE", "protected-row")], r)
    return {"opts": apply_opts(b, r, m), "home": b / "home"}


def s_apply_protected_override(b):
    r = guard_tree(b)
    m = manifest(b / "m" / "prot.json", [row(r, ".omo/memory", "PURGE", "protected-row")], r)
    return {"opts": apply_opts(b, r, m, override=r / ".omo"), "home": b / "home"}


def s_apply_readonly(b):
    r = b / "r"
    f = write(r / "cache/node_modules/pkg/.git/objects/ab/cdef01", "blob")
    os.chmod(f, 0o444)
    empty_home(b)
    m = manifest(b / "m" / "ro.json", [row(r, "cache/node_modules", "PURGE", "cache-tree")], r)
    return {"opts": apply_opts(b, r, m), "home": b / "home"}


def s_apply_readonly_file(b):
    r = b / "r"
    f = write(r / "logs/locked.bak", "ro")
    os.chmod(f, 0o444)
    empty_home(b)
    m = manifest(b / "m" / "ro.json", [row(r, "logs/locked.bak", "PURGE", "backup")], r)
    return {"opts": apply_opts(b, r, m), "home": b / "home"}


def s_apply_junction_ancestor(b):
    r = guard_tree(b)
    GUARDS.new_fixture(r / "outside-hold")
    mkdir(r / "hop")
    GUARDS.junction(r / "hop" / "link", r / "outside-hold" / "keep")
    m = manifest(b / "m" / "hop.json", [row(r, "hop/link/important.txt", "PURGE", "junction-ancestor")], r)
    return {"opts": apply_opts(b, r, m), "home": b / "home"}


def s_apply_missing_verdict(b):
    r = guard_tree(b)
    m = manifest(b / "m" / "nov.json", [{"path": str(r / "cache/node_modules"), "category": "cache-tree", "reason": "no verdict field"}], r, generated=None)
    return {"opts": apply_opts(b, r, m), "home": b / "home"}


def s_apply_budget0(b):
    r = guard_tree(b)
    m = manifest(b / "m" / "budget.json", [row(r, "cache/node_modules", "PURGE", "cache-tree")], r)
    return {"opts": apply_opts(b, r, m, **{"max-minutes": 0}), "home": b / "home"}


def s_apply_lock_live(b):
    r = guard_tree(b)
    m = manifest(b / "m" / "locked.json", [row(r, "cache/node_modules", "PURGE", "cache-tree")], r)
    write(b / "p.lock", json.dumps({"pid": os.getpid(), "started": "probe", "mode": "apply"}))
    return {"opts": apply_opts(b, r, m), "home": b / "home"}


def s_apply_lock_stale(b):
    r = guard_tree(b)
    m = manifest(b / "m" / "stale-lock.json", [row(r, "cache/node_modules", "PURGE", "cache-tree")], r)
    write(b / "p.lock", json.dumps({"pid": 0, "started": "long ago", "mode": "apply"}))
    return {"opts": apply_opts(b, r, m), "home": b / "home"}


def s_apply_stale(b, force=False):
    r = guard_tree(b)
    m = manifest(b / "m" / "stale.json", [row(r, "logs/app.log.bak", "PURGE", "backup")], r, generated="2026-01-01T00:00:00.0000000+00:00")
    opts = apply_opts(b, r, m)
    if force:
        opts["force"] = True
    return {"opts": opts, "home": b / "home"}


def s_apply_maxpaths(b):
    r = guard_tree(b)
    m = manifest(b / "m" / "many.json", [row(r, "cache/node_modules"), row(r, "logs/app.log.bak")], r)
    return {"opts": apply_opts(b, r, m, **{"max-paths": 1}), "home": b / "home"}


def s_apply_failure(b):
    r = guard_tree(b)
    held = write(r / "busy/in-use.txt", "held open")
    m = manifest(b / "m" / "busy.json", [row(r, "busy", "PURGE", "busy-tree")], r)
    return {"opts": apply_opts(b, r, m), "home": b / "home", "hold": [held]}


def s_apply_max_failures(b):
    r = guard_tree(b)
    one = write(r / "busy1/in-use.txt", "held open")
    two = write(r / "busy2longer/in-use.txt", "held open")
    m = manifest(b / "m" / "busy.json", [row(r, "busy1"), row(r, "busy2longer")], r)
    return {"opts": apply_opts(b, r, m, **{"max-failures": 1}), "home": b / "home", "hold": [one, two]}


def s_apply_residue(b):
    r = guard_tree(b)
    m = manifest(b / "m" / "partial.json", [row(r, "cache/node_modules")], r)
    return {"opts": apply_opts(b, r, m), "home": b / "home"}


def s_apply_owner_no_override(b):
    r = guard_tree(b)
    m = manifest(b / "m" / "owner.json", [row(r, "logs/app.log.bak", "OWNER", "owner-row")], r)
    return {"opts": apply_opts(b, r, m), "home": b / "home"}


def s_apply_nested(b):
    r = b / "r"
    write(r / "work/.cache/opencode/pkg.json", "{}", OLD)
    write(r / "work/.cache/other.txt", "x", OLD)
    write(r / "work/.cache/sub/empty.txt", "", OLD)
    for rel in ("work/.cache/opencode", "work/.cache/sub", "work/.cache"):
        mkdir(r / rel, OLD)
    empty_home(b)
    # Removing the child rewrites the parent's LastWriteTime, so the parent row is refused as changed.
    rows = [row(r, "work/.cache"), row(r, "work/.cache/opencode"), row(r, "gone/already")]
    m = manifest(b / "m" / "nested.json", rows, r, generated="2026-01-02T00:00:00.0000000+00:00")
    return {"opts": apply_opts(b, r, m), "home": b / "home"}


def s_usage(opts_fn):
    def build(b):
        r = guard_tree(b)
        return {"opts": opts_fn(b, r), "home": b / "home"}
    return build


def s_missing_path_key(b):
    r = guard_tree(b)
    m = manifest(b / "m" / "nopath.json", [{"verdict": "PURGE", "category": "x"}], r)
    return {"opts": {"root": r, "manifest": m, "lock-file": b / "p.lock"}, "home": b / "home", "stderr": "prefix"}


def s_scan_budget0(b):
    home = build_home(b / "home")
    return {"opts": {"scan": True, "root": home, "out-dir": b / "out", "max-minutes": 0, "lock-file": b / "p.lock"}, "home": home}


ENGINE_SCENARIOS = {
    "scan-home": s_scan_home,
    "scan-home-json": lambda b: s_scan_home(b, json_mode=True),
    "scan-budget0": s_scan_budget0,
    "scan-long-path": s_scan_long,
    "plan-rescan": s_plan_rescan,
    "plan-traps": s_plan_traps,
    "plan-traps-json": lambda b: s_plan_traps(b, json_mode=True),
    "plan-clean": s_plan_clean,
    "apply-full": s_apply_full,
    "apply-full-json": lambda b: s_apply_full(b, json_mode=True),
    "apply-protected": s_apply_protected,
    "apply-protected-override": s_apply_protected_override,
    "apply-readonly": s_apply_readonly,
    "apply-readonly-file": s_apply_readonly_file,
    "apply-junction-ancestor": s_apply_junction_ancestor,
    "apply-missing-verdict": s_apply_missing_verdict,
    "apply-budget0": s_apply_budget0,
    "apply-lock-live": s_apply_lock_live,
    "apply-lock-stale": s_apply_lock_stale,
    "apply-stale": s_apply_stale,
    "apply-stale-force": lambda b: s_apply_stale(b, force=True),
    "apply-maxpaths": s_apply_maxpaths,
    "apply-failure": s_apply_failure,
    "apply-max-failures": s_apply_max_failures,
    "apply-residue": s_apply_residue,
    "apply-owner-no-override": s_apply_owner_no_override,
    "apply-nested": s_apply_nested,
    "usage-scan-and-apply": s_usage(lambda b, r: {"scan": True, "apply": True, "root": r, "manifest": b / "none.json"}),
    "usage-apply-no-manifest": s_usage(lambda b, r: {"apply": True, "root": r}),
    "usage-override-root": s_usage(lambda b, r: {"root": r, "override": str(r) + "\\", "manifest": b / "none.json"}),
    "usage-root-missing": s_usage(lambda b, r: {"root": b / "no-such-root", "manifest": b / "none.json"}),
    "usage-manifest-missing": s_usage(lambda b, r: {"root": r, "manifest": b / "none.json"}),
    "usage-drive-root": s_usage(lambda b, r: {"root": os.environ.get("SystemDrive", "C:") + "\\", "manifest": b / "none.json"}),
    "usage-missing-path-key": s_missing_path_key,
}


# --- adapter scenarios ------------------------------------------------------------------------


def adapter_tree(b, duplicates=False):
    repo = b / "work" / "proj"
    files = ["zero.txt", "a.tmp", "src/b.bak", "src/__pycache__/m.pyc", "old-ignored/x.log", "dup1.txt", "dup2.txt"]
    for rel in files:
        write(repo / rel, "" if rel == "zero.txt" else "data")
    mkdir(repo / "empty-dir")
    mkdir(repo / "nested/empty")
    report = {
        "repo": "proj",
        "indices": {
            "4": {
                "zero_byte": ["proj/zero.txt", "proj/missing.txt"],
                "tmp_bak_orig": ["proj/a.tmp", "proj/src/b.bak", "proj/zero.txt"],
                "pycache": ["proj/src/__pycache__"],
                "ignored_untracked_old": ["old-ignored", "../outside", "proj/../../escape"],
                "safety": {
                    "proj/a.tmp": {"files": 1, "newest_mtime": "2026-01-01 00:00", "branch": None},
                    "proj/src/__pycache__": {"files": 1, "newest_mtime": None, "branch": "main", "uncommitted": 0, "unpushed": 2},
                    "proj/zero.txt": {},
                },
            },
            "15": {"empty_dirs": ["proj/nested/empty", "proj/empty-dir"], "safety": {"proj/empty-dir": {"files": 0}}},
            "16": {"duplicates": [["proj/dup1.txt", "proj/dup2.txt"], ["proj/solo.txt"]]},
        },
    }
    write(b / "records" / "report.json", json.dumps(report, indent=2))
    opts = {"report": b / "records" / "report.json", "repo": repo}
    if duplicates:
        opts["include-duplicates"] = True
    return {"opts": opts}


def adapter_flat(b):
    """A hand-built report with the sections at the top level."""
    repo = b / "work" / "proj"
    write(repo / "x.orig", "o")
    write(b / "records" / "report.json", json.dumps({"4": {"tmp_bak_orig": ["x.orig"]}}))
    return {"opts": {"report": b / "records" / "report.json", "repo": repo, "out-dir": b / "elsewhere"}}


ADAPTER_SCENARIOS = {
    "adapter-report": adapter_tree,
    "adapter-report-duplicates": lambda b: adapter_tree(b, duplicates=True),
    "adapter-flat": adapter_flat,
    "adapter-empty": lambda b: (write(b / "records/report.json", "{}"), mkdir(b / "work/proj"),
                                {"opts": {"report": b / "records/report.json", "repo": b / "work/proj"}})[-1],
    "adapter-report-missing": lambda b: (mkdir(b / "work/proj"),
                                         {"opts": {"report": b / "records/none.json", "repo": b / "work/proj"}, "stderr": "prefix"})[-1],
}


# --- running ----------------------------------------------------------------------------------


def command(engine, opts):
    flags = []
    for name, value in opts.items():
        flags += ["--" + name] if value is True else ["--" + name, str(value)]
    script = ENGINE_PY if engine == "engine" else ADAPTER_PY
    return [sys.executable, str(script), *flags]


def run(engine, base, scenario):
    base = Path(base)
    spec = scenario(base)
    env = dict(os.environ)
    if spec.get("home"):
        env.update(env_for(spec["home"]))
    hold = [open(p, "rb") for p in spec.get("hold", [])]  # an open handle without share-delete blocks removal
    try:
        proc = subprocess.run(command(engine, spec["opts"]), cwd=base, capture_output=True, timeout=TIMEOUT, env=env,
                              stdin=subprocess.DEVNULL)
    finally:
        for f in hold:
            f.close()
    return collect(base, proc, spec)


def tree(base):
    out = []
    for dirpath, dirnames, filenames in os.walk(lp(base)):
        rel = os.path.relpath(dirpath, lp(base))
        for name in list(dirnames):
            full = os.path.join(dirpath, name)
            kind = "l" if os.path.islink(full) or os.path.isjunction(full) else "d"
            out.append(f"{kind} {os.path.normpath(os.path.join(rel, name))}")
            if kind == "l":
                dirnames.remove(name)
        out += [f"f {os.path.normpath(os.path.join(rel, n))}" for n in filenames]
    # pwsh wrote its module cache under the fake %LOCALAPPDATA% while the goldens were recorded.
    return sorted(o for o in out if not re.match(r"\w (out|m|records|elsewhere)(\\|$)", o) and o != "f p.lock"
                  and not re.search(r"AppData\\Local\\Microsoft(\\|$)", o))


def collect(base, proc, spec):
    outputs = []
    for folder in ("out", "records", "elsewhere"):
        d = base / folder
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.name.startswith("Purge "):
                    outputs.append((STAMP.sub("<STAMP>", f.name), f.read_text(encoding="utf-8-sig")))
    return {
        "base": str(base),
        "code": proc.returncode,
        "stdout": proc.stdout.decode("utf-8", errors="replace"),
        "stderr": proc.stderr.decode("utf-8", errors="replace"),
        "outputs": outputs,
        "tree": tree(base),
        "stderr_mode": spec.get("stderr", "exact"),
        "lock_left": (base / "p.lock").exists(),
    }


# --- normalizing ------------------------------------------------------------------------------

VOLATILE = {"generated", "utc", "pid", "journal", "started", "source"}


def scrub(text, base):
    for b in {base, "\\\\?\\" + base}:
        text = re.sub(re.escape(b), "<B>", text, flags=re.I)
    text = text.replace(base.replace("\\", "/"), "<B>")
    return STAMP.sub("<STAMP>", text)


def scrub_json(value, base):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in VOLATILE:
                continue
            if k == "error" or k == "abort_reason" and isinstance(v, str) and "could not be removed" in v:
                v = "<ERR>"
            out[k] = scrub_json(v, base)
        for k in ("entries", "refused"):
            if isinstance(out.get(k), list):
                out[k] = sorted(out[k], key=lambda e: json.dumps(e, sort_keys=True))
        return out
    if isinstance(value, list):
        return [scrub_json(v, base) for v in value]
    if isinstance(value, str):
        return scrub(value, base)
    return value


def lines_of(text, base):
    """Output lines as a sorted multiset; a REFUSED line keeps its reason line, FAILED keeps no message."""
    raw = [scrub(line.rstrip(), base) for line in text.splitlines()]
    joined = []
    for line in raw:
        if line.startswith("         reason: ") and joined:
            joined[-1] += " | " + line.strip()
        elif line.startswith("FAILED  "):
            joined.append(line.split(" :: ")[0] + " :: <ERR>")
        elif line.startswith("ABORT  ") and "could not be removed" in line:
            joined.append("ABORT  <ERR>")
        else:
            joined.append(line)
    return sorted(joined)


def parse_json_stream(text):
    """The JSON document an engine printed with --json (text before the first brace is ignored)."""
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    return json.loads(text[start:]) if start >= 0 else None


def normalize(result):
    base = result["base"]
    record = {"code": result["code"], "tree": [scrub(t, base) for t in result["tree"]], "lock_left": result["lock_left"]}
    if result["stderr_mode"] == "prefix":
        record["stderr"] = "<non-empty>" if result["stderr"].strip() else ""
    else:
        record["stderr"] = re.sub(r"\(pid \d+,", "(pid <PID>,", scrub(result["stderr"].strip(), base))
    json_out = None
    if result["stdout"].lstrip().startswith(("{", "[")):
        json_out = scrub_json(parse_json_stream(result["stdout"]), base)
        record["stdout"] = []
    else:
        record["stdout"] = lines_of(result["stdout"], base)
    record["json"] = json_out
    outputs = []
    for name, content in result["outputs"]:
        if name.endswith(".jsonl"):
            events = [scrub_json(json.loads(line), base) for line in content.splitlines() if line.strip()]
            outputs.append({"name": name, "events": sorted(events, key=lambda e: json.dumps(e, sort_keys=True))})
        else:
            outputs.append({"name": name, "doc": scrub_json(json.loads(content), base)})
    record["outputs"] = outputs
    return record


def golden_path(name):
    return GOLDENS / f"{name}.json"
