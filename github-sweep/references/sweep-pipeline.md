# GitHub Sweep Pipeline Reference

Detailed operational protocol for third-party discovery, CodeGraph setup, triage classification, and change execution.

---

## 1. Discovery Filtering Mechanics

### Dynamic User Resolution
```bash
CURRENT_USER=$(gh api user --jq .login)
```

### Personal Repository Exclusion Rule
For every repository in the sweep, evaluate:
```bash
gh repo view <owner>/<repo> --json owner,isFork --jq '{owner: .owner.login, isFork: .isFork}'
```
- `owner.login == CURRENT_USER` AND `isFork == false` ➔ **EXCLUDE**. (Personal repository. Never touch issues, PRs, or branches in personal repositories).
- `owner.login != CURRENT_USER` ➔ **INCLUDE**. (Third-party repository).
- `owner.login == CURRENT_USER` AND `isFork == true` ➔ **INCLUDE**. (User's fork of a third-party repository).

---

## 2. CodeGraph Ground Truth

When a PR or issue requires code investigation, rebase, or fixes:
1. Clone the upstream default branch with shallow blobless filter:
   ```bash
   gh repo clone <upstream-owner>/<upstream-repo> "$d/repo" -- --filter=blob:none
   ```
2. Initialize CodeGraph index:
   ```bash
   cd "$d/repo" && codegraph init -y
   ```
3. Exclude the index from git diffs:
   ```bash
   grep -qxF '.codegraph/' .git/info/exclude 2>/dev/null || echo '.codegraph/' >> .git/info/exclude
   ```
4. Query the index using `codegraph explore "<symbol or symptom>"` to:
   - Identify whether upstream refactored or incorporated the mechanism already.
   - Trace callers and blast radius before modifying code.
   - Verify that test files and fixtures reflect the current contract.

---

## 3. PR Triage Classification Matrix

Every open PR is categorized into one of three operational states:

| Classification | Definition | Action Required |
| :--- | :--- | :--- |
| **Needs Update (Review / Conflicts / CI)** | Branch has merge conflicts against target base, unaddressed review comments from maintainers, or failing CI checks on new code. | Check out branch, rebase on latest upstream base, apply fixes, verify tests locally, push with `--force-with-lease`. |
| **Awaiting Maintainer** | Branch is mergeable, clean, passes all CI tests, and latest review items are already addressed in existing commits. | Leave intact. Record in preserved items table. |
| **Obsolete / Superceded** | Mechanism was already implemented in upstream `dev`/`main`, or maintainer closed the underlying issue/feature. | Close PR with an explicit rationale citing upstream commit/PR, then purge remote fork branch. |

---

## 4. Upstream Communication Protocol

When updating a PR:
1. Never post noisy intermediate updates.
2. Complete all rebasing, code adjustments, asset regeneration, and local test passes first.
3. Push an atomic commit to the branch.
4. Post a single, structured resolution comment citing:
   - The commit SHA.
   - Exact maintainer points addressed.
   - Local test verification command and results.
