# Q0: maximalist question sweep, then no stopping

Contract: gates, CLI and the state machine are in ../SKILL.md. Q0 is the only phase that asks the user anything. It sits inside P0 (before `G0` can pass) and it is the whole interview: when its questions are over, the run does not stop again until `next` prints `DONE published`.

Why front-load: a question asked at P3 interrupts a run that already spent its evidence budget, and a fork discovered late gets answered by whoever is nearest. Asking everything first costs the user one focused sitting and buys an unattended run.

## 1. Open

1. First user-visible line: `RIGOROUS-PLANNING MODE ENABLED!` (under another mode's mandated first line, print that line first and this marker on the next line).
2. State the working contract once, in your own words, with all of: you are the planner and will not edit product code or start implementers, ever, in this run; approval authorizes the plan, never execution; the order of what follows (orientation read, the sweep, then an unattended run through evidence, design, tasks, review and publish); and that after the last Q0 answer you will not ask again, so anything the user wants a say in must be raised now.
3. Announce the intent verdict in one line: `Intent: CLEAR|UNCLEAR, review default-on|declined, renderer <batch|one-by-one|examples-first>`. CLEAR = the user knows the outcome and the open items are preferences. UNCLEAR = the outcome itself is fuzzy; run the sweep with the examples-first renderer for `outcome` and `scope` (`methods/stance.md`), never a blank-page demand. Genuinely on the fence: treat as CLEAR. A user who says "interview me" gets one-by-one with every owner-decision asked and no defaults adopted silently.
4. If a fuzzy outcome makes the destination unstatable even after examples, that is unknowns: `init --map` and `phases/W0-map.md`.

## 2. Orient (one bounded wave)

Run `init` first (the sweep is on by default; `--no-sweep` only for a throwaway plan) so the ledger exists to record into. Then read enough to ask informed questions and to avoid asking anything the repo can answer: manifests, entry points, tests, existing plans, `GLOSSARY.md`, ADRs, and the git state (record unrelated dirty paths as a `dirty-worktree` fact; they stay out of scope). Use the discovery tiers in `methods/delegation.md` (LSP, then ast-grep, then rg). One wave, no lanes, no external research: this is not P2. Record the destination as the first decision (1-2 lines). Every discoverable answer found here becomes a cited fact, never a question.

## 3. Inventory: ask or scope out, per category

Walk all ten categories. Each category ends as at least one `q0-<category>[-<slug>]` question, or one `q0-<category>` **decision** whose text starts `scoped out:` and gives the reason. Silence is not a scope-out. `G0` fails until every category has one of the two and no `q0-*` question is still open (`q0Errors`).

| Category | Cover (ask each that applies; one question per independent fork) |
| --- | --- |
| `outcome` | what ships; the user's words for success; why now; the six intent fields (outcome, user, why now, success, constraint, out of scope) |
| `users` | every consumer of the result (people, programs, agents); how each uses it today and after; the ideal-state rows and the gaps |
| `scope` | explicit IN and OUT lists; deferred items; topology of 1-6 components; adjacent features that stay out unless asked; the repos involved (each registered with `repo`), existing plans to assimilate and chats to purge (`methods/multi-repo.md`) |
| `constraints` | budget and paid-service spend; mandated stack; scale and capacity; audience and compliance; deadline; compatibility floors |
| `risk` | irreversible, destructive or safety-critical forks; data and schema shape; public config surface; external dependencies and pinned versions; rollback appetite |
| `verification` | test strategy (TDD, tests-after or none; agent QA is always included); the real surface to prove behaviour on; evidence bar; plan-review depth |
| `execution` | who executes and how (`ulw-execute`, a worktree path, `--make-pr`, `--ship`); commit policy; tracker and ticket drafts |
| `parallelism` | whether parallel workers are allowed; max concurrency; isolation (worktrees); categories or models to prefer; any worker spend cap |
| `authorization` | the standing authorization (section 5) and the list of owner-decisions it does not cover |
| `done` | definition of done; the WHEN-TO-STOP line; what a human must still look at; an explicit last question: "anything I have not asked that would change the plan?" |

Maximalist means: if you cannot tell whether the user owns a fork, ask. Skip only (a) what evidence answers, and (b) a fork the ideal state for the affected user settles with no owner-decision attached; record (b) as a `decision` with its reason. Owner-decisions always survive as questions: anything irreversible, destructive or safety-critical, and any cross-cutting choice the user lives with (public config, distribution, external dependency, schema, real spend, scale target, audience or compliance limit).

Each question carries a recommended default (`--recommend`, listed first) and a WHY line: what you explored, why it did not settle the fork, and which part of the plan forks on it.

## 4. Ask, classify, close

1. `round --asks ...` for the whole inventory (Q0 questions are ready together unless one truly depends on another's answer; use `--blocked-by` only then), then `ask --slug S`; call the harness question tool with the exact JSON. The tool takes 1-4 questions per call: send the inventory in as few consecutive calls as that allows, with no other work in between, and no prose questions (if the tool is unavailable, record a blocker).
2. Record each answer with `answer`. Classify every reply fresh with the four states in `methods/stance.md` (RESOLVED, RESOLVED_BUT_UNINFORMED, UNRESOLVED_PROGRESS, UNRESOLVED_BLOCKED) and re-render only the forks that are not resolved. "You decide" on a fork resolves it to the recommended default: answer with `default: <recommendation> (delegated)`.
3. The closing call restates the destination, the scope IN/OUT, the topology and the six intent fields in a few lines and asks for the yes. Record it with `intent --confirm --by user` only after the explicit yes.
4. Run the doubt loop (next subsection). Fold every new scope item its answers introduce into the inventory and ask the new forks in a follow-up call.
5. Record the standing authorization and the `autonomy` decision (section 5), then `gate --id G0`. Fix every `sweep:` error. `next` prints the open sweep line while categories are uncovered.

### The doubt loop (the last thing Q0 does)

**Concept.** A doubt is anything you would otherwise have to guess: a fork the inventory missed, an assumption you are about to make, a term you read two ways, a risk you cannot rate. The category sweep asks what you can think of; the doubt loop asks for what you cannot, by handing the floor back to the user until they have none left. It is a loop because one answer often exposes the next doubt, and the user's explicit statement closes it, never a round count, a timeout or silence.

**Round.**

1. Restate your current understanding in five lines or fewer: outcome, scope IN and OUT, the constraints and risks recorded, and the assumptions you would make if nothing more is said. Add the single weakest point ("what would make this plan wrong?") and lead with the hardest unanswered question, not the easiest.
2. Ask `q0-doubt-<n>` through the question tool with the options "No remaining doubt" (recommended only when the restatement is accepted unchanged) and "I have a doubt" (free text).
3. Fold a doubt in at once: a new `q0-*` question or decision, a corrected decision (`supersede` with a reason), or a scope change. Then round n+1 restates the changed understanding.
4. The loop ends when the latest round is answered with a reply that starts with "No remaining doubt". A later doubt reopens it, because `G0` reads only the highest-numbered round.

**Enforced.** `G0` fails unless the rounds are numbered 1..n without gaps, every round is answered, and the last answer starts with "No remaining doubt" (case-insensitive). `next` prints the label to ask. Once it passes and `autonomy` is recorded, the run does not stop again.

**Not the doubt cycle.** The doubt cycle in P3 (`doubt`, `finding --review doubt:...`) is an adversarial review of one irreversible decision by a fresh reviewer. The doubt loop is a conversation with the user about everything, once, at the start.

## 5. Standing authorization (what makes the rest unattended)

The `q0-authorization` question offers, recommended first:

- **Run through** (default): "Plan to publish without asking me again. I pre-approve the design (`approve-design`), the task graph (`approve-task-graph`) and publishing with any non-converged review findings listed in the plan. The owner-decisions I answered here stand."
- **Checkpoints**: stop for design approval and task-graph approval as the pipeline defines them (`phases/04-design.md`); those two approvals are then the only later questions, asked as an `Approval` question with `required: true`.

On run-through, record `decision --label autonomy --decision "run-through: <the reply summary>"` (the label and first word are checked: `run-through` or `checkpoints`; `G0` fails without it and, for run-through, without an answered `q0-authorization` question), keep the user's reply verbatim, and use that exact quote for `approve --gate G3 --token approve-design --by user --quote "<the reply>"`, `approve-capability-map` when a map exists, `approve --gate G4 --token approve-task-graph ...`, and the escalation tokens if the doubt or review cap is hit. The quote is the user's own words given up front; the agent still never invents one. `approve` enforces it: under run-through, a `--quote` that does not contain the `q0-authorization` answer verbatim is rejected. On checkpoints, record `autonomy` = `checkpoints` and ask at the two gates.

## 6. After Q0: run to publish, do not stop

Between `G0` and `DONE published`, the turn does not end on a question, an approval wait or a summary. Drive with `next` after every command and do the work it names. The tool-only rule still holds: no prose questions, because there are no questions left to ask.

A fork that appears after Q0 never stops the run:

1. Evidence can answer it: record the fact and move on.
2. It is a preference or tradeoff: record `decision --label default-<x>` with the chosen default, why, and how to reverse it. It is listed in the TL;DR under "Decisions I made for you".
3. It is an owner-decision Q0 missed (irreversible, destructive, safety-critical, spend): do not ask and do not guess the dangerous branch. Plan the safe, reversible branch, mark the decision `--irreversible` (so the doubt cycle runs), and add a first task `owner-confirm-<x>` (a root task with no `deps`; `G4` requires one per irreversible decision outside Q0 under run-through) that every dependent task lists in `deps`; its acceptance is the user's explicit yes at execution time. The plan carries the question; the planning run does not.
4. The review or doubt cap is hit without approval: under run-through the standing authorization covers the escalation token; the outstanding blockers are recorded as `risk-*` decisions and listed in the TL;DR, and the plan publishes. Under checkpoints, ask.

A genuine impasse (the harness question tool is down, a required file is unreadable) is recorded as a blocker with the exact command that failed; it is the only legal reason to end the turn early.

The plan review is not a question and not a Q0 item beyond its depth: after `G2`, `next` prints `plan-review --cycle 1` as the required action. Spawn the fresh-context reviewer, persist its findings, and continue; nobody is asked whether to run it. `--no-plan-review` at init is the only opt-out.

## 7. Failure modes this phase prevents

- A `q0-*` question left open: `G0` names it.
- A category skipped without a reason: `G0` names the category.
- "Ask few questions" reflex: the inventory is judged against the table above, not against the user's patience; the user can always answer "you decide" per fork.
- A late irreversible fork silently adopted as a default: section 6 item 3.
