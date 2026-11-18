# Layer 2 — The Gates

The Gates are the anti-deathloop enforcement: how the ledger is consulted and updated so the three deathloops cannot fire. The Record (Layer 1) gives the gates something true to enforce; without the gates, the record is a diary nobody reads and the loops still happen.

## The five gates

### Gate 1 — Read before act
Before any attempt or decision, read the relevant ledger sections: Established facts, Attempts, Decisions. Know what is already proven, what has been tried, and what is decided before you act. Acting without this read is how all three deathloops start.
- Before an attempt: check Attempts for the same or a trivially similar approach.
- Before a decision: check Decisions for an existing settled decision on the same point.
- Before deriving a fact: check Established facts; if it is there, use it, do not re-derive.
- Before a spec change: check the Spec change log and Decisions for the recent history of this point, so a reversal is caught (Gate 5).

### Gate 2 — Write after act
Immediately after any attempt, decision, or spec change, record it: outcome, verbatim evidence, and the reason (and from->to for a spec change). Real-time, not batched. An unrecorded attempt is a future blind retry; an unrecorded decision is a future re-litigation; an unrecorded spec change is a hidden flip-flop.

### Gate 3 — Failure quarantine (kills blind retry)
A failed attempt is quarantined with its reason. To retry it — or a trivial variant — you must state **new evidence**: what changed that makes this worth retrying.
- New evidence: a new observation, a changed condition, or a falsified assumption that bears on why it failed.
- Not new evidence: a hunch, "maybe it will work this time", re-reading the same code, or re-running the same reasoning.

If there is no new evidence, do not retry. Pick a different approach and record it as a new attempt.

### Gate 4 — Settled-decision gate (kills re-litigating)
A settled decision is closed with rationale and evidence. To re-open it, you must present **new evidence that contradicts the rationale** — not a re-run of the same reasoning, and not a preference.
- New evidence contradicts the rationale: re-open, record the new evidence, make a new decision, and mark the old one superseded (keep it).
- No new evidence: the decision stands. Build on it; do not re-argue it.

### Gate 5 — Flip-flop detection (kills spec flip-flopping)
The spec change log makes indecision visible. After each spec change, scan the recent history of that point for a **flip-flop**:
- A reversal: the change returns to a state just left (A->B, then B->A).
- A return to a previously rejected option.
- The same decision point changed repeatedly (a high churn count).

When a flip-flop is detected, surface it to the user — non-judgmentally, with the history: "This is the Nth change to X: A->B->A. This looks like flip-flopping. Let's settle X with a durable rationale before continuing." Then record a settled decision with its rationale and re-open condition. The goal is to make the oscillation visible so it can be broken, not to silently absorb another reversal. This gate is a mirror for the user's indecision, not just a guard on the agent.

## The new-evidence test (the shared rule)

Both the quarantine and the settled gate turn on one question: *what is actually new?*
- Counts: a new observation (a value you had not seen), a changed condition (the environment, input, or state is different), or a falsified assumption (something you relied on is now shown false).
- Does not count: re-deriving the same logic, re-reading the same source, a feeling, or "let me just try again".

State the new evidence explicitly in the ledger before revisiting. If you cannot name it, you are in a deathloop — stop and choose a different path.

## Re-entry protocol (the across-turns guarantee)

On resume, after compaction, or on a new turn picking up this work:
1. Read the ledger first, before any action.
2. Reconstruct state from it: Established facts (do not re-derive), Attempts (do not blindly retry quarantined ones), Decisions (do not re-litigate settled ones), Spec change log (do not silently re-flip-flop), Open items / next (where to resume).
3. Continue from "next". Do not restart the work or re-derive what the ledger already holds.

This is what makes the ledger durable working memory for the same agent across turns.

## How the gates map to the deathloops

| Deathloop | Gates that kill it |
|---|---|
| Blind retry of a failed attempt | Read-before-act (see the quarantine) + Failure quarantine (new evidence to retry) |
| Re-litigating settled decisions | Read-before-act (see the settled decision) + Settled-decision gate (new evidence to re-open) |
| Spec flip-flopping (user indecision) | Spec change log + Flip-flop detection (surface the oscillation, settle durably) |

Write-after-act keeps the gates supplied; re-entry keeps them alive across turns.

## Enforcement is discipline, not tooling

The gates are behavioral rules any agent follows, in any harness. Where a harness offers hooks or pre-action checks, they can reinforce the gates mechanically (for example, block an action that matches a quarantined attempt unless new evidence is recorded). But the sidecar works as discipline anywhere: read before act, write after act, new evidence to revisit, surface flip-flops.

## When a gate blocks you

If a gate stops you — a retry with no new evidence, a re-open with no new evidence, or a detected flip-flop — that is the sidecar working, not an obstacle. Record the blocked impulse in the ledger so it is not silently re-attempted, then choose a different approach, or escalate to the user if genuinely stuck. Do not bypass the gate.