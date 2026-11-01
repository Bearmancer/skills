# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "jsonschema"]
# ///
"""Firecrawl batch scrape: start, status, cancel, errors.

Docs: https://docs.firecrawl.dev/api-reference/v2-openapi.json (`/batch/scrape`, `/batch/scrape/{id}`, `/batch/scrape/{id}/errors`), https://docs.firecrawl.dev/features/batch-scrape
Usage: uv run <skill dir>/scripts/post/firecrawl_batch_scrape.py start <url>... [--formats markdown ...] | status|cancel|errors <id>
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
    start.add_argument("urls", nargs="+")
    start.add_argument("--formats", nargs="+", default=["markdown"])
    pc.add_id_commands(
        sub,
        {
            "status": ("GET", "/batch/scrape/{id}"),
            "cancel": ("DELETE", "/batch/scrape/{id}"),
            "errors": ("GET", "/batch/scrape/{id}/errors"),
        },
    )
    args = ap.parse_args(argv)
    if args.cmd == "start":
        pc.run(
            "firecrawl",
            "POST",
            "/batch/scrape",
            {"urls": args.urls, "formats": args.formats},
        )
    else:
        pc.dispatch("firecrawl", args)


if __name__ == "__main__":
    main()
