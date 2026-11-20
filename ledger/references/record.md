# The Record

What a ledger captures and how. Its job is a faithful, current, maximal-detail account of the work, so the gates (`gates.md`) have something true to enforce. A record that is stale, paraphrased, thin on reasons, or missing its change history cannot stop a deathloop.

Where the file lives and how the write lock works are defined once, in `SKILL.md` ("Where it lives", "Write lock").

## Layout: one file, one section per unit of work

A repo (or no-repo concern) has one `LEDGER.md`. Each unit of work is its own `##` section, so several pieces of work can share the file and one closing never seals another.

```
# Ledger - <repo or concern>

## <task name> (<ISO start>)
Goal: <one line>
Concern: <EPIC concern this serves, or "none">
Purpose: debugging | execution | migration | build | other
Started: <ISO timestamp>
Status: active | paused | done

### Established facts
### Hypotheses
### Attempts
### Decisions
### Spec change log
### Resume point
### Artifacts to revert
```

`Status: done` seals that section only. New work in the same repo opens a new section.

## The sections

### Established facts
Proven observations the work builds on: the verbatim value, its source, when it was established. Never re-derived. A falsified fact is marked falsified with the new evidence, not deleted.
```
- [F1] <verbatim fact> - source: <file:line | command | log> - established <ISO>
```

### Hypotheses
What you believe before it is proven, and how you will test it. Each one ends confirmed (it becomes a fact) or refuted (with the evidence).
```
- [H1] <ISO> belief: <claim> - test: <how> - status: open | confirmed -> F<n> | refuted: <evidence>
```

### Attempts
Every attempt to change or verify the outcome, as a full diagnostic trace:
```
- [A1] <ISO> hypothesis: H<n> - reasoning: <why this fix over the alternatives>
  - executed: <exact command, edit or input>
  - outcome: success | fail - evidence: <verbatim output, error or exit code>
  - why: <why it worked or failed>
  - next: <why the next step follows from this outcome>
  - QUARANTINED (on failure)
```
The **why** is the load-bearing field: it lets a later turn judge whether a retry is justified. A failure without a reason cannot be quarantined meaningfully. The entry should be enough to **reproduce** the result: the command or input, and the observed output.

### Decisions
Every choice the work commits to, including proposals accepted or rejected and Lance's rulings (verbatim, with the question they settled).
```
- [D1] <ISO> decided: <choice> - rationale: <why> - evidence: <verbatim> - SETTLED - re-open if: <condition>
```

### Spec change log
Every change to the spec, requirements or a decision, chronological, so oscillation is visible (gate 5).
```
- [C1] <ISO> spec: <from> -> <to> - reason: <stated reason>
```
Record every change, even reversals. A reversal is appended, so A->B->A stays visible.

### Resume point
Where this unit of work picks up after compaction or hand-off. Remaining backlog belongs in the EPIC, not here.
```
- next: <the single next action for this work>
```

### Artifacts to revert
Transient things created (scratch scripts, instrumentation, temp files), journaled before they are created, each with its revert command. The ledger itself is never listed; it is kept.
```
- [ ] <path> - <what it is> - revert: <command>
```

## Writing rules

- **Real-time.** Write the outcome the moment an attempt or decision happens. Batching leaves a window where compaction loses state and the deathloops re-open.
- **Maximal detail.** The exact command or input, the verbatim output, the complete reasoning, timestamps, and from->to for every change. Detail on substance; purge only noise.
- **Verbatim evidence.** Copy the raw value with its source. "It seemed to fail" is not evidence; the actual error is.
- **Reasons, not just results.** Why an attempt failed, why a decision was made. The reason prevents blind retry and re-litigation.
- **Append.** Attempts and decisions are a log: add entries and mark status changes; keep what happened.
- **Moot-purge carefully.** Remove stale or duplicate noise, but keep every quarantined failure and settled decision: they are the anti-deathloop memory.
- **Redact secrets.** Write `<REDACTED>`; keys stay in env vars, not the ledger.

## What the Record is not

Not a narrative report, not a plan, not a place to re-derive facts. It is the account of what happened, what was decided and what changed. The work itself is done by whatever skill or harness is running; the ledger holds its trace and leaves its logic alone.
