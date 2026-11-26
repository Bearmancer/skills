# research-rigorously

Claim-ledger research skill: fetch, verify, then publish pages to `bearmancer.github.io`. Agents load `SKILL.md` (rules and run commands); decisions are in `references/design.md`.

## Structure

```
rr.py                  entry point with the PEP 723 header: `uv run <skill dir>/rr.py <command>`
scripts/cli.py         `rr` commands: start, resume, remove and the tool subcommands (`rr --help`)
scripts/infer_mode.py  mode routing table (the first phase, registered in `phases/__init__.py`)
scripts/driver.py      phase order, retries, asks (HandRunner), gates
scripts/publish.py     in-place commit/push into the site clone, revert on live-check failure
scripts/remove.py      topic removal (ADR 0030)
scripts/phases/        discover, ingest, write, verify, ship, common
scripts/post/          vendor POST scripts, run as `rr vendor <name>`
scripts/ledger*.py     ledger store and publish gate; workspace.py holds Layout, Config, Ledger, Context
registry/              registry.yaml (surfaces)
schema/                claims, lesson, sources JSON schemas
references/roles.md    role prompts; its `Checking roles:` line names the checking roles
references/design.md   skill-local decision record
```

## Where to look

| Task                           | Location                       | Notes                                                         |
| ------------------------------ | ------------------------------ | ------------------------------------------------------------- |
| Add or change a search surface | `registry/registry.yaml`       | then regenerate `references/routing.md`                       |
| Change a role prompt           | `references/roles.md`          | the `Checking roles:` line names fresh-subagent roles |
| Change a phase or its order    | `scripts/driver.py`, `scripts/phases/` | phases and handlers are registered in `phases/__init__.py` |
| Page layout                    | `references/layouts.md`, `assets/` | one layout per page                                        |
| Publish or removal mechanics   | `scripts/publish.py`, `scripts/remove.py`, `scripts/cli.py` | ADR 0030, 0034, 0039; page meta record: `scripts/render.py` |
| Run the checks                 | `scripts/selfcheck.py`         | `rr selfcheck`; the pre-commit hook runs it for `research-rigorously/` changes |

## Conventions

- `ADR 00NN` inside this folder means `references/design.md`, never `docs/adr/`.
- A new Python dependency goes in `rr.py`'s PEP 723 header (ADR 0040). Modules under `scripts/` import as the `scripts` package (`from scripts import registry`).
- Run state lives under the state root (ADR 0038), never here or in the site clone; `scratch/` is ignored in this folder (`workspace.Layout` owns every path).
- A phase that needs AI writes asks to `ASKS.md` and exits; the agent answers and resumes (ADR 0033).

## Anti-patterns

- Never hand-edit `references/routing.md`: `uv run <this dir>/rr.py gen-routing` writes it from the registry.
- Never hand-edit a generated page: fix the ledger, then regenerate.
