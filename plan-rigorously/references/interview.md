# Stage one: settle what is wanted

Load this when you start a full-path plan. Stage one ends when the user answers `Yes` to `Sign intent`.

## Does the interview run?

Before you ask anything, say these three things to yourself and check each one. This test is your own judgement: the system does not check it, so be honest about the anchor.

1. **Destination:** one sentence naming what will exist when this is done. ("The settings page can be shown in a dark colour scheme.")
2. **First three decisions:** the three choices that must be made first, stated precisely. ("Which pages? Follow the system setting or a manual switch? Where is the choice remembered?")
3. **Anchor:** at least one concrete thing from the user's request: a file path, a symbol, an issue number, numbered steps, acceptance criteria or an error message.

Then pick one:

| What you find | Do this |
|---|---|
| All three hold | Skip the interview. Fill each Intent line only with what the request actually says. A line the request does not answer becomes a question. Then go to `Sign intent`. |
| The anchor or the decisions are vague, but you can still name the destination | Run the interview below. |
| You cannot write the destination sentence, or the decisions fan out into several independent threads that one sitting cannot settle | Chart a decision map instead (map.md). |

Show the three items to the user in the preview of your first question (or of `Sign intent` if you skip the interview). That is the one place they see why you did or did not interview.

## Start the file

Before any question, or any command or fetch whose result you will cite (also on the skip-interview path), create `.rigor/plan.md` at the project root with `path: full`, all six section headings, the six Intent lines set to `...`, and your questions listed under `## Questions` as `[open]` or `[waiting Q-n]`. Planning writes are limited to the plan, the map, `GLOSSARY.md` and `docs/adr/`. Reading, searching and read-only commands are free.

## Run a round

A round is one call of the question tool.

1. **Find the frontier.** The frontier is every open decision whose prerequisites are already settled. A question whose answer depends on another open question waits and is marked `[waiting Q-n]`.
2. **Ask the frontier, at most 4 questions per call.** If more than 4 are ready, ask the 4 that unblock the most others.
3. **Start each question's text with its id**, for example `Q-2: Should the choice persist across devices?`. The id is how the answer is matched to the plan line.
4. **Give every question a recommended answer.** It is the first option, worded so that "yes" accepts it ("Yes, remember it on this device only"). Add 1 to 3 other options. Put the reasoning, an example and what each option costs in the option `preview` and `description`. Text above the dialog is never seen.
5. **Copy the recorded answers into the plan.** The system records the tool answer; you set the line to `[answered]` and add `-> the answer`. The checker rejects a copy with no recorded answer. Recompute the frontier. Waiting questions whose prerequisite is now answered become `[open]`.
6. Repeat until no question is `[open]` or `[waiting]`.

Do not ask for a free-text answer when two or three options cover the space. Never answer a question for the user. Never apply a default for them.

## Facts are yours, decisions are theirs

- A fact is something the project, the web or the machine can tell you: which test runner, whether the page already has a theme, what a library does. Look it up, or send a fresh agent to look it up (subagent rule in SKILL.md). If a listed question turns out to be answerable by lookup, delete its line from `## Questions`. Do not ask the user. A question still marked `[waiting Q-n]` on the deleted one is no longer waiting: mark it `[open]` (or delete it too if the same lookup answers it). Ids are never reused.
- Do not wait on the lookup. A running lookup is an unsettled prerequisite, so only the questions that depend on it wait. Ask the rest now.
- A fact that the plan will rely on becomes a claim with proof (proof.md).
- A decision is a preference, a trade-off, a scope choice or a priority. Ask it.
- When a fact makes a question pointless, say so in one line instead of asking it.

## Probing what the user really wants

- Watch for answers that sound like best practice rather than a wish: "scalable", "clean", "modern", "the standard way", "I should probably". Follow with: "If you did not have to justify this to anyone, what would you actually want?" as a question with the plausible answers as options.
- Name your hypothesis in the first question's preview and what you are least sure of. Be willing to be visibly wrong.
- "Whatever you think" is not an answer. Re-ask as a choice between two concrete options.
- When the user brings an idea rather than a task, restate it as "how might we ... for ..." and offer 2 or 3 structurally different directions as the options. Ask for the riskiest assumption last, as a question: what must be true for this to be worth building.
- Keep a "Not doing" list. Every direction the user declines goes under `## Not doing` (an extra section) and, once confirmed, into the `Out of scope` line.

## Challenge modes

Use each once, as an ordinary question, when it fits:

- Round 4 or later: **Contrarian.** "What if the opposite were true?" Test one habitual assumption.
- Round 6 or later: **Simplifier.** "What is the simplest version that is still valuable?"
- Round 8 or later, if the questions keep shifting: **Ontologist.** "Which of these things is the core, and which are just views of it?"

## Scope cuts

You may propose a cut ("I suggest leaving out the account-wide setting"). Nothing is cut until the user says so in an answer. Cuts the user confirms go in `Out of scope`. If the user cuts nothing, write that in words ("Nothing beyond the Success line; confirmed"), because the line cannot be empty or a dash.

## When the user is away

If a question has no answer yet, keep working on anything that does not depend on it: look up facts, read the code, draft behaviours that are already settled. Never fill in a default. Mark the dependants `[waiting Q-n]`. When everything left depends on an open question, stop and say plainly which questions are unanswered.

## Limits

- Soft limit at round 10: a note comes back. Offer to wrap up with what is settled.
- Three rounds in a row with no fewer open questions: a note tells you to step back. Restate what is settled, then ask what is blocking.
- Hard limit at round 20: questions are blocked. Stop asking. Tell the user in plain words what is unsettled and let them decide what to do. Their next message lifts the limit by 10.
- If after several rounds you still cannot predict the user's next answers, say so: "Something basic is missing. Want to step back?"

## Restate and sign

When the checker's conditions hold (all six lines filled, no open question, every answer recorded), write the six Intent lines in the user's words:

| Line | Holds |
|---|---|
| Outcome | what will exist or work |
| User | who benefits |
| Why now | what changed |
| Success | how anyone will know it worked, observable |
| Constraint | the binding limit |
| Out of scope | what is deliberately not being done |

Then ask with header `Sign intent`. Put the six lines in the preview of the first option, with single quotes instead of double quotes. First option: "Yes, this is the intent". Second: "No, I want to change something". Only an option label beginning with `Yes`, or a bare `yes`, counts. "Sounds good" typed under Other is not a yes: ask what they would refine.

After the signature, do not edit the Intent. Any change to those six lines cancels the signature and returns the plan to stage one. If the intent really changes, say so and ask `Sign intent` again.

Stage one stops here. The next step is drafting the spec (spec.md).
