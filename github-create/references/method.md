# Method

## Delegation

The main loop judges; subagents work by tier, chosen by role, never pinned. Example names are illustrative, not a list to match.

| tier   | examples                                    | use                                                                                    |
| ------ | ------------------------------------------- | -------------------------------------------------------------------------------------- |
| light  | Muse Spark Contributor 1.3, Mimo Flash v2.6 | gather and run                                                                         |
| medium | GLM 5.3 Flash, Sonnet 5.5                   | bounded implementation                                                                 |
| heavy  | Opus 5.5                                    | one whole-diff review of a PR before filing; at most once per filing, never for issues |

| work                                                                                                                                                      | tier      |
| --------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| thread and prior-art sweeps, contract-file reads, source tracing, URL audit, running the repo's checks, test runs, cleanup verification, citation re-open | light     |
| PR fix and regression test, drafted from the confirmed root cause                                                                                         | medium    |
| triage verdict, hypothesis ranking, root-cause conclusion, fix design, drafting, adjudicating a mismatch, any stop decision                               | main loop |

A brief to a subagent names: the one question, the clone path and SHA, the output shape (verbatim quotes as `path:line@SHA`, facts only, no conclusions), a size cap, and "do the work yourself: invoke no skill, spawn no agent". It writes long findings to `$d/notes/<name>.md` and returns the path plus a five-line gist; the main loop opens the note only where it needs the detail. Independent briefs go out in one parallel batch. A report is a hypothesis: re-open every cited line before it enters the draft.

## Read in full, primary sources only

- Read the whole file, function or thread (every comment, the timeline, linked PRs and commits) before asserting what it does. READMEs, docs, changelogs, search snippets, list views and reports are orientation, never evidence. A list view returns bodies without comments: open each thread.
- Trace every claim to the source that owns it: upstream code at the indexed SHA, a spec, official docs, the thread itself. Only a secondary write-up reachable → find the primary or drop the claim.
- Spot-check three random citations in the draft; each must land on the thing itself.

## Upstream records and the feature bar

Read the decision records that touch the area. The upstream's own words (GLOSSARY, ADRs) name things in titles and bodies. A change that contradicts a recorded decision says so: "contradicts <record>, but worth reopening because ...".

A feature request clears the bar only with an observed failure: what was run, what happened, what was expected. Verification and the verdict are in `triage.md` "Verify before judging" and the closure table below.

## Codegraph

The clone's index is the map, not the evidence. `codegraph explore "<symptom> <symbol>"` returns the relevant symbols with source and call paths; `query` finds names, `node` reads one symbol with callers and callees, `callers`/`callees` walk the edge, `impact` gives the blast radius, `affected` names tests. Start from the symptom, not a guessed filename. Record each candidate as `path:line@SHA`; open the file and quote the line before it enters the draft. An empty result is a finding: fall back to `codegraph files` and grep, and say the index did not resolve it. Never cite the index output itself.

## Existing thread

The closure table below decides what to do with a thread on the same mechanism.

