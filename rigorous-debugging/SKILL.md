---
name: rigorous-debugging
description: "Evidence-gated debugging: build a red feedback loop, rank hypotheses, prove the root cause, then fix; 3-attempt circuit breaker."
---

# Rigorous Debugging

Two axioms carry everything below:

1. **You cannot fix what you cannot reproduce.** The moment you read a stack
   trace your instinct names a cause; that instinct is where fix-thrash
   begins. Every stage exists to make the cause _findable_, not guessable.
2. **Discipline that isn't recorded isn't enforced.** A prose checklist is
   skipped under pressure; a ledger file with an unfilled gate is visible to
   you, the checker script, and the next session.

## Redaction rule

Redact every secret to `<REDACTED>` before it is shown or pasted anywhere.
Build loops against env vars so credentials stay in the environment, not in
what gets captured. If the redacted version isn't enough to diagnose, say so
and ask the user.

## Commands

Commands that may run 60 s or more: tee output to a log, end the log with a
`DONE` line, and run detached with `Start-Process pwsh -WindowStyle Hidden
-PassThru`, then read the log with `Get-Content`. Discover by reading whole
files or with search tools; `head` and `tail` are denied.

## The ledger protocol

At Stage 0 copy `assets/LEDGER-template.md` to
`./.rigor/debugging/<slug>/LEDGER.md` at the workspace root (create the
folder). Fill stages in order; an exit artifact is pasted evidence, never a
claim that it worked. Before acting on stage N, confirm stage N-1's required
fields are filled. Append one journal line per event. Vocabulary, layers and
the checker: `references/ledger-protocol.md` (read when recording a journal
line or running the audit).

## The chain

| Stage | Name     | Exit artifact (gate fields)                                                                                                                           |
| ----- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0     | STOP     | changes halted, evidence pasted redacted                                                                                                              |
| 1     | LOOP     | one command, run once, red-capable · deterministic · fast · agent-runnable                                                                            |
| 2     | REPRO    | user's exact symptom confirmed; minimal scenario, load-bearing only                                                                                   |
| 3     | SCOPE    | failing layer named; boundary evidence at each component edge                                                                                         |
| 4     | RESEARCH | every source row `consulted(locator)` or `N/A(reason)`                                                                                                |
| 5     | HYPOTH   | 3–5 ranked falsifiable hypotheses with evidence tiers, rebuttal round answered, `critical_unknown` + `discriminating_probe` named; exactly one chosen |
| 6     | PROBE    | discriminating probe run first (or substitution journalled); probes mapped 1:1 to predictions; one variable changed                                   |
| 7     | FIX      | regression test red→green at a correct seam (or `MISSING-SEAM` note); one change                                                                      |
| 8     | VERIFY   | original un-minimised loop green + full suite + build + e2e spot check; mitigations listed                                                            |
| 9     | CLOSE    | tags stripped, prototypes cleaned, post-fix sweep (if waivers), breaker state, root cause in commit                                                   |

Entry rails:

- Hold edits until evidence is stable (0). Errors compound; a red build
  walked past becomes six.
- Build the loop before the cause (1). Reading code to build a cause before
  the loop is the failure this chain prevents.
- Close research rows before hypothesising (4). Most "mystery" bugs are
  already documented.
- Change one variable at a time (6). Simultaneous changes can't be
  attributed.

Stage detail lives in references — read them when the stage calls for it:
`references/loop-recipes.md` (stage 1), `references/error-trees.md` (stage 3),
`references/research-sources.md` (stage 4), `references/lenses.md` (stage 5),
`references/lanes.md` (parallel read-only lanes), `references/guard-tables.md`
(re-entry triggers), `references/ledger-protocol.md` (journal and checker),
`references/hypothesis-adjudication.md` (stage 5–6 ranking),
`references/early-cause-found.md` (cause found in stages 2–4),
`references/conflict-rules.md` (conflicting hypotheses, fallbacks),
`references/circuit-breaker.md` (three failed attempts).

## Hypothesis adjudication (stages 5–6)

The ranking is a comparison, not a list. Stage 5 closes only with
`critical_unknown` and `discriminating_probe`; stage 6 runs that probe first
unless the journal says why another ranks higher. Full rules:
`references/hypothesis-adjudication.md` (read at stage 5).

## Early cause-found: collapse, don't skip

A cause found in stages 2–4 collapses stages into citations, never skips
them. Non-waivable core: stages 0, 1, 7, 8, 9. Full procedure:
`references/early-cause-found.md` (read when a cause surfaces in stages 2–4).

## Conflict rules

Ranked breadth with single execution; parallel evidence with serial fixes;
test-before-fix at a correct seam; fallbacks are interim, never final. Full
rules: `references/conflict-rules.md` (read when hypotheses conflict, lanes
overlap, or a fallback is opened).

## The circuit breaker

Three failed `attempt` lines freeze the pipeline. Stop, write what the
attempts showed, and take it to the human partner before any fourth attempt.
Full procedure: `references/circuit-breaker.md` (read after the third failed
attempt).

## Simple bugs are on the chain too

Every stage runs for a one-line bug — but a stage's gate is a _property_, not
a duration. A two-second repro still gets typed into the ledger. The cost
scales down; the gate never opens early.
PY