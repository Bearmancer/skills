# Branch Hygiene & Maximal Purge Reference

Branch selection and deletion rules: explicit targets only, never a wildcard, and every deletion confirmed by a fresh listing. The adapter is `scripts/purge_branches.py`. Protocols for pruning remote fork branches and local tracking branches without prompts.

---

## 1. Remote Fork Branch Purge Rules

For every fork belonging to `CURRENT_USER`:

```bash
gh api repos/<user>/<fork>/branches --jq '.[].name'
```

Evaluate each branch against these criteria:

### A. Automatic Purge Criteria (Purge Maximally)

A remote branch is purged immediately if:

1. **Associated PR is Merged:** The PR was merged into the upstream repository (`state == "MERGED"`), and the upstream compare still shows `ahead_by == 0`.
2. **Associated PR is Closed:** The PR was closed without merging (`state == "CLOSED"`), no active work is planned, and the upstream compare shows `ahead_by == 0`.
3. **Orphan Branch with No Divergence:**
   The branch has no associated PR, and comparing against upstream default branch shows `ahead_by == 0` or status `identical` / `behind`:
   ```bash
   gh api repos/<upstream-owner>/<upstream-repo>/compare/<default-branch>...<user>:<branch> --jq '{status: .status, ahead_by: .ahead_by}'
   ```

A merged or closed PR alone never proves the branch is divergence-free: squash merges leave the branch ahead of upstream, so every candidate is compared first (criterion B3 wins over A1/A2).

### B. Inviolable Preservation Criteria (Fail Closed)

A branch is **NEVER** deleted if:

1. It is the repository default branch (`main`, `master`, `dev`).
2. It has an active, **OPEN** pull request associated with it.
3. It has unmerged unique commits (`ahead_by > 0`) not yet integrated upstream.
4. It is currently checked out in an active local worktree (`git worktree list`).

---

## 2. Deletion Commands

Ref names in a REST path must be percent-encoded: `gh api` cuts a raw path at `#` and `?`, so a branch like `fix/a?b` or `fix#12` becomes a wrong or truncated endpoint. `scripts/purge_branches.py` encodes the ref in both of its ref-in-path calls (the `compare` default-branch and head-ref segments, and the `git/refs/heads/<branch>` DELETE), and `scripts/preflight.py` encodes it in the required-status-checks path (`branches/<branch>/protection/...`) — each via `urllib.parse.quote(name, safe="/")`. When running a command below by hand, encode the branch name the same way (`fix%2Fa%3Fb`).

### Remote Branch Deletion

```bash
gh api -X DELETE repos/<user>/<fork>/git/refs/heads/<branch-name>
```

### Local Tracking Branch Deletion

If a local clone exists:

```bash
git branch -d <branch-name>
```

If the branch was merged upstream, `-d` succeeds safely. Use `-D` only if the remote PR was confirmed closed/merged on GitHub.
