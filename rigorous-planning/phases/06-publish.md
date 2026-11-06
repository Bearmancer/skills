# P6: validate, publish, audit

Contract: gates, CLI and the state machine are in ../SKILL.md. This playbook is the detail for this phase.

## P6: validate and publish (fail-closed)

`publish` is allowed only after G4 has advanced the ledger to P5. It re-runs G0-G5, the evidence check and the size audit, stamps `plan_sha256`, sets phase P6 and only then marks the plan published. Any error exits 1, the `ERROR` lines are the report, and no plan is published; there is no partial credit. Hand off with one line: plan path, `plan_sha256`, gates passed, flags in force, branch. Feedback on a published plan: read all of it, clarify every unclear item before changing any, verify each against the code, push back with evidence, record each outcome as a decision or a supersede with a reason, then re-run `publish`. A `gate --id G5` run is the only accepted publish evidence.

## Audit plans (type `audit`)

The deliverable is a report, not a code change. Enumerate scope first (which repos, which states; for personal-repo audits exclude third-party forks and their upstreams) and record the inventory as measured facts. One task per finding group (stale or already fixed in code, duplicates, missing or conflicting labels, blocked or unclear, closed but not resolved), each with a `verify` that checks the claim against code or tracker state. Per issue the report gives evidence (`file:line` or URL), the finding class, and one recommended action in triage vocabulary (needs-info, ready-for-agent, ready-for-human, wontfix, close). Rank by leverage against risk and end with the top recommendation; an empty audit is stated plainly, and a finding without evidence is not reported. Tracker changes are a separate, owner-approved step per batch.
