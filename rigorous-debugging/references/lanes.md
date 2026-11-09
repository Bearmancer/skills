# Tracing lanes — optional parallel evidence collection (stages 5–6)

The default is a single lane: _ranked breadth, single execution_. Lanes are
the exception for expensive evidence — multi-service reproductions, log
mining across hosts, benchmark runs over two configs. When the top two or
three hypotheses live in different subsystems and each lane's evidence
would take more than ~10 minutes, spawn read-only tracer lanes in parallel
(subagents or background jobs), one hypothesis per lane, then merge.

Rules that keep lanes from becoming noise:

- **Deliberately different.** Lanes pursue _different_ explanations, not
  the same explanation twice. If two lane prompts would return the same
  evidence list, that is one lane; pick the runner-up by what would
  falsify the leader.
- **Read-only.** A lane may run, log, probe, and measure — it may not
  edit. The one-variable rule binds changes: mutating probes, `attempt`
  lines, and fixes stay serial and breaker-counted.
- **Return contract.** Each lane comes back in the same shape so the merge
  is mechanical: Lane · Hypothesis · Evidence For · Evidence Against &
  Gaps · Evidence Strength (tier T1–T6, per SKILL.md) · Critical Unknown ·
  Best Discriminating Probe · Confidence. A lane that returns prose is
  re-asked once, structured.
- **Merge, don't concatenate.** The lead re-ranks on the pooled evidence:
  lanes reducing to one mechanism merge (`down-rank … merged-into-parent`);
  the ranked shortlist survives even when one lane dominates; the rebuttal
  round runs against pooled evidence, not per lane. Two lanes _saying the
  same thing_ is not corroboration — convergence requires the same root
  mechanism or independent evidence streams.
- **Budget.** Lanes are for expensive evidence only. Three greps that each
  take 90 seconds are a serial job wearing a lab coat.

Worked shape of a lead prompt: (1) restate the observation exactly;
(2) name the 2–3 deliberately different hypotheses with their tiers;
(3) per lane, gather evidence for and against, rank its strength, name the
critical unknown and best discriminating probe; (4) apply the lenses where
relevant (`lenses.md`); (5) return one merged ranking with the rebuttal
answered, the critical unknown, and the single probe stage 6 will run.
