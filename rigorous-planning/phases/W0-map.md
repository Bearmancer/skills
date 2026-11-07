# W0: map — the unknowns branch

Read this when the unknowns test fails: the destination cannot be stated in one or two lines, or the first three decisions cannot be stated precisely. Map work is planning by decision, not a build. The branch ends when the way is clear; it never mints tasks.

## Initiate

`node scripts/planning.mjs init --slug <slug> --map`

Creates `.rigor/maps/<slug>/ledger.json` and `map.md` at phase `W0`. A map ledger has decisions and decision tickets, no tasks; `task` is refused. No branch, no tracker writes.

## The map

One canonical artifact, an index rather than a store:

```markdown
# Map: <slug>

## Destination
<one or two lines: the spec, decision or change this effort finds its way to>

## Notes
<constraints and context a fresh reader needs>

## Decisions so far
- <name>: <one-line gist>  (detail lives in its ticket)

## Not yet specified
- <a question that cannot be phrased sharply yet>

## Out of scope
- <work ruled beyond the destination; never graduates unless destination is redrawn>
```

A decision lives in exactly one place, its ticket. The map gists and links; it never restates a decision's detail.

## Decision tickets

A ticket is a question whose resolution is a decision, not a slice of a build:

`question --label <stable-kebab> --question "<one sharp question>" --map --kind evidence|prototype|user|task [--blocked-by Q1,Q2]`

- `evidence` — a fact the agent can find; resolve with a read-only lane.
- `prototype` — a question needing a throwaway runnable answer.
- `frontier` — a decision the user owns; resolve by interview.
- `task` — a small piece of work whose result is itself a decision input.

Resolve one ticket per session: `answer --id Qn --answer "<the decision and why>"`, and put evidence under `sources/` when it is a document or run. A ticket whose prerequisites are unsettled waits. The ready set is every active ticket whose `blocked-by` edges are settled; work that set one at a time.

Refer to a map or ticket by its name in everything the human reads, never by a bare id. The id and link ride inside the name.

## Unknowns

Record each item you cannot phrase sharply with `unknowns --add "item"`. An unknown item either becomes a sharp ticket, is ruled out of scope, or is resolved. When the list is empty and every open question is either settled or recorded as a ticket, clear the marker with `unknowns --clear`. G_MAP rejects unknowns still recorded.

## Exit: G_MAP

Before the gate, record the captain's sign-off: `approve --gate G_MAP --token map-destination --by user --quote "<the user's words naming the destination>"`. `approve` accepts `G_MAP` at W0; every other approval waits for P3.

`gate --id G_MAP` passes only when:
- the ledger is in map mode and `map.md` has Destination, Notes, Decisions so far, Not yet specified and Out of scope;
- an active `destination` decision exists and fits in one or two lines;
- `unknowns` is cleared;
- no `map` ticket is still open;
- at least one `map` ticket has been resolved;
- a `map-destination` approval exists with `by=user` and a non-empty quote.

## Handoff

`map-handoff --type feature` (or another issue type) seeds `.rigor/plans/<type>/<slug>/` with the map's active decisions and facts, at phase P0. Run `gate --id G0`, then rejoin the linear pipeline at P1 (axes). Do not jump to P5: collapsing the map straight into tasks throws away the linked decision detail. The handoff is a spec seed, not an implementation order.

## What is a method here

Naming the destination well, writing a readable map, choosing ticket types, and deciding when a ticket is sharp enough are judgement. The hard checks are the map headings, the destination, unknowns, open tickets, at least one resolved ticket, and the owner's signed destination. No tracker writes happen in this branch; filing is a separate owner-approved step.