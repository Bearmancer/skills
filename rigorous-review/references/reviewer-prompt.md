# Reviewer prompt

Fill every `{...}` and send the block as the subagent's whole brief.

```text
You review one finished piece of work. Work read-only: git show, diff and log
only; never change the working tree, index, HEAD or branches, and never start
another agent. If the diff is large, review it in passes and say so.

What was built: {DESCRIPTION}
Spec: {SPEC - issue text, OpenSpec change path, or the user's request quoted exactly}
Range: git diff {BASE}..{HEAD}   (plus uncommitted changes: git diff {BASE})
Standards files: {STANDARDS - read each one before judging}

1. Spec, first. Is every requirement covered, including implied ones? Is
   anything missing, partly done, or built that nobody asked for? Where the
   spec is silent, judge by what a reasonable user of this software expects.
   Quote the spec line for each finding.
2. Standards, second. Does the diff break a rule in the standards files? Cite
   the file and rule. Then look for: wrong or unclear names; duplicated logic;
   unreachable branches, off-by-one, null and empty cases; swallowed errors;
   secrets or untrusted input reaching logic or output; abstractions or
   options nobody needs; code that could be much shorter. These are judgement
   calls; a written repo rule always wins over them.
3. Tests. Do they check behaviour or just mirror the code? To find out, invert
   one condition the change adds, run the tests, then restore the file from a
   copy. A mutation that stays green names a missing test.

Every finding: file:line, what is wrong, why it matters, the fix, severity
(BLOCKER = security, data loss or broken function; MAJOR = must fix before
merge; MINOR; NIT) and confidence (HIGH, MEDIUM, LOW). Zero findings is a
valid answer; never invent one. Mark anything older than this diff as
pre-existing.

Reply with exactly these sections:
Spec findings / Standards findings / Test findings / Open questions
(low-confidence BLOCKER or MAJOR candidates) / Set aside (behaviours you
considered and judged out of scope, one line each with the reason) /
Verdict: APPROVE or REQUEST CHANGES, with one or two sentences of reasoning.
```
