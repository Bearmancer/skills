---
name: github-sweep
description: "Use when auditing, sweeping or triaging open PRs, issues, review requests and fork branches on third-party repos. Fully autonomous: never asks, never stops or defers until no action is left. Excludes personal non-fork repos, prints triage tables."
---

# GitHub Sweep (Unattended Third-Party Audit & Update Protocol)

Autonomous, account-wide audit, triage, update, and branch-purge protocol
across third-party GitHub repos and forks for the authenticated account.

The run is **fully autonomous and maximal**: all permissions granted
up-front. Never ask, stop, or defer work. It ends only when no possible
action is left (§0). A mutation carries primary-source proof; lacking proof,
skip it alone and continue.

Companions:
- `references/sweep-pipeline.md`: discovery, CodeGraph setup, triage states.
- `references/branch-hygiene.md`: branch selection, fail-closed criteria; purge policy in `purge-safety`.
- `references/scripts.md`: bundled scripts and flags.
- `references/invariants.md`: non-negotiable directives.
- `references/execution-flow.md`: phases 1–5 and re-census loop.

## 0. Run Until Exhausted

Repeat passes (census → act → re-census) until one full pass has zero
actions. An action is any permitted mutation or fix.

- **Decide, never ask.** Preserve approved PR intent and invariants; record the choice; continue.
- **Failures are work.** Diagnose and retry differently. After 3 distinct attempts at one item, mark `BLOCKED` and move on.
- **No possible action**: every remaining item waits on someone else or is forbidden by an invariant. Then print the final report and end.
- **In-turn only.** Poll CI/long commands in the same turn; never hand work to a later session.

## Commands

Commands that may run 60 s or more: tee output to a log, end the log with a
`DONE` line, run detached with `Start-Process pwsh -WindowStyle Hidden
-PassThru`, then read the log with `Get-Content`. Discover by reading whole
files or search tools; `head` and `tail` are denied.

## Safety invariants

Personal repo exclusion, comprehensive census, no questions/stops, CodeGraph
first, latest upstream, isolated branch, clean teardown:
`references/invariants.md` (read before any mutation).

## Execution flow

Census → CodeGraph setup → execute/rebase → branch purge → re-census → final
audit: `references/execution-flow.md`.

## 1. Fast Account Discovery

1. `CURRENT_USER=$(gh api user --jq .login)`.
2. `gh-sweep --json` (fallback `python scripts/sweep.py --json`).
3. Branch Decision Gate: if all open PRs are green, mergeable, awaiting
   maintainer review, with zero failing CI, zero unaddressed comments, and
   zero merged/closed fork branches: print the triage table and end. Otherwise
   proceed to Phase 2.

## 2. CodeGraph Setup & Upstream Base Pull

Per target repo needing triage or changes:
1. `d=$(mktemp -d -t gh-sweep-<repo-slug>-XXXXXX)`.
2. `gh repo clone <target-owner>/<target-repo> "$d/repo" -- --filter=blob:none`.
3. `cd "$d/repo"`; if over 150000 tracked files, skip CodeGraph; else
   `CODEGRAPH_PARSE_WORKERS=2 codegraph init -y`; confirm with `codegraph status`.
4. `git fetch origin <default-branch>`.

## 3. Autonomous Execution & Rebase Pipeline

Per PR requiring changes:
1. `git fetch fork <branch-name>`; `git checkout -b <branch-name> fork/<branch-name>`.
2. `git rebase origin/<default-branch>`; resolve conflicts preserving approved intent; rerun required generators.
3. Address review items from `gh pr view <pr> --json reviews,comments,latestReviews`; run local tests.
4. `git push --force-with-lease fork <branch-name>` (never bare `--force`).
5. Post a concise PR comment with the new SHA and points addressed.

## 4. Maximal Branch Purge

`gh repo list --fork --json nameWithOwner,name,parent --limit 100`. For each
fork, list branches, then purge immediately when the branch belongs to a
MERGED or CLOSED PR, or is an orphan with `ahead_by == 0`. Delete with
`gh api -X DELETE repos/<user>/<fork>/git/refs/heads/<branch-name>`. Never
delete default branches, active OPEN PR branches, or branches with
`ahead_by > 0`.

## 5. Final Post-Update Audit Report

Print the ledger and totals.

### A. Execution Ledger

| Repository | Item / Branch | Status | Actions Executed |
| :--- | :--- | :--- | :--- |
| `<owner>/<repo>` | PR #`<num>` | `MERGEABLE` | feedback addressed in `<sha>`, rebased, tests passed |
| `<user>/<fork>` | Branch `<name>` | `PURGED` | merged in PR #`<num>`; ref deleted |

### B. Summary Totals

- Total third-party PRs audited: `<count>`
- PRs updated / rebased: `<count>`
- PRs awaiting maintainer review: `<count>`
- Remote fork branches purged: `<count>`
- `BLOCKED` items: `<count>`
- Personal non-fork repos excluded: `<count>`
PY