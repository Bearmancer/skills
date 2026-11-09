---
name: execute-rigorously
description: "Executes a finished, gated plan produced by plan-rigorously: fresh git worktree and branch, dependency order, red-before-green evidence per task, bounded retries, phase checkpoints, whole-branch independent review, evidence-path closing, all hash-chained in a ledger. Use ONLY when the user explicitly asks to execute or implement a rigorous plan, or says execute-rigorously, AND the plan is final and execution was authorized. An @-mention is not a request. Not for creating or changing a plan (use plan-rigorously)."
---

# execute-rigorously

Same method as `plan-rigorously`: YAML rails, a script that enforces what it can, one ledger. Execution ends at `finish`. It never edits the plan, never touches the main checkout, never pushes or merges unless the user chose that.

**The user invokes only `plan-rigorously` and `execute-rigorously`.** Everything else below is machinery the agent runs by itself; never ask the user to run a verb or name a stage.

## Entry

1. Confirm the request is explicit: an @-mention or passing reference to this skill is not a request to execute a plan. Ask one question to confirm intent before starting.

## Contract (hold on every stage)

1. **No assumptions.** A ruling is allowed only where the spec or plan already decides the answer. Anything else is a question; independent tasks continue, dependents are blocked.
2. **Ask once, in a batch, with the question tool** (`references/exec-questions.yaml`): feedback commands, what happens to the finished branch, topology, dirty checkout. Then run nonstop. Only the listed stops interrupt a run: destructive or irreversible operation, security-sensitive action, side effect outside the worktree, a plan so broken every path is a guess.
3. **Ledger everything.** The script logs what it does. You log rulings with `log --kind decision` (reason starts `Ruling`, authority `finding:<id>` or `rule:<id>`, include the cost if wrong). Never hand-edit `.rigor/ledger.yaml` or `.rigor/exec/run.yaml`.
4. **Evidence, not claims.** A task is done only when `exec vtask` ran its verify commands green on the exact content committed, and (for test-first plans) `exec red` recorded a failing run first.
5. **Scope is conserved.** Only planned files change. Something noticed elsewhere is recorded (`exec noticed`) or follows up (`exec followup`), never edited. Placeholders, skipped tests and stubs are blockers.
6. **Detective, not preventive.** `exec check` re-reads the main checkout and the worktree diff. Say so plainly if asked.
7. **Everything is tracked with the to-do tool.** `exec todo` prints a row per phase, task, checkpoint, verifier, review, final item and delivery step (`status kind id title parent`); keep the widget in step with it.
8. **Long commands run teed and detached.** Any command over about 60 s pipes output through `Tee-Object <log>` ending in a `DONE` line, runs detached via `Start-Process pwsh -WindowStyle Hidden -PassThru`, then the log is read with `Get-Content`, because a service restart kills foreground and background calls.

## The script

`RG` = `uv run --no-dev --project ../plan-rigorously python ../plan-rigorously/scripts/railguard.py` (plain `python` also works; the one `pyproject.toml` lives in the sibling `plan-rigorously`). All verbs below are `RG exec <verb>`.

```
todo                         # rows for the to-do tool
start <plan> --feedback "<cmd>" [--feedback ...] --delivery branch|squash-merge [--away] [--allow-dirty] [--topology inline|subagent]
verify --baseline            # once, before any task; later: verify (new failures vs baseline)
next                         # ready tasks, held checkpoints
task <id> --status started|done|failed|blocked [--agent ID --report TEXT --signature S --output TEXT --harness --reason R]   # subagent topology: --agent required on start
red <id> --cmd "<failing test cmd>" [--expect-exit N]   # must fail with an assertion exit code (1); other codes look like harness errors
vtask <id>                   # runs the task's verify commands, binds evidence to content
checkpoint <CP id> | final <FV id>
verifier <phase-end CP id | branch> pass|fail --agent NAME [--note T]   # fresh independent verifier attests
answer <Q id> --text T [--unblock]       # the user answers a question queued while away
claim <C id> --status established|limited|refuted --note "..."
review <role> approve|reject [--note "..."] [--accept-best]   # --accept-best: user accepts the best version after the round cap
amend <task> --index N --text "..." --reason R --evidence E --authority user   # only the user
followup "<text>" [--file F] [--status open|done|reported] | followup --settle N --status done|reported | noticed "<text>"
check [--final] | finish [--remove-worktree] | discard --reason R
```

Exit codes: 0 ok, 1 gate or verify failed, 2 refused. `RG check --pack` also validates the execution rules, gates and merge ledger.

## Stages (`references/execute.yaml`)

A stage is done when its gates show `passed` in `railguard check` output.

| Stage | Do | Gates |
|---|---|---|
| prepare | front batch, `exec start`, `exec verify --baseline` | GX_start, GX_run |
| implement | loop `next`, dispatch (`references/exec-routing.yaml`), `red`, implement, `vtask`, `task done` | GX_tasks, GX_scope |
| checkpoint | `exec verify` (feedback commands) then `exec checkpoint` at every phase end, then a fresh verifier subagent re-runs the checks and `exec verifier <CP> pass`; later phases wait for both | GX_checkpoints |
| review | independent whole-branch review, one fix pass, re-review sized to the change | GX_review |
| close | `final` items, a fresh verifier on the whole branch (`exec verifier branch pass`), close every claim, settle follow-ups and amendments, answer queued questions | GX_close |
| finish | `check --final`, `finish`, then any authorized delivery | GX_ledger |

## Rules that bite

See `references/working-rules.md`.

## Finish

`exec check --final` until it reports OK (all gates passed, no errors), then `exec finish`. Reply with: branch and where it lives, tasks done and blocked (with gaps), what the final verification and claims showed, **Rulings I made**, noticed items and follow-ups, and what delivery step awaits the user. Blocked tasks make this a partial delivery; say so, never claim success. Do not paste diffs.

## Reference map

- `../plan-rigorously/references/limits.yaml` every number (retries, thresholds, caps, review rounds, timeouts) for both skills; change them there
- `references/execute.yaml` stage rails, start conditions, single-loop authority
- `references/exec-gates.yaml`, `references/exec-lint-rules.yaml` what is checked and how to fix it
- `references/exec-routing.yaml` executor topology, briefs, verifier, retries, reviewers, adversarial classes
- `references/exec-questions.yaml` front batch, stops, rulings, questionnaires
- `references/exec-merge-ledger.yaml` where every rule of the 13 execution source skills went and why; each of the 11 conflicts carries the user's decision
- `references/working-rules.md` start conditions, docs, drift, refusal, topology, retries, verification, delivery, away mode