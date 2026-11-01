# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "jsonschema"]
# ///
"""Exa agent run stop and cancel. Create and poll runs with MCP `agent_run`.

Docs: https://exa.ai/docs/exa-spec.yaml (`/agent/runs/{id}/stop`, `/agent/runs/{id}/cancel`)
stop: ends an `ultra` run early, keeps results so far. cancel: drops a queued or running run, no results. Both bill accrued usage.
Usage: uv run <skill dir>/scripts/post/exa_agent_run.py stop|cancel <run_id>
"""

if not __package__:
    import sys
    from pathlib import Path

    sys.dont_write_bytecode = True
    parents = Path(__file__).resolve().parents
    sys.path.insert(0, str(next(p for p in parents if p.name == "scripts")))
    import launch

    launch.run(__file__)

import argparse

from . import common as pc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    pc.add_id_commands(
        ap.add_subparsers(dest="cmd", required=True),
        {
            "stop": ("POST", "/agent/runs/{id}/stop"),
            "cancel": ("POST", "/agent/runs/{id}/cancel"),
        },
    )
    pc.dispatch("exa", ap.parse_args(argv))


if __name__ == "__main__":
    main()
