# Branch Hygiene & Maximal Purge Reference

Protocols for safely and maximally pruning remote fork branches and local tracking branches without user prompts.

---

## 1. Remote Fork Branch Purge Rules

For every fork belonging to `CURRENT_USER`:

```bash
gh api repos/<user>/<fork>/branches --jq '.[].name'
```

Evaluate each branch against these criteria:

### A. Automatic Purge Criteria (Purge Maximally)
A remote branch is purged immediately if:
1. **Associated PR is Merged:**
   The PR was merged into the upstream repository (`state == "MERGED"`).
2. **Associated PR is Closed:**
   The PR was closed without merging (`state == "CLOSED"`), and no active work is planned.
3. **Orphan Branch with No Divergence:**
   The branch has no associated PR, and comparing against upstream default branch shows `ahead_by == 0` or status `identical` / `behind`:
   ```bash
   gh api repos/<upstream-owner>/<upstream-repo>/compare/<default-branch>...<user>:<branch> --jq '{status: .status, ahead_by: .ahead_by}'
   ```

### B. Inviolable Preservation Criteria (Fail Closed)
A branch is **NEVER** deleted if:
1. It is the repository default branch (`main`, `master`, `dev`).
2. It has an active, **OPEN** pull request associated with it.
3. It has unmerged unique commits (`ahead_by > 0`) not yet integrated upstream.
4. It is currently checked out in an active local worktree (`git worktree list`).

---

## 2. Deletion Commands

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
