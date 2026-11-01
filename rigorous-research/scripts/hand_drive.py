# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "jsonschema"]
# ///
"""Attach a ledger to an already-published topic by hand.

Gap: scripts/cli.py offers start, resume, doctor and remove only. A run owns the
topic it created, so there is no driver route that builds a ledger behind a lesson
already on the site, and no route that re-renders one through the gates. Until a
driver command covers that case, this module runs the driver's own pieces against a
topic directory the caller names:

  uv run <skill dir>/scripts/hand_drive.py fetch --site-root <clone> --topic <slug> <url>...
  uv run <skill dir>/scripts/hand_drive.py check --site-root <clone> --topic <slug> [--publish]

`fetch` walks the registry's fetch ladder (default: direct, then wayback) for each
URL, writes the raw text under `<site>/work/<topic>/raw/`, records one attempt per
surface tried and one source row per URL, exactly as the driver's ingest phase
does. `check` is ledger_check over the same files.

On Windows without MSVC build tools, the pyyaml source build fails on Python 3.15;
`PYYAML_FORCE_LIBYAML=0` builds it pure-python, and the uv cache keeps it.
"""

import argparse
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

if not __package__:
    import sys
    from pathlib import Path

    sys.dont_write_bytecode = True
    parents = Path(__file__).resolve().parents
    sys.path.insert(0, str(next(p for p in parents if p.name == "scripts")))
    import launch

    launch.run(__file__)

from . import fetch as dr_fetch
from . import ledger as dr_ledger
from . import log_attempt as dr_log
from . import registry as dr_registry
from . import workspace as dr_ws

DEFAULT_LADDER = ("direct.fetch", "wayback.fetch")
OFFICIAL_HOSTS = ("history.state.gov", "archives.gov", "avalon.law.yale.edu")


class Ctx:
    def __init__(self, site_root, topic, reg):
        self.reg = reg
        self.site_root = Path(site_root)
        self.topic_dir = self.site_root / "_ledger" / topic
        self.topic_dir.mkdir(parents=True, exist_ok=True)
        self.inbox = self.topic_dir / "inbox"
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.keys = None
        self.runner = None
        self.clock = lambda: datetime.now(timezone.utc)
        self.attempts = []
        self.attempts_path = self.topic_dir / "attempts.jsonl"

    @property
    def ledger(self):
        return self

    def append_attempt(self, rec):
        self.attempts.append(rec)
        dr_log.append(self.attempts_path, rec)

    def work_file(self, name):
        path = self.topic_dir / "work" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


def source_kind(url):
    host = (urlparse(url).hostname or "").lower()
    path = urlparse(url).path.lower()
    if path.endswith(".pdf") or "wikisource.org" in host:
        return "original-document"
    if any(host == h or host.endswith("." + h) for h in OFFICIAL_HOSTS):
        return "original-document"
    if "britannica.com" in host or "uqam.ca" in host or "marxists.org" in host:
        return "reference-work"
    return "unknown"


def load_sources(path) -> list[dict[str, Any]]:
    if not Path(path).exists():
        return []
    return list((dr_ledger.load_sources(Path(path)) or {}).get("sources") or [])


def save_sources(path, sources):
    Path(path).write_text(
        dr_ledger.dump_claims({"schema": 1, "sources": sources}),
        encoding="utf-8",
        newline="\n",
    )


def raw_path(ctx, sid):
    path = ctx.site_root / "work" / ctx.topic_dir.name / "raw" / f"{sid}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def fetch_one(ctx, fetcher, url, ladder):
    ctx.reg = dict(ctx.reg, fetch_ladder=list(ladder))
    return fetcher.read(url, ctx)


def cmd_fetch(args):
    ctx = Ctx(args.site_root, args.topic, dr_registry.load())
    sources_path = ctx.topic_dir / "sources.yaml"
    rows = load_sources(sources_path)
    by_url = {s["url"]: s for s in rows}
    ids = [int(s["id"][1:]) for s in rows if re.fullmatch(r"s[0-9]+", s["id"])]
    next_id = 1 + max(ids, default=0)
    fetcher = dr_fetch.LadderFetcher()
    for url in args.urls:
        known = by_url.get(url)
        if known and known["status"] == "read" and not args.force:
            print(f"skip  {known['id']} already read  {url}")
            continue
        before = len(ctx.attempts)
        res = fetch_one(ctx, fetcher, url, args.ladder)
        host = (urlparse(url).hostname or "").lower()
        kind = source_kind(url)
        rec = known or {"id": f"s{next_id}"}
        if known is None:
            next_id += 1
        rec.update(
            url=url,
            kind=kind,
            tier=dr_ws.tier_for(ctx.reg, kind, url),
            publisher=host,
        )
        if res.ok:
            raw = raw_path(ctx, rec["id"])
            raw.write_text(res.text, encoding="utf-8", newline="\n")
            hashes = [
                a["content_hash"]
                for a in ctx.attempts[before:]
                if a.get("status") == "ok" and a.get("url") == url
            ]
            rec.update(
                status="read",
                retrieved_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                raw_path=str(raw.relative_to(ctx.site_root)).replace("\\", "/"),
                content_hash=hashes[-1]
                if hashes
                else hashlib.sha256(res.text.encode("utf-8")).hexdigest()[:16],
            )
            rec.pop("fail_reason", None)
            print(f"read  {rec['id']} {res.surface} {len(res.text)} chars  {url}")
        else:
            rec.update(status="failed", fail_reason=(res.error or "fetch failed")[:300])
            print(f"FAIL  {rec['id']} {res.error}  {url}")
        by_url[url] = rec
    save_sources(sources_path, list(by_url.values()))
    print(f"sources: {len(by_url)} in {sources_path}")


def cmd_check(args):
    topic_dir = Path(args.site_root) / "_ledger" / args.topic
    found = dr_ledger.check(
        dr_ledger.load_claims(topic_dir / "claims.yaml"),
        dr_ledger.load_sources(topic_dir / "sources.yaml"),
        dr_ledger.load_attempts(topic_dir / "attempts.jsonl"),
        publish=args.publish,
    )
    for item in found:
        print(item)
    errors = [x for x in found if x.severity == "error"]
    print(f"{len(errors)} error(s), {len(found) - len(errors)} warning(s)")
    return 1 if errors else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site-root", required=True, type=Path)
    ap.add_argument("--topic", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("urls", nargs="+")
    f.add_argument("--ladder", nargs="+", default=list(DEFAULT_LADDER))
    f.add_argument("--force", action="store_true")
    f.set_defaults(func=cmd_fetch)
    c = sub.add_parser("check")
    c.add_argument("--publish", action="store_true")
    c.set_defaults(func=cmd_check)
    args = ap.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
