# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Turn a short album spec into lint-clean RED and OPS request payloads.

Every site code, bounty rule, tag rule and the closing tag block live here, so a
request is never hand-assembled. A spec that breaks a rule exits 2 with every
problem listed; nothing is written.

Usage:
  uv run --quiet build_payload.py <spec.json> <out_dir> [--sites red,ops]

The spec is one album object or a list of them (a batch). Album keys:
  title, label, catno, year, discs            required
  artists   [{"name": "...", "role": "conductor|composer|main|guest|..."}]
  tags      ["classical", "Jonathan Nott", "austro-german romantic"] (any spelling;
            normalized to classical, jonathan.nott, austro.german.romantic)
  image     HTTPS cover URL; image_ops overrides it for OPS (Discogs is refused there)
  release   album | anthology | live            default album
  bounty_mb / bounty_gb                         default: disc-count tier
  overview  lines above Contents (string)
  contents  the Contents block (from format_contents.py), required
  sources   list of source URLs, first one is the "Can be downloaded from" line
  download  overrides the "Can be downloaded from" URL

Writes <out_dir>/<catno>.<site>.json per album and site, ready for make_bundle.py.
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ROLES = {"main": 1, "guest": 2, "composer": 4, "conductor": 5, "dj": 6,
         "remixer": 3, "producer": 7, "arranger": 8}
RELEASE = {"red": {"album": "1", "anthology": "6", "live": "11"},
           "ops": {"album": "1", "anthology": "6", "live": "11"}}
# FLAC / Lossless (16-bit) / CD — the only shape this skill files.
CODES = {"red": {"formats": ["1"], "bitrates": ["8"], "media": ["0"]},
         "ops": {"formats": ["1"], "bitrates": ["0"], "media": ["0"]}}
TIERS = ((1, 2), (10, 5), (20, 7))  # max discs -> GB; above 20 -> 10 GB
MIB = 1024 ** 2
TAG_MAX = 200
CONDUCTOR_COMPOSER_OK = {"Lorin Maazel"}
CLOSING = """It would be greatly appreciated if the uploaded files contained proper tags defined as:
1. Title - Work Name, Op. (No) - I. (Movement Name)
2. Artist - Soloists, conductor, orchestra
3. Composer
4. Date - Reflecting the recording date
5. Track number
6. Disc number
7. Total disc
8. Long path issues resolved via shortening box name"""


