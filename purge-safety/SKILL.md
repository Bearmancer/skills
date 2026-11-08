---
name: purge-safety
description: "Use when a purge, cleanup, uninstall, reset or delete script is written, reviewed or about to run, or an agent is one command away from deleting a tree. Judges from evidence: sandboxed guards, proven counts, residue scan, gated real run."
---

# Purge safety

A purge script is safe when four things hold. Not when it looks careful, not when it has comments.

1. It can only delete what it was explicitly given.
2. It cannot reach outside its root or into a protected path.
3. It records each deletion before making it.
4. It stops itself when a guard, a budget or a failure says stop.

Your job is a verdict backed by evidence. "Looks fine" is not a verdict. A PASS names the probe that proved each invariant; a BLOCK names the line that breaks it.

## Purpose, and how it differs from work-audit

The two skills answer different questions and never substitute for each other.

| | work-audit | purge-safety |
| --- | --- | --- |
| Question | What is left, stale or unfinished in the repos this task touched? | Is it safe to delete this, and did the delete do what it claimed? |
| Runs | Every task end, before "done", committing or pushing | Only when something is about to be deleted, or a delete script is written or reviewed |
| Acts on | Repos the session touched | A script and the tree it targets |
| Output | 21-index report and fixes | PASS / BLOCK / UNPROVEN verdict, then a journalled apply |
| Deletes | Never. Indices 4, 15 and 16 only *nominate* candidates | Only through `scripts/purge.py` after the run gate |

work-audit is a finder: broad, cheap, runs every time, and its candidates are
claims. purge-safety is a gatekeeper: narrow, runs on demand, and demands proof
before any claim becomes a delete. Keeping them apart means a routine audit
can never remove data, and a deletion can never skip its guards because a
report called the file stale. Use purge-safety directly, with no audit, to
vet any cleanup script, uninstall or reset; use work-audit alone when nothing
needs to be deleted. The handoff between them is §6.

## Ownership

This skill is the single owner of deletion policy: explicit targets, root
containment, protected paths, verdict gates, manifests, write-ahead journals,
counts, residue, budgets and locks. Other skills link here instead of
restating these rules.

- `github-sweep`: owns branch *selection* only (merged/closed/open, `ahead_by`,
  default branches) and calls its `scripts/purge_branches.py` adapter. It does
  not define a second purge policy.
- `github-create`: may remove its own temporary run directory only; it follows
  the explicit-target/no-wildcard rule here.
- `work-audit`: finds candidates (indices 4, 15, 16) and hands the report to
  `scripts/from-work-audit-report.py`; it never deletes ad hoc.

## 1. Read the destructive surface

Enumerate every call that removes data, then ignore the rest of the file until each one is accounted for.

- PowerShell: `Remove-Item`, `ri`/`rm`/`del` aliases, `[IO.File]::Delete`, `[IO.Directory]::Delete`, `Get-ChildItem | Remove-Item`, `robocopy /MIR` into an empty dir.
- Bash / POSIX: `rm -rf`, `find -delete`, `shred`, `truncate -s 0`, `> file`, `dd`, `git clean -xfd`.
- Node / Python / Go: `fs.rm(..., {recursive:true})`, `shutil.rmtree`, `os.remove`, `pathlib.unlink`, `os.RemoveAll`.

A destructive call fed by a variable is a question, not a fact: find what fills that variable and whether the caller or the script controls it.

## 2. Static invariants

Check each one in the source. The middle column says why it matters; the right column is what a failure looks like so you can name it.

