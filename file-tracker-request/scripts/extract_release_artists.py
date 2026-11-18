"""Extract artist rows and a per-disc work list from a MusicBrainz release.

Usage:
  uv run --no-project python extract_release_artists.py --mbid <release-mbid> [--out extract.json]
  uv run --no-project python extract_release_artists.py --file <saved-release.json> [--out extract.json]

Fetches release?inc=recordings+artist-credits+labels (or reads the saved JSON) and
emits JSON: release facts, artist rows with Gazelle importance roles
(1 Main, 4 Composer, 5 Conductor), and per-disc composer/work groups.
Cross-check composers against a retailer contents listing before posting:
MB track-level composer credits contain real errors.
"""

import argparse
import collections
import http.client
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MAIN, COMPOSER, CONDUCTOR = 1, 4, 5


def fetch_release(mbid):
    url = f"https://musicbrainz.org/ws/2/release/{mbid}?inc=recordings+artist-credits+labels&fmt=json"
    req = urllib.request.Request(url, headers={"User-Agent": "file-tracker-request-skill/1.0 (MusicBrainz lookup for tracker request)"})
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (http.client.IncompleteRead, urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise last


def credit_names(credits):
    return ", ".join(c.get("name") or c.get("artist", {}).get("name", "?") for c in credits or [])


def extract(rel, conductor_names=()):
    artists = {}

    def add(credits, role):
        for c in credits or []:
            a = c.get("artist", {})
            name = c.get("name") or a.get("name")
            if not name or name == "[no artist]":
                continue
            key = a.get("id") or name
            entry = artists.setdefault(key, {"name": name, "type": a.get("type"),
                                             "disambiguation": a.get("disambiguation", ""),
                                             "roles": set()})
            entry["roles"].add(role)

    works_out = []
    for m in rel.get("media", []):
        groups = []
        for t in m.get("tracks", []):
            comp = credit_names(t.get("artist-credit"))
            title = t.get("title", "")
            if comp == "[no artist]" or title.lower() in ("applause", "intro", "introduction"):
                continue
            add(t.get("artist-credit"), "composer")
            add(t.get("recording", {}).get("artist-credit"), "performer")
            work = title.split(":")[0].strip()
            if groups and groups[-1]["composer"] == comp and groups[-1]["work"] == work:
                groups[-1]["tracks"] += 1
                groups[-1]["last_title"] = title
            else:
                groups.append({"composer": comp, "work": work, "tracks": 1, "last_title": title})
        works = []
        for g in groups:
            work = g["work"] if g["tracks"] > 1 else g["last_title"]
            works.append({"composer": g["composer"], "work": work})
        works_out.append({"cd": m.get("position"), "mb_title": m.get("title"), "works": works})

    rows, dual, conductor_review = [], [], []
    explicit = {n.lower() for n in conductor_names}
    for key, v in artists.items():
        name, roles = v["name"], v["roles"]
        dis = (v["disambiguation"] or "").lower()
        pure_conductor = dis.endswith("conductor") and not any(w in dis for w in ("and", "&", ",", "/"))
        is_conductor = name.lower() in explicit if explicit else pure_conductor
        if "composer" in roles and "performer" in roles:
            role = COMPOSER
            dual.append(name)
        elif "composer" in roles:
            role = COMPOSER
        elif is_conductor:
            role = CONDUCTOR
        else:
            role = MAIN
            if "performer" in roles and "conductor" in dis:
                conductor_review.append(name)
        rows.append({"name": name, "role": role, "type": v["type"], "id": key})
    rows.sort(key=lambda r: (r["role"], r["name"].lower()))

    label_info = rel.get("label-info") or [{}]
    facts = {
        "id": rel.get("id"),
        "title": rel.get("title"),
        "artist": credit_names(rel.get("artist-credit")),
        "date": (rel.get("release-events") or [{}])[0].get("date") or rel.get("date"),
        "barcode": rel.get("barcode"),
        "label": (label_info[0].get("label") or {}).get("name"),
        "catalogue": label_info[0].get("catalog-number"),
    }
    return {
        "release": facts,
        "media": len(rel.get("media", [])),
        "tracks": sum(len(m.get("tracks", [])) for m in rel.get("media", [])),
        "distinct_artists": len(rows),
        "by_role": dict(collections.Counter(r["role"] for r in rows)),
        "dual_credit_review": dual,
        "conductor_review": conductor_review,
        "artists": rows,
        "works": works_out,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--mbid", help="MusicBrainz release MBID (fetched live)")
    src.add_argument("--file", help="saved MusicBrainz release JSON")
    ap.add_argument("--conductor", action="append", default=[],
                    help="explicit conductor name (repeatable); otherwise detected via MB disambiguation")
    ap.add_argument("--out", help="write JSON here instead of stdout")
    args = ap.parse_args()

    rel = fetch_release(args.mbid) if args.mbid else json.loads(Path(args.file).read_text(encoding="utf-8"))
    result = extract(rel, args.conductor)
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}: {result['distinct_artists']} artists, {result['media']} discs, {result['tracks']} tracks", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
