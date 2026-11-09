# Execution flow

```
[Phase 1: Fast Account Census] ──► gh-sweep or scripts/sweep.py
         │
         ├──► If no items need updates & no stale branches:
         │      Print census table ➔ end of run.
         │
         └──► If updates needed (review feedback, merge conflicts, red CI) OR stale branches exist:
                │
                ▼
[Phase 2: CodeGraph-Backed Triage & Workspace Setup]
         │ (Per target repository: clone upstream default branch -> codegraph init -y)
         ▼
[Phase 3: Autonomous Change Execution]
         │ 1. Pull latest upstream base (dev/main)
         │ 2. Create isolated task branch (fix/...)
         │ 3. Execute requested maintainer changes & run local test gates
         │ 4. Push with --force-with-lease & comment resolution on PR
         ▼
[Phase 4: Maximal Branch Purge]
         │ Delete remote fork branches for merged, closed, or obsolete PRs
         ▼
[Re-census] ──► any action left? yes ➔ back to Phase 1 (§0)
         │ no
         ▼
[Phase 5: Final Post-Update Audit Table]
         Print conclusive before/after status ledger
```
PY