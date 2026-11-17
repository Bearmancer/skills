---
name: plan-rigorously
description: "Use when a change should be planned before any code is written: the user asks to plan something, says 'grill me' or 'interview me', wants a spec or a task breakdown, or has a big foggy job that needs a decision map. A first word of quick forces the short path and full forces the long one."
---

# Plan rigorously

This skill takes a request from "what do you want?" to an approved plan, then carries the plan out. The plan is one file, `.rigor/plan.md`. The example used everywhere is "add dark mode to the settings page".

## How you work (read this first)

- **You never run a script for this skill.** You write `.rigor/plan.md` (and `.rigor/map.md` for big foggy jobs) with the normal Write and Edit tools. You ask the user through the question tool. You read the short status notes and block messages that come back. That is all. A shell command that names `.rigor` is blocked from the moment `.rigor/plan.md` exists (Monitor counts as a shell tool); read and write `.rigor` only through the file tools. The guard stops accidents only. Evasion is out of scope (plan-format.md, "The guard"), and the rules the system does not check are listed there too.
- **The plan file comes first.** `.rigor/plan.md` lives at the project root (a folder containing `.git`, directory or file, is a root; each linked worktree is its own root with its own plan. With no `.git` anywhere above, the project folder you work in, where you first write the plan, becomes the root). Write it before any question, or any command or fetch whose result you will cite. Until it exists nothing is recorded: not answers, not sign-offs, not command or fetch evidence. A first word `quick` or `full` is recorded only inside a git repository or where `.rigor` already exists; anywhere else (no `.git` above you and no `.rigor` yet) the system forces nothing, so follow the word yourself, and the later `quick` or `full` rules here are then on you.
- **Never edit project files from a shell while a plan is live.** The checker only watches the file tools, so this is a rule, not a guard. Commands that write files only as a side effect, such as test output, are allowed.
- **A status note follows every plan write.** It names the stage (light, light-invalid, invalid, intent, drafting, build) and lists what the next checkpoint still lacks. `invalid` means `.rigor/plan.md` cannot be read; repair it so it parses. Read the note and act on it.
- **A block message says what is missing.** Fix exactly that. Never work around a block: no other file name, no shell redirect, no second plan.
- **Every question goes through the question tool** (`AskUserQuestion`), 2 to 4 options. The first option is your recommendation, worded so that "yes" accepts it. Put the explanation, the example and what each option costs inside the option `preview` and `description`. Never put a double quote (") in a question, a header or an option label, description or preview: the system reads the answer text by its quotes and cannot record an answer to a question that has one, and a reserved-header question with one is denied before it is asked. Quote with single quotes or put the quoted text elsewhere; when plan text enters a preview, swap its double quotes for single quotes (review.md). Text you write above a question dialog is hidden from the user, so never rely on it. Never ask in chat: an answer the user types in chat is not recorded, so re-ask it through the tool. Chat is for reporting.
- **Facts are yours, decisions are the user's.** Look facts up (the code, the docs, a fresh agent). Ask for preferences, scope and trade-offs. Never decide something the user has not decided, and never fill in a default.
- **Subagents (the rule for every file here):** always pass an explicit `model` (the one in the skill's config, default `sonnet`). Never a Fable model, never `inherit`. Never a fork; use a fresh general-purpose agent.
- **Plain words.** Short sentences. One thing per question.

## Reserved question headers

Five headers are special. The system records the tool answer; you copy it into the plan line. Only an option whose label begins with `Yes`, or a bare `yes`, counts as agreement, so word agreeing options "Yes, ..." and others "No, ...".

| Header | When you ask | What `Yes` does |
|---|---|---|
| `Sign intent` | the six Intent lines are filled, nothing open | locks the intent |
| `Approve plan` | drafted and reviewed, all findings settled | freezes the plan and starts the build |
| `Amend plan` | the build needs something the frozen plan does not allow | opens one amendment window |
| `Replace plan` | the user wants a different job while a plan exists | lets one differently named plan replace the old one, which starts clean (a same-name rewrite with a new Intent works only before approval) |
| `Close plan` | all tasks ticked, or the user is stopping | logs one line and deletes the working files |

`Sign intent` and `Approve plan` are blocked, with a list of gaps, until their checks pass. The checks run again at answer time: if they fail then, the answer is not recorded.

## The flow

### 1. Look first
If `.rigor/plan.md` exists, read it and the status note, and continue that plan. Never begin a second. If the plan is in build and this session did not start it, ask the user before continuing. If the plan file is gone, the plan is dead: ask the user whether to start again or close it, and never rebuild sign-offs from memory (after-approval.md). If the new request is a one-file job while a plan is open, edits are blocked: ask through the question tool whether to fold it in or finish and close the plan first (`Close plan`). Folding in works by stage: in the build ask `Amend plan`, then edit the plan; in the intent, drafting or light stages `Amend plan` does nothing, so add the file to the plan directly: in drafting a task's `Edits:`, in a light plan `## Files`; in the intent stage no tasks exist yet, so ask the user and record the file in the Intent lines or as a question. Reading the project's guidance files, `GLOSSARY.md`, `docs/adr/` and `CONSTRAINTS.md` is free.

### 2. Choose the path
- A path is forced only by a first word right after the skill name: `/plan-rigorously quick ...` or `full ...`. `full` always means the full path. `quick` means light and lifts the 3-file cap, but never the risk rule below. A downgrade from full to light goes through `Replace plan`.
- Otherwise: a job that touches **one file** outside the risky areas below needs no plan. Say so and do it. A job that touches **two or more files** (at most 3 unless forced `quick`), is low risk and has obvious steps takes the **light path**. Above 3 files, or anything else, takes the **full path**.
- Risky areas force the full path. This is the one canonical risk list; plan-format.md and spec.md point here: auth-shaped paths (sign-in, permissions, role grants), security, secrets or env files, migrations, CI workflows, lockfiles, infrastructure, payments or a new kind of personal data, file uploads, rate limits, cross-origin rules, tool and repo control files (`.claude`, `.git*` folders, `.husky`, `CLAUDE.md`, `AGENTS.md`), a new outside service, a changed public interface.

### 3. Light path
Write the plan first: `path: light`, `## Files` (every file you will touch, exact paths only) and `## Steps` (format in plan-format.md). The system checks the file count and whether a listed path matches a risky path pattern (auth-shaped paths, secrets, CI and so on). The rest of the risk list above is your judgement. If the check fails, rewrite it as `path: full`. You may edit only the listed files. Finish the steps, then ask `Close plan`.

### 4. Full path, stage one: settle what is wanted
Load interview.md. Write the plan skeleton first, on this path too. Check the destination sentence, the first three decisions and one concrete anchor. If they all hold, draft the Intent and go to `Sign intent`. If not, interview in frontier rounds. If the job is too big and foggy for one plan, chart a decision map first (map.md). Stage one ends with `Sign intent`.

### 5. Full path, stage two: draft
Only the plan, the map, `GLOSSARY.md` and `docs/adr/` may be written until the build starts. Write in this order, loading each file when you reach it:
1. `## Spec`: behaviours and criteria, no file paths (spec.md).
2. `## Claims`: one proven line for every fact the plan leans on (proof.md).
3. Design choices, decision records, glossary, prototypes when needed (design.md).
4. `## Tasks`: vertical slices with exact paths and a verify command each (tasks.md).

### 6. Review
Two independent reviewers read a frozen copy of the plan and try to break it (review.md). Write their findings into `## Review`, settle each one, repeat for at most 3 rounds (a round is one version of the spec), then ask `Approve plan`.

### 7. Build, amend, close
After `Approve plan` you carry on straight into the tasks (after-approval.md). The plan is read-only except for ticking tasks and edits to `## Review`. Changes go through `Amend plan`. When the work ends, ask `Close plan`.

## The example in one pass

The user says: "add dark mode to the settings page."
1. No plan exists. The job touches several files, so full path. The request has no file, no symbol and no criteria, so there is no anchor: interview.
2. The plan skeleton is written first. Round one asks Q-1 (which pages?) and Q-2 (should the choice persist across devices?). Q-3 (where is the preference stored?) waits for Q-2. Each has a recommended first option and a preview showing what it means.
3. Answers go into `## Questions` as `[answered]`. `Sign intent` shows the six Intent lines. The user says yes.
4. Spec: B-1 "When the user turns on dark mode, the settings page shall render with the dark palette." AC-1 covers it.
5. Claims: browser support is proven with an official page and a quote; the test command is proven by running it.
6. Tasks: T-1 theme tokens and switch, T-2 remember the choice. Both name exact files and a verify command.
7. Two reviewers return findings. Each becomes `F-n` with a fix or a reason. The user approves.
8. T-1 and T-2 are built, ticked and checked. `Close plan` logs one line.

## Rules that do not bend

- One plan at a time. Fixed names. Edit in place.
- Nothing is cut from scope unless the user says so.
- Every factual claim has proof, or it comes out of the plan.
- Spec has behaviours and criteria only; paths go in tasks.
- You never invent an answer: the system records the tool answer, you copy it into the plan line, and the checker rejects a copy with no recorded answer. You never approve your own plan or review your own plan.
- Prototypes live in a git worktree or a clone outside the project folder, never a plain branch in the same folder, and are never merged.
- If you cannot continue without the user, say what is missing and stop.

## Files to load, and when

| File | Load it when |
|---|---|
| references/plan-format.md | you write the plan file or a block message mentions the format |
| references/interview.md | you start a full plan |
| references/map.md | the job is too big and foggy for one plan |
| references/spec.md | the intent is signed and you write the spec |
| references/proof.md | you rely on a fact about a library, version, command or existing code |
| references/design.md | an interface other files call is added or changed; a decision, term or design question needs recording |
| references/tasks.md | you write the task list, or the job is a migration or wide refactor |
| references/review.md | the plan is drafted and ready for reviewers |
| references/after-approval.md | the plan is approved, a light plan is in place and you start the edits, or you amend, replace or close a plan |
