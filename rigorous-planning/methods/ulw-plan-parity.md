# ulw-plan parity ledger

Every `ulw-plan` capability and where it lives in this skill. Status: **native** (already here before the integration), **assimilated** (added by the integration), **adapted** (kept, reshaped to the maximalist Q0 and run-through contract), **different** (deliberately not copied, with the reason). Update this file when either skill changes; an unlisted capability is a parity gap.

| # | ulw-plan capability | Home here | Status |
| --- | --- | --- | --- |
| 1 | Opening line `ULW-PLAN MODE ENABLED!` plus the working contract (persona, no-implementation pledge, workflow preview) | `phases/Q0-sweep.md` section 1 (`RIGOROUS-PLANNING MODE ENABLED!`) | assimilated |
| 2 | Plan mode is sticky: "do/fix/build X" means plan X; no implementers, even via subagents | SKILL.md "Planning only"; `phases/00-intake.md` item 2 | native |
| 3 | Intent routing CLEAR / UNCLEAR with an announced verdict; on-the-fence goes CLEAR; "interview me" overrides | `phases/Q0-sweep.md` section 1 item 3 | adapted (both routes run the full sweep; UNCLEAR uses examples-first) |
| 4 | UNCLEAR path never interrogates and adopts announced defaults | none | different: the maximalist Q0 contract asks first; a fork the user delegates ("you decide") still resolves to a logged default |
| 5 | Review modifiers ("high accuracy") are a gate trigger | plan-review is default-on (`--no-plan-review` opts out); depth is a `q0-verification` question | native + adapted |
| 6 | Two filters (evidence-answerable: explore; ideal state or default settles it) with owner-decisions always surviving | `phases/Q0-sweep.md` section 3; `phases/03-clarify.md` | assimilated |
| 7 | Explore before asking; orientation and research waves | `phases/Q0-sweep.md` section 2; `phases/02-evidence.md` | native + assimilated |
| 8 | LSP, then ast-grep, then rg discovery tiers | `methods/delegation.md` | assimilated |
| 9 | Ideal state for the affected user and gap rows as the north star | `phases/02-evidence.md` (`ideal-n`, `gap-n`); `methods/handoff-shape.md` | native |
| 10 | Topology lock: 1-6 independently succeeding components | `phases/03-clarify.md` Topology; `capability` rows | native |
| 11 | Ask with WHY; recommended default first; foggiest gap; clearance check | `phases/Q0-sweep.md` sections 3-4 | assimilated |
| 12 | Stance renderers (batch, one-by-one, examples-first) | `methods/stance.md` | assimilated |
| 13 | Fork-reply classification (four states) and the information-gain test | `methods/stance.md` | assimilated |
| 14 | Override gates ("stop asking", "you decide") and the final authorization block | `methods/stance.md`; the `q0-authorization` question | assimilated |
| 15 | Planning-style episode memory | `methods/stance.md` | assimilated |
| 16 | Counter-questions / contrarian grill | `phases/03-clarify.md` (as decision rows after Q0); `methods/delegation.md` | native + adapted |
| 17 | Test strategy confirmed every time (TDD, tests-after, none; agent QA always) | `q0-verification`; test-first default and `--no-test-first` | native + adapted |
| 18 | Extrinsic-constraint sweep (budget, stack, scale, audience, compliance) | `q0-constraints` | assimilated |
| 19 | Dynamic adversarial workflow (collect, verify, design, adversarial, synthesize); external content as claims; dirty worktree; misleading success | `methods/delegation.md`; `methods/evidence.md` | assimilated |
| 20 | Architect and ultrabrain advisory design lanes | `methods/delegation.md` | assimilated |
| 21 | Delegation prompt contract (TASK / DELIVERABLE / SCOPE / VERIFY / STOP WHEN), `WORKING`/`BLOCKED`, background spawn, no polling | `methods/delegation.md` | assimilated |
| 22 | Plan-consultant gap analysis | `methods/delegation.md` | assimilated |
| 23 | Plan-reviewer review: blocker-eligibility categories, bounded convergence, ledger frozen after round 1, digest-bound approval | `methods/delegation.md`; `plan-review` / `finding` rows; `plan_sha256` | native + assimilated |
| 24 | Review-round state machine with session receipts and compare-and-swap lifecycle | none | different: the append-only ledger, `plan-review --cycle` rows and `plan_sha256` at publish already bind a review to one plan hash; a second state machine would duplicate them |
| 25 | Approval gate (`Approval` question, `required: true`, durable `awaiting-approval`) | run-through: the `q0-authorization` answer is the single approval; checkpoints: the two pipeline approvals (`approve-design`, `approve-task-graph`) | adapted |
| 26 | Durable draft as the compaction-safe resume point | `ledger.json` plus `next` | native |
| 27 | Scaffold script (`scaffold-plan.mjs`) | `planning.mjs init` / `render` | native |
| 28 | Plan template: TL;DR first, Scope, Verification strategy, Execution strategy, Todos, Final verification wave (F1-F4), Commit strategy, Success criteria | `planSkeleton` (TL;DR, Spec, Tasks, Execution strategy, Final verification wave, Commit strategy, Success criteria) | native |
| 29 | Effort bands (Quick / Short / Medium / Large / XL), never hours or days | `methods/handoff-shape.md` TL;DR rule | assimilated |
| 30 | Per-todo `Recommended task executor category:` | task `--category`, rendered on the task row and used by `dag` | assimilated |
| 31 | Per-todo happy and failure QA scenarios with an evidence path | `methods/handoff-shape.md` (task `verify` plus `closes`; the Success criteria table maps each ideal-state row to its proving command) | adapted |
| 32 | Parallel waves and dependency matrix | `executionSection`; now plus the CPM critical path | native + assimilated |
| 33 | Handoff summary shape (what it drives, ideal state, shape counted from rows, added beyond the request, verification, execution handoff) | `methods/handoff-shape.md` | assimilated |
| 34 | `/ulw-execute <plan>` options (`--worktree`, `--make-pr`, `--ship`) named in the handoff | `methods/handoff-shape.md` | assimilated |
| 35 | Plan artifact grammar `- [ ] N.` under `.omo/plans/<slug>.md` | `plan.md` rows are `- [ ] T<n>.` under `.rigor/plans/<type>/<slug>/` | different: the ledger-first renderer keys rows by ledger id, and a gate checks them against the ledger. Closed by design: the plan path stays `.rigor/<dir>/plan.md` (a fixed rule), so no `.omo` export is written; an executor reads the `T<n>` rows and the `dag` / `todos` exports directly, and adapting to that grammar is the executor's job because execution is decoupled |
| 36 | Trivial-tier guard (no full adversarial loop for a tiny request) | Fast path (`--size S`), `--lean` | native |
| 37 | Stop rules: stop when exploration saturates, when the plan is complete; never begin execution | saturation (G1), `next` -> `DONE published`; "Planning only" | native |
| 38 | Close step: record 0-2 qualified planning-style episodes | `methods/stance.md` | assimilated |

| 39 | Review runs without a confirmation question | `next` names `plan-review --cycle 1` after G2; G3 requires persisted findings; `--no-plan-review` is the only opt-out | assimilated (script-enforced) |
| 40 | Plan carries no executor rules | `planSkeleton` handoff is plan content only; execution is a separate session | adapted (the ulw-plan decoupling) |
| 41 | Harness todo for every wave and task | `todos` command, `### Todo mirror` section, G4 check | assimilated (script-enforced) |
| 42 | Sizes are S or L only | `SIZES`, default L, `scopeSize` | different from ulw-plan tiers (Trivial / Standard / Architecture) |

Added beyond `ulw-plan` (this skill's own contract): the Q0 sweep gate (ten categories, none open), standing authorization and run-through, CPM scheduling, the `cpm` and `dag` commands, same-file serialization for parallel workers, the Q0 doubt loop, and multi-repo plans (`repo`, `assimilate`, `chat`, `purge`) with automatic purge of assimilated plans and chats after publish.
