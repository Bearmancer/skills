# Design choices, decisions, vocabulary and prototypes

Load this when the plan adds or changes something other files call, when a decision may deserve a record, when a term is fuzzy, or when a question cannot be settled in words.

## Competing designs

**When:** only when the plan adds or changes an interface that other files call (a function signature, an endpoint, a shared data shape that more than one consumer reads). Not for changes inside one file. Not for choices that are easy to reverse.

**How:**

1. **Frame it** in a few lines: the problem, who calls it, the rules it must keep (invariants), and its dependencies. Put the frame in the preview of the question that asks the user to choose (step 5).
   Dark mode example: the plan adds a shared "current theme" value that several pages will read. Design A has one `getTheme()` entry point. Design B exposes a store with subscribe and set. Design C is a CSS-variable contract with no code API. The user picks, and the losers' reasons go in `## Decisions`.
2. **Send 2 or 3 fresh agents in parallel**, one per design. Each gets its own brief and a different constraint:
   - fewest entry points, most behaviour behind each
   - most flexible, supports many uses
   - best for the most common caller, the usual case is trivial
   - (if the dependency crosses a network or belongs to a third party) built around a replaceable port
   Each returns: the types, the module edge, what callers see, how each rule is kept, one usage example, what is hidden, the trade-offs.
3. **Spawn them under the subagent rule in SKILL.md** (explicit `model`, no Fable, no fork).
4. **Compare, criterion by criterion:** size of what callers must learn, how clear the edge is, whether the rules hold, cost to migrate, ease of deleting later. Prefer the smaller surface and the cleaner edge when it is close.
5. **Ask the user to choose**, with your recommendation first.
6. **Record the result** in an extra `## Decisions` section: the chosen design, the specific reason each loser lost ("worse" is not a reason; name what was worse), the rules the build must keep (each one checkable), and later a register of accepted deviations.

Red flags to look for while comparing: callers must call several methods for one job; the same detail appears in two places; one piece of state has two owners; a mutation callers must remember to undo; settings read at import time; a retry loop that hides real errors; a migration with no plan for a crash halfway; a new outside dependency with no fallback; removing an old interface without checking every caller.

## Vocabulary for design talk

Use these terms exactly in your notes, `## Decisions` and records. In a question to the user use everyday words with an example instead (plain words rule in SKILL.md): not "Is this a deep module?" but "Should callers have one simple entry point that hides the detail, like `getTheme()`, or several small ones?"

- **Module:** anything with an interface and an implementation, at any size.
- **Interface:** everything a caller must know: signature, order of calls, error behaviour, setup, speed.
- **Seam:** the place where behaviour can be changed or observed without editing there.
- **Adapter:** a thing that satisfies an interface at a seam.
- **Deep module:** a lot of behaviour behind a small interface. Shallow is the reverse.
- **Deletion test:** imagine deleting the module. If the complexity vanishes it was a pass-through. If it reappears in many callers it was earning its place.
- One adapter means a hypothetical seam. Two means a real one.

## Decision records (ADRs)

Offer a record only when all three are true (your own judgement; the system does not check this test):

1. It is hard to reverse.
2. A future reader would be surprised without the context.
3. It is the result of a real trade-off between real alternatives.

If any one is missing, do not offer one. Offer it as a question. If the user says yes:

- Write `docs/adr/NNNN-short-slug.md` (next free four-digit number; create the folder if needed). Writing there is allowed during planning.
- Keep it to one short paragraph: the context, what was decided, why. Add a status line, the rejected options (only if they were compared and the rejection is not obvious) or consequences (only if non-obvious).
- Never delete or rewrite an old record. A changed decision gets a new record that supersedes the old one.
- If the project already has records, match its folder, numbering and headings.

## The glossary

`GLOSSARY.md` at the project root is the shared vocabulary. Update it the moment a term is settled, not in a batch at the end.

- Format: a term in bold, one or two sentences saying what it IS, then `_Avoid_:` with the words not to use.
- Only terms specific to this project. No general programming words. No implementation details, no specs, no decisions.
- When the user uses a word that clashes with the glossary, or a word that is vague or overloaded, say so and propose one precise word.
- When the user describes how something works, check the code. If they disagree, raise it as a question.
- Create the file only when the first term is settled. Only the root file can be written during planning. If the project keeps several glossaries, tell the user which others need the same update later.

## Prototypes

Use one only when a design question stalls in words and cannot be answered from the code or by asking. One prototype answers one question. The rules below are for you; the system does not check them.

- **Where:** a git worktree (its `.git` is a file, so it is an independent checkout) or a clone placed outside the project folder. A clone inside the project folder is part of the project and its writes are blocked, like any nested repository (see plan-format.md). Never a plain branch in the same folder, and never merged. Mark the code as a prototype by name.
- **Logic question** ("does this state model hold at the edges?"): put the logic in one small pure module, wrapped in a single self-contained HTML page with a button per action, the full state shown after every click, and a few walk-throughs of awkward cases, written in the user's words.
- **Look question** ("what should this page look like?"): three variants that differ in structure (layout, information order, main action), not colour. Mount them on the existing page behind a switch so real density tests them. Never more than five.
- No tests, no saved data, no polish, no framework.
- The user reacts to it. Their reaction is the decision. Write the question, the verdict and the branch name under `## Decisions`, and fold the verdict into the spec. Nothing from the prototype lands in the project.
- A prototype verdict is a decision, not proof of a fact (proof.md).
