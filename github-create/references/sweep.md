# Housekeeping mode (sweep)

Account-wide autonomous audit, triage, fix and branch purge across third-party repos and the account's forks. All permissions are granted up front: never ask, never stop, never defer until no action is left (§0). A mutation carries primary-source proof; lacking proof, skip that item alone and continue.

Interlock: `method.md` "Fix and test" and "Closure table" and the `triage.md` banner apply unchanged in housekeeping mode. Housekeeping's no-questions, no-stops autonomy overrides create mode's smaller-reversible-option default: decide, record under Decisions, continue.

## §0 Run until exhausted

Repeat passes (census → act → re-census) until one full pass has zero actions. An action is any permitted mutation or fix.

- **Decide, never ask.** No confirmation dialogs, no question tool, no pause. Preserve approved PR intent and the invariants; record the choice; continue.
- **Failures are work.** Diagnose, retry differently. After 3 distinct attempts at one item, mark `BLOCKED` and move on.
- **In-turn only.** Poll CI and long commands in the same turn; never hand work to a later session.
- **End condition:** every remaining item waits on someone else or is forbidden by an invariant. Print §5 and end.

A command that may run 60 s or more: tee output to a log ending with a `DONE` line, run detached via `Start-Process pwsh -WindowStyle Hidden -PassThru`, read the log with `Get-Content`. `head` and `tail` are denied; discover by reading whole files or search tools.

## Invariants (read before any mutation)

1. **Strict personal repository exclusion.** Resolve identity live: `CURRENT_USER=$(gh api user --jq .login)`. Test each repo with `gh repo view <owner>/<repo> --json owner,isFork`: `owner == CURRENT_USER` and `isFork == false` → excluded, never touch its issues, PRs or branches. Third-party upstreams and the user's forks (`isFork == true`) are swept.
2. **Comprehensive census ("check all").** All authored PRs, all authored/assigned issues, all review requests, all fork branches.
3. **No questions, no stops.** Purge merged, closed and stale branches maximally within `branch-hygiene.md`'s criteria.
4. **CodeGraph first.** Any PR or issue needing code evaluation, rebase or change: ground truth on upstream default-branch HEAD (§2) before touching branches or editing files.
5. **Fix-execution gate.** A PR is `UPDATED` only when the fix actually ran: build and the repo's test suite executed locally, green, evidence captured verbatim (§3). Rebasing, pushing or replying to comments without an executed fix is not an update; it is forbidden and the item stays in the ledger as not done.
6. **Latest upstream alignment — never rebase without an executed fix.** A rebase onto latest upstream is permitted only as part of landing a fix in the same push. A PR whose only complaint is merge conflicts or staleness is not rebase-padded: the conflict resolution IS the fix, so run the full local test gate green before the `--force-with-lease` push. A blind `git rebase` + push with no executed verification is forbidden. Pure freshness rebases do not exist.
7. **Isolated branch per work item.** Every fix, rebase or asset update runs in its own task branch in a temporary scratch workspace.
8. **Clean teardown.** Workspaces and merged/closed branches are deleted on completion; final ledger printed. A scratch datedir that outlives its run is a leak: delete the whole datedir. Exception: a conflict-retained workspace (unpushed commits or a dirty tree) is first resolved — commit, rebase, push `--force-with-lease`; failing that after 3 attempts, quarantine it (never auto-delete) and list its path and reason as `BLOCKED`.

## §1 Fast account census

1. `CURRENT_USER=$(gh api user --jq .login)`.
2. `uv run scripts/sweep.py --json` (or system `gh-sweep`).
3. Branch Decision Gate: all open PRs green, mergeable, awaiting maintainer, zero failing CI, zero unaddressed comments, zero merged/closed fork branches → print the triage table and end. Otherwise proceed.

_Done when:_ the census is in hand, each repo excluded or kept by invariant 1, and either the gate ended the run or §2 targets are named.

## §2 Per-repo workspace

`preflight latest` (`github-create/scripts/preflight.py`) runs once per housekeeping run, before any clone: any non-zero exit ends the whole run; report each printed `STALE:` line with its `repair:` command. Per target repo needing triage or changes:

1. `d=$(mktemp -d -t gh-<repo-slug>-XXXXXX)`; `gh repo clone <owner>/<repo> "$d/repo" -- --filter=blob:none`; `cd "$d/repo"`.
2. Size-gate the index: over 150000 tracked files (`git ls-files | wc -l`) → skip CodeGraph; else `CODEGRAPH_PARSE_WORKERS=2 codegraph init -y` (the 8-worker WASM pool peaks ~4.6 GB on monorepos); confirm with `codegraph status`.
3. Keep the index out of diffs: `grep -qxF '.codegraph/' .git/info/exclude 2>/dev/null || echo '.codegraph/' >> .git/info/exclude`.
4. `git fetch origin <default-branch>`. Query with `codegraph explore "<symbol or symptom>"`: did upstream already refactor or absorb the mechanism, callers and blast radius before any edit, do tests and fixtures reflect the current contract.

