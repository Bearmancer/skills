# Grilling: frontier rounds

Contract: gates, CLI and the state machine are in ../SKILL.md. This playbook is the detail for this phase.

**Intent interview.** Needs a live user; non-interactive means flag a blocker, do not guess. Open with `HYPOTHESIS: <one sentence>` and `CONFIDENCE: n%` (append what is unresolved when below ~70%; the number must be defensible: can you predict the reaction to the next 3 questions?). Then one question per message, each with your guess attached:

```text
Q: <one focused question>
GUESS: <your answer with reasoning>
```

Occasionally guess in a direction you expect pushback on. Listen for "want versus should-want": buzzwords (scalable, clean, modern, robust), deference to convention, "I should probably"; probe with "if you didn't have to justify this to anyone, what would you actually want?". Stop when you can predict the next 3 reactions, then restate and require an explicit yes:

```text
Here's what I now think you want:
- Outcome: ..  - User: ..  - Why now: ..  - Success: ..  - Constraint: ..  - Out of scope: ..
Yes / no / refine?
```

Not a yes: "whatever you think" (delegation: re-ask as two concrete options), "sounds good" / "sure, let's go" (ask what to refine), silence then "ok let's start" (interview abandoned: ask what you missed). The Out of scope line is mandatory. Record with `intent --confirm --by user` only after a real yes, then stop the turn. After 3 rounds without rising confidence you are asking the wrong questions: reframe, or tell the user "I've asked N questions and still can't predict your reactions; something foundational is missing".

**Frontier grilling.** Model the plan as a design tree. The frontier is every decision whose prerequisites are settled. Ask the whole frontier in one round, numbered, each with your recommended answer worded so "yes" accepts it; a question that depends on another open one waits for a later round. Recompute after every round; done when the frontier is empty and the user confirms shared understanding. Facts a question needs go to a fresh-context read-only lane, never to the user; do not block on it, ask the rest now.

**Rounds in the ledger.** Before asking, record the round: `round --asks Q1,Q3`. Each question is a `Q` row; one that depends on another carries `--blocked-by Q1`. The CLI refuses a new round while the previous round has open questions unless it is a `--fact-lane`. G2 recomputes the frontier from the rows: an open `Q` that is in no round, or a `Q` asked before its blocker was settled, is an error. The wording, the recommended answers and the shared-understanding check are the method; the round record and the open-frontier check are the hard half. Format:

```text
Q1 - <title>: <body, with choices if any>
-> <your recommended answer>
```

**Playback as you go.** After each settled part, play it back in about 200-300 words: only what the user said is theirs, your fill-ins are labelled proposals with reasons, and end by asking what is wrong or missing. Say defaults aloud: an unheard default cannot be rejected. When you open with a first message and the user already stated what they want: about 200 words, echo what/who/why, add findings (constraints, conflicts, a cheaper path), then ONE question, the open thing whose answer most changes what is built. Plain language slightly above the user; lead with what matters. Ground to cover: kind of thing and what makes it special; why now and success; goals, non-goals and **anti-goals** (failure even if it technically works); prior art; current state and what was tried; details they care about. Which how-it-gets-made choices (tools, platform, language) do they want to make versus hand off? Yours are labelled your call.
