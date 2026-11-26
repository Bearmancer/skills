"""CLI: rr ledger-check <topic_dir> [--publish]. Exit 0 clean, 1 on any error-level violation."""

import argparse
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("topic_dir", type=Path)
    ap.add_argument(
        "--publish", action="store_true", help="treat any open claim as a violation"
    )
    args = ap.parse_args(argv)

    from . import ledger

    d = args.topic_dir
    claims = ledger.load_claims(d / "claims.yaml")
    sources = ledger.load_sources(d / "sources.yaml")
    attempts = ledger.load_attempts(d / "attempts.jsonl")
    found = ledger.check(claims, sources, attempts, publish=args.publish)
    for item in found:
        print(item)
    errors = [x for x in found if x.severity == "error"]
    print(f"{len(errors)} error(s), {len(found) - len(errors)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