def norm_tag(raw):
    """One tag in Gazelle form: lowercase ASCII, words joined by dots."""
    s = unicodedata.normalize("NFKD", str(raw)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[\s\-_/]+", ".", s.strip())
    s = re.sub(r"[^a-z0-9.]", "", s)
    return re.sub(r"\.{2,}", ".", s).strip(".")


def tag_string(tags):
    """Comma-joined tag list; Gazelle splits tags only on commas."""
    seen = []
    for t in ["classical", *tags]:
        n = norm_tag(t)
        if n and n not in seen:
            seen.append(n)
    return ", ".join(seen), seen


def bounty_bytes(album):
    if "bounty_mb" in album:
        return int(album["bounty_mb"]) * MIB, f'{album["bounty_mb"]}', "mb"
    if "bounty_gb" in album:
        gb = album["bounty_gb"]
    else:
        discs = int(album["discs"])
        gb = next((g for top, g in TIERS if discs <= top), 10)
    return int(gb) * 1024 * MIB, f"{gb}", "gb"


def is_latin(name):
    return all(not c.isalpha() or unicodedata.name(c, "").startswith("LATIN") for c in name)


def check(album):
    errs = []
    for key in ("title", "label", "catno", "year", "discs", "contents"):
        if not str(album.get(key, "")).strip():
            errs.append(f"missing {key}")
    if not re.fullmatch(r"\d{4}", str(album.get("year", ""))):
        errs.append(f"year must be 4 digits: {album.get('year')!r}")
    arts = album.get("artists") or []
    if not arts:
        errs.append("no artists")
    for a in arts:
        name, role = a.get("name"), a.get("role")
        if not isinstance(name, str) or not name.strip():
            errs.append(f"artist name must be a non-empty string: {a!r}")
        elif re.fullmatch(r"[\d\s.]+", name):
            errs.append(f"artist name is a number: {a!r}")
        elif not is_latin(name):
            errs.append(f"artist name not Latin script (transliterate): {name}")
        if str(role).lower() not in ROLES and role not in ROLES.values():
            errs.append(f"unknown role {role!r} for {name}")
    cond = {a.get("name") for a in arts if role_code(a.get("role")) == 5}
    comp = {a.get("name") for a in arts if role_code(a.get("role")) == 4}
    if (both := (cond & comp) - CONDUCTOR_COMPOSER_OK):
        errs.append(f"conductor also filed as composer: {sorted(both)}")
    if not cond:
        errs.append("no conductor row")
    if album.get("release", "album") not in RELEASE["red"]:
        errs.append(f"release must be one of {sorted(RELEASE['red'])}")
    for key in ("image", "image_ops"):
        if album.get(key) and not str(album[key]).startswith("https://"):
            errs.append(f"{key} must be HTTPS")
    if not album.get("image"):
        errs.append("missing image")
    if not (album.get("download") or album.get("sources")):
        errs.append("need sources or download URL for the closing block")
    text, tags = tag_string(album.get("tags") or [])
    if len(text) > TAG_MAX:
        errs.append(f"tags {len(text)} chars > {TAG_MAX}: {text}")
    if len(tags) < 2:
        errs.append("need at least one tag beyond classical")
    return errs


def role_code(role):
    return role if isinstance(role, int) else ROLES.get(str(role).lower())


def description(album):
    parts = [f"[b]{album['title']}[/b]"]
    if album.get("overview"):
        parts.append(album["overview"].strip())
    parts.append(album["contents"].strip())
    if album.get("sources"):
        parts.append("[b]Source:[/b]\n" + "\n".join(album["sources"]))
    download = album.get("download") or album["sources"][0]
    parts.append(f"Can be downloaded from: {download}")
    parts.append(CLOSING)
    return "\n\n".join(parts)


def payload(album, site):
    image = album.get("image_ops") if site == "ops" and album.get("image_ops") else album["image"]
    if site == "ops" and "discogs" in image:
        raise SystemExit(f"{album['catno']}: OPS refuses Discogs images - set image_ops to a rehosted URL")
    bytes_, box, unit = bounty_bytes(album)
    text, tags = tag_string(album.get("tags") or [])
    arts = [{"name": a["name"].strip(), "role": role_code(a["role"])} for a in album["artists"]]
    return {"site": site, "type": "Music", "artists": arts, "title": album["title"],
            "recordlabel": album["label"], "cataloguenumber": album["catno"],
            "year": str(album["year"]), "image": image, "tags": text, "tag_list": tags,
            "releasetype": RELEASE[site][album.get("release", "album")],
            **CODES[site], "bounty": {"amount_box": box, "unit": unit, "bytes": bytes_},
            "description": description(album)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("out_dir")
    ap.add_argument("--sites", default="red,ops")
    args = ap.parse_args()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    albums = spec if isinstance(spec, list) else [spec]
    problems = {a.get("catno", f"#{i}"): e for i, a in enumerate(albums) if (e := check(a))}
    if problems:
        for cat, errs in problems.items():
            for e in errs:
                print(f"{cat}: {e}", file=sys.stderr)
        sys.exit(2)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for a in albums:
        for site in args.sites.split(","):
            p = payload(a, site)
            path = out / f"{a['catno']}.{site}.json"
            path.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{path.name}: {len(p['artists'])} artists, tags={p['tags']}, bytes={p['bounty']['bytes']}")


if __name__ == "__main__":
    main()
