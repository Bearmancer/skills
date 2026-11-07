# Multi-repo plans, assimilated plans and purge

Read this when one request spans several repos, or when earlier plans for the same work must be folded into one. One request still makes one plan and one ledger; repos are a registry on that ledger, not separate plans.

## 1. Register and tag

1. `repo --id <kebab> --path <dir> [--role <text>]` once per repo. The path must exist; ids are stable and never reused.
2. `task --repo <id>` and `fact --repo <id>` (also `repo` in a `batch` row). Task `files` are relative to the task's repo, and a fact's file locator resolves against that repo's path.
3. Once any repo is registered, `G4` requires every active task to name a registered repo and `plan.md` to render `## Repos`; `validate` rejects a `--repo` that was never registered.
4. Two or more repos make the plan size `L` and require `approve-task-graph`; under run-through the standing authorization quote supplies it.

## 2. Parallel work across repos

`dag` qualifies every file with its repo: the same path in two repos is two files, so those tasks may run in parallel; the same repo and path is one file, so `dag` serializes the later task and reports it on stderr. Each node's SCOPE names its repo and path. Cross-repo ordering is still `deps`: a consumer repo task lists the producer repo task it needs, and `cpm` computes the critical path across all repos.

## 3. Assimilate existing plans

`assimilate --from <plan dir | ledger.json> [--repo <id>]` folds another plan into this ledger:

- active decisions and code-locator facts are copied; from phase P4 on, tasks are copied too with `deps` remapped to the new ids;
- every label gets the source slug as a prefix (32 characters at most, made unique), so nothing collides;
- URL facts and their snapshots are not carried and are counted in `external_skipped`; re-record them as facts of this plan if they still matter;
- the source directory and the sha256 of its ledger are recorded in `sources`.

Run it before the evidence gate: imported facts belong to the current wave and must be closed with `wave`.

## 4. Purge (automatic, no confirmation)

`chat --path <file>` registers a planning transcript for deletion. A successful `publish` then deletes, without asking, every assimilated source plan directory and every registered chat file; `purge` repeats it on an already published plan. Every outcome is recorded in `purges`, and a skip is never silent. The rules that keep the deletion narrow:

- only a published plan purges: the sources are deleted once their content lives in a published plan;
- a source must sit under a `.rigor/plans` or `.rigor/maps` directory and contain `ledger.json`, and it is never the current plan or one of its parents;
- a source whose ledger changed since assimilation is skipped (`skipped-changed-since-assimilation`), because its newer content is not in this plan;
- a source whose URL evidence was not carried is skipped (`skipped-external-evidence-not-carried`);
- a chat must be a regular file;
- running it again does nothing and records nothing new.

Deletion cannot be undone, so Q0 `scope` asks which plans to assimilate and which chats to register; that answer, together with the standing authorization, is the whole consent. The planning run itself never asks again.