| Invariant               | Why it matters                                                                                 | Failure shape                                                                            |
| ----------------------- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Explicit targets        | A purge that decides its own scope deletes whatever the rule matched today                     | wildcard or glob built from `$HOME`, `Get-ChildItem -Recurse` fed straight into a delete |
| Root containment        | Every target canonicalized and proven under a declared root                                    | `Join-Path $root '..\..'`, relative paths, no `GetFullPath` check                        |
| Protected denylist      | Memory, config, credentials, personal data and installed binaries survive by rule, not by luck | no deny list, or one that runs after the delete                                          |
| Per-path override       | The only way past a protected path is naming it, and the journal records it                    | a global `-Force` that skips every guard                                                 |
| Verdict gate            | A manifest row marked KEEP is never deleted                                                    | delete loop that ignores the verdict column                                              |
| Reparse points unlinked | A junction or symlink is removed as a link; following it deletes the target                    | recursive delete that walks through a junction                                           |
| No wildcard targets     | Expansion happens in the script, after the guards, never in the target string                  | `Remove-Item "$root\*" -Recurse`                                                         |
| Counts before and after | Files, dirs, empty dirs, zero-byte files, bytes: the proof the purge did what it claimed       | "done" with no numbers                                                                   |
| Residue scan            | Re-run the rules after the purge; non-zero residue means the job is unfinished                 | script exits 0 after deleting half the list                                              |
| Journal before delete   | Write-ahead record per target: path, counts, verdict, reason, timestamp                        | log written at the end, or only on success                                               |
| Self-termination        | Time budget, failure ceiling, single-instance lock, explicit exit codes                        | a runaway recursive delete with no ceiling                                               |
| No silent swallowing    | Failures are counted and surfaced; a locked file is a reported failure, not a skipped line     | `-ErrorAction SilentlyContinue` around a delete                                          |
| Idempotent              | A target that is already gone is skipped, not an error                                         | crash on second run, or exit 1 forever                                                   |
| Children before parents | Deepest paths first; emptied ancestors pruned so no shells remain                              | parent deleted first, child delete then fails or is orphaned                             |
| Permanent delete        | The payload does not land in `$Recycle.Bin`; a purge that fills the bin has moved the problem  | `Remove-Item` to the bin, or a bin never cleared                                         |

Two more that the reference engine learned the hard way: **manifest freshness** — a target whose LastWriteTime is newer than the manifest's `generated` stamp is stale and refused, so yesterday's manifest cannot eat today's files; and **build names need a project** — a `bin`/`obj`/`artifacts` folder counts only inside a repo that carries a project manifest and is not the scan root itself, because root`\bin` is a tool directory, not output.

## 3. Dynamic proof

Static review finds intent; the sandbox finds behaviour. Run the bundled harness:

```powershell
uv run <skill>\scripts\purge-guards.py --script <path-to-purge-script> --apply-probes
```

It builds a throwaway fixture under `%TEMP%\PurgeGuardTest\<timestamp>` (or `--workspace`) containing a protected tree, a personal file, an empty dir, a `.bak`, a `node_modules`, a build dir inside a fake repo, a junction into the keep tree, and a manifest carrying an outside-root path, a wildcard, the root itself, a drive root and an OWNER row. Then it drives the script through plan, apply, locked, and budget-exhausted runs and prints one `PASS`/`FAIL`/`UNSUPPORTED` line per invariant.

The harness starts each probe as its own process with an argument list (paths with spaces arrive whole), captures stdout and stderr, and kills a probe that runs past `--timeout-seconds` with its process tree. A `.py` target runs on the harness's interpreter with `--root`-style flags; a `.ps1` target runs under `pwsh -NoProfile -File` with `-Root`-style flags. Without `--apply-probes` only the plan probes run.

A harness that only ever passes proves nothing. Run it once against `scripts/fixtures/lax-purge.py`, a script that speaks the manifest contract and skips every guard: it must come back with FAILs (protected row deleted, no journal, junction ancestor followed, missing verdict deleted). Treat a negative control that passes as a harness bug, not as a safe script.

The harness assumes a manifest contract: root, manifest, apply, override, out-dir, max-minutes and lock-file options (`--root` ... for Python, `-Root` ... for PowerShell). When a script speaks another interface, rebuild the same fixture by hand and drive it the way its user would — the fixture is the contract, not the flag names. `UNSUPPORTED` is an honest result; never turn it into a PASS.

What the sandbox proves, and why each probe exists:

- **Parse gate** — a script with parse errors is reported and never executed; a crash must not pass for a refusal.
- **Contract gate** — a script that never references the root and manifest options (`--root`/`--manifest`, or `$Root`/`$Manifest`) is not executed at all: such a script ignores the fixture root, and even a "plan" call can delete.
- **Refusal evidence** — a non-zero plan exit counts only when the output names a refusal reason; otherwise it is a crash, not a guard.

