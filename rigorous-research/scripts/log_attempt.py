# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "jsonschema"]
# ///
"""Append one attempt record to attempts.jsonl (ADR 0015). Agents call this once per attempt, any route.

Record: claim, round, query_variant, url, surface, paradigm, ladder, route, status, error_class, content_hash, at.
Surface, route and ladder are validated against the registry, so a typo or an unwired surface fails loudly.
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
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import registry

QUERY_VARIANTS = ("supporting", "opposing", "primary", "other-language", "fetch")
ATTEMPT_STATUSES = ("ok", "error", "blocked", "empty")


class AttemptError(ValueError):
    pass


def build_record(
    reg,
    *,
    claim,
    round_no,
    surface,
    route,
    url,
    status,
    query_variant="supporting",
    error_class=None,
    content=None,
    now=None,
):
    surf = registry.surfaces(reg).get(surface)
    if surf is None:
        raise AttemptError(f"unknown surface {surface}")
    if not surf.wired:
        raise AttemptError(f"surface {surface} is not wired")
    if route not in surf.routes:
        raise AttemptError(
            f"{surface} has no {route} route (has {sorted(surf.routes)})"
        )
    if status not in ATTEMPT_STATUSES:
        raise AttemptError(f"status must be one of {ATTEMPT_STATUSES}")
    if query_variant not in QUERY_VARIANTS:
        raise AttemptError(f"query_variant must be one of {QUERY_VARIANTS}")
    if not 1 <= round_no <= reg["max_rounds"]:
        raise AttemptError(f"round must be 1..{reg['max_rounds']}")
    if error_class is not None and error_class not in (
        *registry.ERROR_CLASSES,
        "unknown",
    ):
        raise AttemptError(f"unknown error_class {error_class}")
    if status == "ok" and error_class:
        raise AttemptError("ok attempt cannot carry an error_class")
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "claim": claim,
        "round": round_no,
        "query_variant": query_variant,
        "url": url,
        "surface": surface,
        "paradigm": surf.paradigm,
        "ladder": surf.ladder,
        "route": route,
        "status": status,
        "error_class": error_class,
        "content_hash": hashlib.sha256(content).hexdigest()[:16]
        if content is not None
        else None,
        "at": stamp,
    }


def append(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", type=Path, required=True, help="attempts.jsonl")
    ap.add_argument("--claim", required=True)
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--surface", required=True, help="<server>.<capability>")
    ap.add_argument("--route", required=True, choices=registry.ROUTE_KINDS)
    ap.add_argument("--url", default="")
    ap.add_argument("--status", required=True, choices=ATTEMPT_STATUSES)
    ap.add_argument("--query-variant", default="supporting", choices=QUERY_VARIANTS)
    ap.add_argument("--error-class", default=None)
    ap.add_argument("--content-file", type=Path, default=None)
    args = ap.parse_args(argv)
    try:
        rec = build_record(
            registry.load(),
            claim=args.claim,
            round_no=args.round,
            surface=args.surface,
            route=args.route,
            url=args.url,
            status=args.status,
            query_variant=args.query_variant,
            error_class=args.error_class,
            content=args.content_file.read_bytes() if args.content_file else None,
        )
    except AttemptError as err:
        print(json.dumps({"error": str(err)}), file=sys.stderr)
        return 1
    append(args.file, rec)
    print(json.dumps(rec, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
