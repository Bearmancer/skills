# Handoff shape

Everything still comes from `ledger.json`; `plan.md` is rendered.

## Sections

- **TL;DR (For humans).** Who it is for, what changes, why now, what it will not
  do, effort/risk, the decisions worth a sanity check, and the next move. Render
  from `intent.*`, size and `risk-*`/`top-recommendation` decisions. No gate.
- **Scope.** Affected user and ideal state as `ideal-<n>` decisions; each difference
  as a `gap-<n>` decision whose answer starts with the IDEAL label:
  `decision --label gap-1 --decision "IDEAL-1: today each harness reads a different path"`.
  Every task names the IS or gap it delivers: `task ... --closes gap-1` or
  `--closes ideal-1`. A gap, when used, needs a delivering task.
- **Execution strategy.** Two rendered subsections, both derived from `task.deps`:
  - `### Parallel waves`: each task appears once; a task is in a later wave than
    every dependency.
  - `### Dependency matrix`: `| Task | Depends on | Blocks | Parallel with |`.
  Never hand-edit either; re-render after changing deps. G4 checks that the waves
  list each task once, the order respects deps, and the matrix rows match deps.
- **Tasks.** Each task carries files, interfaces, acceptance, verify, deps and
  (when test-first is on) the seam contract. `verify` is the proving scenario for the
  outcome it delivers. `closes` names `ideal-<n>` or `gap-<n>` and is required when
  ideal/gap rows exist.
- **Success criteria.** A table from every active `ideal-*`: its statement, the gaps
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

## Decoupled from execution

`plan.md` ends at the published `plan_sha256` and carries no executor rules (no fix-round caps, worker statuses or restart blocks); how a plan is executed belongs to the executing session (`/ulw-execute`, mass-ulw). The plan keeps only plan content: the review bar, the commit strategy, the final verification wave, the Dispatch and Todo mirror sections, and read-only exports (`cpm`, `dag`, `todos`, `frontier`). A published plan changes only through a ledgered amendment: any mutating command needs `--reason`, is recorded in `changes`, unpublishes the plan, and requires G4 and `publish` again.

## Chat handoff summary

When the plan is published, the closing message to the user has this shape, in the user's language, counted from the rendered plan (never estimated):

1. **What this plan drives**: the work it performs, in 1-2 sentences.
2. **Affected user and ideal state**: who the result touches and, from the `ideal-n` rows, what will exist or behave differently for them.
3. **Shape**: waves and tasks (N `T` rows plus the four F rows), the critical path from `cpm`, and the executor-category mix (for example 6x `quick`, 2x `unspecified-high`).
4. **Added beyond the request**: what exploration surfaced and was folded in (edge cases, migrations, tests, rollback, docs), each with a one-line reason; "none" if nothing.
5. **Decisions I made for you**: every `default-*` and assumed decision, each with its reversibility, led by the routing call (intent verdict and autonomy).
6. **Verification**: the final verification wave plus the key `verify` commands.
7. **Execution handoff**: execution is a separate session the user starts, for example `/ulw-execute <plan>` in this session or a new one, with `--worktree <absolute-path>` (task-owned worktree; required for PR or branch work), `--make-pr` (deliver as a PR), `--ship` (implies `--make-pr`, keep working until merged); or mass-ulw with the `dag` definition (`methods/cpm-dispatch.md`). This skill starts none of them.

## Effort and executor lines

The TL;DR states effort as exactly one band: Quick (a single edit), Short (one focused change, a few files), Medium (a multi-file feature in one session), Large (several waves, one long session) or XL (multi-session or architectural). Never hours or days: the counted task rows are the size signal, and the CPM `effort` units are relative, not durations.

Each task carries `--category` (its `Recommended task executor category:`, with a one-line reason in `acceptance` or `steps`) from `quick`, `unspecified-low`, `unspecified-high`, `deep-low`, `deep-high`, `ultrabrain`, `visual-engineering`, `writing`, `architect`, `artistry`. The rendered row shows it, and `dag` routes the node by it.

## Per-task QA scenarios

Every task's `verify` is a runnable command with its expected result. Write the happy case in `verify` and the failure case in `acceptance` ("fails with <exit/message> when <input>"), each naming the exact tool, invocation and evidence path. A scenario a human must perform is not a scenario; the Success criteria table maps each `ideal-n` row to the task and `verify` that proves it.

## Hard versus method

Hard: waves and matrix fidelity, ideal/gap closure, task `closes`, success table
presence, and the existing task fields. Method: writing a useful TL;DR, a real
ideal/gap distinction, the final-wave judgement, and the commit sequence. The
template's placeholders are never shipped; `render` fills the derived parts and
the author fills the rest.

## Migration note

An existing plan without ideal/gap rows stays valid: the closure gate only fires
when `ideal-*` or `gap-*` rows exist. Add the rows when the work has a real ideal
state to protect; do not manufacture them for a one-line change.
