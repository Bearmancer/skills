# /// script
# requires-python = ">=3.12"
# dependencies = ["python3-discogs-client"]
# ///
"""Discogs client for music-lookup-artists.

  uv run discogs.py search '<query>' [--barcode B] [--catno C] [--limit N]   candidate releases (JSON)
  uv run discogs.py tracker <release-id-or-url> [--conductor NAME]...       tracker extract (JSON, mb.py shape)
  uv run discogs.py cast <release-id-or-url> [--out FILE]                   cast sheet (.md)

Library: python3-discogs-client 2.x (import discogs_client).
Client(user_agent, user_token=DISCOGS_TOKEN); backoff_enabled (default True) retries 429
with exponential backoff. client.release(id).refresh() then .data is the raw API dict.
Search needs a token. Credits are free-text roles in tracklist[].extraartists and
release extraartists; main artists carry no role. Discogs search never reports "no
results" - an unmatched query returns fuzzy rows, so read the titles.
"""

import argparse
import os
import re
import sys
from pathlib import Path

import discogs_client

from credits_lib import (
    COMPOSER,
    CONDUCTOR,
    INTRO_TITLES,
    MAIN,
    UA,
    classify,
    clean_name,
    desktop_library,
    emit,
    fix_stdout,
    group_works,
    is_ensemble,
    slugify,
    tracker_json,
    write_md,
)

TOKEN_ENV = "DISCOGS_TOKEN"
POSITION = re.compile(r"^(?:CD|Disc|DVD)?\s*(\d+)[-.](\d+)", re.I)
COMPOSED = re.compile(r"compos", re.I)
CONDUCTS = re.compile(r"conduct", re.I)


def client():
    return discogs_client.Client(UA, user_token=os.environ.get(TOKEN_ENV))


def rid_from(arg):
    m = re.search(r"/releases?/(\d+)", arg)
    return int(m[1] if m else arg.strip())


def fetch(rid):
    r = client().release(rid)
    r.refresh()
    return r.data


def search(query, barcode, catno, limit):
    if not os.environ.get(TOKEN_ENV):
        sys.exit(f"{TOKEN_ENV} is required for Discogs search")
    fields = {k: v for k, v in {"barcode": barcode, "catno": catno}.items() if v}
    results = client().search(query or "", type="release", **fields)
    rows = []
    for r in results:
        d = r.data
        rows.append({
            "id": d.get("id"),
            "title": d.get("title"),
            "year": d.get("year"),
            "label": d.get("label", []),
            "catalogue": d.get("catno"),
            "format": d.get("format", []),
            "barcode": d.get("barcode", []),
            "country": d.get("country"),
        })
        if len(rows) >= limit:
            break
    return {"count": results.count, "releases": rows}


def entries(rel):
    """Flatten the tracklist into (disc, title, extraartists, artists, heading) rows."""
    heading = None
    for t in rel.get("tracklist", []):
        kind = t.get("type_")
        if kind == "heading":
            heading = t.get("title")
            continue
        subs = t.get("sub_tracks") if kind == "index" else None
        for s in subs or [t]:
            m = POSITION.match(s.get("position") or t.get("position") or "")
            title = f"{t['title']}: {s['title']}" if subs else s.get("title", "")
            yield (int(m[1]) if m else 1, title,
                   (s.get("extraartists") or []) + (t.get("extraartists") or []) if subs else s.get("extraartists") or [],
                   s.get("artists") or t.get("artists") or [], heading)


