---
name: plan-rigorously
description: "Ledgered planning producing a written, gated, independently reviewed plan; never touches product code. Use ONLY on an explicit request to plan with rigor (rigorous/ledgered plan, plan before implementing, spec plus plan, or 'plan-rigorously'). An @-mention or passing reference is not a request. Not for implement/fix/debug or executing a plan (use execute-rigorously)."
---

# plan-rigorously

Planning only. The deliverable is a final plan in `.rigor/plans/`. Implementation belongs to the sibling skill `execute-rigorously`, which starts only after this one finishes and the user authorized it.

**The user invokes only `plan-rigorously` and `execute-rigorously`.** Everything else below (the clarifying stage, mirroring, drift checks, to-do sync, verifiers, away mode) is machinery the agent runs by itself; never ask the user to run a verb or name a stage.

## Entry

1. Confirm the request is explicit: an @-mention or passing reference to this skill is not a request to plan with rigor. Ask one question to confirm intent before starting.

## Contract (hold on every stage)

1. **No assumptions.** An unresolved decision is a question, never a default. Tasks that depend on it get `blocked_on: [question id]`; independent work continues. Stop and ask only when every remaining task is blocked.
2. **Ask maximally, in batches, with the question tool.** Breadth-first rounds: every question whose prerequisites are settled goes in the same call, then the next layer. One batch at the start (blocking, plus every deferrable question already known) and one at the end (deferrable ones found later). Never one at a time. If research leaves no ambiguity, ask nothing. Every question carries options, a recommendation and an example. Only an explicit yes confirms the restated intent, the clarify destination, the chart and execution authorization; "sure", "sounds good" and silence do not. An agent's pick is a `proposal` until the user confirms it. When answers go in circles, step back and say what is unsettled.
3. **Nonstop after the front batch.** Run to `finalize`, then present the deferred question block.
4. **Ledger everything.** Decisions, questions, answers, plan changes (with reason and authority), review findings, gate results and skips go through `railguard log`. Never edit `.rigor/ledger.yaml` by hand; the hash chain will fail.
5. **Always written.** The plan is a file. Chat shows a short summary and the deferred block, not the plan.
6. **Deliverable is the written plan under `.rigor/plans/`.** Do not edit product code, commit, push, create worktrees, or spawn implementers; docs are planned as tasks and written by `execute-rigorously`. Planning writes no file outside `.rigor/`. This is detective, not preventive: `start` snapshots the working tree and `check` diffs it. Say so plainly if asked.
7. **Scope is conserved.** Every ideal-state gap maps to a task. Words like mvp, v1, later, stretch are linted out of titles and acceptance. Staged shipping is the user's own call, recorded as a user decision when they ask for it; the planner never proposes a cut.
8. **Everything is tracked with the to-do tool.** `RG todo <plan>` lists stages, phases, tasks and checkpoints with their status; keep the widget in step with it.
9. **Ask one question first.** When a request has two plausible meanings and the wrong one costs more than a minute, ask one question before acting.
10. **Long commands run teed and detached.** Any command over about 60 s pipes output through `Tee-Object <log>` ending in a `DONE` line, runs detached via `Start-Process pwsh -WindowStyle Hidden -PassThru`, then the log is read with `Get-Content`, because a service restart kills foreground and background calls.

## The script

One engine, five planning verbs (the sibling skill adds `exec`, in `scripts/rigor_exec.py`). `<skill-dir>` is this skill's directory. Run it through uv so the Python version is pinned by `pyproject.toml` (one file for both skills; there are no runtime dependencies, so plain `python` also works). Shorthand below: `RG` = `uv run --no-dev --project <skill-dir> python <skill-dir>/scripts/railguard.py`.

