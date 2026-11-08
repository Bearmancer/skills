# Purge engine

`purge.py` — enumerate, prove, delete, prove gone. Python 3.12 through `uv run`, standard library only.

```powershell
# 1. enumerate: builds the manifest, deletes nothing
uv run purge.py --scan --out-dir "$HOME\.omo\reports"

# 2. plan: guards and counts against a manifest, deletes nothing
uv run purge.py --manifest "<manifest>.json"

# 3. apply: deletes the accepted rows, journals each one, rescans for residue
uv run purge.py --apply --manifest "<manifest>.json"
```

## Modes

| Mode  | Flag                     | Deletes | Writes                                             |
| ----- | ------------------------ | ------- | -------------------------------------------------- |
| Scan  | `--scan`                 | no      | `Purge Manifest - <date>.json`                     |
| Plan  | none                     | no      | nothing                                            |
| Apply | `--apply` + `--manifest` | yes     | `Purge Journal - <date>.jsonl`, manifest untouched |

## Parameters

| Parameter          | Default                          | Meaning                                                                                                                      |
| ------------------ | -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `--root`           | `%USERPROFILE%`                  | the only tree the engine may touch                                                                                           |
| `--manifest`       | none                             | JSON with `entries[]`; each row needs `path`, `verdict` (`PURGE` or `OWNER`)                                                 |
| `--override`       | none                             | one or more exact paths (or ancestors) allowed past the protected list and the OWNER gate; naming the root itself is refused |
| `--out-dir`        | `~\.omo\reports`                 | manifest and journal location; keep it outside every target                                                                  |
| `--temp-age-days`  | 2                                | age gate for `%LOCALAPPDATA%\Temp` entries                                                                                   |
| `--empty-age-days` | 1                                | age gate for empty directories                                                                                               |
| `--max-minutes`    | 60                               | time budget; aborts mid-run, journalled                                                                                      |
| `--max-paths`      | 5000                             | manifest size ceiling; `--force` raises it                                                                                   |
| `--max-failures`   | 25                               | failure ceiling                                                                                                              |
| `--lock-file`      | `%LOCALAPPDATA%\Temp\Purge.lock` | single-instance lock; a live owner blocks a second run                                                                       |
| `--force`          | off                              | ignores `--max-paths` and manifest freshness                                                                                 |
| `--skip-fd-check`  | off                              | skips the post-apply `fd -u` zero-count check; the journal records `fd_status: skipped`                                      |
| `--json`           | off                              | emit the result object as JSON                                                                                               |

## Exit codes

| Code | Meaning                                                                                                      |
| ---- | ------------------------------------------------------------------------------------------------------------ |
| 0    | applied and clean, or plan with no refusals                                                                  |
| 1    | guard or usage error, refused lock, manifest over `--max-paths`, failure ceiling reached, plan with refusals |
| 2    | residue remained after apply, `fd -u` counted a removed path above 0, or `fd` is missing                     |
| 3    | applied with refusals or failed deletes; a scan that refused candidates                                      |
| 4    | aborted by the time budget                                                                                   |

## Guarantees

- **Explicit rows only.** The delete loop iterates the manifest; nothing is discovered at delete time.
- **Containment.** Every target is canonicalized, must sit under `--root`, may not be the root itself or a drive root, and may not be reached through a reparse point anywhere between root and target.
- **Verdict required.** A row without `verdict` is `MISSING` and refused; `KEEP` is refused; `OWNER` needs `--override`.
- **Protected list.** Memory, agent state, config, credentials, installed binaries and the user folders `Documents`, `Downloads`, `Desktop`, `OneDrive*`, `Pictures`, `Videos`, `Music` survive unless named in `--override`; the journal records `override: true` when it was used.
- **Links are unlinked.** Junctions and symlinks are removed as links; their targets are never walked.
- **Visible accepts.** Apply prints a `DELETE` line with counts for every accepted row, then the journal does the same.
- **Write-ahead journal.** A `delete` record (path, counts, verdict, override) lands before the removal; `removed`, `failed`, `prune-empty-parent`, then `done` or `abort`.
- **Counts.** files, dirs, empty dirs, zero-byte files and bytes, measured live and accrued only on success.
- **Manifest freshness.** A target whose LastWriteTime is newer than the manifest `generated` stamp is refused unless `--force`: yesterday's manifest never eats today's files. Removing a child rewrites its parent's LastWriteTime, so a parent row listed beside its own child is refused on the same run; apply it again from a fresh scan.
- **Build names need a project.** `bin`, `obj`, `dist`, `artifacts` count only inside a repo that carries a project manifest and is not the scan root itself.
- **Cascade.** Emptied ancestors are pruned up to the root, stopping at protected paths.
- **Self-termination.** Time budget, failure ceiling, path ceiling, single-instance lock, explicit exit on every path.

## Companion

`purge-guards.py` in the same folder runs 17 probes against this file with `--apply-probes`, including a protected row, a junction ancestor, a missing verdict, a live lock and a zero-minute budget. It must return 17 PASS with exit 0; the same harness against `scripts\fixtures\lax-purge.py` must return failures. Without `--apply-probes` only the plan probes run and the apply probes report `UNSUPPORTED`. `tests/` in the skill runs both, plus the parity goldens recorded from the PowerShell engine this replaced (#281).

## Installs

`npx skills add Bearmancer/skills -s purge-safety -a <agents> -y` installs the skill folder into `~\.agents\skills\purge-safety` and links it into each named agent's skills folder (for example `~\.claude\skills\purge-safety`), so the `purge-safety` folder in Bearmancer/skills is the only source.
