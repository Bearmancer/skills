# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

STATE = (
    Path(
        os.environ.get("WORK_AUDIT_STATE_DIR")
        or (os.environ.get("USERPROFILE") or os.environ.get("HOME") or ".")
    )
    / ".work-audit-state"
)
STAMP = STATE / "audited.json"
REASON = "State changed since the last audit: run the work-audit skill (state-report.py) before reporting done."


def completed(message):
    return any(
        l.strip().lower().startswith(("result:", "remaining items:"))
        for l in (message or "").splitlines()
    )


def load_record():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(
        "record", Path(__file__).resolve().with_name("record.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fingerprint(rc, cache):
    h = hashlib.sha256()
    for repo in rc.repos():
        h.update(f"{repo}\0{rc.tree_cached(repo, cache)}".encode())
    return h.hexdigest()


def items(entry):
    c = (entry.get("message") or {}).get("content")
    return (
        [{"type": "text", "text": c}]
        if isinstance(c, str)
        else [i for i in (c or []) if isinstance(i, dict)]
    )


def last_turn_tool_uses(lines):
    entries = []
    for l in lines:
        try:
            entries.append(json.loads(l))
        except ValueError:
            continue
    start = 0
    for i, e in enumerate(entries):
        if e.get("type") == "user":
            its = items(e)
            if any(x.get("type") == "text" for x in its) and not any(
                x.get("type") == "tool_result" for x in its
            ):
                start = i + 1
    return [
        x
        for e in entries[start:]
        if e.get("type") == "assistant"
        for x in items(e)
        if x.get("type") == "tool_use"
    ]


def ran_report(uses):
    return any(
        u.get("name") == "Bash"
        and "state-report.py" in str((u.get("input") or {}).get("command", ""))
        for u in uses
    )


def asked(uses):
    return any(u.get("name") == "AskUserQuestion" for u in uses)


def decide(lines, fp, stamp, pairs=(), blocks=None, unresolved=None):
    uses = last_turn_tool_uses(lines)
    if not uses:
        return None, None
    missing = [f"{i}@{r}" for i, r, s, *_ in pairs if s in ("missing", "invalid")]
    failing = [f"{i}@{r} {s}" for i, r, s, *_ in pairs if s in ("fail", "unverifiable")]
    if (
        blocks is not None
        and unresolved is not None
        and (missing or (failing and not asked(uses)))
    ):
        key = (
            "missing:"
            + "|".join(sorted(missing))
            + ";failing:"
            + "|".join(sorted(failing))
        )
        blocks[key] = blocks.get(key, 0) + 1
        if blocks[key] >= 3:
            entry = ", ".join([*missing, *failing])
            if entry not in unresolved:
                unresolved.append(entry)
            return None, None
    if missing:
        return (
            f"Required review records missing or invalid: {', '.join(missing)}. Run record.py brief, spawn reviewers, write records with record.py write.",
            None,
        )
    if failing and not asked(uses):
        return (
            f"Review records not passing: {', '.join(failing)}. Fix the findings or put the open items to AskUserQuestion.",
            None,
        )
    if ran_report(uses):
        return None, fp
    return (None if fp == stamp else REASON), None


def selftest():
    def tu(name, **inp):
        return json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "tool_use", "name": name, "input": inp}]
                },
            }
        )

    def msg(role, text):
        return json.dumps(
            {"type": role, "message": {"content": [{"type": "text", "text": text}]}}
        )

    edit = [msg("user", "fix"), tu("Edit", file_path="a")]
    cases = {
        "no tools, state changed -> pass": (
            [msg("user", "why?"), msg("assistant", "Because X.")],
            "b",
            "a",
            (),
            (None, None),
        ),
        "tools, state changed, no audit -> block": (edit, "b", "a", (), (REASON, None)),
        "tools, state unchanged since audit -> pass": (
            [msg("user", "look"), tu("Read", file_path="a")],
            "a",
            "a",
            (),
            (None, None),
        ),
        "tools, ran state-report -> pass and stamp": (
            [msg("user", "fix"), tu("Bash", command="uv run x/state-report.py")],
            "b",
            "a",
            (),
            (None, "b"),
        ),
        "missing pair -> block listing it": (
            edit,
            "a",
            "a",
            [("19", "r1", "missing")],
            ("Required review records missing or invalid: 19@r1.", None),
        ),
        "missing pair blocks even after state-report": (
            [msg("user", "x"), tu("Bash", command="state-report.py")],
            "b",
            "a",
            [("21", "r2", "invalid")],
            ("Required review records missing or invalid: 21@r2.", None),
        ),
        "failing record, no question -> block": (
            edit,
            "a",
            "a",
            [("20", "r1", "fail")],
            ("Review records not passing: 20@r1 fail.", None),
        ),
        "failing record, AskUserQuestion used -> pass": (
            edit + [tu("AskUserQuestion", q="x")],
            "a",
            "a",
            [("20", "r1", "unverifiable")],
            (None, None),
        ),
        "all pairs ok -> pass": (edit, "a", "a", [("19", "r1", "ok")], (None, None)),
    }
    ok = True
    for name, (lines, fp, stamp, pairs, want) in cases.items():
        reason, new = decide(lines, fp, stamp, pairs)
        good = (reason[: len(want[0])] if reason else None, new) == want
        ok &= good
        print(
            f"{'PASS' if good else 'FAIL'} {name}: {(reason[:70] if reason else None, new)}"
        )
    scoped = selftest_scope(load_record())
    return 0 if ok and scoped else 1


