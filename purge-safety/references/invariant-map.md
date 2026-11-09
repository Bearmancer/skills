# Reference engine invariant map

`<skill>\scripts\purge.py` implements every invariant above and is the
fixture partner for the harness; `references/engine.md` lists its flags and
exit codes. `npx skills add Bearmancer/skills -s purge-safety -a <agents> -y`
installs this skill from the public Bearmancer/skills repo into
`~\.agents\skills\purge-safety` and links it into each named agent's skills
folder (for example `~\.claude\skills\purge-safety`), so one source survives.
Do not treat it as pre-approved: run the harness against it, and if a line
contradicts an invariant, the line is wrong.

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
| `fd -u` zero count | `fd_residue`: exit 2 on a non-zero count or a missing `fd`; `--skip-fd-check` journals `skipped`          |
| Journal            | `apply_mode`: `delete` record appended before `remove_tree`, `removed`/`failed`/`prune-empty-parent` after |
| Self-termination   | `budget`, `--max-failures`, `enter_lock`/`exit_lock`, an explicit exit code from `main`                    |
| Cascade            | `remove_empty_ancestors`                                                                                   |
| No swallowing      | per-target `try/except` increments `failures` and journals the message                                     |
| Junction ancestors | `test_entry` walks every ancestor between root and target and refuses a reparse point                      |
| Verdict required   | `read_entries` marks a row without `verdict` as `MISSING`; `test_entry` refuses it                         |
| Counts on success  | deleted files/dirs/bytes accrue after removal, so a failed delete does not inflate the report              |
| Manifest freshness | `read_entries` stores `generated`; `apply_mode` refuses a target newer than it unless `--force`            |
| Build rule         | `build_container`: repo must carry a project manifest and must not be the scan root                        |
PY