# Verifier brief

A worker on a cheaper model answered the units of the skills assigned to you. You re-check EVERY non-boilerplate answer and correct the wrong ones. Work from C:/Users/Lance/Dev/skills (node is on PATH). Read assimilation/WORKER.md first: its lane list, answer vocabulary and standing user decisions are the standard you judge against.

## Steps, in order
1. For each skill: `node assimilation/review.mjs <source> <skill>` prints every answered unit next to its answer (boilerplate drops are collapsed; use --all if a collapsed run looks suspicious). Add a file name to review one file. Text is cut at 170 characters: when a judgement depends on the full text, read the source file (folders in assimilation/sources.json, line numbers are in `node assimilation/list.mjs <source> <skill>`).
2. Judge each shown answer. It is WRONG when:
   - a unique rule, step, threshold or checklist item was dropped as boilerplate, example-only or runtime (a rule is only droppable as example-only if another unit states it; the cheaper model's note must be true);
   - methodology was dropped as runtime (only harness machinery may be: SDK calls, tool names, state folders, CLIs, hooks);
   - it was absorbed into a lane that does not fit what the rule does (see the lane list);
   - machinery was absorbed as if it were a rule;
   - a unit about a user-dropped topic (frontend frameworks, browsing, API design, release) was absorbed instead of dropped out-of-scope;
   - the note is missing, vague or false.
   Section names that differ in wording but mean the same thing are NOT wrong; leave them.
3. For each wrong answer: `node assimilation/unanswer.mjs <source> <skill> <file> <from>[-<to>]` clears it (ranges are split safely), then `node assimilation/answer.mjs <source> <skill> <file> <from>[-<to>] ... --part <your id>` records the corrected answer. Use ranges.
4. Also scan the UNANSWERED rows: answer them or, when the original worker was told to report NEEDS-USER or DEFERRED-SWEEP, leave them and list them.
5. Finish each skill with `node assimilation/check.mjs <source> --skill <skill>`. Fix what it says. Skills reported NEEDS-USER or DEFERRED-SWEEP are expected to fail coverage only on those units.
6. Final message, at most 25 lines: per skill: units judged, units corrected, corrections by kind (e.g. "unique rule dropped as example-only: 7"), and an overall error rate for the group (corrected units divided by judged units). List up to five corrections the user should look at, and anything you could not decide.

Never edit any file except through answer.mjs and unanswer.mjs. Never delete anything else. Never commit.
