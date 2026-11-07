# P3: clarify

Contract: gates, CLI and the state machine are in ../SKILL.md. This playbook is the detail for this phase.

## P3: clarify (tool only)

**After Q0 this phase asks the user nothing.** The interview already happened (`phases/Q0-sweep.md`): every `q0-*` question is answered, intent is confirmed, and `autonomy` is recorded. Here you finish the bookkeeping the gate checks: put every answered Q in a recorded `round`, record the topology, and run the counter-questions below as self-answered `decision` rows (label `challenge-*`, with the chosen default and how to reverse it), not as new user questions. A fork that Q0 missed follows `phases/Q0-sweep.md` section 6: fact, logged default, or a first `owner-confirm-*` task. Under `autonomy = checkpoints`, the two approvals at design and task graph are the only later questions. The rest of this page is the mechanics for Q rows, rounds and answers, which Q0 also uses.

Every question is a `Q` row: `question --label ... --question ... [--recommend "..."] [--blocked-by Q...]`. The ready frontier is recorded with `round --asks ...`. `ask --slug ...` prints JSON for the harness `question` tool; call that tool with the exact JSON in the same turn. Record every answer with `answer --id ...`. A turn never ends with an active `Q`.

If the user stops, record `decision --label early-exit --decision "<open Q ids and why>"`, then `retract` each open `Q` with reason `user stopped clarification`; G2 blocks publish until the early-exit decision is superseded. Or start with `--no-interview`: fill the six intent fields from request plus evidence, record shaky ones as facts `--kind assumed`, run `intent --assume`, log the choices as decisions; `confirmed` stays false.

If the `question` tool is unavailable, record a blocker; do not ask in prose.

**Q rows.** A candidate becomes a `Q` row only when evidence cannot settle it; otherwise record a fact. There is no confidence score, no hypothesis line and no one-question-per-message cadence. `blocked-by` encodes prerequisites; G2 recomputes the ready frontier from the rows.

**Intent.** The six intent fields are `Q` rows when missing; `intent --confirm --by user` only after the user's explicit yes. Under `--no-interview`, no Q rows exist; the assumed path above applies. On the fast path with complete intent, one restate and one yes.

**Topology.** Record 1-6 components as `capability` rows (several) or one `decision` (one), with deferred components listed. When the user must choose the split, that choice is a `Q` row; never a prose list.

**Counter-questions** (once each, recorded as `challenge-*` decisions; produce `Q`/`D` rows, never a verdict):

| Trigger (countable) | Challenge | Row it forces |
| --- | --- | --- |
| First frontier round settled | Contrarian | `Q` |
| Scope about to lock | Simplifier | `Q` |
| 5+ `Q` rows open after round 2 | Ontologist | `Q` |
| Hard-to-reverse decision about to settle | Doubt | `doubt` |

**Domain terms and ADRs.** When a term resolves, record `--domain-term <term>` and a `fact --label term-<term> --locator GLOSSARY.md:<line>` whose quote matches `**Term**: definition _Avoid_: synonyms`; G4 rejects a closed term with no glossary fact. A hard-to-reverse decision passing the three-part test is recorded with `--adr --adr-file docs/adr/NNNN-x.md`; G3 requires the `adr-convention` fact.

**Quality bar.** Use `methods/quality-bar.md`; record the result as a decision labelled `quality-bar` (G4 requires it at L). It is not a separate interview: any open choice is a `Q` row.

**Questionnaire.** A decision owned by someone else becomes a blocked `Q` naming the recipient and a `to-questionnaire-<slug>.md` draft. It is a document, not a chat question.

**Approaches.** Before the spec, produce 2-3 grounded options with trade-offs and one recommendation; the pick is a decision row, and if the user must choose, it is a `Q` row.

**Doubt cycle** (mandatory for every `--irreversible` decision). (1) Name the decision in 2-3 lines. (2) Extract the smallest reviewable artifact plus contract. (3) Hand only artifact and contract to a fresh-context adversary with the adversarial review prompt. (4) Offer a cross-model second opinion; each external CLI use needs the user's explicit go-ahead. (5) Reconcile: classify each finding as contract misread, valid and actionable, valid trade-off, or noise; persist every finding with `finding --review doubt:<decision>:<cycle> --class ... --locator ...`. (6) Stop after 3 cycles, when the next cycle yields only trivial findings, or on user stop; escalate with `approve --token doubt-escalated`.

Gate **G2**. Interview mode needs an explicit yes recorded; flag mode needs the assumed-evidence check. A user saying "don't ask me anything" in prose does not waive G2: only `--no-interview` does, and then evidence fills every fact while remaining owner decisions become logged assumed decisions with consequence.
