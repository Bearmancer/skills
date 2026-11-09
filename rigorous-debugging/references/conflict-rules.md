# Conflict rules

Where the parent disciplines disagreed, the chain sequences both rules
instead of picking winners:

- **Ranked breadth, single execution.** Generate 3–5 hypotheses at stage 5,
  test exactly one per cycle. A failed cycle returns to stage 5's ranking,
  not to stacking a second fix on the first.
- **Parallel evidence, serial fixes.** Single execution binds _changes_,
  not reads. When the top hypotheses live in different subsystems and each
  lane's evidence costs more than ~10 minutes to gather, run read-only
  tracer lanes in parallel — one hypothesis per lane, return contract in
  `references/lanes.md` — then merge the pooled evidence into one ranking
  before the rebuttal round. Probes that mutate the system and `attempt`
  lines stay serial and counted.
- **Test-before-fix where the seam is correct.** The regression test must
  exercise the real bug pattern as it occurs at the call site. When the only
  available seam is too shallow, record `MISSING-SEAM: <why>` — the missing
  seam is itself a finding about the architecture — and keep a post-fix
  recurrence guard as the backstop.
- **Fallbacks are interim, never final.** Safe defaults, graceful degradation,
  retries are allowed under pressure _while the investigation stays open_;
  each one gets a `[mitigation]` journal line and appears in Stage 8's
  record. Shipping a mitigation silently is the symptom-fix failure.
PY