"""Shared helpers for the music-lookup-artists clients (mb.py, discogs.py, allmusic.py).

One source of truth for: name cleaning, grouping rules, the cast-sheet format
(bare lines, one entity per line, no role suffixes, headings separate the groups)
and the tracker-extract JSON shape that file-tracker-request consumes.
"""

import collections
import json
import re
import sys
import unicodedata
from pathlib import Path

GROUPS = ("Composers", "Orchestras", "Soloists")
MAIN, COMPOSER, CONDUCTOR = 1, 4, 5
UA_APP, UA_VERSION = "music-lookup-artists", "1.0"
UA = f"{UA_APP}/{UA_VERSION}"
INTRO_TITLES = {"applause", "intro", "introduction"}
RIP_NOISE = re.compile(r"\s*\(\s*\d+\s*dB\s*\)", re.I)

_DISAMBIG = re.compile(
    r"\s*\((?:\d+|[a-z]\.?|.*?-\s*\w+\s*(?:musician|music|composer|or.*|choir))\)\s*$",
    re.I,
)

_ENSEMBLE = re.compile(
    r"(orchestra|philharmonic|symphony orchestra|sinfonia|orquest|orchestre|conservatoire|"
    r"choir|chorus|chapel? (?:royal )?choir|knabench|chamber (?:ensemble|orchestra))",
    re.I,
)

_SKIP_ROLES = re.compile(
    r"producer|engineer|photograph|design|notes|writer|text|interview|funding|funder|"
    r"remaster|transferring|editor|archivist|coordinat|director \[|music (?:director|supervisor)\b",
    re.I,
)

_SOLOIST_ROLES = re.compile(
    r"^(piano|fortepiano|organ|harpsichord|violin|viola|cello|double bass|contrabass|flute|oboe|"
    r"clarinet|bassoon|harp|trumpet|horn|trombone|tuba|saxophone|guitar|lute|recorder|percussion|"
    r"timpani|celesta|accordion|harmonica|soprano|mezzo-?soprano|contralto|tenor|baritone|bass "
    r"(?!baritone)|bass|countertenor|alto|voice|vocals|singing)"
    r"(?:\s*\((?:vocal|vocals|soprano|tenor|mezzo-soprano)\))?$",
    re.I,
)


def clean_name(name):
    if not name:
        return ""
    n = unicodedata.normalize("NFKC", name).strip()
    n = _DISAMBIG.sub("", n).strip()
    return re.sub(r"\s+", " ", n)


def is_ensemble(name):
    return bool(_ENSEMBLE.search(name))


def classify(role, name):
    """Map (role, name) to one of GROUPS, or None to drop the credit line."""
    role = (role or "").strip()
    name = clean_name(name)
    if not name:
        return None
    if re.search(r"composer|composed", role, re.I):
        return "Composers"
    if re.search(r"orchestra|choir|chorus|ensemble", role, re.I) or is_ensemble(name):
        return "Orchestras"
    if re.search(r"conductor", role, re.I) or _SKIP_ROLES.search(role):
        return None
    if re.search(r"performer|solo|instrument", role, re.I) or _SOLOIST_ROLES.match(role):
        return "Soloists"
    return None


def work_name(title):
    """Strip movement suffixes: 'Symphony No. 5: I. Allegro' -> 'Symphony No. 5'."""
    s = RIP_NOISE.sub("", title.strip())
    while True:
        head, sep, tail = s.rpartition(":")
        t = tail.strip()
        numbered = t[:1].isdigit() and ". " in t[:4]
        if not sep or not (t[:1].isalpha() or numbered):
            return s
        s = head.strip()


def group_works(tracks):
    """tracks: (composer, title) in disc order -> [{composer, work}] with runs merged."""
    groups = []
    for comp, title in tracks:
        work = work_name(title)
        if groups and groups[-1]["composer"] == comp and groups[-1]["work"] == work:
            groups[-1]["tracks"] += 1
        else:
            groups.append({"composer": comp, "work": work, "tracks": 1, "last_title": title})
    return [
        {"composer": g["composer"], "work": g["work"] if g["tracks"] > 1 else work_name(g["last_title"])}
        for g in groups
    ]


def tracker_json(facts, rows, works, media, tracks, dual=(), conductor_review=()):
    """The tracker-extract shape file-tracker-request fills request forms from."""
    rows = sorted(rows, key=lambda r: (r["role"], r["name"].lower()))
    return {
        "release": facts,
        "media": media,
        "tracks": tracks,
        "distinct_artists": len(rows),
        "by_role": dict(collections.Counter(r["role"] for r in rows)),
        "dual_credit_review": list(dual),
        "conductor_review": list(conductor_review),
        "artists": rows,
        "works": works,
    }


def write_md(out_path, title, site, source_url, groups):
    lines = [f"# {title}", "", f"Source: {site} — {source_url}", ""]
    for group in GROUPS:
        names = sorted(groups.get(group, set()), key=str.lower)
        lines += [group, *(names or ["(none found)"]), ""]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return out_path


def slugify(title, max_len=60):
    s = unicodedata.normalize("NFKD", title)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:max_len].rstrip("-") or "release"


def desktop_library(site):
    return Path.home() / "Desktop" / "md-library" / site


def emit(result, out):
    """Write JSON to --out, else print UTF-8 to stdout."""
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
    else:
        print(text)


def fix_stdout():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
