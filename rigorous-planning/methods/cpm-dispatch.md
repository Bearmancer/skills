# CPM and parallel dispatch (mass-ulw)

Default method for P5 and for the execution handoff. Read it when you write tasks, set `deps`, or fill the plan's Dispatch block. The ledger computes the schedule; you supply honest `deps`, `files` and `effort`.

## 1. CPM is the default arranger

The critical path method orders work by what actually blocks what: a forward pass gives each task its earliest start (ES) and finish (EF), a backward pass gives its latest start (LS) and finish (LF), and slack = LS - ES. Zero slack means critical: any delay moves the finish. The plan renders this under `## Execution strategy`, `### Critical path (CPM)`, and `node scripts/planning.mjs cpm --slug S` prints it (`length`, `critical`, one line per task).

Inputs, per task:

- `deps`: only true blockers (task B consumes something A produces). A dependency added "to be safe" lengthens the critical path and removes parallelism; a missing one makes the schedule lie.
- `--effort n`: relative size in comparable units, not hours or days (unit 1 = a focused XS/S slice; M about 3, L about 5; XL means split). Default 1. Only ratios matter; use the same scale for every task in the plan.
- `files`: the exact write scope; it drives the parallel-safety check in section 3.

Reading the schedule:

1. Critical tasks first: staff them with the strongest `category` and the earliest checkpoint; split any critical task that is L or larger so the path shortens.
2. Risk-first still wins: an unproven piece goes early even with slack, because slack is only valid if the estimate is.
3. Slack tasks are the batching pool: they may run alongside the path, be deferred to fill idle workers, or be merged when they share files. A slack of 0 anywhere off the longest chain means parallel critical paths; treat each as critical.
4. Re-render after any `deps`, `effort` or `files` change (`render`); `G4` re-checks waves and the matrix. The waves are the level view; CPM adds which of them matter.

## 2. Parallel workers are the default, where safe

"Where safe" is mechanical, not a feeling. Two tasks may run at the same time only when all hold:

1. Neither depends on the other, directly or through a chain.
2. Their `files` are disjoint. If they share a file, one waits for the other. `dag` enforces this: it adds a `dependsOn` edge from the earlier task to the later one and reports `serialized: ...` on stderr. Fix the cause in the plan when you can (split the file's change into one task, or move it into a contract-first slice 0).
3. They share no mutable state outside `files` (migrations, lockfiles, generated output, a database, a port): those are sequential by rule, or isolated per worker.
4. A shared interface (API shape, schema, types) is defined by an earlier task both consume.
5. The Q0 `parallelism` answers allow it: worker count, isolation (worktree per worker), categories, spend cap. If the user scoped parallelism out, the plan says so and the executor runs the waves serially.

`G4` enforces CPM when the ledger has `flags.cpm` (default from `init`; `--no-cpm` turns it off): every active task needs a positive `--effort` and a `--category`, and `plan.md` must name the same `Critical path:` the script computes. `dag` writes `dag.json` (or `dag-after-<ids>.json` with `--done`) beside `plan.md`.

## 3. From plan to mass-ulw

Planning never starts workers; it produces the definition the executor starts.

1. `node scripts/planning.mjs dag --slug S` prints a mass-ulw workflow definition (`{ key, name, nodes }`): one node per active task with `id`, `label`, `category`, `dependsOn` and a self-contained English prompt (`TASK / DELIVERABLE / SCOPE / VERIFY / STOP WHEN`, with the test contract when the task has one). `category` is the task's `--category` (the plan's `Recommended task executor category:`), else a default (`docs` kind: `writing`; at most 60 changed lines in at most 2 files: `quick`; otherwise `unspecified-high`). Valid categories: `quick`, `unspecified-low`, `unspecified-high`, `deep-low`, `deep-high`, `ultrabrain`, `visual-engineering`, `writing`, `architect`, `artistry`.
2. mass-ulw runs one phase per run, where a phase is a verification checkpoint (the plan puts one after every 2-3 tasks and early for high-risk ones). Emit the next segment with `dag --done T1,T2` (finished tasks drop out and their dependents lose that edge), and start a new run per segment. A changed definition needs a new `key`; `dag` derives the key from the nodes, so the same segment re-issued is the same run.
3. The executor reads mass-ulw's `references/planning.md` in full before `start`, binds the run to the goal, and treats every node's "done" as false until the VERIFY evidence is captured. The plan's Dispatch block (rendered in the handoff, see `methods/handoff-shape.md`) names these three commands and the checkpoint segments.
4. Supervision belongs to the executor: check each active node against its own SCOPE on every wake, steer drift with `send`, fix a bad node with `retry` or `amend` after the wave settles.

### Harness todo mirror

Every wave and every task is mirrored into the harness todo tool (senpi `todo`, TodoWrite, update_plan or the equivalent): one phase per wave, one item per task, plus a `Final verification wave` phase. `node scripts/planning.mjs todos --slug S [--done T1,T2]` prints the exact `{ op: "init", list }` JSON and writes `todos.json`; `plan.md` renders `### Todo mirror` and `G4` rejects a plan whose mirror lacks any wave or task. Items start when work starts and finish when it ends, never batched.

## 4. Workers during planning itself

Planning may fan out only read-only work (`methods/delegation.md`): one `explore` or `librarian` lane per axis in P2, the design-consultation lanes, the review. Use plain parallel `task` spawns for those; they have no ordering to protect. A mass-ulw graph at planning time is justified for the adversarial workflow at size L (collect -> verify -> design -> adversarial -> synthesize, where each stage consumes the one before), and every node prompt in it must declare itself advisory-only: read-only analysis, no file edits, answers returned as text. Never route an implementer category at planning time.

## 5. What is a gate, what is method

Hard (script): `deps` acyclic and rendered, waves list each task once after its dependencies, `effort` positive, `category` in the list, `cpm` and `dag` computed from the ledger. Method (judgement): honest `deps`, comparable `effort`, whether a critical task should be split, the checkpoint placement, the `parallelism` fit.
