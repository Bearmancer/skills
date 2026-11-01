# /// script
# requires-python = ">=3.12"
# ///
"""Sprawl gate: no plan lives only in a file, no orphan worktrees.

check   -> print every violation; exit 1 when any exist.
hook    -> Claude PreToolUse (Write|Edit|MultiEdit): deny a write that would create plan sprawl.
stop    -> Claude Stop: report violations to the agent once (exit 2), then let the turn end.
explain -> print the hook verdict and the mechanism that decided it for each path argument (read-only).
drain   -> delete each plan-home file whose Tracker line names an issue that exists; keep the rest.

Spec, verdict table and the reason behind every exemption: references/sprawl-gate.md.

Base rules (deny unless an exemption below covers the path)
- plan-home-live: the plan home (~/.claude/plans) may hold a plan only until it is live. A file
  without a "Tracker: <issue url>" line is not live (plan-not-live); a file with one is a second
  copy of the issue and waits for `drain` (plan-live-undrained). Writes into the plan home are
  allowed, so plan mode can save its file; the tracker stays the one source of truth.
- stray-plan-dir: any file in a plan dir outside the plan home (STRAY_DIRS, anywhere in the path,
  including ~/.omo/plans: owner ruling on #247) is a violation.
- worktrees: every dir in <repo>/.claude/worktrees must be registered in `git worktree list`,
  and every registered worktree path must exist.

Exemptions, two mechanisms that never share a list
- OMO_RUNTIME_NEEDS: what omo needs to run, owned by the omo version, kept in this file.
- user exceptions: what the owner allowed, kept in sprawl-gate.toml (env SPRAWL_GATE_EXCEPTIONS_FILE);
  every entry needs path, reason and granted (a date), or it is reported and not applied.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

HOME = Path(os.environ.get("SPRAWL_GATE_HOME", Path.home()))
PLAN_HOME = Path(os.environ.get("SPRAWL_GATE_PLAN_HOME", HOME / ".claude" / "plans"))
DEV = Path(os.environ.get("SPRAWL_GATE_DEV", HOME / "Dev"))
EXCEPTIONS_FILE = Path(os.environ.get("SPRAWL_GATE_EXCEPTIONS_FILE", Path(__file__).with_name("sprawl-gate.toml")))
STRAY_DIRS = (".omo/plans", ".mo/plans", ".claude/plans", ".omc/plans")
# The issue CLI drain asks whether an issue exists; env SPRAWL_GATE_GH swaps in a fake for tests.
GH = os.environ.get("SPRAWL_GATE_GH", "gh")
TRACKER = re.compile(r"^\s*Tracker:\s*https://github\.com/([\w.-]+/[\w.-]+)/issues/(\d+)\b", re.MULTILINE)

# Omo runtime needs: (dir directly under the plan home, reason). Not owner consent; derived from
# omo's executor state layout, so an omo layout change is a change here and in the spec.
# Empty since #174: nothing on this machine writes executor state into the plan home any more.
OMO_RUNTIME_NEEDS: tuple[tuple[str, str], ...] = ()

USER_EXCEPTION = "user exception"
OMO_NEED = "omo runtime need"
OUT_OF_SCOPE = "out of scope"


def norm(p: Path | str) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def under(n: str, root: str) -> bool:
    return n == root or n.startswith(root + os.sep)


def user_exceptions() -> tuple[list[tuple[str, str]], list[str]]:
    """Return ([(normalized path, reason)], [problems]) from the owner's exception file."""
    if not EXCEPTIONS_FILE.is_file():
        return [], []
    try:
        data = tomllib.loads(EXCEPTIONS_FILE.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        return [], [f"user exception file unreadable, no exception applied: {EXCEPTIONS_FILE}: {e}"]
    good: list[tuple[str, str]] = []
    bad: list[str] = []
    for i, entry in enumerate(data.get("exception", [])):
        missing = [k for k in ("path", "reason", "granted") if not str(entry.get(k, "")).strip()]
        if missing:
            bad.append(f"user exception #{i + 1} in {EXCEPTIONS_FILE} lacks {', '.join(missing)}; not applied")
            continue
        raw = str(entry["path"])
        path = HOME / raw[2:] if raw.startswith("~/") else Path(raw)
        good.append((norm(path), f"{entry['reason']} (granted {entry['granted']})"))
    return good, bad


NESTED_ROOTS = ("instances", "fixups")


def roots() -> list[Path]:
    out: list[Path] = []
    if not DEV.is_dir():
        return out
    for a in DEV.iterdir():
        if not a.is_dir():
            continue
        out.append(a)
        if a.name in NESTED_ROOTS:
            out.extend(b for b in a.iterdir() if b.is_dir())
    return out


def tracker(f: Path) -> tuple[str, str] | None:
    """Return (owner/repo, issue number) from the file's Tracker line, or None."""
    try:
        m = TRACKER.search(f.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    return (m.group(1), m.group(2)) if m else None


def plan_files() -> list[Path]:
    """Every file in the plan home that no omo runtime need or user exception covers."""
    if not PLAN_HOME.is_dir():
        return []
    exceptions = user_exceptions()[0]
    needs = {os.path.normcase(name) for name, _ in OMO_RUNTIME_NEEDS}
    home = norm(PLAN_HOME)
    out: list[Path] = []
    for f in sorted(PLAN_HOME.rglob("*")):
        n = norm(f)
        if not f.is_file() or n[len(home) + 1 :].split(os.sep)[0] in needs:
            continue
        if not any(under(n, root) for root, _ in exceptions):
            out.append(f)
    return out


def plan_violations() -> list[str]:
    exceptions, v = user_exceptions()

    def excepted(p: Path) -> bool:
        return any(under(norm(p), root) for root, _ in exceptions)

    for f in plan_files():
        t = tracker(f)
        if t is None:
            v.append(f"[plan-not-live] file this plan as a tracker issue, add a 'Tracker: <issue url>' line, then run drain: {f}")
        else:
            v.append(f"[plan-live-undrained] {t[0]}#{t[1]} is the record; run drain to delete this copy: {f}")
    for r in roots():
        for sub in STRAY_DIRS:
            d = r / sub
            if d.is_dir():
                for f in sorted(d.rglob("*")):
                    if f.is_file() and not excepted(f):
                        v.append(f"[stray-plan-dir] stray plan file: {f}")
    return v


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30)
    return r.stdout


def worktree_violations() -> list[str]:
    v: list[str] = []
    for r in roots():
        if not (r / ".git").is_dir():
            continue
        registered = {norm(line[9:]) for line in git(r, "worktree", "list", "--porcelain").splitlines() if line.startswith("worktree ")}
        for path in sorted(registered):
            if not os.path.exists(path):
                v.append(f"{r.name}: registered worktree missing on disk: {path}")
        wt = r / ".claude" / "worktrees"
        if wt.is_dir():
            for d in sorted(wt.iterdir()):
                if d.is_dir() and norm(d) not in registered:
                    v.append(f"{r.name}: orphan worktree dir (not in git worktree list): {d}")
    return v


def violations() -> list[str]:
    return plan_violations() + worktree_violations()


def verdict(file_path: str) -> tuple[bool, str, str]:
    """Return (allowed, mechanism, reason) for a hooked write; mechanism names what decided it."""
    p = Path(file_path)
    n = norm(p)
    for root, reason in user_exceptions()[0]:
        if under(n, root):
            return True, USER_EXCEPTION, reason
    home = norm(PLAN_HOME)
    if not n.startswith(home + os.sep):
        for sub in STRAY_DIRS:
            if f"{os.sep}{os.path.normcase(sub.replace('/', os.sep))}{os.sep}" in n:
                return False, "base rule stray-plan-dir", f"a plan is a tracker issue body, never a file; {p} is in a stray plan dir"
        return True, OUT_OF_SCOPE, "not in the plan home or a plan dir"
    rel = n[len(home) + 1 :]
    for name, reason in OMO_RUNTIME_NEEDS:
        if rel.split(os.sep)[0] == os.path.normcase(name):
            return True, OMO_NEED, reason
    return True, "base rule plan-home-live", "a plan may sit in the plan home until it is filed as a tracker issue and drained"


def issue_exists(repo: str, number: str) -> bool:
    cmd = [sys.executable, GH] if GH.endswith(".py") else [GH]
    try:
        r = subprocess.run([*cmd, "issue", "view", number, "-R", repo, "--json", "number"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    try:
        return r.returncode == 0 and str(json.loads(r.stdout).get("number")) == number
    except (ValueError, AttributeError):
        return False


def drain() -> int:
    """Delete live plan copies; keep and report every file that is not live yet."""
    kept = 0
    for f in plan_files():
        t = tracker(f)
        if t is None:
            print(f"kept, not live (no Tracker line): {f}")
            kept += 1
        elif not issue_exists(*t):
            print(f"kept, {t[0]}#{t[1]} not found: {f}")
            kept += 1
        else:
            f.unlink()
            print(f"deleted, live as {t[0]}#{t[1]}: {f}")
    return 1 if kept else 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode == "check":
        v = violations()
        print("\n".join(v) if v else "sprawl-gate: clean")
        return 1 if v else 0
    if mode == "hook":
        data = json.load(sys.stdin)
        ti = data.get("tool_input") or {}
        allowed, mechanism, reason = verdict(ti.get("file_path") or "")
        if not allowed:
            message = f"sprawl-gate [{mechanism}]: {reason} (no omo runtime need or user exception covers it)"
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": message}}))
        return 0
    if mode == "explain":
        for path in sys.argv[2:]:
            allowed, mechanism, reason = verdict(path)
            print(f"{'allow' if allowed else 'deny '}  [{mechanism}]  {path}  -- {reason}")
        return 0
    if mode == "stop":
        data = json.load(sys.stdin) if not sys.stdin.isatty() else {}
        if data.get("stop_hook_active"):
            return 0
        v = violations()
        if v:
            print("sprawl-gate found sprawl; fix it or tell the user why it stays:\n" + "\n".join(v), file=sys.stderr)
            return 2
        return 0
    if mode == "drain":
        return drain()
    print("usage: sprawl-gate.py check|hook|stop|drain|explain <path>...", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
