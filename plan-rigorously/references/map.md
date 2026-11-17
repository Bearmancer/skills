# The decision map

Load this when the job is too big and too foggy for one plan: you cannot write the destination sentence, or the open decisions fan out into several independent threads, or a decision cannot even be stated until another is settled. The map is for deciding. It builds nothing.

The map is just a file: `.rigor/map.md`, written with the normal tools. It is not a second plan and it has no format check. The single-plan rule still holds: a map and one plan can exist together, never two plans.

## Layout

```markdown
# Map: Dark mode across the whole product

## Destination
One or two lines: what reaching the end of this map looks like (a signed intent, a spec, or a decision).

## Open decisions
- D-1 Which surfaces get dark mode first?
- D-2 Do themes sync across devices? (blocked by D-1)
- D-3 Build on the existing colour tokens or start a new token set? (blocked by a lookup of what tokens exist)

## Settled
- D-4 Follow the system setting by default: yes. (settled; one-line gist)

## Out of scope
- Printing styles. Ruled out by the destination, not by difficulty.

## Fog
- Something is coming about offline behaviour, but the question cannot be stated yet.
```

- **Open decisions:** each is a question you can state sharply right now, even if you cannot answer it yet. Say what blocks it by naming the other decision.
- **Settled:** one line per decision, the answer in a few words. The detail lives in the plan or ADR it ended up in, never twice.
- **Out of scope:** work ruled beyond the destination. It does not come back unless the destination changes, and then it comes back as a new effort.
- **Fog:** work you can tell is coming but cannot state sharply. Do not break fog into ticket-sized pieces. When a settled decision clears the view, move what has become sharp into Open decisions and delete it from Fog.

## Fog or open decision?

The test is whether you can state the question precisely now, not whether you can answer it now. Sharp but blocked: open decision. Not sharp: fog.

## Working the map

1. **Write the plan skeleton first** (interview.md, "Start the file"), before any question, or nothing is recorded.
2. **Name the destination** with the user (a question; the answer is the first line of the map). If the user cannot name one, offer the two or three best candidates and let them choose or park the job.
3. **Chart breadth first.** Ask the frontier of decisions whose prerequisites are settled, 4 questions per call, exactly as in interview.md, each with a recommended answer. Write each answer into Settled. Map rounds count toward the interview's round limits (soft 10, hard 20) once that plan file exists, so spend them on decisions that matter.
4. **Settle as many decisions as fit in a session.** Do not stop after one. Stop when the questions left are all blocked, when facts must be looked up first, or when the user runs out of time. Then say plainly what is left.
5. **Facts go to lookups**, not to the user (a fresh agent under the subagent rule in SKILL.md, or you). A decision that needs a prototype is answered with one (design.md).
6. **Rule things out of scope** with the user's yes. Out-of-scope work is never reopened unprompted.
7. **Sediment as you go:** a settled term goes to `GLOSSARY.md`, a hard-to-reverse surprising trade-off goes to an ADR (design.md).
8. **Each new session starts from the map file**, not from memory. Read it, restate the destination in a sentence, take the next open decisions.

## Finishing

The map is done when Open decisions and Fog are both empty.

1. Collapse Settled into the six Intent lines (Outcome, User, Why now, Success, Constraint, Out of scope). A settled decision that fits no line is either folded into an Intent line (for example Constraint) or put to the user again through the question tool, with the question text starting `Q-n:`, and then recorded in the plan's `## Questions` as `[answered]`. A `D-n` answer given during mapping is not a recorded `Q-n` answer, so a plan line cannot just claim it.
2. Start the plan. The finished map is the source for the Intent, but the Intent is not signed until the user answers `Sign intent`. Interview any line that is still thin.
3. Leave the map file in place until the plan is closed. Closing the plan removes the map along with the rest of the working files.

If the map shows that several capabilities can be built and checked separately, say so, order them in the map, and plan the first one now. Each later capability becomes its own plan after the previous one closes.
