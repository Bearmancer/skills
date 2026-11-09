# Stage 4 — the exhaustive research sweep

No hypothesis may be written until every row below is closed
`consulted(<locator>)` or `N/A(<reason>)`. Why: the single biggest cause of
wrong fixes is theorising in a vacuum — the answer is usually already
recorded somewhere: a commit, a working example, an upstream issue, a doc.

Each row records what you _actually looked at_ — a file:line, a commit SHA, a
URL, a command and its result — not a feeling of familiarity. A bare row name
is an unfilled gate.

## The rows

1. **Project docs and decisions** — GLOSSARY.md, ADRs, README, architecture
   notes. Terminology mismatches between what the code should do and what you
   assume are a whole class of "bug" that is really a misread contract.
2. **Recent changes** — `git log` on the failing area, diffs of new
   dependencies, config and environment changes, deploys. For "worked
   yesterday": identify the good and bad states, and where possible bisect.
3. **Working examples** — code in this repo that does it right. What is
   similar that works? Enumerate every difference, however small; never
   assume "that can't matter".
4. **Reference implementations** — if following a pattern or SDK usage, read
   the complete reference, not a skim. Partial understanding guarantees bugs.
5. **Official docs** — for the version actually installed, not your memory
   of it. Look for new releases, renamed APIs, changed defaults, recent fixes;
   training data goes stale quietly.
6. **Upstream issues / changelog** — has someone hit this exact failure?
   "Fixed in vX.Y" is a root cause _and_ a plan in one line.
7. **Environment deltas** — versions, OS, env vars, data shape (empty vs
   populated), CI vs local, machine vs machine.

The sweep feeds Stage 5 directly: every hypothesis should name the ledger
rows that produced it, so theorising stays traceable to evidence.

## The post-fix confirmation sweep (the collapsed-chain tax)

When stages 2–4 were collapsed under a cause-found, row-closing moves to
Stage 9, run cheaply in hindsight because you now know what to look for:

- **Recent changes**: does the diff of the introducing commit fully explain
  the symptom, or only part of it?
- **Working examples / reference**: does the fix now match the correct
  pattern, or does it invent a fifth way?
- **Upstream / docs**: is the fix the sanctioned one, or will it break on the
  next version?
- **Environment deltas**: could any other delta have produced the same
  red?

The point is co-contributors: a fix that turns the loop green may have
silently stepped over a second defect adjacent to the cause. Record the
sweep as `post_fix_sweep: done(<rows re-checked, outcome>)`; any new finding
from it becomes journal lines, not a drive-by fix.
