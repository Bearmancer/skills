"""Extract artist rows and a per-disc work list from a MusicBrainz release.

Usage:
  uv run --no-project --with musicbrainzngs python -I extract_release_artists.py --mbid <release-mbid> [--out extract.json]
  uv run --no-project --with musicbrainzngs python -I extract_release_artists.py --file <saved-release.json> [--out extract.json]
  uv run --no-project --with musicbrainzngs python -I extract_release_artists.py --search 'release:"X" AND artist:"Y"'

Uses the musicbrainzngs library (alastair/python-musicbrainzngs) for transport,
rate limiting and retries. Emits JSON: release facts, artist rows with Gazelle
importance roles (1 Main, 4 Composer, 5 Conductor), and per-disc composer/work
groups. Cross-check composers against a retailer contents listing before posting:
MB track-level composer credits contain real errors.
"""

import argparse
import collections
import json
import re
import sys
import time
from pathlib import Path

import musicbrainzngs as mb

MAIN, COMPOSER, CONDUCTOR = 1, 4, 5
INCLUDES = ["recordings", "artist-credits", "labels"]
RIP_NOISE = re.compile(r"\s*\(\s*\d+\s*dB\s*\)", re.IGNORECASE)


def work_name(title):
    s = RIP_NOISE.sub("", title.strip())
    while True:
        head, sep, tail = s.rpartition(":")
        t = tail.strip()
        numbered = t[:1].isdigit() and ". " in t[:4]
        if not sep or not (t[:1].isalpha() or numbered):
            return s
        s = head.strip()


def client():
    mb.set_useragent("file-tracker-request-skill", "1.0", "lordlance@outlook.in")
    return mb


def retry(fn, *a, **kw):
    last = None
    for attempt in range(4):
        try:
            return fn(*a, **kw)
        except (mb.NetworkError, mb.ResponseError, OSError) as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise last


def media_of(rel):
    return rel.get("medium-list") or rel.get("media") or []


def tracks_of(medium):
    return medium.get("track-list") or medium.get("tracks") or []


def credits_of(node):
    return [c for c in (node or []) if isinstance(c, dict)]


def credit_names(credits):
    return ", ".join(
        c.get("name") or c.get("artist", {}).get("name", "?") for c in credits_of(credits)
    )


def fetch_release(mbid):
    return retry(client().get_release_by_id, mbid, includes=INCLUDES)["release"]


def search_releases(query, limit=25):
    d = retry(client().search_releases, query=query, limit=limit)
    rows = []
    for r in d.get("release-list", []):
        li = r.get("label-info-list") or r.get("label-info") or []
        media = media_of(r)
        rows.append({
            "id": r.get("id"),
            "title": r.get("title"),
            "date": r.get("date"),
            "discs": len(media),
            "tracks": sum(int(m.get("track-count") or len(tracks_of(m))) for m in media),
            "label": [(x.get("label") or {}).get("name") for x in li],
            "catalogue": [x.get("catalog-number") for x in li],
            "barcode": r.get("barcode"),
            "country": (r.get("release-event-list") or [{}])[0].get("area", {}).get("name") if r.get("release-event-list") else r.get("country"),
        })
    return {"count": d.get("release-count"), "releases": rows}


def extract(rel, conductor_names=()):
    artists = {}

    def add(credits, role):
        for c in credits_of(credits):
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
    for m in media_of(rel):
        groups = []
        for t in tracks_of(m):
            comp = credit_names(t.get("artist-credit"))
            title = t.get("title") or (t.get("recording") or {}).get("title") or ""
            if comp == "[no artist]" or title.lower() in ("applause", "intro", "introduction"):
                continue
            add(t.get("artist-credit"), "composer")
            add((t.get("recording") or {}).get("artist-credit"), "performer")
            work = work_name(title)
            if groups and groups[-1]["composer"] == comp and groups[-1]["work"] == work:
                groups[-1]["tracks"] += 1
                groups[-1]["last_title"] = title
            else:
                groups.append({"composer": comp, "work": work, "tracks": 1, "last_title": title})
        works = []
        for g in groups:
            work = work_name(g["work"] if g["tracks"] > 1 else g["last_title"])
            works.append({"composer": g["composer"], "work": work})
        pos = m.get("position")
        works_out.append({"cd": int(pos) if str(pos).isdigit() else pos,
                          "mb_title": m.get("title"), "works": works})

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

    label_info = (rel.get("label-info-list") or rel.get("label-info") or [{}])
    events = rel.get("release-event-list") or rel.get("release-events") or [{}]
    media = media_of(rel)
    facts = {
        "id": rel.get("id"),
        "title": rel.get("title"),
        "artist": credit_names(rel.get("artist-credit")),
        "date": events[0].get("date") or rel.get("date"),
        "barcode": rel.get("barcode"),
        "label": (label_info[0].get("label") or {}).get("name"),
        "catalogue": label_info[0].get("catalog-number"),
    }
    return {
        "release": facts,
        "media": len(media),
        "tracks": sum(len(tracks_of(m)) for m in media),
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
    src.add_argument("--file", help="saved MusicBrainz release JSON (library or ws/2 shape)")
    src.add_argument("--search", help="MusicBrainz release search query; prints candidates instead of extracting")
    src.add_argument("--search-file", help="read the search query from this file (use when the query contains quotes)")
    ap.add_argument("--conductor", action="append", default=[],
                    help="explicit conductor name (repeatable); otherwise detected via MB disambiguation")
    ap.add_argument("--limit", type=int, default=25, help="search result limit")
    ap.add_argument("--out", help="write JSON here instead of stdout")
    args = ap.parse_args()

    if args.search or args.search_file:
        query = args.search or Path(args.search_file).read_text(encoding="utf-8").strip()
        result = search_releases(query, args.limit)
    else:
        rel = fetch_release(args.mbid) if args.mbid else json.loads(Path(args.file).read_text(encoding="utf-8"))
        result = extract(rel, args.conductor)
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        if args.search:
            print(f"wrote {args.out}: {result['count']} matches, {len(result['releases'])} returned", file=sys.stderr)
        else:
            print(f"wrote {args.out}: {result['distinct_artists']} artists, {result['media']} discs, {result['tracks']} tracks", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)


if __name__ == "__main__":
    main()
