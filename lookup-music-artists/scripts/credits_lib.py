"""Shared helpers for lookup-music-artists scripts.

One source of truth for: name cleaning, grouping rules, and the
owner's deliverable format (bare lines, one entity per line, no
role suffixes, no commas — headings separate the groups).
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

GROUPS = ("Composers", "Orchestras", "Soloists")

# Discogs/MB disambiguator tails that are database plumbing, not names.
_DISAMBIG = re.compile(r"\s*\((?:\d+|[a-z]\.?|.*?-\s*\w+\s*(?:musician|music|composer|or.*|choir))\)\s*$", re.I)

# Ensemble-name heuristic (Discogs rarely tags a role; the artist name tells us).
_ENSEMBLE = re.compile(
    r"(orchestra|philharmonic|symphony orchestra|sinfonia|orquest|orchestre|conservatoire|"
    r"choir|chorus|chapel? (?:royal )?choir|knabench|chamber (?:ensemble|orchestra))",
    re.I,
)

# Roles that are never part of the three requested lists.
_SKIP_ROLES = re.compile(
    r"producer|engineer|photograph|design|notes|writer|text|interview|funding|funder|"
    r"remaster|transferring|editor|archivist|coordinat|director \[|music (?:director|supervisor)\b",
    re.I,
)

# Soloist-ish roles: anything that performs, except conductor-ish handled separately.
_SOLOIST_ROLES = re.compile(
    r"^(piano|fortepiano|organ|harpsichord|violin|viola|cello|double bass|contrabass|flute|oboe|"
    r"clarinet|bassoon|harp|trumpet|horn|trombone|tuba|saxophone|guitar|lute|recorder|percussion|"
    r"timpani|celesta|accordion|harmonica|soprano|mezzo-?soprano|contralto|tenor|baritone|bass "
    r"(?!baritone)|bass|countertenor|alto|voice|vocals|singing)"
    r"(?:\s*\((?:vocal|vocals|soprano|tenor|mezzo-soprano)\))?$",
    re.I,
)


def clean_name(name: str) -> str:
    """Normalize one artist name for output: no database disambiguators, single spaces."""
    if not name:
        return ""
    n = unicodedata.normalize("NFKC", name).strip()
    n = _DISAMBIG.sub("", n).strip()
    n = re.sub(r"\s+", " ", n)
    return n


def is_ensemble(name: str) -> bool:
    return bool(_ENSEMBLE.search(name))


def classify(role: str, name: str) -> str | None:
    """Map (role, name) to one of GROUPS, or None to drop the credit line."""
    role = (role or "").strip()
    name = clean_name(name)
    if not name:
        return None
    if re.search(r"composer|composed", role, re.I):
        return "Composers"
    if re.search(r"orchestra|choir|chorus|ensemble", role, re.I) or is_ensemble(name):
        return "Orchestras"
    if re.search(r"conductor", role, re.I):
        return None  # not in the three requested groups by default
    if _SKIP_ROLES.search(role):
        return None
    if re.search(r"performer|solo|instrument", role, re.I) or _SOLOIST_ROLES.match(role):
        return "Soloists"
    if role == "":  # credited with no role on the release itself
        return "Orchestras" if is_ensemble(name) else None
    return None


def write_md(out_path: Path, title: str, site: str, source_url: str, groups: dict[str, set[str]]) -> Path:
    """Write the deliverable: grouped bare lists, names only."""
    lines = [f"# {title}", "", f"Source: {site} — {source_url}", ""]
    for group in GROUPS:
        names = sorted(groups.get(group, set()), key=str.lower)
        lines.append(group)
        lines.extend(names if names else ["(none found)"])
        lines.append("")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return out_path


def slugify(title: str, max_len: int = 60) -> str:
    s = unicodedata.normalize("NFKD", title)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:max_len].rstrip("-") or "release"


def desktop_library(site: str) -> Path:
    base = Path.home() / "Desktop" / "md-library" / site
    return base


def fix_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
