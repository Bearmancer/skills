# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Safety probes for a purge script.

Builds a throwaway fixture with traps, drives the target script through plan, apply, budget and
lock scenarios, and prints one PASS / FAIL / UNSUPPORTED line per invariant. Exit 0 when every
probe passes, 2 when any probe fails, 1 when the fixture itself could not be built.

Each probe starts the target as its own process with an argument list, so paths with spaces
arrive whole, stdout and stderr are captured as UTF-8, and a probe that runs past
--timeout-seconds is killed with its process tree and reported as timed out.

A `.py` target runs on this interpreter and is driven with `--root`-style flags; a `.ps1` target
runs under `pwsh -NoProfile -File` and is driven with `-Root`-style flags.

Plan probes run by default. The destructive probes (apply, budget, lock) need --apply-probes,
because running an unaudited script against a fixture is still running it.
"""

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

FLAGS = {
    ".py": {"root": "--root", "manifest": "--manifest", "apply": "--apply", "override": "--override",
            "out-dir": "--out-dir", "max-minutes": "--max-minutes", "lock-file": "--lock-file"},
    ".ps1": {"root": "-Root", "manifest": "-Manifest", "apply": "-Apply", "override": "-Override",
             "out-dir": "-OutDir", "max-minutes": "-MaxMinutes", "lock-file": "-LockFile"},
}
# The contract a script must declare before it is ever executed.
CONTRACT = {
    ".py": (re.compile(r"--root\b"), re.compile(r"--manifest\b"), re.compile(r"--lock-file\b")),
    ".ps1": (re.compile(r"(?i)\$Root\b"), re.compile(r"(?i)\$Manifest\b"), re.compile(r"LockFile")),
}

FIXTURE_FILES = {
    "cache/node_modules/pkg/index.js": "x" * 1024,
    "proj/.git/HEAD": "ref: refs/heads/main",
    "proj/artifacts/out.dll": "y" * 2048,
    "logs/app.log.bak": "old log",
    "logs/keep.log": "live log",
    "zero/stub.txt": "",
    "keep/important.txt": "do not delete",
    ".omo/memory/note.md": "memory",
}
OLD_DIRS = ("cache/uploads/empty1", "cache/uploads/empty2", "cache/uploads/empty2/nested", ".omo/agent/projects/orphan")
OLD_STAMP = datetime(2026, 1, 1).timestamp()


def junction(link, target):
    """A directory junction at link pointing at target."""
    try:
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    except (ImportError, AttributeError):
        os.symlink(target, link, target_is_directory=True)


def new_fixture(base):
    base = Path(base)
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    for rel, content in FIXTURE_FILES.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")
    for rel in ("cache/uploads/empty1", "cache/uploads/empty2/nested", ".omo/agent/projects/orphan"):
        (base / rel).mkdir(parents=True, exist_ok=True)
    for rel in OLD_DIRS:
        os.utime(base / rel, (OLD_STAMP, OLD_STAMP))
    (base / "junctions").mkdir()
    junction(base / "junctions" / "lock", base / "keep")


def write_manifest(path, rows, root, generated=True):
    doc = {"root": str(root), "entries": rows}
    if generated:
        # Written right after the fixture; one second covers a filesystem clock that runs ahead of ours,
        # which would otherwise make a fresh fixture look changed after its manifest.
        doc["generated"] = (datetime.now() + timedelta(seconds=1)).astimezone().isoformat()
    Path(path).write_text(json.dumps(doc, indent=2), encoding="utf-8")


def row(base, rel, verdict, category):
    return {"path": str(Path(base) / rel), "verdict": verdict, "category": category, "reason": category}


class Harness:
    def __init__(self, script, workspace, timeout, as_json):
        self.script = Path(script).resolve()
        self.kind = self.script.suffix.lower()
        self.workspace = Path(workspace)
        self.timeout = timeout
        self.json = as_json
        self.failures = 0
        self.results = []
        self.source = self.script.read_text(encoding="utf-8-sig", errors="replace")
        self.supports_lock = bool(CONTRACT[self.kind][2].search(self.source))

    def result(self, name, state, detail):
        self.results.append({"invariant": name, "state": state, "detail": detail})
        if state == "FAIL":
            self.failures += 1
        if not self.json:
            print(f"{state:<4} {name:<28} {detail}", flush=True)

    def finish(self, code):
        if self.json:
            print(json.dumps(self.results, indent=2))
        return code

    def command(self, args):
        if self.kind == ".py":
            return [sys.executable, str(self.script), *args]
        return [shutil.which("pwsh") or "pwsh", "-NoProfile", "-NonInteractive", "-File", str(self.script), *args]

    def run(self, **opts):
        """Run the target with contract options (root=..., apply=True, ...); returns (code, output)."""
        flags = FLAGS[self.kind]
        # Isolate the single-instance lock per workspace, or two audits (or a live purge) collide.
        if self.supports_lock and "lock-file" not in opts:
            opts["lock-file"] = self.workspace / "probe.lock"
        args = []
        for name, value in opts.items():
            if value is True:
                args.append(flags[name])
            else:
                args += [flags[name], str(value)]
        env = dict(os.environ, PYTHONUTF8="1")
        proc = subprocess.Popen(self.command(args), cwd=self.workspace, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=env, stdin=subprocess.DEVNULL)
        try:
            out, err = proc.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            out, err = proc.communicate()
            return 124, decode(out) + decode(err)
        return proc.returncode, decode(out) + decode(err)

    def parses(self):
        """(ok, detail): a script that does not parse cannot be probed."""
        if self.kind == ".py":
            try:
                ast.parse(self.source, str(self.script))
            except SyntaxError as error:
                return False, f"parse error at line {error.lineno}; static review only"
            return True, "parses with 0 errors"
        probe = ("$e = $null; $null = [System.Management.Automation.Language.Parser]::ParseFile($args[0], [ref]$null, [ref]$e); "
                 "@($e).Count")
        proc = subprocess.run([shutil.which("pwsh") or "pwsh", "-NoProfile", "-NonInteractive", "-Command",
                               f"& {{ {probe} }} '{str(self.script).replace(chr(39), chr(39) * 2)}'"],
                              capture_output=True, text=True, timeout=self.timeout)
        count = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "?"
        if proc.returncode != 0 or count != "0":
            return False, f"{count} parse error(s); static review only"
        return True, "parses with 0 errors"

    def probe(self, apply_probes):
        sandbox = self.workspace
        new_fixture(sandbox)
        outside_root = Path(os.environ.get("SystemDrive", "C:") + "\\") / "Windows" / "Temp"
        trap_rows = [
            row(sandbox, ".omo/memory", "PURGE", "trap-protected"),
            {"path": str(outside_root), "verdict": "PURGE", "category": "trap-outside", "reason": "outside root"},
            {"path": str(sandbox / "cache") + "\\*", "verdict": "PURGE", "category": "trap-wildcard", "reason": "wildcard"},
            {"path": str(sandbox), "verdict": "PURGE", "category": "trap-root", "reason": "root itself"},
            {"path": os.environ.get("SystemDrive", "C:") + "\\", "verdict": "PURGE", "category": "trap-drive", "reason": "drive root"},
            row(sandbox, ".omo/agent/projects/orphan", "OWNER", "trap-owner"),
            row(sandbox, "cache/node_modules", "PURGE", "cache-tree"),
        ]
        apply_rows = [
            row(sandbox, "cache/node_modules", "PURGE", "cache-tree"),
            row(sandbox, "proj/artifacts", "PURGE", "build-output"),
            row(sandbox, "logs/app.log.bak", "PURGE", "backup"),
            row(sandbox, "junctions/lock", "PURGE", "junction"),
            row(sandbox, "cache/uploads/empty1", "PURGE", "empty-shell"),
            row(sandbox, "cache/uploads/empty2/nested", "PURGE", "empty-shell"),
            row(sandbox, ".omo/agent/projects/orphan", "OWNER", "owner-row"),
        ]
        trap_manifest = sandbox / "traps.json"
        apply_manifest = sandbox / "apply.json"
        out_dir = sandbox / "out"
        write_manifest(trap_manifest, trap_rows, sandbox)
        write_manifest(apply_manifest, apply_rows, sandbox)

        # Never invoke a script that does not declare the manifest contract: it would ignore the root
        # and act on whatever path it hardcodes, and even a "plan" call can delete.
        root_rx, manifest_rx, _ = CONTRACT[self.kind]
        if not (root_rx.search(self.source) and manifest_rx.search(self.source)):
            self.result("contract-declared", "FAIL", "script never references the root/manifest contract; not executed, static review only")
            self.result("plan-refuses-traps", "UNSUPPORTED", "blocked by the contract check")
            self.result("apply-probes", "UNSUPPORTED", "blocked by the contract check")
            return 2
        self.result("contract-declared", "PASS", "root and manifest referenced")

        # A script that does not parse cannot be probed, and a parse error must not masquerade as a refusal.
        ok, detail = self.parses()
        if not ok:
            self.result("script-parses", "FAIL", detail)
            return 2
        self.result("script-parses", "PASS", detail)

        # --- plan probes: nothing may be deleted by a plan ---
        code, output = self.run(root=sandbox, manifest=trap_manifest, **{"out-dir": out_dir})
        says_why = re.search(r"(?i)refus|outside root|protected|wildcard|drive root", output)
        if code != 0 and says_why:
            self.result("plan-refuses-traps", "PASS", f"exit {code}, refusal reasons reported")
        elif code != 0:
            self.result("plan-refuses-traps", "FAIL", f"exit {code} without naming a refusal reason")
        else:
            self.result("plan-refuses-traps", "FAIL", "plan exited 0 with protected, outside-root, wildcard, root and drive rows")
        if (sandbox / "cache/node_modules").exists():
            self.result("plan-deletes-nothing", "PASS", "targets intact after plan")
        else:
            self.result("plan-deletes-nothing", "FAIL", "plan removed a target")

        if not apply_probes:
            self.result("apply-probes", "UNSUPPORTED", "skipped; rerun with --apply-probes to exercise deletion in the fixture")
            return 2 if self.failures else 0

        # --- apply probes ---
        code, output = self.run(root=sandbox, manifest=apply_manifest, apply=True,
                                override=sandbox / ".omo/agent/projects/orphan", **{"out-dir": out_dir})
        apply_output = output
        if code == 0:
            self.result("apply-clean-exit", "PASS", "exit 0")
        else:
            first = " / ".join(output.splitlines()[:3])
            self.result("apply-clean-exit", "FAIL", f"exit {code}: {first}")

        if (sandbox / ".omo/memory/note.md").exists():
            self.result("protected-survives", "PASS", ".omo\\memory intact")
        else:
            self.result("protected-survives", "FAIL", "protected tree was deleted")

        # --- protected refusal probe: a protected row must be refused, with its tree intact ---
        prot = sandbox / "prot"
        new_fixture(prot)
        prot_manifest = sandbox / "prot.json"
        write_manifest(prot_manifest, [row(prot, ".omo/memory", "PURGE", "protected-row")], prot)
        code, _ = self.run(root=prot, manifest=prot_manifest, apply=True, **{"out-dir": prot / "out"})
        intact = (prot / ".omo/memory/note.md").exists()
        if code != 0 and intact:
            self.result("protected-refused", "PASS", f"exit {code}, tree intact")
        else:
            self.result("protected-refused", "FAIL", f"exit {code}, tree intact={intact}")

        if (sandbox / "keep/important.txt").exists():
            self.result("keep-survives", "PASS", "personal file intact")
        else:
            self.result("keep-survives", "FAIL", "personal file was deleted")

        link_gone = not os.path.lexists(sandbox / "junctions/lock")
        target_kept = (sandbox / "keep/important.txt").exists()
        if link_gone and target_kept:
            self.result("junction-unlinked", "PASS", "link removed, target intact")
        else:
            self.result("junction-unlinked", "FAIL", f"link gone={link_gone} target intact={target_kept}")

        if not (sandbox / "cache").exists():
            self.result("cascade-pruned", "PASS", "emptied parents removed")
        else:
            self.result("cascade-pruned", "FAIL", "cache still exists")

        # --- read-only probe: git marks its object files read-only; a purge must still remove them ---
        ro = sandbox / "ro"
        ro_file = ro / "cache/node_modules/pkg/.git/objects/ab/cdef01"
        ro_file.parent.mkdir(parents=True)
        ro_file.write_text("blob", encoding="utf-8")
        os.chmod(ro_file, 0o444)
        ro_manifest = sandbox / "ro.json"
        write_manifest(ro_manifest, [row(ro, "cache/node_modules", "PURGE", "cache-tree")], ro)
        code, _ = self.run(root=ro, manifest=ro_manifest, apply=True, **{"out-dir": ro / "out"})
        gone = not (ro / "cache/node_modules").exists()
        if code == 0 and gone:
            self.result("read-only-removed", "PASS", "read-only file deleted, exit 0")
        else:
            self.result("read-only-removed", "FAIL", f"exit {code}, target gone={gone}")

        journals = sorted(out_dir.glob("*.jsonl")) if out_dir.is_dir() else []
        if not journals:
            self.result("journal-write-ahead", "FAIL", "no journal file")
        else:
            text = journals[0].read_text(encoding="utf-8-sig")
            delete_at, removed_at = text.find('"event":"delete"'), text.find('"event":"removed"')
            if delete_at >= 0 and removed_at > delete_at:
                self.result("journal-write-ahead", "PASS", "delete recorded before removed")
            else:
                self.result("journal-write-ahead", "FAIL", "delete record missing or written after removal")

        if "residue paths=0" in apply_output:
            self.result("residue-zero", "PASS", "post-purge scan found nothing")
        else:
            self.result("residue-zero", "UNSUPPORTED", "script did not report residue counts")

        # --- junction ancestor probe: a target reached through a junction must be refused ---
        outside = sandbox / "outside-hold"
        new_fixture(outside)
        hop = sandbox / "hop"
        hop.mkdir()
        junction(hop / "link", outside / "keep")
        hop_manifest = sandbox / "hop.json"
        write_manifest(hop_manifest, [row(hop, "link/important.txt", "PURGE", "junction-ancestor")], sandbox)
        code, _ = self.run(root=sandbox, manifest=hop_manifest, apply=True, **{"out-dir": sandbox / "out"})
        intact = (outside / "keep/important.txt").exists()
        if code != 0 and intact:
            self.result("junction-ancestor-refused", "PASS", f"exit {code}, outside file intact")
        else:
            self.result("junction-ancestor-refused", "FAIL", f"exit {code}, outside file intact={intact}")

        # --- missing verdict probe: no verdict field must never mean PURGE ---
        nov = sandbox / "nov"
        new_fixture(nov)
        nov_manifest = sandbox / "nov.json"
        write_manifest(nov_manifest, [{"path": str(nov / "cache/node_modules"), "category": "cache-tree", "reason": "no verdict field"}],
                       nov, generated=False)
        code, _ = self.run(root=nov, manifest=nov_manifest, apply=True, **{"out-dir": nov / "out"})
        intact = (nov / "cache/node_modules").exists()
        if code != 0 and intact:
            self.result("missing-verdict-refused", "PASS", f"exit {code}, target intact")
        else:
            self.result("missing-verdict-refused", "FAIL", f"exit {code}, target intact={intact}")

        # --- budget probe ---
        budget = sandbox / "budget"
        new_fixture(budget)
        budget_manifest = sandbox / "budget.json"
        write_manifest(budget_manifest, [row(budget, "cache/node_modules", "PURGE", "cache-tree")], budget)
        code, _ = self.run(root=budget, manifest=budget_manifest, apply=True, **{"out-dir": budget / "out", "max-minutes": 0})
        intact = (budget / "cache/node_modules").exists()
        if code != 0 and intact:
            self.result("budget-aborts", "PASS", f"exit {code}, target intact")
        elif code != 0:
            self.result("budget-aborts", "FAIL", f"exit {code} but the target was already deleted")
        else:
            self.result("budget-aborts", "UNSUPPORTED", "no max-minutes support")

        # --- lock probe ---
        if self.supports_lock:
            locked = sandbox / "locked"
            new_fixture(locked)
            lock_manifest = sandbox / "locked.json"
            write_manifest(lock_manifest, [row(locked, "cache/node_modules", "PURGE", "cache-tree")], locked)
            lock_path = sandbox / "probe.lock"
            lock_path.write_text(json.dumps({"pid": os.getpid(), "started": "probe", "mode": "apply"}), encoding="utf-8")
            code, _ = self.run(root=locked, manifest=lock_manifest, apply=True, **{"out-dir": locked / "out", "lock-file": lock_path})
            intact = (locked / "cache/node_modules").exists()
            lock_path.unlink(missing_ok=True)
            if code != 0 and intact:
                self.result("live-lock-refuses", "PASS", f"exit {code}, target intact")
            else:
                self.result("live-lock-refuses", "FAIL", f"exit {code}, target intact={intact}")
        else:
            self.result("live-lock-refuses", "UNSUPPORTED", "script has no lock parameter")

        return 2 if self.failures else 0


def decode(data):
    return data.decode("utf-8", errors="replace") if data else ""


def kill_tree(proc):
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()


def main(argv=None):
    p = argparse.ArgumentParser(prog="purge-guards.py", description=__doc__.split("\n")[0], allow_abbrev=False)
    p.add_argument("--script", required=True)
    p.add_argument("--workspace", default=str(Path(tempfile.gettempdir()) / "PurgeGuardTest" / datetime.now().strftime("%Y%m%d-%H%M%S")))
    p.add_argument("--apply-probes", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--timeout-seconds", type=int, default=180)
    args = p.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    script = Path(args.script)
    if not script.is_file():
        sys.stderr.write(f"purge-guards: script not found: {script}\n")
        return 1
    if script.suffix.lower() not in FLAGS:
        sys.stderr.write(f"purge-guards: no driver for {script.suffix or 'an extensionless'} script; drive it by hand (the fixture is the contract)\n")
        return 1
    harness = Harness(script, args.workspace, args.timeout_seconds, args.json)
    try:
        code = harness.probe(args.apply_probes)
    except OSError as error:
        sys.stderr.write(f"purge-guards: fixture could not be built: {error}\n")
        return 1
    return harness.finish(code)


if __name__ == "__main__":
    sys.exit(main())