def tracker(rel, conductor_names=()):
    artists, explicit = {}, {n.lower() for n in conductor_names}

    def add(credit, role):
        name = clean_name(credit.get("anv") or credit.get("name") or "")
        if name:
            artists.setdefault(credit.get("id") or name, {"name": name, "roles": set()})["roles"].add(role)

    def kind(credit):
        role = credit.get("role") or ""
        if COMPOSED.search(role):
            return "composer"
        if CONDUCTS.search(role):
            return "conductor"
        return "performer" if classify(role, credit.get("name", "")) or is_ensemble(credit.get("name", "")) else None

    for a in rel.get("artists", []):
        add(a, "performer")
    for x in rel.get("extraartists", []):
        if k := kind(x):
            add(x, k)
    release_composers = [clean_name(x["name"]) for x in rel.get("extraartists", []) if kind(x) == "composer"]

    discs = {}
    for disc, title, extras, track_artists, heading in entries(rel):
        composers = [clean_name(x["name"]) for x in extras if kind(x) == "composer"]
        for x in extras:
            if k := kind(x):
                add(x, k)
        for a in track_artists:
            add(a, "composer")
        composers = composers or [clean_name(a["name"]) for a in track_artists]
        comp = ", ".join(composers) or (release_composers[0] if len(release_composers) == 1 else heading or "")
        if title.lower() not in INTRO_TITLES:
            discs.setdefault(disc, []).append((comp, title))

    rows, dual = [], []
    for key, v in artists.items():
        name, roles = v["name"], v["roles"]
        if "composer" in roles:
            role = COMPOSER
            if roles & {"performer", "conductor"}:
                dual.append(name)
        elif (name.lower() in explicit) if explicit else "conductor" in roles:
            role = CONDUCTOR
        else:
            role = MAIN
        rows.append({"name": name, "role": role, "type": None, "id": key})

    labels = rel.get("labels") or [{}]
    barcodes = [i["value"] for i in rel.get("identifiers", []) if i.get("type") == "Barcode"]
    facts = {
        "id": rel.get("id"),
        "title": rel.get("title"),
        "artist": ", ".join(clean_name(a.get("name", "")) for a in rel.get("artists", [])),
        "date": rel.get("released"),
        "barcode": barcodes[0] if barcodes else None,
        "label": labels[0].get("name"),
        "catalogue": labels[0].get("catno"),
    }
    works = [{"cd": d, "mb_title": None, "works": group_works(seq)} for d, seq in sorted(discs.items())]
    return tracker_json(facts, rows, works, len(discs), sum(len(s) for s in discs.values()), dual)


def cast(rel):
    groups = {"Composers": set(), "Orchestras": set(), "Soloists": set()}

    def add(role, name):
        n = clean_name(name)
        g = classify(role, n) or ("Orchestras" if n and is_ensemble(n) else None)
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


def main():
    fix_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("query", nargs="?")
    s.add_argument("--barcode")
    s.add_argument("--catno")
    s.add_argument("--limit", type=int, default=25)
    s.add_argument("--out")
    t = sub.add_parser("tracker")
    t.add_argument("release", help="Discogs release id or URL")
    t.add_argument("--conductor", action="append", default=[])
    t.add_argument("--out")
    c = sub.add_parser("cast")
    c.add_argument("release", help="Discogs release id or URL")
    c.add_argument("--out")
    a = ap.parse_args()

    if a.cmd == "search":
        emit(search(a.query, a.barcode, a.catno, a.limit), a.out)
    elif a.cmd == "tracker":
        emit(tracker(fetch(rid_from(a.release)), a.conductor), a.out)
    else:
        rel = fetch(rid_from(a.release))
        groups = cast(rel)
        if not any(groups.values()):
            sys.exit("no credits found on this Discogs release")
        title = rel.get("title", "discogs-release")
        artists = ", ".join(x.get("name", "") for x in rel.get("artists", [])[:2])
        out = Path(a.out) if a.out else desktop_library("discogs") / f"{slugify(title)}.md"
        path = write_md(out, f"{title} — {artists}".strip(" —"), "Discogs",
                        f"https://www.discogs.com/release/{rel.get('id')}", groups)
        print(f"wrote {path}")
        print("; ".join(f"{k}: {len(v)}" for k, v in groups.items()))


if __name__ == "__main__":
    main()