def selftest_scope(rc):
    base = rc.RECORDS / ".tmp" / "guard-selftest"
    if base.exists():
        rc.rmtree(base)
    base.mkdir(parents=True)
    saved = dict(os.environ)
    os.environ["GIT_CEILING_DIRECTORIES"] = str(base)
    try:
        repos = []
        for n in ("repo-a", "repo-b"):
            r = base / n
            r.mkdir()
            for a in (("init", "-q"), ("commit", "-q", "--allow-empty", "-m", "i")):
                assert (
                    rc.git(r, "-c", "user.name=t", "-c", "user.email=t@t", *a)
                    is not None
                )
            repos.append(r.resolve())
        a, b = repos
        edit = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Edit",
                            "input": {"file_path": str(b / "f.txt")},
                        }
                    ]
                },
            }
        )
        rc.SCOPE[:] = rc.scope(a, [edit])
        cache = {}
        fp1 = fingerprint(rc, cache)
        same = fingerprint(rc, cache) == fp1
        (b / "f.txt").write_text("x")
        changed = fingerprint(rc, cache) != fp1
        rc.SCOPE[:] = rc.scope(a, [])
        only_a = rc.SCOPE == [a]
        fp2 = fingerprint(rc, cache)
        (b / "f.txt").write_text("y")
        ignores_untouched = fingerprint(rc, cache) == fp2
        results = {
            "scope = cwd + transcript repos": len(rc.scope(a, [edit])) == 2,
            "fingerprint stable": same,
            "fingerprint follows touched repo content": changed,
            "cwd-only scope": only_a,
            "untouched repo ignored": ignores_untouched,
        }
    finally:
        rc.SCOPE[:] = []
        os.environ.clear()
        os.environ.update(saved)
        rc.rmtree(base)
    for k, v in results.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    return all(results.values())


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    try:
        data = json.load(sys.stdin)
        if data.get("stop_hook_active") or not completed(
            data.get("last_assistant_message")
        ):
            return
        p = Path(data.get("transcript_path") or "")
        if not p.is_file():
            return
        rc = load_record()
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        rc.SCOPE[:] = rc.scope(data.get("cwd"), lines)
        old = json.loads(STAMP.read_text()) if STAMP.is_file() else {}
        cache = old.get("repos", {})
        blocks = old.get("blocks", {})
        unresolved = old.get("unresolved", [])
        fp = fingerprint(rc, cache)
        reason, new_stamp = decide(lines, fp, old.get("fingerprint"))
        if reason is not None and reason.startswith("State changed"):
            key = f"state:{fp}"
            blocks[key] = blocks.get(key, 0) + 1
            if blocks[key] >= 3:
                old_fp = old.get("fingerprint")
                entry = (
                    f"state changed, no audit since {old_fp[:10] if old_fp else '?'}"
                )
                if entry not in unresolved:
                    unresolved = unresolved + [entry]
                reason = None
                new_stamp = new_stamp or old_fp or fp
        elif reason is None:
            blocks = {}
            if new_stamp:
                unresolved = []
        STAMP.parent.mkdir(parents=True, exist_ok=True)
        tmp = STAMP.with_name(f".{STAMP.name}.{os.getpid()}.tmp")
        tmp.write_text(
            json.dumps(
                {
                    "fingerprint": new_stamp or old.get("fingerprint"),
                    "repos": cache,
                    "blocks": blocks,
                    "unresolved": unresolved,
                }
            )
        )
        rc.atomic_replace(tmp, STAMP)
    except Exception as e:
        print(f"stop-guard note: hook failed ({e}), allowing", file=sys.stderr)
        return
    if reason:
        sys.stdout.write(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
