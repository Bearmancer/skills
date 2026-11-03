---
name: github-sweep
description: 'Use when auditing, sweeping, or triaging pre-existing GitHub PRs, issues, review requests, and fork branches across third-party repositories. Runs fully unattended without interactive permission stops: strictly excludes personal non-fork repos, checks all open items, front-loads fresh CodeGraph indexing before branch/code evaluation, checks latest upstream base, executes requested changes in isolated branches, pushes with lease protection, maximally purges merged/closed fork branches, and prints initial/final triage tables.'
---

# GitHub Sweep (Unattended Third-Party Audit & Update Protocol)

Autonomous, account-wide audit, triage, update, and branch-purge protocol across all third-party GitHub repositories and forks associated with the authenticated account.

The run is **fully unattended and maximal**: all permissions are granted up-front; never stop to prompt or ask the user. Stops are strictly mechanical and fail closed. A mutation (code push, branch deletion, thread closure) carries primary-source proof or is not executed.

Companions:
- `references/sweep-pipeline.md`: Discovery mechanics, CodeGraph setup, triage states.
- `references/branch-hygiene.md`: Maximal branch purge logic and fail-closed safety criteria.
- `scripts/sweep.py`: Account-wide census CLI (PRs, issues, forks, CI states).
- `scripts/purge.py`: Autonomous maximal fork branch purge engine.
- `scripts/rebase.py`: CodeGraph-backed isolated PR rebase and push runner.
- `scripts/ci_status.py`: Detailed CI check analyzer and error parser.

---

## Bundled Scripts Inventory (`scripts/`)

All mechanical discovery, branch auditing, and rebasing operations are encapsulated in the skill's `scripts/` directory—**never hand-create or re-derive ad-hoc scripts in chat**:

1. **`python scripts/sweep.py`** (or system `gh-sweep`):
   - Fast account-wide census across third-party repos.
   - Flags: `--open-only`, `--json`, `--prs-only`, `--issues-only`, `--forks-only`, `--out <file>`.
2. **`python scripts/purge.py`**:
   - Maximal remote fork branch purger.
   - Deletes merged/closed/stale branches across all forks without interactive stops.
   - Flags: `--dry-run`, `--verbose`.
3. **`python scripts/rebase.py <repo> <pr_number>`**:
   - Clones target repo into temporary scratch workspace, initializes CodeGraph on upstream base, rebases PR branch, and optionally pushes with `--push` (`--force-with-lease`).
4. **`python scripts/ci_status.py <repo> <pr_number>`**:
   - Detailed check-run analyzer reporting failed jobs, error logs, and pending states. Flags: `--json`.

---

## Non-Negotiable Directives & Safety Invariants

1. **Strict Personal Repository Exclusion:**
   - Identity is resolved dynamically: `CURRENT_USER=$(gh api user --jq .login)`.
   - Never touch personal, non-fork repositories (`owner == CURRENT_USER and isFork == false`).
   - Only third-party upstream repos and user forks of third-party repos (`isFork == true`) are swept.
2. **Comprehensive Census ("Check All"):**
   - Sweeps all authored PRs, all authored/assigned issues, all review requests, and all fork branches.
3. **No Interactive Permission Stops:**
   - No interactive confirmation dialogs. Purge merged, closed, and stale branches maximally.
4. **CodeGraph First for Changes:**
   - When any PR or issue requires code evaluation, rebase, or changes: establish ground truth on upstream default-branch HEAD with CodeGraph (`codegraph init -y`) before touching branches or editing files.
5. **Latest Upstream Alignment:**
   - Always pull and align against latest upstream base (`dev` or `main`) before applying changes.
6. **Isolated Branch per Work Item:**
   - Every fix, rebase, or asset update runs in an isolated task branch and temporary scratch workspace.
7. **Clean Teardown:**
   - Workspaces and merged/closed branches are deleted upon completion; final status table printed post-updates.

---

## Execution Flow

```
[Phase 1: Fast Account Census] ──► gh-sweep or scripts/sweep.py
         │
         ├──► If no items need updates & no stale branches:
         │      Print initial census table ➔ Done.
         │
         └──► If updates needed (review feedback, merge conflicts, red CI) OR stale branches exist:
                │
                ▼
[Phase 2: CodeGraph-Backed Triage & Workspace Setup]
         │ (Per target repository: clone upstream default branch -> codegraph init -y)
         ▼
[Phase 3: Autonomous Change Execution]
         │ 1. Pull latest upstream base (dev/main)
         │ 2. Create isolated task branch (fix/...)
         │ 3. Execute requested maintainer changes & run local test gates
         │ 4. Push with --force-with-lease & comment resolution on PR
         ▼
[Phase 4: Maximal Branch Purge]
         │ Delete remote fork branches for merged, closed, or obsolete PRs
         ▼
[Phase 5: Final Post-Update Audit Table]
         Print conclusive before/after status ledger
```