_Done when:_ `preflight latest` exited 0 once this run and each targeted repo has a fresh blobless clone, an indexed (or size-skipped) upstream base, `.codegraph/` excluded.

## §3 Triage states and the update protocol

Every open PR gets one of three states:

- **Needs Update** — unaddressed maintainer review, failing CI on new code, or merge conflicts against the base. `git fetch fork <branch>`; `git checkout -b <branch> fork/<branch>`; execute the fix per `method.md` "Fix and test"; rebase onto `origin/<default-branch>` only where the fix needs it to land (invariant 6), resolving conflicts to preserve approved intent and rerunning required generators; run build plus the repo's full test suite locally, green, output captured verbatim; push with `--force-with-lease` (never bare `--force`); post one structured resolution comment citing the new SHA, the exact maintainer points addressed, and the local test command and results. Never post noisy intermediate updates: rebase, code adjustments, asset regeneration and the test pass finish before the push and the comment. _Done when:_ tests green locally, pushed, one resolution comment posted.
- **Awaiting Maintainer** — mergeable, clean, CI green, and every review point already answered by a pushed fix with test evidence. Leave intact; record in the ledger.
- **Obsolete / superseded** — the mechanism landed upstream or the maintainer closed the underlying issue. Close the PR citing the upstream commit or PR, then purge the branch (§4).

**One review point, one test.** Every maintainer review request on our PR produces a new test: red on the current head before the fix, green after, per `method.md` "Fix and test" — regression test at the real seam, red before green, run counts shown in the output. A review point answered by prose only is unaddressed and the PR stays Needs Update.

**Issue ↔ PR links.** An issue whose mechanism is covered by an existing PR, or a PR filed in this run, must name that PR in the issue body: `Linked PR #<n>`, or the template's equivalent field. You own the issue or have WRITE → `gh issue edit` the body; otherwise post a comment carrying the link and the `triage.md` banner.

## §4 Branch purge

Selection rules and fail-closed preservation criteria live in `references/branch-hygiene.md`; not restated here. Enumerate forks with `gh repo list --fork --json nameWithOwner,name,parent --limit 100`, then run `uv run scripts/purge_branches.py` (`--dry-run`, `--verbose`). _Done when:_ every purge-eligible fork branch across every fork is gone — eligibility is decided by branch-hygiene's criteria, and a merged/closed PR alone never proves the branch divergence-free — and every kept branch satisfies a branch-hygiene criterion.

## §5 Re-census and final audit

Re-run §1. Any action left → next pass (§0). One full pass with zero actions → print the ledger and end.

### A. Execution Ledger

| Repository | Item / Branch | Status | Actions executed |
| :-- | :-- | :-- | :-- |
| `<owner>/<repo>` | PR #`<num>` | `UPDATED` | fix executed in `<sha>`, build + tests green (`<run counts>`), rebased to land the fix, one resolution comment |
| `<owner>/<repo>` | PR #`<num>` | `AWAITING` | mergeable, green, left intact |
| `<owner>/<repo>` | Issue #`<num>` | `LINKED` | body names `Linked PR #<n>` (or banner comment) |
| `<user>/<fork>` | Branch `<name>` | `PURGED` | merged in PR #`<num>`; ref deleted |
| `<owner>/<repo>` | PR #`<num>` | `BLOCKED` | 3 distinct attempts, reasons, quarantine path |

### B. Summary Totals

- Total third-party PRs audited: `<count>`
- PRs updated with executed fix and green tests: `<count>`
- Review points converted to red→green tests: `<count>`
- PRs awaiting maintainer review: `<count>`
- Issues linked to their PRs: `<count>`
- Remote fork branches purged: `<count>`
- `BLOCKED` items: `<count>`
- Personal non-fork repos excluded: `<count>`

## Bundled scripts

Mechanical discovery, branch auditing and rebasing run through `scripts/` — never hand-create or re-derive ad-hoc scripts in chat:

1. `uv run scripts/sweep.py` (or system `gh-sweep`): fast account-wide census across third-party repos. Census limits are 1000 (the search API ceiling); hitting a limit emits a truncation warning in the report, so an incomplete census is never mistaken for a complete one. Flags: `--open-only`, `--json`, `--prs-only`, `--issues-only`, `--forks-only`, `--out <file>`.
2. `uv run scripts/purge_branches.py`: §4 adapter; deletes merged/closed/stale fork branches without interactive stops. Compares run as batched GraphQL (50 branches per query) with per-branch REST fallback; local worktrees are guarded (bounded scan of cwd and ~/Dev); an incomplete PR census or failed worktree scan aborts a real purge (fail closed). Flags: `--dry-run`, `--verbose`, `--fork <owner/repo>` (repeatable).
3. `uv run scripts/rebase.py <repo> <pr_number>`: clones to scratch, indexes upstream base, rebases the PR branch; `--push` pushes with `--force-with-lease` — permitted only as part of landing an executed fix (invariant 6), never standalone.
4. `uv run scripts/ci_status.py <repo> <pr_number>`: failed jobs, error logs, pending check-runs. Flags: `--json`.