```
RG start <slug>          # .rigor/, state, snapshot, codegraph init+sync
#   resume after user-authorized changes: start <slug> --rebaseline --rebaseline-reason "why"
RG check <plan> [--final]
RG log "<reason>" --kind K --authority user|system|rule:<id>|finding:<id> [--subject S] [--plan P]
RG render <plan> [--questionnaire]  # markdown view, recorded hash; --questionnaire writes the open questions for someone else to answer
RG publish <plan> [--yes] # GitHub issues via gh; dry run without --yes
RG todo [plan]           # rows for the to-do tool: status kind id title parent
RG clarify <verb>        # internal clarifying stage; the agent runs it, never the user
RG check --pack           # self-check of this skill
```

Developer tests: `uv run --project <skill-dir> pytest`. Exit codes: 0 ok, 1 gate failed, 2 refused (existing incomplete plan, bad arguments), 3 needs a user decision (duplicate issue). Plans live in `.rigor/plans/<slug>.plan.yaml` next to `spec.yaml`; evidence files in `.rigor/evidence/<proposal id>/<tool>.md`.

## Stages

Read `references/pipeline.yaml` for the full rails. Do the stage, pass its gates, advance. A stage is done when its gates show `passed` in `railguard check` output.

| Stage | Output | Gates |
|---|---|---|
| route | tier (`references/tiers.yaml`), plan type, `start` | G_existing_plan, G_route |
| ground | parallel research; every library, API, version, approach or behavioural claim registered in `plan.proposals` | G_ground, G_delegates_closed |
| clarify | automatic when the fog test fails (destination not statable in one sentence, or first three decisions not precise): destination signed, chart signed, tickets of type research or grilling, resolved, closed into the intent | G_clarify |
| ask | breadth-first question rounds (`references/questions.yaml`); restate intent (outcome, user, why now, success, constraint, out of scope) and get an explicit yes | G_questions, G_intent |
| audit | independent proposal audit (`references/audit-tools.yaml`) | G_audit |
| requirements | `spec.yaml` (what and why, no file paths, anchors for code); ideal state and gaps | G_requirements, G_scope |
| evidence | claims, 2+ candidate paths, one chosen, affordances, one owner task per claim | G_evidence |
| plan | phases containing tasks, vertical slices, CPM order, checkpoints; each planned doc has a task that writes it | G_tasks, G_sediment, G_order, G_tier2 |
| review | routed independent reviewers (`references/routing.yaml`) | G_review |
| finalize | `check --final`, `render`, `publish --yes`, deferred block | G_ledger, G_no_impl, G_render, G_publish |

Manual gates (G_ground, G_delegates_closed, G_existing_plan) are recorded with `log --kind gate --subject G_x --status passed`. A gate may be skipped only with a reason and authority `user` or `rule:<id>`; `check` prints the skip so nothing is silent. Rule text and fixes: `references/lint-rules.yaml`, gate definitions: `references/gates.yaml`.

## Working rules

See `references/working-rules.md`.

## Finish

Run `check <plan> --final` until it reports OK (all gates passed, no errors), set `meta.status: final` in the plan, then `render` (it records the final plan hash that `exec start` requires), then `publish --yes`. Reply with: where the plan is, tier, task and phase counts, the critical path, and the **deferred question block** from the plan (open questions, each with options, a recommendation, and the tasks it blocks). Do not paste the plan. Do not start implementation; if `execute_authorized` is true, say that `execute-rigorously` can now be run (it will ask for the feedback commands and delivery mode), otherwise ask.

## Reference map

- `references/limits.yaml` every number both skills use; change them there
- `references/pipeline.yaml` stage rails and boundary
- `references/tiers.yaml` tiers, risk signals, sizes, definition of done
- `references/gates.yaml`, `references/lint-rules.yaml` what is checked and how to fix it
- `references/questions.yaml` question filters, batching, owner-decision axes
- `references/routing.yaml` who plans, who reviews, re-review levels
- `references/audit-tools.yaml` independent audit tools and evidence rules
- `references/merge-ledger.yaml` where every rule of the source skills went and why
- `references/working-rules.md` authority, tier floor, scope, sediment, GitHub, existing plans