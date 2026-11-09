# Cross-check lenses — pressure-testing a leading explanation

Use at stage 5 before the ranking locks, when a cause-found fires (as the
cheap sanity check the collapse rule doesn't waive away), and when the
circuit breaker trips. A lens earns its keep only if it surfaces a missed
explanation, a hidden dependency, or a weak inference; when none can, put
one journal line saying so and move on. Lenses are one-line checks, not a
second investigation.

## Systems lens — when the failure involves coordination

Ask: what queues, retries, timeouts, or backpressure sit between the
symptom and the suspected cause? What feedback loop could turn one error
into a storm — a health check re-spawning into a half-failed path, a retry
re-entering before the first attempt finished, a dedup guard living only on
the outer branch of a restart loop? Which upstream feeds this component
stale, partial, or out-of-order data? Which component boundary has no probe
on it yet (stage 3's boundary evidence)?

## Premortem lens — when the ranking feels finished

Assume the current best explanation is wrong or incomplete. What
observation would embarrass this ledger later? The classic answers:
_co-contributors_ — the fix that turns the loop green may have stepped over
a second defect adjacent to the cause (exactly what the Stage-9 post-fix
sweep collects as the collapsed-chain tax); and _the loop proves the
symptom, not the mechanism_ — a green revert-test says the variable
matters, not that it is the whole story. Name the one alternative failure
mode you would least like to find, then state which cheap artifact could
rule it out now.

## Science lens — when the evidence is comparative

Controls: is there a run identical except for the suspected cause? The
negative control (revert → red again) is already a stage-7 gate — apply the
same shape at stage 5 to the ranking itself. Confounders: what else differs
between the working and broken states — version, env var, data shape,
timing, machine? Measurement bias: does the probe observe what it claims,
at the right grain — a key applied across several entities, a filter whose
shape doesn't match the schema grain, a column name assumed portable across
runtimes (see `error-trees.md` premise audit). Discriminative power: do the
top hypotheses make _different_ predictions? A probe that cannot falsify
any hypothesis is theatre — replace it with the cheapest one that can
(kill the leader or the runner-up, not both-sides-maybe).
