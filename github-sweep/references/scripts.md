# Bundled scripts inventory

All mechanical discovery, branch auditing, and rebasing operations are
encapsulated in the skill's `scripts/` directory—never hand-create or
re-derive ad-hoc scripts in chat:

1. **`python scripts/sweep.py`** (or system `gh-sweep`):
   - Fast account-wide census across third-party repos.
   - Flags: `--open-only`, `--json`, `--prs-only`, `--issues-only`,
     `--forks-only`, `--out <file>`.
2. **`python scripts/purge_branches.py`**:
   - Maximal remote fork branch purger (adapter; policy: purge-safety).
   - Deletes merged/closed/stale branches across all forks without
     interactive stops.
   - Flags: `--dry-run`, `--verbose`.
3. **`python scripts/rebase.py <repo> <pr_number>`**:
   - Clones target repo into temporary scratch workspace, initializes
     CodeGraph on upstream base, rebases PR branch, and optionally pushes
     with `--push` (`--force-with-lease`).
4. **`python scripts/ci_status.py <repo> <pr_number>`**:
   - Detailed check-run analyzer reporting failed jobs, error logs, and
     pending states. Flags: `--json`.
PY