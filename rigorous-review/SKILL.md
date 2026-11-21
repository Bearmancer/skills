---
name: rigorous-review
description: Use at the end of every task before reporting done, committing or pushing, and whenever asked to review a diff, branch or PR, or for status or what is left. A fresh reviewer checks the diff against repo standards and the spec, then the repo is audited for unpushed or dirty work, stashes, clutter, unfinished markers, broken doc links and open EPIC items. One report, one verdict.
---

# Rigorous review

One flow every time: scope, review the diff, QA, audit the repo, report. There are no modes or flags; the situation decides what runs. The point is that nothing reaches "done" on the author's own say-so, and nothing is left behind in the repo that the owner would have to find later.

## 1. Scope

For each repo the task touched, run:

```
uv run --quiet <this skill>/scripts/review.py <repo> [--base <ref>]
```

It is read-only. It reviews from the upstream merge-base (only the working tree when nothing is unpushed). When the session's work is already pushed, pass `--base` with the commit before the session's first commit. It prints the diff scope (commits, files, size, standards files, spec candidates) and the audit findings, and exits 1 when anything needs action.

A diff of about 1000 changed lines or more cannot be reviewed properly in one pass: say so and propose how to split it (by commit, by file group, or by feature slice) instead of pretending to have read it.

## 2. Review the diff

The author never signs off their own work, so the review goes to one fresh subagent. Fill `references/reviewer-prompt.md` with what was built, the spec (the issue, the OpenSpec change, or the user's request quoted exactly), the base and head, and the standards files from step 1. Give it that crafted context, never the session history: the reviewer's value is that it sees only the work. Use the model `~/.agents/AGENTS.md` names for subagents.

A trivial diff (a typo, one line, no change in behaviour) is checked inline instead. So is any review run from inside a subagent: OpenCode allows one level of subagents by default (`experimental.subagent_depth` = 1), so a subagent cannot start a reviewer. Then walk `references/reviewer-prompt.md` yourself and label the verdict "self-review" in the report.

When the reviewer returns, check each finding against the code (callers, guards, tests) before reporting it. Drop what the code rules out. Keep low-confidence survivors as open questions rather than dropping them. A timeout or an empty reply means "not reviewed", never approval.

## 3. QA

If the change has something runnable (a CLI, script, server or page), run it yourself: the happy path the request names, the riskiest edge (empty, boundary, malformed), and one neighbouring behaviour that could have regressed. Record the command, what you expected and what you saw. With nothing runnable, report QA as unproven and say why. A row with no observed output is not a pass.

## 4. Audit the repo

Resolve every audit line from step 1 in the same turn:

- **state**: push unpushed commits when pushing is authorized. Uncommitted files, stashes, extra worktrees and local-only branches are somebody's work: finish it, commit it, or ask.
- **clutter, drafts, empty dirs, duplicates**: deletion candidates (handoff notes and scratch files are not deliverables here).
- **unfinished**: TODO/FIXME markers, unchecked boxes and skipped or deleted tests added by this work. Finish them or ask.
- **links**: fix broken paths. A line naming a deleted skill or folder means the deletion left a dangling reference behind.
- **epic**: open EPIC items that mention a stash, branch or path about to go. Read them before deleting anything: an open item may be the only record of why it exists.

To delete: list the exact paths with what the audit says about them, ask with the question tool, delete only the approved paths (never a wildcard), then rerun the script to prove they are gone.

## 5. Report

The last message, short:

```
Verdict: APPROVE | REQUEST CHANGES | NOT REVIEWED - one-line reason
Remaining items: N
Standards: [SEVERITY/confidence] file:line - problem -> fix   (most severe first)
Spec:      [SEVERITY/confidence] file:line - problem -> fix
Open questions: ...
QA: rows passed/total, or unproven + reason
Audit: one line per category - count and what was done
```

Severity: BLOCKER (security, data loss, broken function), MAJOR (must fix before merge), MINOR, NIT. Standards and spec findings stay under their own headings and are never ranked against each other: code can follow every standard and still build the wrong thing. Any BLOCKER or MAJOR at high confidence means REQUEST CHANGES. `Remaining items` counts open decisions, each also asked through the question tool; call the work done only at 0.

## When review feedback arrives

When someone else's review comments are in hand, follow `references/feedback.md` before changing any code.
