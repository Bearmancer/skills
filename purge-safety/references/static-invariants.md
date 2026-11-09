# Static invariants

Check each one in the source. The middle column says why it matters; the right
column is what a failure looks like so you can name it.

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
| `fd -u` zero count      | `fd -u` (hidden and ignored files included) over each removed path must count 0; the script's own scan is not a second witness | residue check that reuses the delete rules, so it cannot see what they missed |
| Journal before delete   | Write-ahead record per target: path, counts, verdict, reason, timestamp                        | log written at the end, or only on success                                               |
| Self-termination        | Time budget, failure ceiling, single-instance lock, explicit exit codes                        | a runaway recursive delete with no ceiling                                               |
| No silent swallowing    | Failures are counted and surfaced; a locked file is a reported failure, not a skipped line     | `-ErrorAction SilentlyContinue` around a delete                                          |
| Idempotent              | A target that is already gone is skipped, not an error                                         | crash on second run, or exit 1 forever                                                   |
| Children before parents | Deepest paths first; emptied ancestors pruned so no shells remain                              | parent deleted first, child delete then fails or is orphaned                             |
| Permanent delete        | The payload does not land in `$Recycle.Bin`; a purge that fills the bin has moved the problem  | `Remove-Item` to the bin, or a bin never cleared                                         |

Two more that the reference engine learned the hard way: **manifest
freshness** — a target whose LastWriteTime is newer than the manifest's
`generated` stamp is stale and refused, so yesterday's manifest cannot eat
today's files; and **build names need a project** — a `bin`/`obj`/`artifacts`
folder counts only inside a repo that carries a project manifest and is not
the scan root itself, because root`\bin` is a tool directory, not output.
PY