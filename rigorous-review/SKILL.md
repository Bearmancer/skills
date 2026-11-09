---
name: rigorous-review
description: "Perform, request or receive code review (--mode=axes|gate|request|receive); feedback is verified against the codebase before implementing."
---

# Review

The super-union of `code-review` (Matt, two-axis), `code-review-and-quality` (Addy, five-axis), `requesting-code-review` + its reviewer template (Superpowers), `receiving-code-review` (Superpowers), OMO `review-work` (manual QA + one gate reviewer), OMC `review` (two axes run apart, configured quality gates), and the OMC `code-reviewer` agent (severity+confidence, modes). The full union matrix — every feature, its source, and where it lives here — is in [references/feature-union.md](references/feature-union.md). Checklists are in [references/checklists.md](references/checklists.md); the dispatchable reviewer prompt is in [references/reviewer-prompt.md](references/reviewer-prompt.md).

## Mode selection — default is ALL; `--mode=<axes|gate|request|receive>` narrows

Invocation form: `rigorous-review [--mode=<mode>] [fixed point | PR | feedback]`.

**No flag = run the full union.** Every axis, every perform lane, and the full metrics roll-up that the inputs support:

1. **Two-axis lanes** (Standards + Intent, parallel, reported apart) — with the five-axis checklist (correctness, readability, architecture, security, performance), the smell baseline, SOLID/diagnostics, and the specialised checks (style/API/performance/quality-strategy) applied inside them.
2. **Manual QA matrix** on the real surface (when a runnable surface exists; when none exists the matrix is reported as UNPROVEN with the reason — never silently skipped).
3. **ONE gate reviewer** consuming the axis reports + QA matrix + context mining, issuing the gate verdict.
4. **Configured quality gates**, when the project configures any.
5. **Metrics roll-up** (see Output): findings by severity × confidence, per-axis totals and worsts, QA rows passed/total with artifact count, size class, files/lines changed, gate-lane records, time-to-verdict when known.

The only lanes a default run does not force are the input-conditioned ones: `receive` (runs only when feedback text is actually in hand — processing it is then part of the run) and `request`'s dispatch mechanics (the default run _is_ the dispatched review; there is no extra reviewer-of-reviewers). State in the first line: `mode: ALL (pass --mode=<x> to narrow)`.

| Flag (narrows to exactly this) | Job                                                                                                |
| ------------------------------ | -------------------------------------------------------------------------------------------------- |
| `--mode=axes`                  | Two-axis review only: Standards + Intent against a fixed point, reported apart, never cross-ranked |
| `--mode=gate`                  | Gate review only: manual QA matrix + ONE gate reviewer, PASSED/FAILED/INCONCLUSIVE                 |
| `--mode=request`               | Dispatch one fresh reviewer subagent for your own just-finished work                               |
| `--mode=receive`               | Process reviewer feedback that has arrived (verify → evaluate → respond → implement)               |

Rules:

- **An explicit `--mode` always wins and narrows.** Run exactly that mode's workflow — not the full union, and not a different mode. Do not add another mode's steps "for completeness".
- **Unknown mode is an error, not a prompt for interpretation**: `--mode=<anything else>` → stop and list the four valid modes plus the no-flag default. Never map an unknown value to the nearest mode.
- **Prerequisites fail visibly.** Each mode names its required inputs (axes: a resolvable fixed point; gate: goal + a runnable surface or an explicit UNPROVEN matrix; request: base/head SHAs; receive: the actual feedback text). A selected mode missing its input stops and names the missing input — it does not fall back to another mode or quietly widen into the full run.
- Modes still compose across a change's life as separate invocations (review before merge, `receive` after comments) — never blended inside one pass: a reviewer lane never authors, and the author never signs off their own work in the same context.

## Rules that bind every mode