- **Protected survival** — `.omo\memory` style path in the manifest; after apply the tree still holds its file.
- **Protected refusal** — a manifest that contains only a protected row exits non-zero and leaves the tree intact, so the refusal is proven on the delete path and not only on plan.
- **Keep survival** — a personal file next to the targets; it is still there.
- **Outside-root refusal** — a path under another root is refused, not resolved.
- **Wildcard refusal** — a `*` in a manifest path is refused.
- **Root and drive refusal** — the root itself and `C:\` are refused.
- **Owner gate** — an OWNER row is refused without an override.
- **Junction discipline** — the junction is gone; the directory it pointed at still holds its contents.
- **Junction ancestor** — a row whose path is reached through a junction (`root\hop\link\file`, `link` being a junction) is refused; following it would delete outside the root.
- **Missing verdict** — a manifest row with no `verdict` field is refused, never defaulted to PURGE.
- **Cascade** — emptied parents disappear, so the next scan finds no shells.
- **Residue zero** — the post-purge scan returns 0 candidates.
- **Live lock** — a second instance with a live owner lock exits non-zero and deletes nothing.
- **Budget** — a zero-minute budget aborts before the first delete with a journalled reason.

## 4. The verdict

Report a table, one row per invariant: `Invariant | Result | Evidence`. Evidence is the probe name, the exit code, or `file:line`.

- **PASS** — every destructive invariant proven by a probe or a cited line; nothing UNPROVEN.
- **BLOCK** — at least one invariant fails, or a red flag below is present. Name the fix.
- **UNPROVEN** — the script could not be driven (interface mismatch, missing interpreter). Say what would settle it; do not soften this into PASS.

Block outright, whatever the rest looks like: recursive delete aimed at `$HOME`/`/`/a drive root; wildcard scope; no dry-run path; junctions followed; deletes issued before their journal record; errors swallowed around deletes; a purge that only moves data to the recycle bin.

## 5. The run gate

Safety of the script is necessary, not sufficient. Before any real `--apply`:

1. **Fresh scan, fresh manifest.** Never apply a manifest older than the last change to the tree. Scanning costs real time — on this host the reference engine scans `~\Dev` in about 1.7 s and the whole home folder (about 890k files in candidate rows) in about 2 minutes — so start the scan as its own background run and keep the manifest it writes.
2. **Compare totals.** Paths, files, dirs against the scan you reviewed. A factor-of-ten jump means the rules matched something new; re-read the diff before applying.
3. **Clear the OWNER list path by path.** Those rows are the only ones needing a human; the rest are mechanical.
4. **Check the journal location is writable and outside every target.** A journal inside a purged tree is a journal you lose.
5. **Set the budget.** `--max-minutes` and `--max-failures` must be plausible for the tree size; an unbounded run is a runaway.
6. **State the expected residue.** Normally 0. A non-zero residue after apply means the run is unfinished, not "mostly done".
7. **Re-scan afterwards** and report counts, not adjectives: deleted files/dirs, residue paths, refused rows.

## 6. Work-audit handoff

This section is the single home for work-audit routing; work-audit and its indices only point here.

work-audit already finds the candidates (index 4 stale artifacts, index 15 empty dirs) and records their `safety` facts. Do not let it delete them ad hoc: convert the report into a purge manifest and let this engine do the deleting.

```powershell
uv run <skill>\scripts\from-work-audit-report.py --report "<records>\<repo>-<hash>\<tree>\report.json" --repo "C:\path\to\repo"
uv run <skill>\scripts\purge.py --manifest "<written manifest>"            # plan
uv run <skill>\scripts\purge.py --apply --manifest "<written manifest>"    # journal + residue
```

Mapping: `4.zero_byte`/`tmp_bak_orig`/`pycache`/`ignored_untracked_old` and `15.empty_dirs` become PURGE rows, each reason carrying the report's safety facts; `--include-duplicates` turns index 16 pairs into OWNER rows (first path, keeper named in the reason), because a duplicate needs a human keeper choice. Routing runs 4, then 15, then 16, ascending: every row is stamped with its index, entries sort by index then path, and the adapter echoes the order line (`order: 4 -> 15 -> 16`). The canonical ordered index table (1..21: name, kind, purge routing) lives in work-audit's `references/indices.md`.

`--home-config` also routes omo's generated state (#216). The repo manifest drops every row outside the repo, so this writes a second manifest, `Purge Manifest - work-audit home-config - <date>.json`. Its root is the report's `~\.omo` config root (index 4 `config_root_entries`), never the home folder, a drive root or a linked folder. Plan and apply it with `--root <that .omo>`. The rules, settled by the owner on 2026-10-25:

- **Rows.** Each child of `evidence`, `drafts`, `tmp`, `reports`, `plans`, `ulw-loop` and `wayfinder` is a row; the subdirs themselves stay. Loose `*.bak`/`*.old` files at the omo root are rows too. Every reason carries the row's safety facts (files, newest mtime).
- **Verdicts.** PURGE for `evidence`, `drafts`, `tmp`, `reports` and the loose backups. OWNER for the executor-adjacent `plans`, `ulw-loop` and `wayfinder` (boulders, ledgers, waves), which need a per-path `--override`.
- **Age gate.** A row whose newest mtime falls inside 7 days (`--home-age-days`) stays out of the manifest and is printed as `held`, so plan review shows it before anything lands.
- **Engine files.** `Purge Manifest - *` and `Purge Journal - *` under `reports` are never routed.
- **Protected list unchanged.** `memory`, `agent\{sessions,projects,skills,extensions,runtime}`, `binary-runtime` and `omo.jsonc` are never routed. The engine refuses them even when a hand-built row names them.

When the engine scans the omo root after apply, it can report residue that its own rules match, such as `.omo\logs`, and exit 2. Read that exit as a list of further candidates, not as a failed delete.

## 7. Reference engine

`<skill>\scripts\purge.py` implements every invariant above and is the fixture partner for the harness; `references/engine.md` lists its flags and exit codes. `npx skills add Bearmancer/skills -s purge-safety -a <agents> -y` installs this skill from the public Bearmancer/skills repo into `~\.agents\skills\purge-safety` and links it into each named agent's skills folder (for example `~\.claude\skills\purge-safety`), so one source survives. Do not treat it as pre-approved: run the harness against it, and if a line contradicts an invariant, the line is wrong.

| Invariant          | Where it lives                                                                                             |
| ------------------ | ---------------------------------------------------------------------------------------------------------- |
| Explicit targets   | `scan_entries`: rule table and `explicit` pairs; `read_entries` for a manifest                             |
| Root containment   | `test_entry`: `abspath`, root equality, drive-root regex, `under` the root                                 |
| Protected denylist | `PROTECTED_PATTERNS`, applied by `test_entry` before any measure                                           |
| Per-path override  | `overridden`, exact path or ancestor, only from `--override`                                               |
| Verdict gate       | `test_entry` refuses anything but PURGE/OWNER                                                              |
| Reparse points     | `is_reparse`; `measure` counts instead of walking; `remove_tree` unlinks                                   |
| Counts             | `measure`; `totals`; the `APPLY` summary line                                                              |
| Residue scan       | `apply_mode` `finally`: `scan_entries` + exit 2 when residue remains                                       |
| Journal            | `apply_mode`: `delete` record appended before `remove_tree`, `removed`/`failed`/`prune-empty-parent` after |
| Self-termination   | `budget`, `--max-failures`, `enter_lock`/`exit_lock`, an explicit exit code from `main`                    |
| Cascade            | `remove_empty_ancestors`                                                                                   |
| No swallowing      | per-target `try/except` increments `failures` and journals the message                                     |
| Junction ancestors | `test_entry` walks every ancestor between root and target and refuses a reparse point                      |
| Verdict required   | `read_entries` marks a row without `verdict` as `MISSING`; `test_entry` refuses it                         |
| Counts on success  | deleted files/dirs/bytes accrue after removal, so a failed delete does not inflate the report              |
| Manifest freshness | `read_entries` stores `generated`; `apply_mode` refuses a target newer than it unless `--force`            |
| Build rule         | `build_container`: repo must carry a project manifest and must not be the scan root                        |
