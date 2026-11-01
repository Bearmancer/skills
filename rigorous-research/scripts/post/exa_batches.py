# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "jsonschema"]
# ///
"""Exa batches (beta): start, status, cancel.

Docs: https://exa.ai/docs/exa-spec.yaml (`/batches`, `/batches/{id}`, `/batches/{id}/cancel`; CreateBatchRequest, BatchRequestItem)
status returns `resultsUrl` (presigned JSONL download link, null until the batch completes); fetch it as-is.
Every call sends `Exa-Beta: batches-2026-06-06` (required by the spec).
`--requests`: JSON array of {"customId","method":"POST","url":"/search"|"/agent/runs","body":{...}}, or @file. customId unique, max 64 chars.
Usage: uv run <skill dir>/scripts/post/exa_batches.py start --requests '[...]' | status <id> | cancel <id>
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

BETA = {"Exa-Beta": "batches-2026-06-06"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    start = sub.add_parser("start")
    start.add_argument("--requests", required=True)
    start.add_argument("--metadata", help="JSON object of string values, or @file")
    pc.add_id_commands(
        sub,
        {
            "status": ("GET", "/batches/{id}"),
            "cancel": ("POST", "/batches/{id}/cancel"),
        },
    )
    args = ap.parse_args(argv)
    if args.cmd == "start":
        body = {"requests": pc.load_json_arg(args.requests)}
        if args.metadata:
            body["metadata"] = pc.load_json_arg(args.metadata)
        pc.run("exa", "POST", "/batches", body, headers=BETA)
    else:
        pc.dispatch("exa", args, headers=BETA)


if __name__ == "__main__":
    main()
