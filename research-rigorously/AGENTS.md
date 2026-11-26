# research-rigorously

Claim-ledger research skill: fetch, verify, then publish pages to `bearmancer.github.io`. Agents load `SKILL.md` (rules and run commands); decisions are in `references/design.md`.

## Structure

```
rr.py                  entry point with the PEP 723 header: `uv run <skill dir>/rr.py <command>`
scripts/cli.py         `rr` commands: start, resume, remove and the tool subcommands
scripts/driver.py      phase order, retries, asks (HandRunner), gates
scripts/publish.py     in-place commit/push into the site clone, revert on live-check failure
scripts/remove.py      delete a topic's pages, publish the index change
scripts/phases/        infer_mode, discover, ingest, write, verify, ship, common
scripts/post/          vendor POST scripts, run as `rr vendor <name>`
scripts/ledger*.py     ledger store and publish gate; workspace.py holds Layout, Ledger, Config
registry/              registry.yaml (surfaces)
schema/                claims, lesson, sources JSON schemas
references/roles.md    role prompts; its `Checking roles:` line names the checking roles
references/design.md   skill-local decision record
```

## Where to look

| Task                           | Location                       | Notes                                                         |
| ------------------------------ | ------------------------------ | ------------------------------------------------------------- |
| Add or change a search surface | `registry/registry.yaml`       | then regenerate `references/routing.md`                       |
| Change a role prompt           | `references/roles.md`          | the `Checking roles:` line selects fresh-subagent roles       |
| Change a phase or its order    | `scripts/driver.py`, `scripts/phases/` | phases and handlers are registered in `phases/__init__.py` |
| Page layout                    | `references/layouts.md`, `assets/` | one layout per page                                        |
| Publish or removal mechanics   | `scripts/publish.py`, `scripts/remove.py`, `scripts/cli.py` | page meta record: `scripts/render.py` |
| Remove a published topic       | `scripts/remove.py`            | republishes the index, live-checks 404s                       |
| Run the checks                 | `scripts/selfcheck.py`         | `rr selfcheck`; the pre-commit hook runs it for `research-rigorously/` changes |

## Conventions

- `ADR 00NN` inside this folder means `references/design.md`, never `docs/adr/`.
- `rr.py` is the only entry point and the only file with a PEP 723 header; a new dependency goes in that header. Modules under `scripts/` carry no header and import as the `scripts` package (`from scripts import registry`). No `pyproject.toml`, lockfile or `.venv`.
- Run state lives under the state root (`--state-root`, default `~/.rigor`), never here and never in the site clone; `work/`, `scratch/` are ignored in this folder too (`workspace.Layout` owns every path).
- Scripts never call a model or start another agent. A phase that needs AI writes asks to `ASKS.md` and exits; the agent answers and resumes (ADR 0033).

## Anti-patterns

- Never hand-edit `references/routing.md`: `uv run <this dir>/rr.py gen-routing` writes it from the registry.
- Never hand-edit a generated page: fix the ledger, then regenerate.
