# rigorous-research — user guide

Installed research skill, never under `~/.claude/skills`, which take the core preset only. Agents load `SKILL.md`; decisions are in `references/design.md`, layouts in `references/layouts.md`, role prompts in `references/roles.md`.

The scripts do the mechanical work (fetch, ledger, gates, render, publish, remove, URL audit, key rotation) and never call a model or start another agent program. The agent that loaded the skill answers every AI step from the ask files a run writes, checking steps in fresh subagents, one per batch file (ADR 0033, #340).

- Preflight: `uv run <skill dir>/scripts/cli.py doctor --site-root <abs path>`
- Run: `uv run <skill dir>/scripts/cli.py start --site-root <abs path> --topic <slug> [--mode <mode>] --model <id> "<prompt>"`; on exit 3 answer the asks in `ASKS.md`, then `cli.py resume --model <id> <run_dir>`
- Tests: `uv run --directory <skill dir> --with pytest --with pyyaml --with jsonschema --with pytest-xdist -m pytest -q -n auto -p no:cacheprovider tests`
