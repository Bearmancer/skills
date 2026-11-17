# Review

Load this when the plan is drafted and you are ready for independent review. Two reviewers who have never seen your reasoning read the plan and try to break it. Only after that does the user approve.

## Before you spawn anything

The drafted checkpoint must pass first (plan-format.md). If a reviewer spawn is blocked, the message lists the gaps. Fix them and spawn again. Do not reword the prompt to get past a block.

## How to spawn

- Spawn both reviewers: one soundness, one completeness. Two separate agent calls, both in one message so they run at the same time. Never put one reviewer's output in the other's spawn prompt; `## Review` is part of the frozen plan each reviewer sees. Do not change the plan outside `## Review` between the two spawns: the second reviewer would get a different frozen copy, and a change to behaviours or criteria opens a new round.
- Spawn under the subagent rule in SKILL.md (explicit `model`, no Fable, no `inherit`, no fork).
- The prompt must contain its marker on a line by itself, exactly as written below. The marker is how the system knows this is a review and freezes the plan for it.
- A spawn is recorded when it starts, not when it finishes, and any agent type counts. The system cannot tell whether the reviewer read the plan or returned anything, so never spawn one just to fill a slot.
- Give the reviewer nothing from yourself: no summary, no explanation, no hint about what you worry about. Copy the prompt below as is, with one allowed change: replace `.rigor/state/snapshot.md` with its absolute path (the project root followed by `/.rigor/state/snapshot.md`), so it opens wherever the reviewer starts.
- Reviewers only read. They do not edit any file. (Not checked by the system.) They open the frozen copy with the Read tool, never a shell command (shell commands naming it are blocked). The prompts below say so.

## Prompt: soundness

```
rigor-review: soundness

You are an adversarial reviewer. Your job is to find what is wrong with a plan. Assume its author is overconfident. Do not validate. Do not summarise. Do not praise.

Open the file .rigor/state/snapshot.md with the Read tool, not a shell command. That is the frozen plan. Do not edit any file. Report findings only. Read nothing the planner wrote elsewhere, and do not ask the planner anything. You may read the project's code and use the web to check statements.

Lens: soundness. Would building exactly this plan produce what the Intent asks for, safely? Look for:
- behaviours or criteria that contradict each other, the Intent, or its Out of scope line
- criteria that cannot be observed or tested as written (vague words, no number)
- tasks that do not actually achieve the criteria they cover, or are in the wrong order
- Verify commands that do not exist, would not detect failure, or check the wrong thing
- hidden coupling, shared state, or an interface change that breaks callers
- a design that is shallow or leaks detail, or a migration that could fail halfway
- security or data-loss risk the plan does not address
- claims that are wrong when you check them yourself

Also flag any factual claim in the plan (about a library, an API, a version, existing code or a command) that is not listed under ## Claims.

Report findings as a list. Each finding is one line:
- [blocker|major|minor] "exact text quoted from the plan" -- what is wrong and why it matters

blocker: the plan cannot work or is unsafe as written. major: it would give wrong behaviour or cause real rework. minor: unclear or inconsistent but the result is the same.
Every finding must quote the plan. If you find nothing after careful reading, say exactly: No findings.
```

## Prompt: completeness

```
rigor-review: completeness

You are an adversarial reviewer. Your job is to find what is missing from a plan. Assume its author is overconfident. Do not validate. Do not summarise. Do not praise.

Open the file .rigor/state/snapshot.md with the Read tool, not a shell command. That is the frozen plan. Do not edit any file. Report findings only. Read nothing the planner wrote elsewhere, except GLOSSARY.md and docs/adr/, and do not ask the planner anything. You may read the project's code and use the web to check statements.

Lens: completeness. What would an implementer have to guess, and what would they miss? Look for:
- Intent lines (Outcome, Success, Constraint) not turned into any behaviour or criterion
- missing behaviours: error paths, edge cases, bounds (inside, at, beyond), state changes, permission and abuse cases, speed or accessibility needs
- decisions silently assumed instead of asked (look in ## Questions and ## Spec)
- things in Out of scope that reappear in the spec or tasks
- missing tasks: tests, migrations, docs, rollback, cleanup of old code, updating callers
- tasks that edit files the plan never explains, or criteria no task covers
- terms used in two senses, or terms that clash with the project glossary
- unstated assumptions about the environment, versions or data

Also flag any factual claim in the plan (about a library, an API, a version, existing code or a command) that is not listed under ## Claims.

Report findings as a list. Each finding is one line:
- [blocker|major|minor] "exact text quoted from the plan" -- what is missing and why it matters

blocker: a required behaviour or safeguard is missing. major: an implementer would likely build the wrong thing. minor: small gap, easily inferred.
Every finding must quote the plan. If a gap has nothing to quote, quote the Intent line it should have come from. If you find nothing after careful reading, say exactly: No findings.
```

