# Live e2e: CI check path on a third-party PR

Runtime-only run on 2026-10-21, read-only: no PR, issue or comment was created or changed on any third-party repo. Not a suite test.

Subjects (public, open, picked from `gh search prs --state open --checks failure`):

- `juju4/ansible-harden-apache#32`: real workflow failures, many jobs queued or running.
- `eigenpal/docx-editor#1452`: mostly pending, one external-status failure.

## What ran

1. `gh pr checks 32 -R juju4/ansible-harden-apache`, plain and `--json name,workflow,state,link`. First snapshot: 20 `pending` rows plus `renovate/stability-days pass`, exit 8 (gh's pending code). The earlier search listing showed 8 failures; the PR's runs had been re-triggered, so everything was queued again.
2. `timeout 120 gh pr checks 32 -R juju4/ansible-harden-apache --watch --fail-fast --interval 10`. Refreshed the table until the first failure, then exited 1 with `build  fail  1m9s` (workflow `lint`, job 119049251205) shown on the final table, ahead of the other 19 still-pending jobs. Fail-fast stopped the watch at the first failure as intended.
3. `timeout 90 gh pr checks 1452 -R eigenpal/docx-editor --watch --fail-fast --interval 10` on a PR that was pending: the watch refreshed while jobs moved from `pending` to `pass` (api-changeset, cla, typecheck, wheel linux/macos) and exited 1 because of the standing `Vercel fail 0 Authorization required to deploy` status, which is an external deploy-authorization failure, not a workflow job.
4. Step 11 of the skill, its script leg: `GITHUB_CREATE_STATE_DIR=<tmp> preflight learn juju4/ansible-harden-apache --from-pr 32`. The override sends the repo doc to a scratch directory and turns auto-commit off, so nothing was written in the skill and nothing was pushed. Output: `learned: 1 note(s)`.

## Classification vs gh

| Source                                                                                            | Failed checks                                                                                                          |
| ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `learn --from-pr 32` (state `failure`/`error`/`timed_out`/`cancelled` from `gh pr checks --json`) | one: workflow `lint`, job `build`, run 39547616734/job/119049251205, log tail from the failing ansible step            |
| `gh pr checks 32` at the same time                                                                | the same one job (`build`, `fail 1m9s`)                                                                                |
| `gh pr checks 32 --json` re-read afterwards                                                       | two failures: that `lint/build` job and `default-bare` `build (ubuntu-24.04, false)`, which failed after the learn run |

Match: the skill recorded exactly the failures gh reported at that moment, with workflow, job, link and a log excerpt, and none of the queued, in-progress or passing jobs. The second failure appeared later in a live CI, not a classification miss; it was not re-run.

## Observations

- `gh pr checks` exits 8 while only pending, 1 on any failure; `--watch --fail-fast` returned 1 on the first failure in both runs.
- `learn` ignores pending checks, so running it on a still-queued PR records nothing; step 11 runs it after a snapshot that already holds failures.
