# Tasks

Load this when the spec is settled and you start `## Tasks`.

## Vertical slices

A task is a thin slice that cuts through every layer it needs and can be checked on its own. "The settings page shows a working dark-mode switch" is a slice. "Add all theme tokens", then "add the switch" is not: the first task shows nothing.

- Each slice leaves the project building and its tests passing.
- Each slice is small enough for one focused session: about an hour of work, no "and" in the title, describable with three criteria or fewer.
- Do the preparing refactor first, as its own slice: make the change easy, then make the easy change.
- Put the riskiest or most uncertain slice early, so a failure shows up before the rest is built.
- If a task needs more than 5 files, split it. If it touches two unrelated subsystems, split it.

Dark mode example: "T-1 Theme tokens and switch" is a slice (tokens, the switch and its test, one visible result). "T-2 Remember the choice" depends on T-1 and edits a file T-1 created or changed.

Sizing guide: 1 file is tiny, 1 to 2 small, 3 to 5 medium (the limit), 6 or more must be split or marked as a batch (below).

## Task fields

```markdown
- [ ] T-1: Theme tokens and toggle state
  - Covers: AC-1
  - Edits: src/theme.ts, src/settings/page.tsx
  - Creates: src/theme/dark-*.ts
  - Depends: -
  - Verify: `npm test -- theme`
```

- **Covers:** criterion ids only. Never copy the criterion's words into the task. `Covers: -` is allowed for a preparatory task, but every criterion must still be covered by some task.
- **Edits:** exact paths, no wildcards. Each file exists now, or is listed under `Creates:` by a task this one depends on, directly or through other tasks. Look each one up before you write it.
- **Creates:** exact paths that do not exist yet, or globs with `*` in the file name only, such as `src/theme/dark-*.ts` (no `**`, no wildcard folders). If the file exists, it belongs under Edits.
- Include the test files the slice needs. They count toward the 5.
- **Depends:** task ids that must finish first, or a dash. No loops.
- **Verify:** a real command the project runs, with its flags, in backticks. Find it in the project's scripts or config; do not guess. Use the commands from the project's standing quality bar if it has one. If a command is cheap, run it once while planning so you know it works.
- Every criterion is covered by at least one task.

## Order

1. Put foundations before the things that use them: data shapes before functions, contracts before callers, fixtures before tests.
2. Tasks that touch the same files, or change shared state, are sequential (use `Depends:`). Independent slices have no `Depends:` between them and can run in parallel.
3. Where two sides need to be built in parallel, make the contract its own first task and let both sides depend on it.

## Checkpoints

The checker has no checkpoint field. Record them in an extra `## Checkpoints` section, for example "After T-2: run the full test command and the build, then show the user a one-line status." Place one after every 2 or 3 tasks, before anything irreversible, and at the end.

## Wide refactors

A wide refactor is one mechanical change (rename a field, change a shared type) that touches so many files that no single slice can land green. Do not force it into a slice. Sequence it as expand, migrate, contract:

1. **Expand:** add the new form beside the old one. Nothing breaks. One task.
2. **Migrate:** move callers over in batches sized by blast radius (per folder or package). One task per batch, each depending on the expand. The old form still exists, so the build stays green between batches.
3. **Contract:** delete the old form once no caller remains. One task, depending on every migrate batch.

Mark each migrate batch `Batch: wide-refactor`. That lifts the 5-file limit only. Every file is still listed by exact path, with no wildcards. Find them with a search and list them all.

## Migrations and removals

When the plan replaces or removes something people or code depend on:

- The replacement exists and is proven before the old thing is deprecated. A removal with no replacement is a question for the user.
- Count the consumers first. That count is a fact: look it up and make it a claim.
- Deprecation is advisory by default (warnings, a migration guide). Make it compulsory (a date) only when the old thing is unsafe or its upkeep is unsustainable, and then provide the tooling.
- If you own the old thing, you move its consumers. Do not announce and leave.
- Migrate one consumer at a time, then remove the old thing only after usage is verified at zero.
- Add before you remove. Additive steps can ship any time. Drops and renames go in their own later task, after nothing refers to the old shape.
- Data changes follow expand, backfill, switch reads, then contract. Backfills run in batches. Every migration has a tested way back, and that is a task `Verify:`, not a hope.
- Never change a column or field in place while old and new code run together.
- New features do not go into a system that is being deprecated.

## Do not plan these

- Work outside the criteria ("while we are here"). Note it in `## Not doing` or ask the user.
- Speculative abstractions for a second use that does not exist yet.
- A task whose only check is "it compiles".

## Before review

Walk the tasks top to bottom and check by eye what the checker will check: every path exists (or is a new exact path or glob), no task is over 5 files, every `Depends:` points to a real task and there is no loop (an earlier task is good practice, but the checker does not require it), every criterion is covered.
