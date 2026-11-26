# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Prove build_payload.py on the two 2026-11-24 defects and the happy path.

Runs with: uv run --quiet scripts/test_build_payload.py
"""

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_payload import bounty_bytes, check, norm_tag, payload, tag_string  # noqa: E402

GOOD = {
    "title": "Mahler: Symphony No. 6 in A minor 'Tragic'", "label": "Exton", "catno": "OVCL-00854",
    "year": 2024, "discs": 2, "image": "https://files.catbox.moe/x.jpg",
    "artists": [{"name": "Jonathan Nott", "role": "conductor"},
                {"name": "Tokyo Symphony Orchestra", "role": "main"},
                {"name": "Gustav Mahler", "role": "composer"}],
    "tags": ["Jonathan Nott", "exton", "Tokyo Symphony Orchestra", "hybrid-sacd", "austro-german romantic"],
    "contents": "Contents:\n2-disc set\nGustav Mahler — Symphony No. 6",
    "sources": ["https://tokyosymphony.jp/news/52092/"], "bounty_mb": 200,
}
fails = []


def expect(name, cond):
    if not cond:
        fails.append(name)


expect("good spec is clean", check(GOOD) == [])

# Defect 1: tags joined with ';' became one merged tag on both sites.
text, tags = tag_string(GOOD["tags"])
expect("tags comma-joined", text == "classical, jonathan.nott, exton, tokyo.symphony.orchestra, hybrid.sacd, austro.german.romantic")
expect("classical added once", tags.count("classical") == 1)
expect("semicolon string is not one tag", norm_tag("jonathan-nott;exton") == "jonathan.nottexton")
bad = copy.deepcopy(GOOD)
bad["tags"] = ["x" * 210]
expect("over-200 tags refused", any("chars" in e for e in check(bad)))

# Defect 2: artist rows filed as the number 1.
bad = copy.deepcopy(GOOD)
bad["artists"][0] = {"name": 1, "role": 5}
bad["artists"][1] = {"name": "1", "role": 1}
errs = check(bad)
expect("numeric artist refused", sum("artist name" in e for e in errs) == 2)

bad = copy.deepcopy(GOOD)
bad["artists"].append({"name": "Jonathan Nott", "role": "composer"})
expect("conductor-as-composer refused", any("conductor also filed" in e for e in check(bad)))
bad = copy.deepcopy(GOOD)
bad["artists"][0]["name"] = "Елена Образцова"
expect("Cyrillic refused", any("Latin" in e for e in check(bad)))
bad = copy.deepcopy(GOOD)
del bad["catno"]
expect("catalogue number required", any("catno" in e for e in check(bad)))

red, ops = payload(GOOD, "red"), payload(GOOD, "ops")
expect("200 MB in bytes", red["bounty"]["bytes"] == 209715200)
expect("lossless code per site", red["bitrates"] == ["8"] and ops["bitrates"] == ["0"])
expect("roles numeric", [a["role"] for a in red["artists"]] == [5, 1, 4])
expect("closing block last", red["description"].endswith("shortening box name"))
expect("download line", "Can be downloaded from: https://tokyosymphony.jp/news/52092/" in red["description"])
expect("tier 1 disc = 2 GB", bounty_bytes({"discs": 1})[0] == 2 * 1024 ** 3)
expect("tier 12 discs = 7 GB", bounty_bytes({"discs": 12})[0] == 7 * 1024 ** 3)
expect("tier 25 discs = 10 GB", bounty_bytes({"discs": 25})[0] == 10 * 1024 ** 3)
disc = copy.deepcopy(GOOD)
disc["image"] = "https://i.discogs.com/a.jpg"
try:
    payload(disc, "ops")
    fails.append("OPS Discogs image refused")
except SystemExit:
    pass

print("FAIL: " + ", ".join(fails) if fails else "all checks pass")
sys.exit(1 if fails else 0)
