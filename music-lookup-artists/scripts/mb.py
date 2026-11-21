# /// script
# requires-python = ">=3.12"
# dependencies = ["musicbrainzngs"]
# ///
"""MusicBrainz client for music-lookup-artists.

  uv run mb.py search '<lucene query>' | --query-file F [--limit N]   candidate releases (JSON)
  uv run mb.py tracker <mbid-or-url> | --file F [--conductor NAME]... tracker extract (JSON)
  uv run mb.py cast <mbid-or-url> [--out FILE]                         cast sheet (.md)
  uv run mb.py dates <mbid-or-url>                                     per-track recording date + venue (JSON)

musicbrainzngs paces requests at 1/s and retries 500/502/503 eight times with a growing
delay (_safe_read) before raising NetworkError, so a "busy" reply is never parsed.
It reads the XML API: medium-list / track-list / label-info-list, join phrases as bare
strings inside artist-credit, and a track's title is omitted when it equals the
recording title (fall back to recording.title). Relation dates are begin / end.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import musicbrainzngs as mb

from credits_lib import (
    COMPOSER,
    CONDUCTOR,
    INTRO_TITLES,
    MAIN,
    UA_APP,
    UA_VERSION,
    clean_name,
    desktop_library,
    emit,
    fix_stdout,
    group_works,
    slugify,
    tracker_json,
    write_md,
)

MBID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
TRACKER_INC = ["recordings", "artist-credits", "labels"]
DATES_INC = ["recordings", "recording-level-rels", "artist-rels", "place-rels"]
BROWSE_INC = ["artist-rels", "place-rels"]
ENSEMBLE_TYPES = {"Orchestra", "Choir", "Ensemble", "Chorus"}
JUNK = {"[no artist]", "[unknown]", "[traditional]", "[anonymous]"}
PARTICLES = {"de", "van", "von", "der", "den", "di", "da", "du", "le", "la", "el", "al"}
RECORDED_AT = "recorded at"

mb.set_useragent(UA_APP, UA_VERSION)


def mbid_from(arg):
    m = MBID.search(arg.lower())
    if not m:
        sys.exit(f"no MBID found in {arg!r}")
    return m[0]


def media_of(rel):
    return rel.get("medium-list") or rel.get("media") or []


def tracks_of(medium):
    return medium.get("track-list") or medium.get("tracks") or []


def credits_of(node):
    return [c for c in (node or []) if isinstance(c, dict)]


def credit_names(credits):
    return ", ".join(c.get("name") or c.get("artist", {}).get("name", "?") for c in credits_of(credits))


def name_of(c):
    return c.get("name") or c.get("artist", {}).get("name") or ""


def track_title(t):
    return t.get("title") or (t.get("recording") or {}).get("title") or ""


def release(mbid, includes):
    return mb.get_release_by_id(mbid, includes=includes)["release"]


def search(query, limit):
    d = mb.search_releases(query=query, limit=limit)
    rows = []
    for r in d.get("release-list", []):
        li = r.get("label-info-list") or []
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
            "country": r.get("country"),
        })
    return {"count": d.get("release-count"), "releases": rows}


def tracker(rel, conductor_names=()):
    artists = {}

    def add(credits, role):
        for c in credits_of(credits):
            a = c.get("artist", {})
            name = c.get("name") or a.get("name")
            if not name or name == "[no artist]":
                continue
            entry = artists.setdefault(a.get("id") or name, {
                "name": name, "type": a.get("type"),
                "disambiguation": a.get("disambiguation", ""), "roles": set(),
            })
            entry["roles"].add(role)

    works_out = []
    for m in media_of(rel):
        seq = []
        for t in tracks_of(m):
            comp, title = credit_names(t.get("artist-credit")), track_title(t)
            if comp == "[no artist]" or title.lower() in INTRO_TITLES:
                continue
            add(t.get("artist-credit"), "composer")
            add((t.get("recording") or {}).get("artist-credit"), "performer")
            seq.append((comp, title))
        pos = m.get("position")
        works_out.append({"cd": int(pos) if str(pos).isdigit() else pos,
                          "mb_title": m.get("title"), "works": group_works(seq)})

    rows, dual, review = [], [], []
    explicit = {n.lower() for n in conductor_names}
    for key, v in artists.items():
        name, roles, dis = v["name"], v["roles"], (v["disambiguation"] or "").lower()
        pure_conductor = dis.endswith("conductor") and not any(w in dis for w in ("and", "&", ",", "/"))
        if "composer" in roles:
            role = COMPOSER
            if "performer" in roles:
                dual.append(name)
        elif (name.lower() in explicit) if explicit else pure_conductor:
            role = CONDUCTOR
        else:
            role = MAIN
            if "performer" in roles and "conductor" in dis:
                review.append(name)
        rows.append({"name": name, "role": role, "type": v["type"], "id": key})

    li = rel.get("label-info-list") or rel.get("label-info") or [{}]
    events = rel.get("release-event-list") or rel.get("release-events") or [{}]
    media = media_of(rel)
    facts = {
        "id": rel.get("id"),
        "title": rel.get("title"),
        "artist": credit_names(rel.get("artist-credit")),
        "date": events[0].get("date") or rel.get("date"),
        "barcode": rel.get("barcode"),
        "label": (li[0].get("label") or {}).get("name"),
        "catalogue": li[0].get("catalog-number"),
    }
    return tracker_json(facts, rows, works_out, len(media),
                        sum(len(tracks_of(m)) for m in media), dual, review)


def surname(name):
    parts = [p for p in name.lower().split() if p.strip("'") not in PARTICLES]
    return parts[-1] if parts else name.lower()


def cast(rel):
    composers, orchestras, persons, leads = set(), set(), set(), set()
    for c in credits_of(rel.get("artist-credit")):
        if (n := clean_name(name_of(c))) and n.lower() not in JUNK:
            leads.add(n)
    for m in media_of(rel):
        for t in tracks_of(m):
            for c in credits_of(t.get("artist-credit")):
                n, typ = clean_name(name_of(c)), c.get("artist", {}).get("type") or ""
                if n and n.lower() not in JUNK and typ not in ENSEMBLE_TYPES:
                    composers.add(n)
            for c in credits_of((t.get("recording") or {}).get("artist-credit")):
                n, typ = clean_name(name_of(c)), c.get("artist", {}).get("type") or ""
                if not n or n.lower() in JUNK:
                    continue
                if typ in ENSEMBLE_TYPES:
                    orchestras.add(n)
                elif typ == "Person":
                    persons.add(n)
    lead = {surname(x) for x in leads | composers}
    return {"Composers": composers, "Orchestras": orchestras,
            "Soloists": {p for p in persons if surname(p) not in lead}}


def relations(rec):
    return (rec.get("artist-relation-list") or []) + (rec.get("place-relation-list") or [])


def browse_relations(mbid):
    by_id, offset = {}, 0
    while True:
        page = mb.browse_recordings(release=mbid, includes=BROWSE_INC, limit=100, offset=offset)
        recs = page.get("recording-list", [])
        by_id |= {r["id"]: relations(r) for r in recs}
        offset += len(recs)
        if not recs or offset >= int(page.get("recording-count", 0)):
            return by_id


def dates(mbid):
    rel = release(mbid, DATES_INC)
    tracks = [(m, t) for m in media_of(rel) for t in tracks_of(m)]
    rels = {t["recording"]["id"]: relations(t["recording"]) for _, t in tracks}
    if not any(rels.values()):
        rels |= browse_relations(mbid)
    rows = []
    for m, t in tracks:
        rs = rels.get(t["recording"]["id"], [])
        begins = [r["begin"] for r in rs if r.get("begin")]
        ends = [r.get("end") or r["begin"] for r in rs if r.get("begin")]
        rows.append({
            "disc": m.get("position"),
            "track": t.get("position"),
            "title": track_title(t),
            "begin": min(begins, default=None),
            "end": max(ends, default=None),
            "venues": sorted({r["place"]["name"] for r in rs if r.get("type") == RECORDED_AT and r.get("place")}),
        })
    return {"release": {"id": rel.get("id"), "title": rel.get("title")}, "tracks": rows}


def main():
    fix_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("query", nargs="?")
    s.add_argument("--query-file", help="read the query from a file (use when it contains quotes)")
    s.add_argument("--limit", type=int, default=25)
    s.add_argument("--out")
    t = sub.add_parser("tracker")
    t.add_argument("release", nargs="?", help="release MBID or URL")
    t.add_argument("--file", help="saved musicbrainzngs release JSON")
    t.add_argument("--conductor", action="append", default=[],
                   help="explicit conductor (repeatable); otherwise detected from MB disambiguation")
    t.add_argument("--out")
    c = sub.add_parser("cast")
    c.add_argument("release")
    c.add_argument("--out")
    d = sub.add_parser("dates")
    d.add_argument("release")
    d.add_argument("--out")
    a = ap.parse_args()

    if a.cmd == "search":
        query = a.query or Path(a.query_file).read_text(encoding="utf-8").strip()
        emit(search(query, a.limit), a.out)
    elif a.cmd == "tracker":
        rel = json.loads(Path(a.file).read_text(encoding="utf-8")) if a.file else release(mbid_from(a.release), TRACKER_INC)
        emit(tracker(rel.get("release", rel), a.conductor), a.out)
    elif a.cmd == "cast":
        mbid = mbid_from(a.release)
        rel = release(mbid, TRACKER_INC)
        groups = cast(rel)
        if not any(groups.values()):
            sys.exit("nothing extracted - release has no classical artist credits?")
        out = Path(a.out) if a.out else desktop_library("musicbrainz") / f"{slugify(rel.get('title', mbid))}.md"
        print(f"wrote {write_md(out, rel.get('title', mbid), 'MusicBrainz', f'https://musicbrainz.org/release/{mbid}', groups)}")
        print("; ".join(f"{k}: {len(v)}" for k, v in groups.items()))
    else:
        emit(dates(mbid_from(a.release)), a.out)


if __name__ == "__main__":
    main()