---

## 1. Fast Account Discovery

1. Resolve authenticated identity:
   ```bash
   CURRENT_USER=$(gh api user --jq .login)
   ```
2. Run the sweep engine:
   ```bash
   gh-sweep --json
   ```
   *Fallback if `gh-sweep` CLI is unavailable:* run `python scripts/sweep.py --json`.

3. **Branch Decision Gate:**
   - If all open PRs are green, mergeable, and awaiting maintainer review, with zero failing CI, zero unaddressed review comments, and zero merged/closed branches on remote forks:
     - Print the structured Markdown triage table and exit cleanly.
   - If any PR has merge conflicts, unaddressed review comments, failing tests, or stale branches to purge: proceed immediately to Phase 2.

---

## 2. CodeGraph Setup & Upstream Base Pull

For each target repository requiring triage or code modification:

1. **Isolated Workspace:**
   ```bash
   d=$(mktemp -d -t gh-sweep-<repo-slug>-XXXXXX)
   ```
2. **Clone Upstream Default Branch:**
   ```bash
   gh repo clone <target-owner>/<target-repo> "$d/repo" -- --filter=blob:none
   ```
3. **Initialize CodeGraph Immediately:**
   ```bash
   cd "$d/repo" && codegraph init -y
   ```
   Confirm with `codegraph status`. All mechanism investigations, symbol lookups, and blast-radius tracing run against this indexed default-branch HEAD.
4. **Ensure Latest Base:**
   Fetch latest upstream refs (`git fetch origin <default-branch>`).

---

## 3. Autonomous Execution & Rebase Pipeline

For each pull request requiring changes:

1. **Checkout & Branch Isolation:**
   Fetch the PR branch from the user's fork into an isolated worktree or branch:
   ```bash
   git fetch fork <branch-name>
   git checkout -b <branch-name> fork/<branch-name>
   ```
2. **Rebase on Upstream Base:**
   ```bash
   git rebase origin/<default-branch>
   ```
   - Resolve conflicts preserving the PR's approved functional intent.
   - Re-run any repository-mandated asset/code generators (e.g. `bun run build:senpi-plugin`, prelude generators, model catalog scripts).
3. **Address Maintainer Review Items:**
   - Inspect maintainer review comments in full (`gh pr view <pr> --json reviews,comments,latestReviews`).
   - Implement required test adjustments, mock fixes, error handling, or documentation updates.
   - Run localized unit and integration tests locally before pushing.
4. **Push with Lease Protection:**
   ```bash
   git push --force-with-lease fork <branch-name>
   ```
   *Never use bare `git push --force`.* `--force-with-lease` guards against overwriting upstream maintainer tweaks.
5. **Maintainer Communication:**
   Post a concise, objective summary on the PR thread referencing the new commit SHA and specific points addressed.

---

## 4. Maximal Branch Purge (No Permission Asks)

Audit remote branches across all user forks:
```bash
gh repo list --fork --json nameWithOwner,name,parent --limit 100
```
For each fork:
1. List remote branches: `gh api repos/<user>/<fork>/branches --jq '.[].name'`.
2. Compare each non-default branch against the PR census:
   - If the branch belongs to a **MERGED** PR: **PURGE IMMEDIATELY**.
   - If the branch belongs to a **CLOSED** PR: **PURGE IMMEDIATELY**.
   - If the branch is an orphan with zero unmerged commits (`ahead_by == 0` vs upstream): **PURGE IMMEDIATELY**.
3. **Execution Command:**
   ```bash
   gh api -X DELETE repos/<user>/<fork>/git/refs/heads/<branch-name>
   ```
4. **Safety Exclusions (Fail Closed):**
   - Never delete default branches (`main`, `master`, `dev`).
   - Never delete branches associated with active **OPEN** PRs.
   - Never delete branches with unmerged unique commits (`ahead_by > 0`).

---

## 5. Final Post-Update Audit Report

Print the conclusive triage ledger at the end of the run:

### A. Execution Ledger
| Repository | Item / Branch | Status | Actions Executed |
| :--- | :--- | :--- | :--- |
| `<owner>/<repo>` | PR #`<num>` (`<title>`) | `MERGEABLE` | Addressed review feedback in `<sha>`, rebased on `<base>`, tests passed |
| `<user>/<fork>` | Branch `<name>` | `PURGED` | Merged in PR #`<num>`; remote ref deleted |

### B. Summary Totals
- Total third-party PRs audited: `<count>`
- PRs updated / rebased: `<count>`
- PRs awaiting maintainer review: `<count>`
- Remote fork branches purged: `<count>`
- Personal non-fork repositories excluded: `<count>`
