# The plan file

Load this before you write `.rigor/plan.md` for the first time, and again whenever a block message mentions the format.

## Rules of the file

- The name is always `.rigor/plan.md`, at the project root (the folder holding `.git`; with no `.git` anywhere above, the project folder you work in, and the folder where you first write the plan becomes the root). Write it before any question, or any command or fetch whose result you will cite, because nothing is recorded until it exists. Never `plan-v2.md`, never a copy. Edit it in place.
- There is only ever one plan. A second job needs the `Replace plan` question first.
- The `name:` in the frontmatter is short kebab-case and does not change while the plan lives.
- Use LF line endings and plain Markdown.
- Headings, ids and status words below are read by a checker. Spell them exactly.

## Full path: the complete example

```markdown
---
name: dark-mode-settings
path: full
---
# Plan: Dark mode on the settings page

## Intent
- Outcome: The settings page can be shown in a dark colour scheme.
- User: People who use the app at night.
- Why now: Support gets weekly complaints about glare.
- Success: A user can switch to dark mode and it stays on after a reload.
- Constraint: No new dependencies.
- Out of scope: Dark mode on pages other than settings.

## Questions
- Q-1 [answered] Which pages get dark mode? -> Settings only
- Q-2 [open] Should the choice persist across devices?
- Q-3 [waiting Q-2] Where is the preference stored?

## Spec
### Behaviours
- B-1: When the user turns on dark mode, the settings page shall render with the dark palette.
- B-2: While dark mode is on, a page reload shall keep dark mode on.
### Criteria
- AC-1 (Covers: B-1): Toggling the switch changes the page background within one frame.
- AC-2 (Covers: B-2): After a reload with dark mode on, the page background is the dark colour.

## Claims
- C-1: prefers-color-scheme is supported in all target browsers -- doc: https://example.org/page "quoted passage from the page"
- C-2: the theme is read in exactly one place -- code: src/theme.ts:14
- C-3: the test suite passes today -- cmd: `npm test`

## Tasks
- [ ] T-1: Theme tokens and toggle state
  - Covers: AC-1
  - Edits: src/theme.ts, src/settings/page.tsx
  - Creates: src/theme/dark-*.ts
  - Depends: -
  - Verify: `npm test -- theme`
- [ ] T-2: Remember the choice across reloads
  - Covers: AC-2
  - Edits: src/theme.ts
  - Creates: -
  - Depends: T-1
  - Verify: `npm test -- theme-persist`

## Review
- F-1 [major] "AC-1: Toggling the switch changes the page background within one frame." -- not testable without a frame counter -> fixed
- F-2 [minor] "T-2: Remember the choice" -- title is vague -> rejected: the criterion it covers is specific
- No findings (round 2)
```

The example shows every status word at once. A real plan has no `[open]` or `[waiting]` question by the time the intent is signed, and no open finding by the time it is approved.

## What the checker reads

- Frontmatter: `name` (kebab-case) and `path` (`full` or `light`). Nothing else is needed.
- Headings are exactly `## Intent`, `## Questions`, `## Spec`, `## Claims`, `## Tasks`, `## Review`. Inside Spec, exactly `### Behaviours` and `### Criteria`.
- Extra `##` sections are allowed and ignored: `## Decisions`, `## Seams`, `## Risks`, `## Checkpoints`, `## Not doing`. Use them for notes people need.
- Ids are `Q-n`, `B-n`, `AC-n`, `C-n`, `T-n`, `F-n`. Each is unique within its kind and is never reused.
- Question status is `[open]`, `[answered]` or `[waiting Q-n]`. An answered line ends with `-> the user's answer`.
- Task sub-bullets are `Covers:`, `Edits:`, `Creates:`, `Depends:`, `Verify:` and optionally `Batch:`. Lists are comma separated. A dash means none.
- A finding has a severity (`[blocker]`, `[major]`, `[minor]`). The part after `->` is exactly `fixed` (no full stop after it), `rejected: <reason>` or `user: <decision>`. No `->` means the finding is still open.
- A claim ends with ` -- ` and one proof: `doc: <url> "<quote>"`, `code: <path>:<line>` or ``cmd: `<command>` ``.

## Light path: the complete example

Use it only when the job touches two or more files and the light check passes.

```markdown
---
name: fix-readme-links
path: light
---
## Files
- README.md
- docs/setup.md
## Steps
1. Find every link that points at the old docs site.
2. Replace each with the new address and open the page to confirm it loads.
```

One-file jobs write no plan. A light plan has no approval question; the file list is the scope.

## What each checkpoint needs

