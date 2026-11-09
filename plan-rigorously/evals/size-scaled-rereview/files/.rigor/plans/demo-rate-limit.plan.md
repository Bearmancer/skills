# Plan: demo-rate-limit

status: draft | tier: 1 | type: implementation | spec: spec.yaml

## Requirements
**Problem.** Public API endpoints accept unlimited requests per client, so one noisy client can degrade service for everyone.

**Solution.** Add a per-client request limiter in front of the public API that rejects excess requests with a clear retry hint.

**Success criteria**
1. A client exceeding its limit receives a rejection with a retry-after value.
2. Clients under the limit see no behavior change.

**User stories**
1. As an API consumer, I want a clear retry hint when limited, so that I can back off correctly.
2. As an operator, I want limits configurable per client tier, so that paid tiers get more headroom.
3. As a maintainer, I want limiter state behind one interface, so that the store can be swapped later.

**Test seams:** S1 Limiter interface

## Ideal state and gaps
| Party | Ideal property | Reason |
|---|---|---|
| API consumer | Receives a retry hint whenever limited | Lets clients back off without guessing |
| Operator | Limits differ per client tier | Paid tiers need headroom |

| Gap | Description | Reason |
|---|---|---|
| G1 | No limiter exists | Nothing rejects excess requests today |
| G2 | No per-tier configuration | All clients would share one limit |

## Global constraints
- Standard library only; no new runtime dependencies.

## Definition of done
- tests pass
- build passes
- lint clean

## Must not have
- Distributed or persistent limiter state

## Proposals and audit
| Id | Kind | Claim | Verdict | Tools |
|---|---|---|---|---|
| P1 | internal | The handler is the single entry point for public requests. | supported | codegraph |

## Evidence path
Test strategy: tdd
- Claim C1: Excess requests are rejected with a retry hint (owner task T1)
- Claim C2: Tier limits are applied (owner task T2)
- Path EP1 (chosen): Unit tests against the limiter interface; limits: Does not cover the wire format
- Path EP2: Manual curl against a running server; limits: Not repeatable
- Affordance fake clock (durable, task T1)

## Phases
### PH1: Limiter core
- [ ] T1. Fixed-window limiter with retry hint (size S, depends none, CRITICAL)
  - Covers: ['G1']
  - File: src/limiter.py (create, verified 2026-11-08)
  - Anchor: A1
  - Consumes: []; Produces: ['RateLimiter']
  - Acceptance 0: Requests over the limit are rejected with a retry-after value
  - Acceptance 1: Requests under the limit pass
  - Verify (happy): `python -m pytest tests/test_limiter.py -k over_limit` expect rejected with retry-after
  - Verify (failure): `python -m pytest tests/test_limiter.py -k under_limit` expect passes
- [ ] T2. Per-tier limits (size S, depends ['T1'], CRITICAL)
  - Covers: ['G2']
  - File: src/handler.py (modify, verified 2026-11-08)
  - Anchor: A2
  - Consumes: ['RateLimiter']; Produces: ['TierConfig']
  - Acceptance 0: Each client tier uses its configured limit
  - Verify (happy): `python -m pytest tests/test_tiers.py -k configured` expect tier limit applied
  - Verify (failure): `python -m pytest tests/test_tiers.py -k unknown_tier` expect falls back to default limit
- [ ] CP1. Checkpoint after task T2
  - Verify: python -m pytest

## Critical path order
| Task | Dur | ES | EF | LS | LF | Slack | Critical |
|---|---|---|---|---|---|---|---|
| T1 | 1 | 0 | 1 | 0 | 1 | 0 | yes |
| T2 | 1 | 1 | 2 | 1 | 2 | 0 | yes |

Waves (tasks that can run together): [T1]; [T2]

## Final verification
- [ ] FV1. Limiter rejects and tiers apply end to end - `python -m pytest` expect all pass

## Review focus
- Retry hint is accurate at window edges -> expected: No off-by-one (task T1)

## Risks
| Risk | Impact | Mitigation | Detection |
|---|---|---|---|
| Clock skew at window boundaries | Occasional early rejection | Fake clock tests | Boundary test |

## Deferred question block
None open.

