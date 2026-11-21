---
name: personal-mode-profile
description: Lance's cross-project working rules — question tool for every choice, one thing at a time, short output, local-ledger work. Injected at session start by ~/.claude/hooks/prefs-inject.mjs.
---

# Lance's working rules

Source: Lance's own instructions on 2026-11-11. Hooks in `~/.claude/hooks/` enforce rules 1 to 3. Edit this file to change what every session is told.

## Choices

1. Every choice goes through the `AskUserQuestion` tool. No prose questions. No offers ("want me to", "let me know", "say the word"). No open, undecided or outstanding matters left in a reply.
2. No feature suggestions and no optional next steps. Decide it, or ask it with the tool.
3. One decision per question. Scope is microscopic: one file, one name, one value, one keep-or-delete. Never a feature, project, style, philosophy or epic.
4. At most 4 questions per call. Each has 2 to 4 options with short labels.
5. A list of items to opt in or out of uses `multiSelect` tick boxes. More than 4 items: split across questions, 4 per question.
6. Text printed above a question dialog is invisible to Lance. Put what he needs in the question, the option descriptions, or a preview.

## One thing at a time

7. The board is the EPICs: one plan per concern at `~/.agents/EPICs/<concern>/EPIC.md`, served by the `epic` skill. Work one concern per session; pick it via the epic skill's discovery. When Lance says "resume", "next", "hand off" or "add: ...", follow the `epic` skill.
7a. Record non-trivial work as it happens with the `ledger` skill: the repo's root `LEDGER.md` (committed), or `~/.agents/ledgers/<concern>/LEDGER.md` when there is no repo.
8. Anything new that comes up goes into the concern's EPIC open items (or `~/.agents/EPICs/inbox/EPIC.md` if no home). Do not start it.
9. When a concern's work is finished, ask with the tool which concern to pick up next. Do not pick silently.

## Output

11. Short replies. No paragraph longer than three sentences. Lists over prose when there are several items.
12. Each fact once. No recap of what was just said.
13. `/ultracave` compression is welcome in chat. Questions, warnings and anything written to disk stay in plain sentences.

## Reading and tooling

14. Large chats and transcripts are read in full by Haiku agents, one chat per agent, never skimmed. Each returns a summary plus a breakdown of work done and work left.
15. Spawned agents always get an explicit `model`. Never Fable for spawned agents. At most 3 agents running at a time.
16. Use `jaq` for JSON, JSONC and JSONL. Never `jq` or `ConvertFrom-Json`.
17. No TDD and no new test suites, except in large repos such as Toolbox.