- **Thin** means any of: no minimal repro, no mechanism or code path, no verbatim evidence, no environment, template fields blank, stale against the current base.
- **Permission:** you own the thread (author) or have WRITE → `gh issue edit`/`gh pr edit --body-file`, adding required labels; you own the PR branch → push commits and `--force-with-lease` on a rebase. TRIAGE can label, assign and close, but it is comment-only for another author's body. Another author's PR → comment the missing evidence; never push to their branch. No permission → comment; do not edit.
- **Record** the verdict (new / comment / update #n / refile) and the category/state under Decisions, with the thread number and the reason.

## Root cause

The issue pipeline uses steps 1-2 to make the repro credible; the PR pipeline runs all five before the fix.

1. **Loop.** One command, already run, output captured and redacted, that goes red on the reported symptom (not a neighbor failure), same verdict every run, seconds, runnable unattended. Prefer: failing test at the seam; CLI on a fixture diffed against known-good; HTTP script; replayed capture; throwaway harness; fuzz; `git bisect run`; old-vs-new differential. Flaky → raise the reproduction rate first. No loop → file nothing, report what was tried; no theorizing without one.
2. **Minimise.** Cut inputs, config and steps one at a time until every remaining element is load-bearing.
3. **Hypotheses.** 3-5 ranked, each falsifiable: "if X is the cause, changing Y makes it vanish". Include the rivals: user config, version (reproduce on default-branch HEAD and the latest release; fixed there → stop), documented intended behavior, environment, a known issue, another tool path. Run each. Every one, failures included, is a row in the ledger.
4. **Instrument.** One variable at a time; a debugger over logs; tag every probe `[DEBUG-xxxx]` and grep it to zero before commit. Performance: measure a baseline first, then bisect.
5. **Mutations.** A red forced by editing code, a fixture or a stash: `diff` against a pristine copy to prove the edit landed.

## Fix and test (PR pipeline)

- Smallest diff, one hunk per mechanism, at the existing seam and idiom. No new abstraction for one caller, no drive-by refactor, no format churn.
- Regression test at the seam where the real bug pattern occurs. Only a too-shallow seam exists → say so in the body; no false-confidence test.
- Red before green: watch it fail on base, then pass with the fix. Expected values are independent literals, never recomputed the way the code computes them. Assert through the public interface; mock only system boundaries. The output shows the test name and a run count: a skipped test (gitignored fixtures skip silently) is unverified.
- Each acceptance item and claim names the observation that would show it false, and that observation fails at base.
- Run the repo's own checks on the changed paths (the CI `run:` lines `contract` lists, package scripts). Never pass --no-verify. Match the `git log` style for commits, `-s` when DCO or CLA is flagged.
- Self-review in a fresh context on two axes, then stop (not looped until clean). **Standards:** upstream's documented rules; baseline smells as judgment calls (Duplicated Code, Speculative Generality, Shotgun Surgery, Mysterious Name, Message Chains, Middle Man), the repo's rules override. **Spec:** the linked issue's lines; anything beyond them is scope creep. Every finding cites a rule, a hunk or a spec line.

## Redact

Credentials, usernames, hostnames and home paths become `<REDACTED>` or `<user>` before output enters a body; keep the credential in the environment and quote only the lines that carry the signal. `preflight.py check` blocks on a hit.

## Closure table

Pull the timeline before deciding comment, new post or update:

```bash
gh api repos/ --jq '.[] | select(.event=="closed" or .event=="cross-referenced") | {event:.event, actor:(.actor.login // null), at:.created_at}' <owner >/ <repo >/issues/ <n >/timeline
```

A bot-applied `not_planned` is the stale default, not a rejection: read the timeline, never the label.

| thread                                                                                   | action                                                                                                                          |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| open issue, same mechanism, sound                                                        | adopt it; comment only with new evidence; no duplicate issue                                                                    |
| open PR, same mechanism, sound                                                           | comment new evidence or update that PR; ends the issue pipeline; no duplicate                                                   |
| open issue or PR, same mechanism, thin                                                   | update in place: `gh issue edit`/`gh pr edit` the body and title, push the missing commits if the branch is yours; no duplicate |
| open PR by another author, thin                                                          | comment the missing evidence, or a competing PR only with a materially stronger case; never push to their branch                |
| open issue, no PR, fix confirmed                                                         | file the PR and link it; update the issue only if the fix direction is missing                                                  |
| closed `not_planned` by `github-actions[bot]`                                            | stale close: new post citing the old number                                                                                     |
| closed `completed` or merged PR, still reproduces                                        | regression: new post citing the old issue and PR                                                                                |
| closed `not_planned` or unmerged PR by a human, or a matching record in `.out-of-scope/` | refile only with a materially stronger case: new impact, new mechanism, narrower diff, working PR, fresh repro on current base  |
| CONTRIBUTING says issue-only or proposals-only                                           | issue only, say why                                                                                                             |
| CONTRIBUTING says PR-only                                                                | skip the issue, file the PR, record the exception                                                                               |
| `gh repo view --json viewerPermission` is READ, TRIAGE or none                           | fork path; WRITE or above → own branch, still never the base                                                                    |
| base moved                                                                               | rebase on `origin/HEAD`, retest. Run the rebase gate: `rebase-gate check-rebase <repo> <base-ref> --allow ...`.                 |

## Corrections

Edit your own body or title (`gh issue|pr edit --body-file`) or delete a bad comment (`gh api -X DELETE repos/<owner>/<repo>/issues/comments/<id>`); never post a superseding correction or open a second PR; push rebases with `--force-with-lease`.