- **Review never authors the change it judges.** Reviewers are read-only on the checkout; use `git show/diff/log`, or a separate worktree for another revision — never move HEAD on the author's checkout. A reviewer does not dispatch its own sub-reviewers; if the diff is large it reviews in passes and says so.
- **Spec/intent first, quality second.** Trivial changes (one line, typo, no behaviour change) skip the intent stage and get a brief quality pass only.
- **Discovery is for recall, reporting is for precision.** Surface every candidate finding with severity + confidence; then verify each against the callers, guards, and tests that reach the changed code and drop what they rule out. What survives verification at low confidence goes to **Open Questions** — surfaced, never silently dropped, never blocking on its own. Soft instructions ("only important issues") are ranking guidance, not a licence to pre-filter discovery.
- **Every finding**: file:line, what is wrong, why it matters, a concrete fix, severity, confidence. Zero findings is a valid result; never invent one to look thorough. Findings that pre-date the change are labelled pre-existing, separate from regressions.
- **Canonical severity** (all source taxonomies map here): `BLOCKER` (security, data loss, broken function) · `MAJOR` (must fix before merge: architecture, missing behaviour, error handling, test gaps) · `MINOR` (should fix) · `NIT` (optional style) · `NOTE` (informational). Confidence `HIGH/MEDIUM/LOW` travels with each. Verdict is set by the highest severity at HIGH confidence: any BLOCKER/MAJOR@HIGH → **REQUEST CHANGES** (gate mode: REJECT); only MINOR/NIT/NOTE → **COMMENT/APPROVE-WITH-NOTES**; clean → **APPROVE**. See the mapping table in [references/feature-union.md](references/feature-union.md).
- **Approval standard**: approve when the change definitely improves overall code health, even if imperfect and not how you would have written it. Facts and data override preference; the style guide is absolute on style; codebase consistency is acceptable unless it degrades health. "I'll clean it up later" is not accepted — cleanup lands before merge, or a bug is filed and self-assigned. Comment on code, never people; accept an author's override gracefully when they hold full context.
- **Advisory by default.** A review informs; it does not gate. Hard gates (release, security, destructive operations) stay separate and fail closed. Configured quality gates, when they exist, are the one exception — see Perform step 6.

## `--mode=axes` — two-axis review (branch / PR / diff since a fixed point)

1. **Pin the fixed point.** Whatever the user named (SHA, branch, tag, `main`, `HEAD~5`). None named → ask. Run `node scripts/review-context.mjs --fixed <ref>`: it refuses an unresolvable ref or an empty diff here, not inside the sub-agents, and emits commits, changed files, `git diff <fixed>...HEAD` (three-dot, merge-base) stats, size class, standards candidates, issue refs, spec candidates, run-command candidates, and context mining (recent history per file, TODO/FIXME/HACK warnings). For PRs/branches under review, do this from a dedicated review worktree (`git worktree add <path> <branch>`, then `git worktree lock <path> --reason "review:<pr>"`); the main worktree stays read-only context.
2. **Find the intent source**, in order: issue references in commit messages (fetched from the tracker), a path the user passed, a spec file under `docs/`, `specs/`, `.scratch/` matching the branch/feature, else ask. No spec → the Intent lane skips and the report says "no spec available". **Find the standards sources**: every repo doc on how code should be written (`CODING_STANDARDS.md`/`CONTRIBUTING.md` must be on the list when they exist; also `CLAUDE.md`/`AGENTS.md`, `docs/standards/`). A standards file you didn't look for is a standard you didn't apply.
3. **Context mining** (from the script, kept short): recent commits and their reasons per changed file, related commits/issues/PRs by goal keywords, importers of changed modules, tests touching the same paths, docs/config referencing the changed behaviour. Record source → finding → why it matters. History that explains _why_ code is this way is review evidence.
4. **Run the two axes apart** — two fresh-context sub-agents issued in parallel (a small diff stays one pass):
   - **Standards**: the diff against the discovered standards, plus the smell baseline in [references/checklists.md](references/checklists.md) pasted in full (the sub-agent has no other access). Repo standards override the baseline; smells are always judgement calls; skip anything tooling already enforces.
   - **Intent**: the diff against the spec/task — requirements missing or partial, behaviour nobody asked for (scope creep), requirements implemented wrong. Every finding quotes its spec line. For behaviour the spec is silent on, judge by what a reasonable user of this software would expect; silence is not permission.
     Each brief stays under ~400 words, pointed at one axis only.
