# ULW plan shape

The plan is an execution handoff. It borrows the omo ULW plan shape (template:
`~/.omo/plans/all-pending-work.md`; filled example:
`~/.omo/plans/github-24h-direction-audit.md`) without creating a second ledger.
Everything still comes from `ledger.json`; `plan.md` is rendered.

## Sections

- **TL;DR (For humans).** Who it is for, what changes, why now, what it will not
  do, effort/risk, the decisions worth a sanity check, and the next move. Render
  from `intent.*`, size and `risk-*`/`top-recommendation` decisions. No gate.
- **Scope.** Affected user and ideal state as `is-<n>` decisions; each difference
  as a `gap-<n>` decision whose answer starts with the IS label:
  `decision --label gap-1 --decision "IS-1: today each harness reads a different path"`.
  Every task names the IS or gap it delivers: `task ... --closes gap-1` or
  `--closes is-1`. A gap, when used, needs a delivering task.
- **Execution strategy.** Two rendered subsections, both derived from `task.deps`:
  - `### Parallel waves`: each task appears once; a task is in a later wave than
    every dependency.
  - `### Dependency matrix`: `| Task | Depends on | Blocks | Parallel with |`.
  Never hand-edit either; re-render after changing deps. G4 checks that the waves
  list each task once, the order respects deps, and the matrix rows match deps.
- **Tasks.** Each task carries files, interfaces, acceptance, verify, deps and
  (when TDD is on) the seam contract. `verify` is the proving scenario for the
  outcome it delivers. `closes` names `is-<n>` or `gap-<n>` and is required when
  IS/GAP rows exist.
- **Success criteria.** A table from every active `is-*`: its statement, the gaps
  naming it, the delivering tasks and their `verify` commands. An unmapped row is
  visible, not hidden. G4 rejects a gap with no delivering task, a task with no
  closure, and an IS with no delivering task.
- **Final verification wave.** When executing: F1 plan compliance audit, F2 code
  quality review, F3 real manual QA, F4 ideal-state fidelity. They run in
  parallel after all tasks, all must approve, and the owner's explicit okay
  follows. Planning never runs this wave.
- **Commit strategy.** One concern per commit; explicit paths; conventional
  `type(scope): summary`; never commit a red suite or a weakened test. The
  executor commits; planning does not.

## Hard versus method

Hard: waves and matrix fidelity, IS/GAP closure, task `closes`, success table
presence, and the existing task fields. Method: writing a useful TL;DR, a real
IS/GAP distinction, the final-wave judgement, and the commit sequence. The
template's placeholders are never shipped; `render` fills the derived parts and
the author fills the rest.

## Migration note

An existing plan without IS/GAP rows stays valid: the closure gate only fires
when `is-*` or `gap-*` rows exist. Add the rows when the work has a real ideal
state to protect; do not manufacture them for a one-line change.
