# Frontier: tool-only frontier rounds

Contract: gates, CLI and the state machine are in ../SKILL.md. This playbook is the detail for this phase.

**Every question is a `Q` row.** `question --label ... --question ... [--recommend "..."] [--blocked-by Q...]`. No prose questions, no confidence score, no one-question cadence.

**Round.** `round --asks Q1,Q3` records the ready frontier. A dependent question waits via `--blocked-by`; G2 recomputes the frontier from the rows and rejects an open `Q` that is in no round or asked before its blocker settled.

**Ask.** `ask --slug ...` prints JSON for the harness `question` tool. Call that tool with the exact JSON in the same turn; never end a turn with an active `Q`.

**Answer.** `answer --id Q1 --answer "..."` immediately. If the user stops, `decision --label early-exit` naming the open `Q` rows and `retract` each with a reason; or start with `--no-interview`.

**No tool.** If the `question` tool is unavailable, record a blocker; do not ask in prose.

**Intent.** The six intent fields are `Q` rows when missing; `intent --confirm --by user` only after the explicit yes. `--no-interview` fills them from request plus evidence, records assumed facts and `intent --assume`, and keeps `confirmed` false.

**Topology.** 1-6 components as `capability` rows or one `decision`; deferred components stay listed. A split the user must choose is a `Q` row.

**Counter-questions.** Contrarian after the first settled round, Simplifier at scope lock, Ontologist at 5+ open `Q` rows after round 2, Doubt before an irreversible decision. Each is recorded and produces `Q`/`D` rows; never a verdict.

**Other P3 work.** Quality bar, glossary, approaches, questionnaire and the doubt cycle are not frontier; follow `phases/03-clarify.md` and the matching `methods/` file.
