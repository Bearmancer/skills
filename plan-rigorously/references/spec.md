# The spec: behaviours and criteria

Load this after `Sign intent`, when you start `## Spec`. The spec says WHAT must be true. Tasks say how it gets built, and they come later.

## Shape

- `### Behaviours`: numbered `B-1`, `B-2`, ... One observable behaviour each, in document order.
- `### Criteria`: numbered `AC-1`, `AC-2`, ... One observable outcome each. Each names the behaviour it covers: `AC-1 (Covers: B-1): ...`.
- Every behaviour has at least one criterion. A criterion may cover several behaviours.
- Who it is for and why live in the Intent, not here. Do not write user stories.
- Every decision the user has made goes in as a behaviour, a criterion or an Out of scope line. A decision with no home in the spec was lost.

## No file paths in the spec

The checker rejects any path on a behaviour (`B-n`) or criterion (`AC-n`) line of `## Spec`; it does not scan other text in the section, but keep paths out of that too. That includes names of files that exist (`package.json`, `README.md`) and anything shaped like `folder/name.ext`. Say "the settings page", "the theme setting", "the build script". Paths belong in tasks; sources belong in claims. This is the one place the rule is stated.

## Sentence shapes (guidance, not checked)

Use the smallest shape that fits. These keep behaviours testable.

| Situation | Shape |
|---|---|
| Always true | The <thing> shall <response>. |
| Triggered by an event | When <trigger>, the <thing> shall <response>. |
| True while in a state | While <state>, the <thing> shall <response>. |
| Only when a feature is present | Where <feature>, the <thing> shall <response>. |
| Something unwanted happens | If <bad trigger>, then the <thing> shall <response>. |
| State plus event | While <state>, when <trigger>, the <thing> shall <response>. |

Dark mode examples:
- B-1: When the user turns on dark mode, the settings page shall render with the dark palette.
- B-3: If the saved theme value is not recognised, then the settings page shall use the system setting and discard the saved value.

## Writing good criteria

- **Observable and numeric.** "Faster" becomes a number: "The page background changes within one frame." Reframe every vague word (fast, intuitive, correct, secure) into something a test can check, then ask the user whether the number is right.
- **One outcome per criterion.** If the sentence has "and" between two outcomes, split it.
- **Do not prescribe the build.** "Stores the choice in local storage" is a task detail. "The choice survives a reload" is a criterion.
- **Bounded values get three criteria:** inside the bound, at the bound, beyond it.
- **Error paths state the response and whether it is all-or-nothing.** "If saving fails, the page keeps the old theme and shows an error" says what happens, not just what does not.
- **State changes get one criterion per transition.**
- **Anything about permissions gets a negative criterion** that names the forbidden outcome: "If a signed-out user opens settings, then the system shall redirect to sign-in and shall not show any saved value."
- **Non-functional needs** (speed, accessibility, privacy, compatibility) get the same shapes with a threshold and the load or setting it applies in. If you decide a category does not apply, say so in an extra `## Not doing` note.
- If a behaviour cannot be phrased as a trigger and a response without inventing a product decision, stop writing and ask the user. Do not guess.

## Criteria versus the project's standing quality bar

A criterion is specific to this job: "did we build the right thing?". The standing bar is the same for every change: tests pass, lint is clean, no skipped tests, no suppressed warnings, coverage floors, accessibility floors.

- If the project has a `CONSTRAINTS.md` (or equivalent), read it. It is the definition of done for every task. Do not copy it into criteria.
- Put the bar's commands into each task's `Verify:` line.
- Never weaken it to make a task fit. If a task cannot meet the bar, that is a question for the user.
- If the project has no written bar, do not invent one. Tell the user in one sentence that none exists and carry on.

## Seams agreed up front

A seam is the public edge where behaviour is observed by a test, without reaching inside. Tests are written only at seams the user has approved.

1. Look for existing seams first. Prefer the highest one that can show the behaviour. One seam for the whole job is the ideal.
2. Propose each seam to the user as a question. Use the class names below in your notes and in `## Seams`. In the question itself use everyday words with an example ("tested directly in code, nothing outside involved", "tested against a local stand-in for the database", "tested against our own service over the network", "tested against a third party's real service"), and one line on what the test catches and what it lets through. The classes:
   - in-process (pure code, no I/O)
   - locally substitutable (a local stand-in exists)
   - owned remote (your own service across a network)
   - true external (a third party)
3. Record the answer in an extra `## Seams` section.
4. A seam needs two real adapters (usually production and test) to be worth adding. One adapter is just indirection.
5. If a behaviour cannot be observed at any approved seam, that is a finding to take to the user, not a reason to test internals.

## Interfaces: contract first

When the job adds or changes something other files call (a function signature, an endpoint, a shared data shape):

- Write the contract before anything else: inputs, outputs, error shapes, ordering and retry rules. It goes in the spec as behaviours, and the exact shape in `## Decisions` (see design.md).
- Prefer adding optional fields to changing or removing existing ones. Anything callers can observe, someone will depend on.
- Validate at the edge where outside data enters, and nowhere inside.
- State what happens on a repeated call. If the call changes state, decide whether repeating it is safe.
- Hand off to competing designs when the shape is genuinely open (design.md).

## Risky work: threat prompts

Treat the job as risky when it touches sign-in or permissions, stores a new kind of personal or payment data, adds an outside service, changes cross-origin rules, accepts file uploads, changes rate limits or grants roles. Each of these is also a reason to use the full path, and each is a question for the user before it is a behaviour.

For risky jobs add, as questions and then criteria:

1. **Trust boundaries:** where does outside data enter? Include request fields, files, webhooks, third-party responses and model output.
2. **Assets:** what is worth stealing or breaking?
3. **Per boundary, six prompts:** who could pretend to be someone else, what could be altered, what could be denied later, what could leak, what could be overwhelmed, who could gain rights they should not have.
4. **Abuse cases:** for each use case, how would someone misuse it? Write the abuse as a negative criterion first.

## Large requests

If one request bundles several capabilities that could be built and verified separately (sign-in, billing, reporting), do not write one huge spec. Agree a short capability list with the user: a stable id per capability, what it depends on, a build order. Keep it in `.rigor/map.md` (map.md). Plan the first capability now. Only one plan exists at a time, so the rest wait.

## Before you ask for review

- Every behaviour has a criterion, every criterion names a real behaviour.
- No path, no vague adjective.
- Every fact the spec leans on is listed under `## Claims` with proof.
- Each open product question is answered by the user, not by you.
