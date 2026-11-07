# Sprawl gate: rules, exemptions and verdicts

Spec for `scripts/sprawl-gate.py` (#215, #174; plan-home-live ruling 2026-10-25). Every exemption is listed here with its reason, and every verdict in the table has a test in `tests/test_sprawl_gate.py`. A change to a rule, an exemption or a verdict changes this file, the script and the test together.

## Modes

- `check`: print every violation, exit 1 when any exist.
- `hook`: Claude PreToolUse on Write, Edit and MultiEdit. Prints a deny for a write that would create plan sprawl; prints nothing to allow.
- `stop`: Claude Stop hook. Reports violations once (exit 2), then lets the turn end.
- `explain <path>...`: prints the hook verdict for each path and the mechanism that decided it. It only reads, so it is the live-probe tool for demonstrations.
- `drain`: for each plan-home file with a `Tracker: https://github.com/<owner>/<repo>/issues/<n>` line, asks `gh issue view` whether that issue exists and deletes the file only if it does. Files with no Tracker line, or naming an issue that is not found, are kept and printed. Exit 1 when anything is kept. Env `SPRAWL_GATE_GH` swaps in a fake issue CLI for the tests.

## Base rules

A path is denied by a base rule unless an exemption covers it. A deny message names the rule in brackets, for example `sprawl-gate [base rule stray-plan-dir]: ...`, and ends with `(no omo runtime need or user exception covers it)`. `check` prefixes each plan violation with the same rule name.

| Rule             | What it denies                                                                                                                                                                                                                                                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `plan-home-live` | `check` only; writes are allowed. A file in the plan home (`~/.claude/plans`) may hold a plan until it is live: without a `Tracker: <issue url>` line it fails as `plan-not-live`; with one it is a second copy of the issue and fails as `plan-live-undrained` until `drain` deletes it. Empty folders and a missing plan home are clean. |
| `stray-plan-dir` | Any file in `.omo/plans`, `.mo/plans`, `.claude/plans` or `.omc/plans` outside the plan home, wherever that segment appears in the path. `check` scans these dirs under the `~/Dev` roots.                                                                                                                                                 |
| worktrees        | `check` only: a dir in `<repo>/.claude/worktrees` that `git worktree list` lacks, or a registered worktree missing on disk.                                                                                                                                                                                                                |

## Two exemption mechanisms

They never share a list. A denial names which mechanism would have had to cover the path, so the reader knows whom to ask: the owner for a user exception, the omo version for a runtime need.

### Omo runtime needs

What omo needs in order to run. Owned by the omo version, not the owner, and kept as `OMO_RUNTIME_NEEDS` in the script. An omo layout change is a change to that tuple and to this section.

None today. The former need, `<plan home>/.omo` (omo's executor boulder and wave state for the plans it ran from the plan home), was removed by #174. On 2026-10-25 the plan home did not exist on disk, no `.omo` folder was under it, and no omo or OpenCode config named it; the only `~/.claude/plans` text under `~/.omo` was the bundled Claude Code settings schema (the `plansDirectory` default) plus session transcripts. Omo's wave records were ingested and the plan-home state removed by #153.

### User exceptions

What the owner allowed. Kept in `scripts/sprawl-gate.toml` (env `SPRAWL_GATE_EXCEPTIONS_FILE` overrides it, which the tests use). Only the owner adds an entry. Each entry is one `[[exception]]` table:

```toml
[[exception]]
path = "~/some/dir" # ~/ means the home folder; covers the path and everything beneath it
reason = "why the owner allows it"
granted = "2026-10-25"
```

An entry missing `path`, `reason` or `granted` is not applied, and `check` reports it. A file that does not parse applies nothing, and `check` reports that too. User exceptions are checked first, so one can cover a path any base rule would deny.

No user exception is granted today.

## Rulings

- Plans may be kept, but only until they are live (owner, 2026-10-25, replacing #174's empty plan home). Claude Code's `plansDirectory` only accepts a folder inside the project, so plan mode keeps the default plan home; the hook therefore allows writes there. The tracker stays the one source of truth: `check` fails on any plan-home file until it names its issue and `drain` has verified that issue exists and deleted the copy.
- `~/.omo/plans` stays policed (owner, #247, 2026-10-25). Plans live only in the tracker; an exemption would let omo plans escape the tracker, the problem #144 cleans up; omo writes its plans through its own process, so the Write/Edit hook only blocks hand edits by Claude. The files already there are ingested by #254. `check` does not scan `~/.omo/plans` (it scans the `~/Dev` roots only), so the existing files raise no Stop-hook report; only new hooked writes are denied.
- The rest of omo home (`drafts/`, `evidence/`, `reports/`, `tmp/`, `ulw-loop/`, `wayfinder/` and the app dirs) and the rest of a repo's `.omo` are not plan dirs: out of scope, not exemptions.

## Verdict table

Each row is a test. `explain` prints the same verdict and mechanism.

| Path                                                                       | Verdict              | Mechanism                                |
| -------------------------------------------------------------------------- | -------------------- | ---------------------------------------- |
| a file in `<plan home>` with no Tracker line (`check`), `.omo/**` included | fail                 | base rule `plan-not-live`                |
| a file in `<plan home>` with a Tracker line (`check`)                      | fail                 | base rule `plan-live-undrained`          |
| any write into `<plan home>`, `<plan home>/.omo/**` included               | allow                | base rule `plan-home-live`               |
| `drain`: Tracker issue exists / not found / no Tracker line                | delete / keep / keep | base rule `plan-home-live`               |
| empty folders, empty or missing `<plan home>` (`check`)                    | clean                | none                                     |
| `~/.omo/plans/**`                                                          | deny                 | base rule `stray-plan-dir` (ruling #247) |
| `~/.omo/drafts/**`, `~/.omo/evidence/**`, other omo dirs                   | allow                | out of scope                             |
| `<repo>/.omo/plans/**`, `.mo/plans`, `.claude/plans`, `.omc/plans`         | deny                 | base rule `stray-plan-dir`               |
| a path under a well-formed user exception                                  | allow                | user exception (reason and date printed) |
| a stray plan path under an entry missing reason or date                    | deny                 | base rule; `check` reports the entry     |
| an exception file that does not parse                                      | deny                 | base rule; `check` reports the file      |

## Live probes

Committed tests use fabricated homes only. The demonstration against the real gate stays a visible ritual, run read-only before a change lands:

```
uv run scripts/sprawl-gate.py explain ~/.claude/plans/x.md ~/.claude/plans/.omo/waves/boulder.json ~/.omo/plans/x.md ~/.omo/drafts/x.md <repo>/.omo/plans/x.md
uv run scripts/sprawl-gate.py check
```
