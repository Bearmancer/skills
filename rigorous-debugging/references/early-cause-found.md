# Early cause-found: collapse, don't skip

Finding the cause during stages 2–4 is normal and good. The chain reacts by
**collapsing stages into citations, not by vanishing** — because a rail that
opens on a feeling of certainty is not a rail, while one that opens on a
recorded claim with a prediction keeps the discipline and drops the cost.

1. Raise it as a journal line: `[cause-found] <claim> @<discovery>` — where
   the discovery is evidence _already obtained_: a diff, the user's failing
   test, a stack trace, a closed research row. Pattern-matching from memory
   is not a discovery; that's a Stage-5 hypothesis wearing a costume.
2. Non-waivable core: stages 0, 1, 7, 8, 9. Stages 2–3 and 6 are usually
   already satisfied by what happened — quote it. The user's failing test _is_
   the loop; the observed symptom _is_ the repro.
3. Every waiver is written, never mental: `WAIVED(reason, locator)` in the
   gate field, licensed by the cause-found line. A bare waiver is a checker
   violation.
4. The cause claim carries a prediction: "if X is the cause, the loop goes
   green with X fixed, and red again on revert." Stage 7 must demonstrate it;
   record `negative_control: yes(<revert>)` or waive it with reason.
5. Stage 4 is deferred, not deleted: with any waiver in play, Stage 9 requires
   `post_fix_sweep: done(<rows closed>)` — the exhaustive sweep run cheaply in
   hindsight, which catches co-contributors the primary fix missed.
6. A failed shortcut is an attempt: log `REJECTED`, void the collapse,
   re-enter the chain at the stage where evidence contradicted the cause. The
   breaker counts it like any other fix.

Net effect: an honest early find costs about three minutes of citation
writing instead of thirty minutes of ceremony; a confident wrong find pays
immediately at the loop, mechanically, with a ledger trail showing exactly
where to re-enter.
PY