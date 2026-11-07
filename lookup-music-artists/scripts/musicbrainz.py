#!/usr/bin/env python3
"""Extract Composers / Orchestras / Soloists from a MusicBrainz release.

Usage:
    uv run musicbrainz.py <release-mbid-or-url> [--out FILE] [--dump FILE]

Algorithm (proven live 2026-11-06 on 46-CD boxes, ONE request):
  GET /ws/2/release/{mbid}?fmt=json&inc=artists+labels+media+recordings
  - track-level artist-credit   -> Composers (classical convention: the
    release editor sets each track's credit to the composer)
  - any credit with artist.type in {Orchestra, Choir, Ensemble} -> Orchestras
  - release-level artist-credit (the set's lead, usually the conductor) and
    composer names are removed from the remaining Person credits -> Soloists
  Caveat: a *second* conductor credited only on some recordings (not the
  release credit) will land in Soloists. --out files are always reviewed
  against the release page's "Other artists" block before keeping.

Notes for future maintainers:
  * recording-level-rels / work-level-rels are silently EMPTY on the release
    GET (probed 2026-11-06); /js/ and /ws2/js/ dump endpoints 404 on live.
  * 'media' alone yields tracks with no recording objects; always include
    '+recordings'. 503s happen under load: the fetcher backs off.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from credits_lib import clean_name, desktop_library, fix_stdout, slugify, write_md

UA = {"User-Agent": "lookup-music-artists/1.0 (personal md-library research)"}
ENSEMBLE_TYPES = {"Orchestra", "Choir", "Ensemble", "Chorus"}
JUNK = {"[no artist]", "[unknown]", "[traditional]", "[anonymous]"}


def mbid_from(arg: str) -> str:
    m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", arg)
    if not m:
        sys.exit(f"no MBID found in {arg!r}")
    return m.group(0)


def fetch_release(mbid: str, host: str) -> dict:
    url = f"{host}/ws/2/release/{mbid}?fmt=json&inc=artists+labels+media+recordings"
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (500, 503):
                time.sleep(10 * (i + 1))
                continue
            raise
        except Exception:  # noqa: BLE001 transport
            time.sleep(6)
    sys.exit("musicbrainz unreachable after retries")


def harvest(rel: dict) -> dict[str, set[str]]:
    composers: set[str] = set()
    orchestras: set[str] = set()
    persons: set[str] = set()
    conductors: set[str] = set()

    def eat(credit_list):
        for c in credit_list or []:
            name = clean_name(c.get("name") or "")
            if not name or name.lower() in JUNK:
                continue
            typ = (c.get("artist") or {}).get("type") or ""
            if typ in ENSEMBLE_TYPES:
                orchestras.add(name)
            elif typ == "Person":
                persons.add(name)

    for c in rel.get("artist-credit", []) or []:
        n = clean_name(c.get("name") or "")
        if n and n.lower() not in JUNK:
            conductors.add(n)

    for m in rel.get("media", []) or []:
        for t in m.get("tracks", []) or []:
            tc = t.get("artist-credit") or []
            for c in tc:
                n = clean_name(c.get("name") or "")
                typ = (c.get("artist") or {}).get("type") or ""
                if n and n.lower() not in JUNK and typ not in ENSEMBLE_TYPES:
                    composers.add(n)
            eat((t.get("recording") or {}).get("artist-credit"))

    def surname(n: str) -> str:
        parts = [
            p
            for p in n.lower().replace("’", "'").split()
            if p.strip("'")
            not in {
                "de",
                "van",
                "von",
                "der",
                "den",
                "di",
                "da",
                "du",
                "le",
                "la",
                "el",
                "al",
            }
        ]
        return parts[-1] if parts else n.lower()

    lead = {surname(x) for x in conductors | composers}
    soloists = {p for p in persons if surname(p) not in lead}
    return {"Composers": composers, "Orchestras": orchestras, "Soloists": soloists}


def main() -> None:
    fix_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("release", help="release MBID or musicbrainz.org/beta URL")
    ap.add_argument("--out")
    ap.add_argument("--dump", help="also save raw JSON here")
    args = ap.parse_args()

    host = (
        "https://beta.musicbrainz.org"
        if "beta." in args.release
        else "https://musicbrainz.org"
    )
    mbid = mbid_from(args.release)
    rel = fetch_release(mbid, host)
    if args.dump:
        Path(args.dump).write_text(
            json.dumps(rel, ensure_ascii=False), encoding="utf-8"
        )
    title = rel.get("title", mbid)
    groups = harvest(rel)
    if not any(groups.values()):
        sys.exit("nothing extracted — release has no classical artist credits?")

    out = (
        Path(args.out)
        if args.out
        else desktop_library("musicbrainz") / f"{slugify(title)}.md"
    )
    path = write_md(
        out, title, "MusicBrainz", f"https://musicbrainz.org/release/{mbid}", groups
    )
    for k, v in groups.items():
        print(f"{k}: {len(v)}")
    print(f"wrote {path}")
    if groups["Soloists"]:
        print(
            "REMINDER: cross-check Soloists against the release page's Other "
            "artists block — non-lead conductors can leak in."
        )


if __name__ == "__main__":
    main()
