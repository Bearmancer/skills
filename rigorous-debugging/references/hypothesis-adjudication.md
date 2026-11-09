# Hypothesis adjudication (stages 5–6)

Stage 5's failure mode is not thin hypotheses but a list that never
confronts itself: five plausible lines, nothing forcing one to beat
another. A ranking is a comparison, so the chain makes the comparison
explicit:

- **Evidence tiers.** Rate the evidence behind each hypothesis, strongest
  first: `T1` controlled reproduction or uniquely discriminating artifact ·
  `T2` primary-source artifact with tight provenance (log line, diff,
  metric, file:line behaviour) · `T3` independent sources converging ·
  `T4` single-source code-path inference · `T5` circumstantial (timing,
  naming, stack order, resemblance to a past bug) · `T6` intuition or
  analogy. A T5–T6 backing never outranks a contradictory T1–T2 artifact;
  when something moves a hypothesis down the list, the journal says so with
  a `down-rank` line and one of the six named reasons. This is why "I just
  know it's X" costs a tier tag: the tag makes the knowing inspectable.
- **Default lanes.** Unless the evidence suggests a better partition, take
  at least one hypothesis from each of: **code-path / implementation**;
  **config / environment / orchestration**; **measurement / verification
  defect** — including the possibility that the loop or the repro itself is
  wrong. The third lane is mandatory because it is the easiest to forget: a
  zero-row or mismatch result is often a broken _question_ about the system
  rather than a broken system (premise audit in `references/error-trees.md`).
- **Convergence check.** Two hypotheses that reduce to the same mechanism
  are one hypothesis: merge them, journal `down-rank … merged-into-parent`.
  Similar wording is not convergence — lanes stay separate only while they
  imply different discriminating probes; that, or the same mechanism
  confirmed by independent evidence streams, is what convergence means.
- **Rebuttal round.** Before choosing, the strongest backup lane gets one
  shot at the leader, and the leader must answer with evidence, not
  assertion. An unanswered rebuttal changes the ranking, so the probe tests
  the rebuttal winner; one `decision` journal line records the answer and
  its locator. (Under a cause-found collapse the round is waived like the
  rest, with citations.)
- **Critical unknown + discriminating probe.** Stage 5's gate closes only
  with the single missing fact still keeping the top two apart
  (`critical_unknown`) and the cheapest observation that would separate
  them (`discriminating_probe`) — cheapest information yield per minute,
  not most interesting test. The ranked shortlist stays on the page even
  when one explanation dominates: the runner-up is what makes the leader's
  margin visible. Stage 6 runs that probe first unless the journal says why
  another ranks higher; "it was handy" is not a why.
- **Lenses.** Before the ranking locks, pressure-test the leader with the
  systems, premortem, and science lenses where the domain suggests them —
  `references/lenses.md`. A lens that surfaces nothing costs one journal
  line saying so.
PY