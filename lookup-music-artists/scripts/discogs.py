#!/usr/bin/env python3
"""Extract Composers / Orchestras / Soloists from a Discogs release.

Usage:
    uv run discogs.py <release-id-or-url> [--out FILE]

Discogs facts baked in: the public API needs a UA (and optional
DISCOGS_TOKEN env bearer); credits live in tracklist[].extraartists as
free-text roles ("Composed By", "Piano", "Violin", "Orchestra", ...), and
main artists carry no role — ensemble detection is by name.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

from credits_lib import (
    classify,
    clean_name,
    desktop_library,
    fix_stdout,
    is_ensemble,
    slugify,
    write_md,
)

API = "https://api.discogs.com/releases/"
UA = {"User-Agent": "lookup-music-artists/1.0 (personal md-library research)"}


def rid_from(arg: str) -> str:
    m = re.search(r"/release[s]?/(\d+)", arg)
    return m.group(1) if m else arg.strip()


def fetch(rid: str) -> dict:
    headers = dict(UA)
    tok = os.environ.get("DISCOGS_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(API + rid, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def harvest(rel: dict) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {
        "Composers": set(),
        "Orchestras": set(),
        "Soloists": set(),
    }

    def add(role: str, name: str):
        n = clean_name(name)
        if not n:
            return
        g = classify(role, n)
        if g is None and is_ensemble(n):
            g = "Orchestras"
        if g:
            groups[g].add(n)

    for a in rel.get("artists", []) or []:
        add(a.get("role", ""), a.get("name", ""))
    for t in rel.get("tracklist", []) or []:
        for x in t.get("extraartists", []) or []:
            add(x.get("role", ""), x.get("name", ""))
    for x in rel.get("extraartists", []) or []:
        add(x.get("role", ""), x.get("name", ""))
    return groups


def main() -> None:
    fix_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("release", help="Discogs release id or URL")
    ap.add_argument("--out")
    args = ap.parse_args()

    rel = fetch(rid_from(args.release))
    groups = harvest(rel)
    if not any(groups.values()):
        sys.exit("no credits found on this Discogs release")
    title = rel.get("title", "discogs-release")
    artists = ", ".join(a.get("name", "") for a in rel.get("artists", [])[:2])
    out = (
        Path(args.out)
        if args.out
        else desktop_library("discogs") / f"{slugify(title)}.md"
    )
    path = write_md(
        out,
        f"{title} — {artists}".strip(" —"),
        "Discogs",
        f"https://www.discogs.com/release/{rel.get('id')}",
        groups,
    )
    for k, v in groups.items():
        print(f"{k}: {len(v)}")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
