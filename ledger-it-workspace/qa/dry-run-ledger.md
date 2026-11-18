# ledger-it — QA dry-run ledger (worked example)

Manual-QA artifact: a concrete ledger produced by following ledger-it's SKILL.md + references on a toy task, to exercise each gate. Toy host task: "choose and implement a caching strategy for the /items endpoint." The domain work is the host's; this ledger only records it and applies the gates. This is a worked-example dry-run by the orchestrator, not an independent agent run.

## Header
```
Goal: choose + implement a caching strategy for /items
Host: planning + execution workflow (toy)
Purpose: execution
Started: 2026-11-15T00:00:00Z
Status: active
```

## Established facts
- [F1] /items p95 latency = 840ms — source: `bench-items.sh` output line 12 — established 2026-11-15T00:01Z

## Attempts
- [A1] tried: in-process LRU cache, no TTL — outcome: fail — evidence: "stale reads after upstream update; test_items_freshness FAILED (expected v2, got v1)" — why: no invalidation on upstream change, so stale data served — QUARANTINED
- [A2] tried: Redis cache with TTL=30s + write-through invalidation — outcome: success — evidence: "test_items_freshness PASSED; p95 840ms -> 95ms" — why: invalidation removes staleness; TTL bounds it
- [A3] tried: in-process LRU now that upstream emits change events — outcome: (allowed, see Gate 3 exercise) — new evidence: upstream now emits change events

## Gate exercises (the QA assertions)
- **Blind-retry impulse:** "retry A1 (in-process LRU, no TTL)". Read-before-act finds A1 QUARANTINED. New evidence? None (same code, same condition). **Gate 3 BLOCKS.** Blocked impulse recorded; chose A2 instead.
- **Retry-with-new-evidence:** "retry A1 now that upstream emits change events". New evidence = a changed condition bearing on why A1 failed. **Gate 3 ALLOWS**; recorded as new attempt A3.
- **Re-litigate impulse:** "re-open D1 (use Redis), maybe in-process is simpler". Read-before-act finds D1 SETTLED. New evidence contradicting the rationale? None (a preference, not evidence). **Gate 4 BLOCKS.** D1 stands.

## Decisions
- [D1] decided: use Redis cache (not in-process) — rationale: shared across instances + supports invalidation; in-process caused staleness (A1) — evidence: A1 failure + A2 success — SETTLED — re-open if: deployment becomes single-instance AND the invalidation requirement is dropped

## Spec change log
- [C1] 2026-11-15T00:10Z spec: TTL=30s -> TTL=5s — reason: "want fresher data"
- [C2] 2026-11-15T00:12Z spec: TTL=5s -> TTL=30s — reason: "5s hits the DB too hard"
- **Gate 5 on C2:** reversal detected (30s -> 5s -> 30s). **SURFACED to user:** "This is the 2nd change to TTL: 30s -> 5s -> 30s. This looks like flip-flopping. Let's settle TTL with a durable rationale (freshness target vs DB load budget) before continuing." Then settle as D2 with rationale + re-open condition.

## Re-entry exercise
Simulated new turn: read ledger FIRST. Reconstruct: F1 established (do not re-bench), A1 quarantined (do not retry blindly), D1 settled (do not re-argue Redis), TTL flip-flop surfaced (do not silently re-change). Resume from "next". Result: no re-derivation, no blind retry, no re-litigation, no silent re-flip-flop.

## Open items / next
- next: settle TTL (D2) with a freshness target + DB load budget, then implement.

## Artifacts to revert
- [ ] this QA dry-run file — QA scaffolding — revert: delete after the review