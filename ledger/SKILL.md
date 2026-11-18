---
name: ledger
description: 'Pick up and put down Lance''s cross-project backlog a few items at a time, from local LEDGER.md files. Use when Lance says "ledger", "resume", "next", "questions", "pop", "where was I", "add: ...", "hand off", or starts a session without naming a task. The backlog is segregated by repo/concern: each repo keeps its own LEDGER.md at its root, and work with no repo home lives at C:\Users\Lance\.agents\EPICs\<concern>\LEDGER.md. Serves at most 4 microscopic questions and 3 tasks per turn — never the whole backlog at once.'
---

# Ledger (local)

The backlog is Lance's cross-project work, picked up and put down a few items at a time. Authority is local files only: plain `LEDGER.md` files on this machine. No remote tracker, no API, no network — the file on disk is the backlog, so any harness that can read and write files can serve it, and a handoff is just a well-written file.

## Where the backlog lives

Segregate by repo/concern — one ledger per home, so work in one concern never drowns in another's noise:

- A repo or concern with a repo keeps `LEDGER.md` at its root, e.g. `C:\Users\Lance\Dev\Toolbox\LEDGER.md`, `C:\Users\Lance\Dev\Skills\LEDGER.md`.
- Work with no repo/concern home lives at `C:\Users\Lance\.agents\EPICs\<concern>\LEDGER.md`. Concerns include `tracker-requests`, `opencode-host`, `classical-library`, `arr-stack`, `md-library`, `foobar2000`, `research`, `salvage`, `inbox` — enumerate dynamically (discovery finds every concern folder). Create the concern folder and its `LEDGER.md` on first write if missing.
- Known exemptions (existing owner rulings — keep them):
  - Media / Lance-Cmdlets / media-research-tools → `C:\Users\Lance\Documents\PowerShell\Modules\Media\LEDGER.md`, one section per concern.
  - DVD concert library → `D:\DVDs` (merge initiative complete; per-folder `tags.json` sidecars are the metadata authority).

## Gates come from ledger-it

This skill serves the backlog; it does not define the discipline for recording work. That discipline lives in `~/.agents/skills/ledger-it` — read its `SKILL.md` and its two references, `references/record.md` (the ledger schema and maximal-detail verbatim evidence) and `references/gates.md` (read-before-act, write-after-act, failure quarantine, settled decisions, flip-flop surfacing), and follow them. One meaning, one home: do not restate or fork those rules here. Every ledger this skill touches uses ledger-it's schema, and every answer, checkpoint, and decision below is recorded under those gates — in particular, read the ledger before acting on it and write to it immediately after each answer or task outcome, not batched at the end.

## Discovery

Find the homes before reading anything, so you resume the right concern instead of a stale memory of one:

1. Enumerate existing ledgers (the `-I` flag matters: some homes git-exclude their LEDGER.md, so an ignore-respecting search can miss them):

   ```
   fd -HI -d 2 "^LEDGER\.md$" C:\Users\Lance\Dev
   fd -HI -d 2 "^LEDGER\.md$" C:\Users\Lance\.agents\EPICs
   ```

   Skip the EPICs line until that tree exists. Add the two exemption homes above to the result set.
2. Repo roots under `C:\Users\Lance\Dev` are candidate homes even without a `LEDGER.md` yet — first work in a repo creates its ledger at the root.
3. If Lance names a concern or repo, go straight to its ledger.
4. If he names none, do not guess: ask with the question tool, one multi-select tickbox entry per concern that has open items, each labelled with its next item. He ticks; you serve that concern.
5. Read the chosen ledger before acting (ledger-it re-entry): status, established facts, settled decisions, open items / next. Resume from "next" — do not restart the work or re-derive what the ledger already holds.

## The serve budget

Serve at most **4 microscopic questions and 3 tasks per turn**. The point is to pick up a few items and put them down cleanly, not to dump the backlog — a wall of items buries the one thing Lance can answer right now. A question is microscopic when one tickbox or one short sentence settles it; if it needs a paragraph of context, split it into several microscopic questions instead.

## Questions and answers

Questions and their answers live in the ledger itself, in an `Open questions` section — the file is the record, so an answer survives compaction, harness switches, and turn boundaries:

```
## Open questions
- [Q1] <question, one line> — asked <ISO date>
  - [ ] <option A>
  - [ ] <option B>
  - answer: <verbatim option label or Lance's words> — recorded <ISO date>
```

Ask through the question tool. In Claude Code that is one `AskUserQuestion` call with up to 4 entries, shaped from the open questions; checkbox options become the question's options. Text printed above the dialog is invisible to Lance — anything he needs goes inside the question, its description, or a preview.

Record the answer in the ledger the moment he gives it: verbatim under the question, dated, question marked answered. Ambiguous or double-checked answers get asked again through the question tool — never guess, because a guessed answer recorded as fact poisons every later turn that reads it.

## What Lance says, and what it maps to

| He says | Do |
|---|---|
| "ledger", "resume", "where was I" | Discovery, read the chosen ledger, report position from its status and open items |
| "next", "questions", "pop" | Read back recorded answers, then serve up to 4 microscopic questions and 3 tasks from the open items |
| "add: <text>" | Append the item to the ledger's open items, confirm in one line, start nothing |
| "switch to <concern>" | Write the closing checkpoint on the current ledger, then discovery and read on the new one |
| "what first", "order", "critical path" | Read the ledgers' blocked-by and ordering notes; report the order |
| "hand off" | Write the closing checkpoint; any harness picks up from the same file |
| "that question is too big" | Re-split it into several microscopic questions |

## Put down

Before ending a turn in which Lance said "stop", "enough" or "hand off", write a closing checkpoint into the ledger's `Open items / next`: position, what is half-done, and exactly where to start next. Name the harness that wrote it, so a reader knows whose half-done state it is. The file is the handoff — there is no reservation to sign and no lock to hold; the next harness, or the next session of this one, reads the same `LEDGER.md` and continues from "next".

## Reporting

End on statements, not prose questions or offers — in Claude Code the Stop hook blocks a reply containing them. Anything Lance must decide goes through the question tool, and its answer goes into the ledger.

Next action for a fresh session: run discovery, ask which concern if none is named, read that ledger, and serve within the budget.
