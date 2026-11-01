# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "jsonschema"]
# ///
"""Browserbase agent runs: start, status.

Docs: https://docs.browserbase.com/reference/api/run-an-agent, https://docs.browserbase.com/reference/api/get-a-run
start returns 201 with the run in PENDING; status values: PENDING, RUNNING, COMPLETED, FAILED, STOPPED, TIMED_OUT, PAUSED.
Usage: uv run <skill dir>/scripts/post/browserbase_agent_run.py start "<task>" [--result-schema JSON|@file] | status <run_id>
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
    sub = ap.add_subparsers(dest="cmd", required=True)
    start = sub.add_parser("start")
    start.add_argument("task")
    start.add_argument("--result-schema", help="JSON Schema object, or @file")
    pc.add_id_commands(sub, {"status": ("GET", "/agents/runs/{id}")})
    args = ap.parse_args(argv)
    if args.cmd == "start":
        body = {"task": args.task}
        if args.result_schema:
            body["resultSchema"] = pc.load_json_arg(args.result_schema)
        pc.run("browserbase", "POST", "/agents/runs", body)
    else:
        pc.dispatch("browserbase", args)


if __name__ == "__main__":
    main()