5. **Verify and aggregate.** Run each candidate finding through the verification rule above (callers/guards/tests; mutation probe where a test's value is in doubt — invert one condition the change adds, run the suite, restore from a copy; a mutation that stays green is a finding naming the missing test). Present the two reports under `## Standards` and `## Intent`, cleaned but not merged and **never cross-ranked** — a change can pass one axis and fail the other, and picking a single winner across axes is exactly what the separation prevents. End with per-axis totals and the worst issue _within each axis_.
6. **Configured quality gates (only when they exist).** If the project configures gates for this review stage, run each as an independent lane on the same diff (never passing it another lane's output), record `{gate, mode, verdict}` per gate, show validation errors, treat an unavailable gate as `gate_unavailable` with a visible warning (never PASS, never blocking), and let a blocking `BLOCK` turn the overall result into REQUEST CHANGES. No configured gates → no gate section, no gate calls, nothing added.
7. **Opt-in slop lane.** Only when asked: an `ai-slop-cleaner`-style pass for dead code and duplication, reported as its own lane. After any refactor, list orphaned code explicitly and ask before deleting it — never silently delete what you are not sure about.

## `--mode=gate` — gate review (finished work, pre-PR handoff)

1. **Gather**: GOAL (the original request), CONSTRAINTS, BACKGROUND, CHANGED_FILES, DIFF, neighbouring files showing established patterns, RUN_COMMAND (detect from `package.json`/`Makefile`/`docker-compose.yml`, else ask one focused question), CONTEXT_MINING (step 3 above). Extract from the conversation first; ask only if truly missing.
2. **Manual QA — you, on the real surface, never delegated.** Reuse fresh evidence for this exact tree if it exists; a fix after a capture stales it. Pick the channel that faithfully exercises the surface: HTTP (`curl -i`), CLI/TUI (real pty transcript), web (browser session + screenshot), desktop (OS automation + screenshot), library/SDK (exercising script transcript), data-shaped work (the artifact itself, diffed/dumped). Cover at least: the happy path the goal names, the riskiest edge (empty/boundary/malformed/concurrent), one adjacent regression, and a row per stated success criterion. Build the QA matrix — `# | Scenario | Exact command/action | Expected | Observed | Verdict | Artifact`. A row without an artifact is not PASS; an app that cannot start is an immediate FAIL. **Any FAIL ends the review here**: report REVIEW FAILED with the failing rows and skip the reviewer; fix, then re-enter at step 1 on the delta.
3. **ONE gate reviewer** (never a panel — widen its brief instead), dispatched fresh with goal, constraints, background, diff, file contents or paths, context mining, and the full QA matrix ([references/reviewer-prompt.md](references/reviewer-prompt.md) carries the brief). It breaks the goal into sub-requirements (ACHIEVED/MISSED/PARTIAL, implied ones included), checks every constraint, traces representative + edge scenarios, audits each QA artifact, and may only block on a cited goal item, constraint, or QA row it can prove fails — everything else is a NOTE. Style preference and hypothetical futures do not block.
4. **Collect honestly.** Timeout, ack-only, or empty ≠ APPROVE. Silence past the follow-up → lane INCONCLUSIVE, respawn one smaller reviewer once; still nothing → close it, keep INCONCLUSIVE, and name the incomplete lane. Lane verdicts are stored separately (Manual QA PASS/FAIL; Gate APPROVE/REJECT/INCONCLUSIVE). Tear down the review worktree only after the reviewer is terminal (`git worktree unlock` then `remove`); a crashed review leaves the locked tree as the recoverable marker.
5. **Verdict logic**: QA clean **and** APPROVE → **REVIEW PASSED**. Any QA FAIL **or** REJECT → **REVIEW FAILED — criteria not met** (failing rows first, then blockers deduplicated in fix order, each with its pointer and exact fix). INCONCLUSIVE with nothing failed → **REVIEW INCONCLUSIVE — not approved**. A re-review after fixes is a fresh pass on the delta plus affected QA rows, with a NEW reviewer — never a followup to the previous one.

## `--mode=request` — dispatch a reviewer for your own finished work

Mandatory: after each task in subagent-driven work, after a major feature, before merge. Valuable: when stuck, before a refactor (baseline), after a complex bug fix.

1. Capture `BASE_SHA=$(git merge-base origin/main HEAD)` (or `HEAD~1`) and `HEAD_SHA=$(git rev-parse HEAD)`.
2. Dispatch one fresh general-purpose sub-agent with [references/reviewer-prompt.md](references/reviewer-prompt.md), filling DESCRIPTION (what was built), PLAN_OR_REQUIREMENTS, BASE_SHA, HEAD_SHA. Precisely crafted context — **never your session history** (the diff and the evaluation live in the reviewer's context; only findings come back to yours).
3. Act on the result: BLOCKER immediately, MAJOR before proceeding, MINOR noted for later. Reviewer wrong → push back with technical reasoning and code/tests, per Receive below.

## `--mode=receive` — reviewer feedback arrived

**Pattern: READ (all of it, without reacting) → UNDERSTAND (restate in your own words, or ask) → VERIFY (against this codebase) → EVALUATE (technically sound here?) → RESPOND (technical acknowledgment or reasoned pushback) → IMPLEMENT (one item at a time, test each).** Verify before implementing; technical correctness over social comfort.

- **Unclear feedback stops everything.** If any item is unclear, implement nothing yet and ask about the unclear items — items may be related, and partial understanding is wrong implementation. ("I understand 1, 2, 3, 6. Need clarification on 4 and 5 before proceeding.")
- **Never performative**: no "You're absolutely right!", "Great point!", "Let me implement that now" (before verification), and no gratitude expressions at all. Instead: restate the technical requirement, ask a specific question, push back with reasoning, or just fix it and show the code ("Fixed. [what changed, where]").
- **Source matters.** From your human partner: trusted — implement after understanding, still ask if scope is unclear, skip to action. From external reviewers, check before implementing: technically correct for _this_ codebase? Breaks existing behaviour? Why is the current implementation this way (legacy/compat)? Works on all platforms/versions? Does the reviewer hold full context? If it conflicts with your partner's prior decisions, stop and discuss with your partner first. Can't verify → say what you cannot verify and ask how to proceed.
- **YAGNI check**: a suggestion to "implement properly" (metrics, tracking, export…) gets a grep for actual usage first. Unused → "This isn't called. Remove it (YAGNI)?" Used → implement properly.
- **Push back when** the suggestion breaks functionality, the reviewer lacks context, it violates YAGNI, it is technically incorrect for this stack, legacy/compat reasons exist, or it conflicts with settled architecture — with technical reasoning, specific questions, and working code/tests as evidence; architectural conflicts go through your human partner. If you pushed back and were wrong: "You were right — I checked X and it does Y. Implementing now." Factual, brief, no apology theatre.
- **Implement in order**: blocking (breaks, security) → simple (typos, imports) → complex (refactors, logic), testing each fix individually, then a regression check. On GitHub, reply in the review thread (`gh api repos/{owner}/{repo}/pulls/{pr}/comments/{id}/replies`), not a top-level PR comment.

## Output (all modes; a narrowed `--mode` reports its own slice)

The last message is the deliverable — never a content-free sign-off. It contains: scope (fixed point, commits, files, lines + size class), what was checked and found clean, findings most-severe-first per axis/lane (each file:line + scenario + fix + severity + confidence), Open Questions (low-confidence survivors), Declined-to-judge (behaviours considered and set aside, one line each with the reason — nothing set aside is dropped silently), QA matrix + configured-gate records (gate mode / when configured), positive observations (specific, accurate), and the verdict with one-or-two-sentence reasoning. Split recommendation when the change is too large (~1000+ changed lines, or a diff growing an already ~1000-line file): name the splitting strategy (stack, by file group, horizontal, vertical) instead of pretending to have reviewed it properly.

Persist the final report to `./.rigor/reviews/<slug>/review.md` when a file is requested; otherwise the last message remains the deliverable.

**Metrics roll-up (always in a default ALL run; the relevant rows in a narrowed run):**

| Metric                                                                                   | Source                        |
| ---------------------------------------------------------------------------------------- | ----------------------------- |
| Findings by severity (BLOCKER/MAJOR/MINOR/NIT/NOTE) × confidence (HIGH/MED/LOW)          | all lanes, after verification |
| Per-axis totals + worst finding within each axis (never cross-ranked)                    | Standards, Intent             |
| QA rows passed / total, artifacts present / required                                     | manual QA matrix              |
| Gate verdict + confidence; configured gates `{gate, mode, verdict}`                      | gate lane / project config    |
| Size: files changed, lines added/deleted, size class (~100 good / ~300 ok / ~1000 split) | `scripts/review-context.mjs`  |
| Coverage notes: behaviours checked-clean, could-not-assess list                          | all lanes                     |

A metric that could not be produced is reported as such (e.g. "QA: UNPROVEN — no runnable surface"), never omitted to make the roll-up look complete.

## Rationalizations that end reviews badly

| Excuse                                                  | Reality                                                                                                                                                    |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "It works / tests pass, that's enough"                  | Tests do not catch architecture, security, or readability failures. The axes exist because each misses what another catches.                               |
| "I'll review the diff myself instead of dispatching"    | Your context is for driving the work. The reviewer's fresh context is the point — findings come back, the diff stays there.                                |
| "The reviewer needs my session history"                 | Hand precisely crafted context. History puts the reviewer on your thought process instead of the work product.                                             |
| "Only flag the important stuff"                         | Discovery is recall: flag everything with severity+confidence. Filtering is the consumer's stage — after verification, not instead of it.                  |
| "LGTM" (to be agreeable / quick)                        | A rubber stamp without evidence helps no one and softening a production bug into "a minor concern" is dishonest. Quantify, or say what you did not assess. |
| "Implement the reviewer's suggestion, they reviewed it" | Verify against this codebase first. Reviewers lack context and are sometimes wrong; one-at-a-time, tested, or it is blind implementation.                  |
| "Thanks, great catch!"                                  | Actions speak. State the fix and its location.                                                                                                             |
| "We'll split / clean it up later"                       | Later rarely comes. Split before review, cleanup before merge, or a filed bug with an owner.                                                               |
