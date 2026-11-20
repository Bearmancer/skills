# Layer 1 — The Record

The Record is the documentation rigor: what the ledger captures and how. Its job is to make the ledger a faithful, authoritative, always-current account of the work — in maximal detail — so the Gates (Layer 2) have something true to enforce. A record that is stale, paraphrased, thin on reasons, or missing its change history cannot stop a deathloop.

## The ledger file

- **Location:** `LEDGER.md` at the repo root, committed. Work with no repo goes to `C:\Users\Lance\.agents\ledgers\<concern>\LEDGER.md`. Never in temp or Desktop.
- **One writer at a time.** Before writing, check for `LEDGER.md.lock` beside the file. If another session holds it, stop and tell Lance. Otherwise create it with your session id, and delete it when you hand back. Add `*.lock` to the repo's ignore rules, so a lock is never committed.
- **Durable.** The ledger survives compaction and turn boundaries, and it persists after the work because it is the deliverable.
- **Journal, then modify.** Before you create any transient artifact, add it to "Artifacts to revert" with its revert command. The ledger itself is never listed there; it is kept.

## The schema

### Header
```
# Ledger — <work name>
Goal: <one line>
Host: <skill / harness / task being recorded>
Purpose: execution | debugging | planning | other
Started: <ISO timestamp>
Status: active | paused | done
```

### Established facts
Proven observations the work builds on. Each carries the verbatim value, its source, and when it was established. These are never re-derived. If a fact is later falsified, mark it falsified with the new evidence — do not silently delete it.
```
- [F1] <verbatim fact> — source: <file:line | command | log> — established <ISO>
```

### Attempts
Every attempt to change or verify the outcome — including hypotheses the host tests. Each carries what was tried, the outcome, verbatim evidence, WHY it succeeded or failed, and its quarantine status.
```
- [A1] <ISO> tried: <what> — outcome: fail — evidence: <verbatim> — why: <reasoning> — QUARANTINED
- [A2] <ISO> tried: <what> — outcome: success — evidence: <verbatim> — why: <reasoning>
```
The **why** is the load-bearing field: it is what lets a future turn judge whether a retry is justified. A failure without a reason cannot be quarantined meaningfully. The record should be sufficient to **reproduce the failure**: the command or input, and the observed output.

### Decisions
Every choice the work commits to — including proposals accepted or rejected. Each carries the decision, its rationale, evidence, status, and the re-open condition.
```
- [D1] <ISO> decided: <choice> — rationale: <why> — evidence: <verbatim> — SETTLED — re-open if: <condition>
```

### Spec change log
Every change to the spec, requirements, or a decision — chronological, so oscillation is visible. Each carries what changed (from -> to), when, and the stated reason. This is the raw material for flip-flop detection (Gate 5).
```
- [C1] <ISO> spec: <from> -> <to> — reason: <stated reason>
```
Record every change, even small ones and even reversals. A reversal is not deleted; it is appended, so the pattern A->B->A stays visible.

### Open items / next
What is unresolved and what happens next. This is the re-entry handoff: a returning agent reads it to know where to resume.
```
- [ ] <open item>
- next: <the single next action>
```

### Artifacts to revert
Transient things created (scratch scripts, instrumentation, temp files), each with its revert command.
```
- [ ] <path> — <what it is> — revert: <command>
```

## Writing rules

- **Real-time.** Write the outcome the moment an attempt or decision happens. Batching at the end leaves a window where compaction loses state and the deathloops re-open.
- **Maximal detail.** Capture the full substance: the exact command or input, the verbatim output, the complete reasoning, timestamps, and from->to for every change. Thin entries are what let deathloops hide. Detail on substance; purge only noise.
- **Verbatim evidence.** Copy the raw value with its source. "It seemed to fail" is not evidence; the actual error or output is.
- **Reasons, not just results.** Record WHY an attempt failed and WHY a decision was made. The reason is what prevents blind retry and re-litigation.
- **Append, do not overwrite history.** Attempts and decisions are a log: add new entries and mark status changes, but keep the record of what happened.
- **Moot-purge, carefully.** Remove stale, duplicate, or superseded noise so the ledger stays legible. But never purge a quarantined failure or a settled decision — those are the anti-deathloop memory; deleting them re-enables the loops. Purge noise, keep the memory.
- **Redact secrets.** Write `<REDACTED>`; keep credentials in env vars, not the ledger.

## What the Record is not

It is not a narrative report, not a todo list, and not a place to re-derive established facts. It is the authoritative, maximal-detail, always-current account of what happened, what was decided, and what changed — detailed on substance, purged of noise. The domain work belongs to the host; the Record only holds its trace, and never rewrites the host's logic.
