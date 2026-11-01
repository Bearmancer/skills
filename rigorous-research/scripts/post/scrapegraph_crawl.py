# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "jsonschema"]
# ///
"""ScrapeGraph v2 crawl management: start, status, stop, resume, delete, pages.

Docs: https://docs.scrapegraphai.com/api-reference/endpoint/crawl/get-status, https://docs.scrapegraphai.com/api-reference/endpoint/crawl/manage, https://docs.scrapegraphai.com/api-reference/endpoint/crawl/pages, https://docs.scrapegraphai.com/api-reference/endpoint/crawl/start
Uses the v2 host; ids from the installed MCP 1.0.1 (v1 tool names) may not resolve here. Use ids from this script's `start`.
delete removes the job and its pages permanently. pages: --limit 1-100 (default 50), --cursor index from pagination.nextCursor.
Usage: uv run <skill dir>/scripts/post/scrapegraph_crawl.py start <url> [--max-pages N] | status|stop|resume|delete <id> | pages <id> [--limit N] [--cursor N]
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
    start.add_argument("url")
    start.add_argument("--max-pages", type=int)
    parsers = pc.add_id_commands(
        sub,
        {
            "status": ("GET", "/crawl/{id}"),
            "stop": ("POST", "/crawl/{id}/stop"),
            "resume": ("POST", "/crawl/{id}/resume"),
            "delete": ("DELETE", "/crawl/{id}"),
            "pages": ("GET", "/crawl/{id}/pages"),
        },
    )
    parsers["pages"].add_argument("--limit", type=int)
    parsers["pages"].add_argument("--cursor", type=int)
    args = ap.parse_args(argv)
    if args.cmd == "start":
        body = {"url": args.url, "formats": [{"type": "markdown"}]}
        if args.max_pages:
            body["maxPages"] = args.max_pages
        pc.run("scrapegraph", "POST", "/crawl", body)
    elif args.cmd == "pages":
        pc.dispatch(
            "scrapegraph", args, params={"limit": args.limit, "cursor": args.cursor}
        )
    else:
        pc.dispatch("scrapegraph", args)


if __name__ == "__main__":
    main()
