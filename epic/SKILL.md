---
name: epic
description: Lance's plans and cross-project backlog - one EPIC.md per concern at ~/.agents/EPICs/<concern>/, served a few items at a time. Use when Lance says "epic", "plan", "backlog", "resume", "next", "questions", "pop", "where was I", "what first", "add: ...", "hand off", or starts a session without naming a task; when writing down any plan; and when pruning done or stale backlog items. Event logs of work in progress are NOT epics - use the ledger skill for those.
---

# Epic

An EPIC is a plan: what is still to do for one concern, and the open questions blocking it. It is edited in place. Finished, stale and superseded items leave it, so opening an EPIC shows only live work.

It is not a log. How a piece of work went (attempts, failures, reasons) lives in that work's ledger (the `ledger` skill). An EPIC item links to its ledger; the ledger never duplicates the plan.

## Where it lives

Always `C:\Users\Lance\.agents\EPICs\<concern>\EPIC.md`. There are no other plan locations.

- `<concern>` is a short kebab-case name: a repo (`skills`, `toolbox`, `media-cmdlets`, `website`) or an area (`opencode-host`, `arr-stack`, `classical-library`, `tracker-requests`, `md-library`, `research`, `salvage`, `inbox`). Enumerate the folders rather than trusting this list.
- Work that fits no concern goes to `inbox` until it is triaged.
- Data files that the plan depends on, but which are not plan items, may sit beside the EPIC. One example is `tracker-requests\24BIT-ONLY.md`, the skip list of boxes not to request.
- Logs never go here. A plan found anywhere else is moved into its concern.

## Format

```
# EPIC - <concern>
Goal: <one line>
Status: active | paused | CLOSED

## Current truths
- <a standing fact or settled decision the plan relies on, one line, with its source>

## Open items
- [ ] <item> - blocked-by: <item | question> - log: <path to its LEDGER.md, if work started>
- next: <the single next action>

## Open questions
- [Q1] <question> - asked <ISO date>
  - [ ] <option A>
  - [ ] <option B>
```

- **Current truths** holds only what the plan still needs. When a ledger closes, its lasting facts and decisions are promoted here.
- An item leaves the EPIC when any of these apply:
  - it is done;
  - its target no longer exists (check the disk, the URL or the code it cites);
  - a later ruling supersedes it;
  - it duplicates an item elsewhere.

  Record why it left in one line in the concern's ledger, or in the commit message. Don't keep a struck-through copy.

## Discovery

1. Run `fd -HI -d 2 "^EPIC\.md$" C:\Users\Lance\.agents\EPICs`.
2. If Lance names a concern, open it. If he names none, ask with the question tool, one tickbox per active EPIC, labelled with its `next:` line.
3. Read the EPIC, plus the ledger of any item already in progress, before acting.
4. Never serve a `Status: CLOSED` EPIC.

## Lock

Before writing, check `EPICs\<concern>\.lock` (`session: <id>`, `heartbeat: <ISO UTC>`). In OpenCode your id is `$env:OPENCODE_SESSION_ID`.

- **No lock:** create it.
- **Your lock:** refresh the heartbeat.
- **Another session's lock:** the EPIC is read-only for you. Tell Lance through the question tool.

Delete your lock on hand-off. Never clear a foreign lock; only Lance does.

## Serving

**Budget:** at most 4 microscopic questions and 3 tasks per turn. A microscopic question is one that a tickbox or one short sentence settles.

- **Check each question is still live before serving it.** Its target should exist, and `rg` its id across `EPICs` should show no other ledger has already answered it.
- **Ask through the question tool.** Text printed above the dialog is invisible to Lance.
- **Record the answer right away.** Move a settled answer into Current truths and drop the question. Re-ask an ambiguous answer; never guess.

| Lance says | Do |
|---|---|
| "resume", "where was I", "epic" | Run discovery, read the EPIC, report its `next:` |
| "next", "questions", "pop" | Serve within the budget |
| "add: <text>" | Append it to Open items, confirm in one line, start nothing |
| "what first", "order", "critical path" | Report the order from the blocked-by links |
| "switch to <concern>" | Update `next:`, release the lock, open the new concern |
| "hand off", "stop", "enough" | Update `next:` with position and exact next step, then release the lock |
| "purge", "prune" | Remove done, stale and superseded items under the rules above |

End on statements. Anything Lance must decide goes through the question tool.