**Light check** (when you write a light plan). Every listed path is an exact relative path inside the project (no wildcards). At most 3 files, unless `quick` was the first word after the skill name (it lifts the count, never the risk rule). No path in a risky area: auth, security, secrets or env files, migrations, CI workflows, lockfiles, infrastructure, payments, `.claude`, `.git*` folders (`.git`, `.githooks`), `.husky`, `CLAUDE.md`, `AGENTS.md`. Only path patterns are matched; other kinds of risk are your judgement. If it fails, rewrite the plan as `path: full`.

**Sign intent** (asked after the intent is written). All six Intent lines are filled with real words (not `...`, `TBD`, `?` or `-`). No question is `[open]` or `[waiting]`. Every `[answered]` question has the user's recorded answer. An answer counts only if the question text began with its id (`Q-2: ...`) and was asked through the question tool. An answer typed in chat is not recorded: re-ask it. A question you can settle by looking it up is deleted from `## Questions` (a fact becomes a claim with proof).

**Approve plan** (asked after drafting and review). Two parts.

Drafted:
- The signed intent is unchanged.
- At least one behaviour. Every behaviour is covered by at least one criterion, and every `Covers:` on a criterion names a real behaviour.
- Every criterion is covered by at least one task, and every task `Covers:` names a real criterion.
- Every task has `Verify:` and at least one of `Edits:` or `Creates:`. `Covers: -` is allowed for a preparatory task, but every criterion must still be covered by some task.
- `Edits:` entries are exact paths with no `*` or `?`. Each exists today, or is listed under `Creates:` of a task it depends on. `Creates:` entries are exact paths that do not exist yet (once a plan is approved, and for a task already ticked, an existing file is not a gap; but if an approval is dropped and the plan is back in drafting, an unticked task whose exact `Creates:` file already exists is flagged: move that file from `Creates:` to `Edits:`), or globs with `*` or `?` in the file name only (no `**`, no wildcard folders; the name must not start with a dot and needs a letter or digit, so `*` and `.*` are refused). A glob never covers a file in a risky area such as `.env.local` or a lockfile; list such a file by its exact path.
- At most 5 files per task (`Edits` plus `Creates`) unless the task says `Batch: wide-refactor`.
- `Depends:` names real tasks and never loops.
- No file path appears on any behaviour (`B-n`) or criterion (`AC-n`) line. See spec.md for what counts as a path. (Other text in `## Spec` is not scanned, but keep paths out of it too.)
- Every claim has valid proof (see proof.md).

Reviewed:
- Both reviewers looked at the current spec. (After 3 rounds, a later spec change needs a `-> user: <decision>` finding instead; see review.md.)
- `## Review` is not empty and every finding has a disposition.
- No blocker is `rejected` unless the user decided it (`user: ...`).

## What you may write, by stage

`.rigor/plan.md` and `.rigor/map.md` can be written in every stage (the plan only as far as the stage allows; see below), and `GLOSSARY.md` and `docs/adr/` in every stage.

| Stage (named in the status note) | You may also write |
|---|---|
| none (no plan yet; no status note) | anything: nothing is blocked until a plan exists |
| invalid | nothing else; repair the plan so it parses |
| light | the files under `## Files` |
| light-invalid | nothing else; rewrite the plan as `path: full` |
| intent, drafting | nothing else |
| build | the paths named in a task's `Edits:` or `Creates:`; in the plan only ticks and `## Review` edits |

Everything else is blocked. In build, the block message tells you to ask with `Amend plan`.

A repository nested in the project is part of the project: its files need the same plan. A folder with a `.git` FILE (a linked worktree or submodule) is an independent checkout and is not covered.

## The guard

The guard stops accidental edits of `.rigor`. Deliberate evasion through the shell is out of scope and not defended. A shell command naming `.rigor` is blocked while a plan is live; use the file tools.

## Rules the system does not check

These are on you. The system never looks at them.

- Facts are yours, decisions are the user's: never decide for the user, never fill in a default, ask every decision.
- Subagents: only the two reviewer spawns are checked (explicit model, no Fable, no `inherit`, no fork). Any other subagent follows the same rule by your discipline, and a reviewer's independence is on you.
- Nothing is cut from scope unless the user says so.
- A task touches only its own `Edits:` and `Creates:` paths (the system allows the paths of any task). Ticking a task needs no evidence: run `Verify:` and look at the output. Never lower the quality bar (no skipped tests, suppressions, removed assertions or lowered thresholds).
- Re-review after a fix to a blocker or major finding, and ask the user about real trade-offs (the system only requires a user decision for a rejected blocker).
- The number in `No findings (round n)`.
- Proof quality: the system checks that a doc URL was fetched and the quote is long enough, not that the quote is on the page. The source hierarchy and "never cite forums" are yours. Only lines under `## Claims` are checked; a factual statement elsewhere in the plan is not seen.
- Vague words in the spec.
- Prototypes live in a git worktree or a clone outside the project folder, never a plain branch in the same folder, and are never merged.
- Never edit project files from a shell during planning.
