# W0: wayfinder — the fog branch

Read this when the fog test fails: the destination cannot be stated in one or two lines, or the first three decisions cannot be stated precisely. Wayfinding is planning by decision, not a build. The branch ends when the way is clear; it never mints tasks.

## Initiate

`node scripts/planning.mjs init --slug <slug> --wayfinder`

This creates `docs/maps/<slug>/ledger.json` and `map.md` at phase `W0`. A wayfinder ledger has decisions and decision tickets, no tasks; `task` is refused because the phase is below P4. It does not create a branch and never writes to a tracker.

## The map

The map is one canonical artifact, an index rather than a store:

```markdown
# Map: <slug>

## Destination
<one or two lines: the spec, decision or change this effort finds its way to>

## Notes
<the constraints and context a fresh reader needs>

## Decisions so far
- <name>: <one-line gist>  (detail lives in its ticket)

## Not yet specified
- <a question that cannot be phrased sharply yet>

## Out of scope
- <work ruled beyond the destination; it never graduates unless the destination is redrawn>
```

A decision lives in exactly one place, its ticket. The map gists and links; it never restates a decision's detail.

## Decision tickets

A ticket is a question whose resolution is a decision, not a slice of a build:

`question --label <stable-kebab> --question "<one sharp question>" --wayfinder --kind research|prototype|grilling|task [--blocked-by Q1,Q2]`

- `research` — a fact the agent can find; resolve it with a read-only lane, not by asking the user.
- `prototype` — a question that needs a throwaway runnable answer.
- `grilling` — a decision the user owns; resolve it by interview.
- `task` — a small piece of work whose result is itself a decision input.

Resolve one ticket per session: `answer --id Qn --answer "<the decision and why>"`, and put the evidence under `sources/` when it is a document or a run. A ticket whose prerequisites are unsettled waits. The ready set is every active ticket whose `blocked-by` edges are settled; work that set one at a time.

Refer to a map or ticket by its name in everything the human reads, never by a bare id. The id and link ride inside the name.

## Fog

Record each item you cannot phrase sharply with `fog --add "item"`. A fog item either becomes a sharp ticket, is ruled out of scope, or is resolved. When the list is empty and every open question is either settled or recorded as a ticket, clear the marker with `fog --clear`. G_WF rejects `fog` that is still recorded.

## Exit: G_WF

`gate --id G_WF` passes only when:

- the map is a wayfinder map and `map.md` has Destination, Notes, Decisions so far, Not yet specified and Out of scope;
- an active `destination` decision exists and fits in one or two lines;
- `fog` is cleared;
- no `wayfinder` ticket is still open;
- at least one `wayfinder` ticket has been resolved.

## Handoff

`wayfinder-handoff --type feature` (or another issue type) seeds `docs/plans/<type>/<slug>/` with the map's active decisions and facts, at phase P0. Run `gate --id G0`, then rejoin the linear pipeline at P1 (axes). Do not jump to P5: collapsing the map straight into tasks throws away the linked decision detail. The handoff is a spec seed, not an implementation order.

## What is a method here

Naming the destination well, writing a readable map, choosing ticket types, and deciding when a ticket is sharp enough are judgement. The hard checks are the map headings, the destination, fog, open tickets, and at least one resolved ticket. No tracker writes happen in this branch; filing is a separate owner-approved step.
