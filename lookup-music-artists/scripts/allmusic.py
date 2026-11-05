#!/usr/bin/env python3
"""Extract Composers / Orchestras / Soloists from an AllMusic album page.

Usage:
    uv run allmusic.py <album-url-or-mwID> [--out FILE]

AllMusic has no API and blocks bare fetchers (403). Order of attack:
  1. urllib with a browser UA (occasionally served);
  2. `firecrawl scrape <url> --format html` via the local firecrawl CLI
     (~/.bun/bin/firecrawl.exe, FIRECRAWL_API_KEY set) which renders it.
Credits are parsed from artist anchors: the text after each
allmusic.com/artist/ link inside the same table cell is the role list
("Byron Janis" + "Piano", "Eileen Farrell" + "Soprano (Vocal)", ...).
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from credits_lib import (classify, clean_name, desktop_library, fix_stdout,
                         is_ensemble, slugify, write_md)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"}
ANCHOR = re.compile(
    r'href="https://www\.allmusic\.com/artist/[^"]*"[^>]*>([^<]+)</a>.*?'
    r'<span class="artistCredits">([^<]*)</span>',
    re.I | re.S)


def url_from(arg: str) -> str:
    if arg.startswith("http"):
        return arg
    return f"https://www.allmusic.com/album/{arg}"


def fetch_html(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
        if "credits" in body.lower() or "album-credits" in body.lower():
            return body
    except Exception:  # noqa: BLE001 - expected 403; fall through to firecrawl
        pass
    fc = shutil.which("firecrawl") or str(Path.home() / ".bun" / "bin" / "firecrawl.exe")
    tmp = Path.home() / ".cache" / "opencode" / "allmusic_raw.html"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([fc, "scrape", url, "--format", "html", "-o", str(tmp)],
                   check=True, timeout=180)
    return tmp.read_text(encoding="utf-8", errors="replace")


def best_group(name: str, role: str) -> str | None:
    """AllMusic stacks comma-separated roles ('Interviewee, Piano'); judge each
    part and keep the most performer-like hit."""
    parts = [p.strip() for p in re.split(r"[;,]", html.unescape(role or "")) if p.strip()]
    order = {"Composers": 3, "Orchestras": 2, "Soloists": 1}
    best: str | None = None
    for p in parts:
        g = classify(p, name)
        if g and (best is None or order[g] > order[best]):
            best = g
    if best is None and is_ensemble(name):
        best = "Orchestras"
    return best


def harvest(page: str) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {"Composers": set(), "Orchestras": set(), "Soloists": set()}
    for name, role in ANCHOR.findall(page):
        name = clean_name(html.unescape(name.strip()))
        if not name or name.lower() in ("[none]",):
            continue
        g = best_group(name, role)
        if g:
            groups[g].add(name)
    return groups


def main() -> None:
    fix_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("album", help="AllMusic album URL or mw-id")
    ap.add_argument("--out")
    args = ap.parse_args()

    page = fetch_html(url_from(args.album))
    groups = harvest(page)
    if not any(groups.values()):
        sys.exit("no credits parsed — page layout may have changed, check raw html")
    mt = (re.search(r'<meta property="og:title" content="([^"]+)"', page)
          or re.search(r"<title>([^<]+)</title>", page)
          or re.search(r"<h1[^>]*>([^<]+)</h1>", page))
    if mt:
        title = html.unescape(mt.group(1)).split(" | ")[0].strip()
    else:
        us = re.search(r"/album/([^/]+?)(?:-mw\d+)?/?$", args.album)
        if us:
            title = us.group(1).replace("-", " ").title()
        else:
            mslug = re.search(r"(mw\d+)", args.album)
            title = f"AllMusic album {mslug.group(1)}" if mslug else "allmusic-album"
    out = Path(args.out) if args.out else desktop_library("allmusic") / f"{slugify(title)}.md"
    path = write_md(out, title, "AllMusic", url_from(args.album), groups)
    for k, v in groups.items():
        print(f"{k}: {len(v)}")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