## Handling the findings

**The preview rule:** findings and claims carry double quotes in the plan file. When plan text enters a question preview, replace its double quotes with single quotes. A reserved-header question with a double quote is denied before it is asked, and no answer to a question with one can be recorded (SKILL.md).

1. Write every finding into `## Review` as `F-1`, `F-2`, ... with its severity, the quote, and what is wrong. Use one id per finding even if both reviewers found the same thing.
2. Decide each one on the evidence in the plan text, not on who said it. A fresh reviewer lacks your context, so it can be wrong. A reviewer who agrees with you is not proof either.
   - Valid: change the plan, then end the line with `-> fixed`.
   - Not valid: end the line with `-> rejected: the reason`.
   - A blocker cannot be rejected by you. Ask the user with the question tool, give the finding and your reason in the preview (single quotes, per the preview rule above), and write `-> user: their decision`.
   - A real trade-off you will not fix: also ask the user. Do not accept it silently.
3. If a fix changes behaviours or criteria, the reviewers must see the new text. After any fix to a blocker or major finding, spawn both reviewers again on the updated plan. This is a new round only if a `B-n` or `AC-n` line changed; otherwise it stays in the same round.
4. A round with nothing to report is recorded as `- No findings (round 2)`, using the spec-version number (which version of the spec was just reviewed), not a count of reviewer pairs.
5. **Three rounds at most** for one plan. An amendment that changes a behaviour or criterion starts a fresh count.
   - A round is one version of the spec. Any change to a `B-n` or `AC-n` line, even a typo, is a new spec version and uses a round.
   - Edits to tasks, claims or wording outside those lines get a new frozen copy but stay in the same round.
   - After round 3 a reviewer can still run on the same spec. Once the spec changes after round 3, no more reviewers can be spawned.
   - A late spec change needs both lenses (soundness and completeness) to have reviewed the last reviewed spec. It also needs a finding with `-> user:`. The system refuses `Approve plan` without both.
   - Put open findings and any late spec change to the user first, in an ordinary question (not the `Approve plan` header). The preview lists each open finding with your recommendation (fix, accept or drop), with double quotes replaced by single quotes (the preview rule above).
   - Record the user's decision in `## Review` as `-> user: <decision>`, for example `- F-9 [minor] "B-2: While dark mode is on, a page reload shall keep dark mode on." -- spec changed after round 3 -> user: accepted`. Only then ask `Approve plan`.
   - If one lens never reviewed the last reviewed spec, open `.rigor/state/snapshot.md` with the Read tool and put the Spec lines back exactly as they are there. Run the missing review on them (the spec is the same, so it is allowed), then make the change again.

If reviewers keep finding substantial problems, the plan may not be ready. Say so in the `Approve plan` preview.

Example: a reviewer says "AC-2: After a reload with dark mode on, the page background is the dark colour." is untestable if the saved value can be cleared. You add a behaviour for a cleared value, fix the criterion, write `-> fixed`, and run round 2 with both reviewers.

## Then ask for approval

When `## Review` is not empty and every finding has a disposition, ask with header `Approve plan`.

- Option 1: "Yes, approve this plan". Put in its preview: the Intent in six lines, the behaviours, the task list with dependencies, the claims, and the review result (counts by severity and how each ended). Make it short enough to read. Use single quotes in the preview, never double quotes (the preview rule above).
- Option 2: "No, I want changes". Their change request starts another round of drafting.
- If the checks fail, the question is blocked with the gaps. Fix them and ask again.

Only an option label beginning with `Yes`, or a bare `yes`, approves. On approval the plan is frozen and you carry on into the build (after-approval.md).
