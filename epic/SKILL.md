---
name: epic
description: "Serve and maintain Lance's plans and cross-project backlog - one EPIC.md per concern in ~/.agents/EPICs/<concern>/, served a few items at a time and kept free of finished work. Use whenever Lance resumes or asks what is next (\"resume\", \"next\", \"add: ...\", \"hand off\"), starts a session without naming a task, writes down any plan, or asks to purge the backlog. Event logs of work in progress belong to the ledger skill, not here."
---

# Epic

An EPIC is a plan: what is still to do for one concern, and the open questions blocking it. It is edited in place and holds only live work, so opening it shows exactly what is next.

How a piece of work went (attempts, failures, reasons) lives in that work's ledger (the `ledger` skill). An EPIC item links to its ledger section; the ledger never duplicates the plan.

## Where it lives

`C:\Users\Lance\.agents\EPICs\<concern>\EPIC.md`, the one home for every plan.

- `<concern>` is a short kebab-case name: a repo (`skills`, `toolbox`, `website`) or an area (`opencode-host`, `arr-stack`, `tracker-requests`, `research`, `salvage`, `inbox`). Enumerate the folders rather than trusting this list.
- Work that fits no concern goes to `inbox` until triaged.
- Data files the plan depends on may sit beside the EPIC. Before the folder is deleted, move any that outlive the plan beside the ledger (e.g. `ledgers\tracker-requests\24BIT-ONLY.md`).
- Event logs go to repo roots or `~/.agents/ledgers/` (the `ledger` skill). A plan found anywhere else moves into its concern.

## Format

```
# EPIC - <concern>
Goal: <one line>
Status: active | paused

## Current truths
- <a standing fact or settled decision the plan relies on, one line, with its source>

## Open items
- [ ] <item> - blocked-by: <item | question> - log: <ledger path#section, once work started>
- next: <the single next action>

## Open questions
- [Q1] <question> - asked <ISO date>
  - [ ] <option A>
  - [ ] <option B>
```

**Current truths** holds only what the plan still needs; when a ledger section closes, its lasting facts and decisions are promoted here.

## Purge (automatic)

Every time you open or serve an EPIC, and whenever a linked ledger section closes, first remove each item or question that:

- is done;
- has a target that no longer exists (check the disk, the URL or the code it cites);
- is superseded by a later ruling;
- duplicates an item elsewhere.

Record each removal as one line, `- <item> - removed: <reason> - evidence: <command + result>`, in the item's ledger section when it has one, otherwise under `## EPIC removals` in `~/.agents/ledgers/<concern>/LEDGER.md`. The EPIC keeps no struck-through copy. When unsure whether an item is still live, keep it and mark it `(unverified)`.

When the purge leaves an EPIC with no open items and no open questions, and its ledger sections record the work as done, delete the concern's EPIC folder without asking. Log `- <concern> EPIC - removed: finished - evidence: <ledger section>` under `## EPIC removals` in its ledger. There is no closed status: a finished EPIC is gone.

## Discovery

1. Run `fd -HI -d 2 "^EPIC\.md$" C:\Users\Lance\.agents\EPICs`.
2. If Lance names a concern, open it. Otherwise ask with the question tool, one tickbox per active EPIC, labelled with its `next:` line.
3. Read the EPIC, plus the ledger section of any item already in progress, before acting.
4. Serve only `active` EPICs.

## Lock

The lock marks which session owns a concern's EPIC for the length of a session. It is a file, `EPICs\<concern>\.lock`, holding `session: <id>` and `heartbeat: <ISO UTC>`.

- **Session id:** `$env:OPENCODE_SESSION_ID` in OpenCode; elsewhere the harness's session id, or `<harness>-<ISO start>` when it exposes none.
- **Before writing:**
  - No lock: create it.
  - Your lock: refresh the heartbeat.
  - Another session's lock: the EPIC is read-only for you; tell Lance through the question tool.
- **Stale lock:** a heartbeat more than an hour old usually means a crashed session. Ask Lance through the question tool whether to clear it, showing the holder and the heartbeat age, with clearing as the recommended option. Only he clears a foreign lock.
- **Hand-off:** delete your lock.

## Serving

**Budget:** at most 4 microscopic questions and 3 tasks per turn. A microscopic question is one that a tickbox or one short sentence settles.

- **Check each question is still live before serving it.** Its target should exist, and `rg` its id across `~/.agents/EPICs`, `~/.agents/ledgers` and the concern repo's `LEDGER.md` should show no recorded answer.
- **Ask through the question tool.** Text printed above the dialog is invisible to Lance.
- **Record the answer right away.** Move a settled answer into Current truths and drop the question. Re-ask an ambiguous answer instead of guessing.

| Lance says | Do |
|---|---|
| "resume", "where was I" | Run discovery, purge, read the EPIC, report its `next:` |
| "next" | Purge, then serve within the budget |
| "add: <text>" | Append it to Open items, confirm in one line, start nothing |
| "what first" | Report the order from the blocked-by links |
| "switch to <concern>" | Update `next:`, release the lock, open the new concern |
| "hand off" | Update `next:` with position and exact next step, then release the lock |
| "purge" | Run the purge across every active EPIC |

End on statements. Anything Lance must decide goes through the question tool.
