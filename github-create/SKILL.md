---
name: github-create
description: "Use when filing an issue, PR or feature request on a third-party GitHub repo, after root-causing a bug in a dependency or CLI, or when auditing, sweeping, housekeeping or triaging your open PRs, review-requested changes, issues and fork branches account-wide. Runs unattended through latest-version gate, proven fix, PR, CI and cleanup; housekeeping mode is fully autonomous until no action is left and never rebases without an executed fix. Excludes personal non-fork repos, prints triage tables."
---

Third-party repos only, two modes: **create** (file or adopt an issue, then a proven fix PR — `references/create-path.md`) and **housekeeping** (account-wide sweep of your open PRs, review requests and fork branches — Housekeeping mode below). The run is unattended and maximal: every step runs in full, and the stops are mechanical and fail closed (preflight, URL audit, loop limits). A post carries proof or is not filed: the reviewer checks every claim against source, diff or demo alone.

With no user to ask, the smaller reversible option (narrower scope, fewer claims) is taken and recorded under Decisions in the report. A thread that needs a maintainer decision stays `needs-triage` with the question in the comment.

Companions: `references/create-path.md` (create pipeline steps 0–13), `references/method.md` (method, delegation tiers, proof bar, closure table, corrections), `references/bodies.md` (issue and PR layouts, PR body craft, URL audit), `references/triage.md` (roles, outcomes, briefs and the unattended deltas), `references/ci-harvest.md` (one row of CI facts per repo doc), `references/sweep.md` (housekeeping census, triage table, executed-fix rebase pipeline, branch purge, re-census loop), `references/branch-hygiene.md` (fork branch purge criteria; deletion policy owned by `purge-safety`). The bundled scripts `preflight.py` and `rebase-gate.py` live in this skill's `scripts` folder; below, `preflight <command>` and `rebase-gate <command>` mean `uv run --script` on that script from there. Housekeeping adds `sweep.py`, `rebase.py`, `purge_branches.py` and `ci_status.py` in the same folder, run with `uv run`.

## Shape

Symptom, no fix, or unclear → issue. Missing capability → feature issue, then the implementing PR. Fix for an existing bug, or root cause confirmed in the repo's own code with the fix building and testing green in the clone, and the repo takes PRs → issue first, then the fix PR (`Fixes #<n>` with the filed number). An existing thread on the same mechanism, or a CONTRIBUTING rule, can change that: `method.md` "Closure table".

## Create mode

The full create pipeline - steps 0-13: existing-thread search, version gate and workspace, issue pipeline, PR pipeline, CI, re-audit, cleanup - lives in `references/create-path.md`. Read it in full before any create-mode run; each step ends on a checkable criterion. Housekeeping asks take the Housekeeping mode section below instead.


## Housekeeping mode (sweep of what already exists)

A sweep, audit or housekeeping ask over the account's own open PRs, review requests, issues and fork branches takes this path instead of the create path; the full protocol, invariants and ledger are `references/sweep.md` (read before any mutation). The gates, non-negotiable:

- **Executed fixes only.** An item counts as updated only when the fix really ran: repo build and test suite green locally in the clone, before/after evidence captured verbatim. A push, a rebase or a comment reply without an executed fix is not an update and is forbidden.
- **A maintainer review request on our PR always produces new tests.** Each review point gets a test failing at the pre-fix head and passing after (red→green, `method.md` "Fix and test"); prose-only answers leave the point open.
- **No rebase without an executed fix.** Rebasing onto latest upstream happens only inside the push that lands a fix; resolving merge conflicts counts as the fix only with the full local test gate run green before `--force-with-lease`. Bare freshness rebases do not exist.
- **Issues link their PRs.** Whenever an existing issue and an existing PR cover the same mechanism, the issue body names the PR (`Linked PR #<n>` or the template field); edit with ownership/WRITE, else comment the link with the `triage.md` banner.
- **Personal non-fork repos untouched; census comprehensive; run until exhausted** — census → act → re-census until a full pass holds zero actions; then the ledger and summary totals (`sweep.md`).

The report opens with the remaining-items count, then URLs, preflight result, Decisions taken, the Learnings recorded this run, and what waits on others.
