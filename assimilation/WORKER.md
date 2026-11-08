# Answering units: worker brief

Project: a pack of `<verb>-rigorously` skills replaces five third-party skill packs. Every piece ("unit") of every source skill must get exactly one recorded answer. Your job: answer every unit of the skills assigned to you. Work from C:/Users/Lance/Dev/skills. Be exact; a script checks structure, the user reviews judgement.

## Tools (run with node, from the repo root)
- `node assimilation/list.mjs <source> <skill> [file]`  compact listing; a * after the number means already answered. Text is cut at 110 chars: when a decision depends on the full text, read the source file (root folders are in assimilation/sources.json; the listing shows line numbers L a-b) or grep assimilation/units/<source>.jsonl.
- `node assimilation/answer.mjs <source> <skill> <file> <from>[-<to>] <disposition> ... --part <your worker id>`  appends one answer line for a run of units (see the header of assimilation/answer.mjs for the exact forms). Always pass --part so parallel workers never write the same file.
- `node assimilation/check.mjs <source> --skill <skill>`  must print PASS when you have answered a skill completely. Its messages are exact; fix what it says.

## Answers (closed vocabulary)
- absorbed: the idea lives in a lane. to = {skill: <lane>, section: <short noun phrase, 8 words max>}.
- duplicate: same text as another unit of the same skill that you answered absorbed (of = that unit id).
- dropped: why = boilerplate (headings, labels, lead-in lines, separators, table header rows; no note needed) | example-only (worked examples, sample transcripts, sample output; note required) | noise (plugin administration or display only) | runtime (harness machinery: hooks, SDK calls, harness tools such as create_goal, todo, task, workflow, eval, state folders like .omo/ .omc/, the omc CLI, tmux; note names the feature) | superseded | out-of-scope (note says which user decision).
Keep the methodology a runtime feature implements (loop discipline, evidence gates, dispatch rules, stop conditions) as absorbed into execute-rigorously or core; drop only the machinery.

## Lanes (the only legal values for to.skill)
- planning-rigorously: the question sweep, intent, scope, requirements and specs, design and architecture (routed by task scope), task breakdown, test-first planning, risks, plan documents, decision records.
- research-rigorously: investigating open questions, external facts, sources, claims, citations.
- review-rigorously: judging finished work: code review, QA, verification gates, security and performance checks as review axes, simplification and slop cleanup.
- debugging-rigorously: diagnosing failures: hypotheses, tracing, root cause, error recovery.
- execute-rigorously: carrying out an approved plan: implementation steps, loops, parallel agents and dispatch, evidence, completion checks.
- version-control-rigorously: commits, branches, worktrees, rebase, merge, finishing a branch, history search.
- visualize-rigorously: diagrams, HTML pages, figures, visual QA and verdicts (not frontend frameworks).
- sweep-rigorously: GitHub work (sweeping, PR creation and review, issues). Deferred: do NOT answer GitHub-platform units, see below.
- init-rigorously: preparing a project for agents: generating and maintaining the AGENTS.md hierarchy and repo conventions (omo init-deep, omc deepinit). Built last; answer units into it now.
- core: how a run is controlled: ledger, step order, schemas and checks, waivers, attended versus unattended, parked questions, stop rule, resuming.

## Standing user decisions (apply them)
- Questions are always asked as a whole round up front through the question tool; one-at-a-time questioning is superseded.
- Examples and noise are dropped after enumerating.
- TDD is on by default in planning, with a flag to turn it off: TDD rules go to planning-rigorously.
- All work, including incremental work, lives in planning and execute only. Design and architecture are part of planning.
- Dropped for now: frontend frameworks and UI building, browsing, API design, release and launch. Units about them: dropped, why out-of-scope, note "user: dropped <topic>".
- Git rules go to version-control-rigorously. Visuals go to visualize-rigorously.
- A non-stop run (omo ulw, omc ralph) is the pack's execute/core: ask everything up front, then never stop; unanswerable items are parked and asked together at the end.
- A rule that conflicts with a standing decision: absorb it anyway into the lane section it belongs to, and end the section name with " [conflict: <short reason>]" so the user can find it. Do not drop it silently.

## Rules of judgement
- Losing a rule is worse than keeping a duplicate: when unsure whether a unit holds a unique rule, absorb it.
- Reuse the same section name for the same idea inside your assignment; do not invent one section per unit. Name sections by the idea, e.g. "Question sweep: restate and explicit yes".
- Use ranges for runs with the same answer. A `duplicate` or a `dropped` with --ref names a single unit and may only point at a unit of the same skill that you answered absorbed. Ignore the DUP marker in listings unless the original is in your own skill.
- Leave a unit unanswered and report it (do not guess) when: it is about the GitHub platform (gh CLI, PRs, issues, labels, triage, CI hosting): report DEFERRED-SWEEP; or a whole skill fits no lane (for example authoring skills, wikis, memory tools): report NEEDS-USER with a one-line reason.
- Never edit units/, sources.json, lanes.json, check.mjs, enumerate.mjs, list.mjs, answer.mjs or another worker's files. Never delete anything. Never commit.

## Finish
For each skill you own completely: list.mjs shows no row without *, and check.mjs prints PASS (skills you share by file: only the list.mjs check). Final message, at most 25 lines: per skill the counts by disposition, every DEFERRED-SWEEP or NEEDS-USER item, and up to five judgement calls the user should review.
