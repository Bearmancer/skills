---
name: purge-safety
description: "Use when a purge, cleanup, uninstall, reset or delete script is written, reviewed or about to run, or an agent is one command away from deleting a tree. Judges from evidence: sandboxed guards, proven counts, residue scan, gated real run."
---

# Purge safety

A purge script is safe when four things hold. Not when it looks careful, not
when it has comments.

1. It can only delete what it was explicitly given.
2. It cannot reach outside its root or into a protected path.
3. It records each deletion before making it.
4. It stops itself when a guard, a budget or a failure says stop.

Your job is a verdict backed by evidence. "Looks fine" is not a verdict. A
PASS names the probe that proved each invariant; a BLOCK names the line that
breaks it.

## Ownership

This skill is the single owner of deletion policy: explicit targets, root
containment, protected paths, verdict gates, manifests, write-ahead journals,
counts, residue, budgets and locks. Other skills link here instead of
restating these rules.

- `github-sweep`: owns branch *selection* only and calls
  `scripts/purge_branches.py`. It does not define a second purge policy.
- `github-create`: may remove its own temporary run directory only; it follows
  the explicit-target/no-wildcard rule here.
- `work-audit`: finds candidates (indices 4, 15, 16) and hands the report to
  `scripts/from-work-audit-report.py`; it never deletes ad hoc.

## Commands

Commands that may run 60 s or more: tee output to a log, end the log with a
`DONE` line, run detached with `Start-Process pwsh -WindowStyle Hidden
-PassThru`, then read the log with `Get-Content`. Discover by reading whole
files or search tools; `head` and `tail` are denied.

## 1. Read the destructive surface

Enumerate every call that removes data, then ignore the rest of the file
until each one is accounted for.

- PowerShell: `Remove-Item`, `ri`/`rm`/`del` aliases, `[IO.File]::Delete`,
  `[IO.Directory]::Delete`, `Get-ChildItem | Remove-Item`, `robocopy /MIR`
  into an empty dir.
- Bash / POSIX: `rm -rf`, `find -delete`, `shred`, `truncate -s 0`,
  `> file`, `dd`, `git clean -xfd`.
- Node / Python / Go: `fs.rm(..., {recursive:true})`, `shutil.rmtree`,
  `os.remove`, `pathlib.unlink`, `os.RemoveAll`.

A destructive call fed by a variable is a question, not a fact: find what
fills that variable and whether the caller or the script controls it.

## 2. Static invariants

Invariant table, why each matters, and failure shape:
`references/static-invariants.md` (read when reviewing a script).

## 3. Dynamic proof

Run the bundled harness:

```powershell
uv run <skill>\scripts\purge-guards.py --script <path-to-purge-script> --apply-probes
```

Probe list and interpretation: `references/dynamic-proof.md` (read when
running or extending the harness). A harness that only ever passes proves
nothing; run it once against `scripts/fixtures/lax-purge.py` and expect
FAILs. `UNSUPPORTED` is an honest result, never a PASS.

## 4. The verdict

Report a table, one row per invariant: `Invariant | Result | Evidence`.
Evidence is the probe name, the exit code, or `file:line`.

- **PASS** — every destructive invariant proven by a probe or a cited line;
  nothing UNPROVEN.
- **BLOCK** — at least one invariant fails, or a red flag below is present.
  Name the fix.
- **UNPROVEN** — the script could not be driven (interface mismatch, missing
  interpreter). Say what would settle it; do not soften this into PASS.

Block outright, whatever the rest looks like: recursive delete aimed at
`$HOME`/`/`/a drive root; wildcard scope; no dry-run path; junctions
followed; deletes issued before their journal record; errors swallowed
around deletes; a purge that only moves data to the recycle bin.

## 5. The run gate

Pre-apply checklist: `references/run-gate.md` (read before any real
`--apply`).

## 6. Work-audit handoff

Convert the report to a manifest, then plan/apply:
`references/work-audit-handoff.md` (read when routing work-audit candidates).

## 7. Reference engine

`<skill>\scripts\purge.py` implements every invariant; `references/engine.md`
lists its flags and exit codes; `references/invariant-map.md` maps each
invariant to its code. Do not treat it as pre-approved: run the harness
against it, and if a line contradicts an invariant, the line is wrong.
PY