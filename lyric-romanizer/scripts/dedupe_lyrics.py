# /// script
# requires-python = ">=3.12"
# ///

import re
import sys
import unicodedata
from pathlib import Path

_ARABIC_MARKS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")
_VARIANTS = str.maketrans(
    {
        "\u064a": "\u06cc",
        "\u0649": "\u06cc",
        "\u0643": "\u06a9",
        "\u0647": "\u06c1",
        "\u0629": "\u06c1",
    }
)
_NUKTA = "\u093c"

_REPEAT_MARK = re.compile(
    r"[\(\[\{]?\s*(?:x\s*\d+|\d+\s*x|\u00d7\s*\d+|\d+\s*\u00d7|\d+\s*times|repeat(?:\s*x?\d+)?)"
    r"\s*[\)\]\}]?\s*$",
    re.I,
)
_HEADER = re.compile(
    r"^\s*[\[\(\{]?\s*(?:intro|verse|chorus|pre[- ]?chorus|bridge|outro|hook|refrain|"
    r"interlude|instrumental|mukhda|antara|sthayi|pallavi|anupallavi|charanam|repeat\s+\w+)"
    r"\s*\d*\s*[\]\)\}]?\s*:?\s*(?:x\s*\d+|\d+\s*x)?\s*$",
    re.I,
)


def key(line):
    s = unicodedata.normalize("NFD", unicodedata.normalize("NFKC", line))
    s = _ARABIC_MARKS.sub("", s).translate(_VARIANTS).replace(_NUKTA, "")
    s = "".join(c for c in s if not 0x300 <= ord(c) <= 0x36F)
    out = []
    for c in s.casefold():
        cat = unicodedata.category(c)
        if cat[0] in "PSZ" or c.isspace():
            out.append(" ")
        elif cat in ("Cf", "Cc"):
            continue
        else:
            out.append(c)
    return " ".join("".join(out).split())


def dedupe(text):
    seen, kept, removed = set(), [], 0
    for raw in text.lstrip("\ufeff").splitlines():
        line = raw.strip()
        if not line or _HEADER.match(line):
            continue
        line = _REPEAT_MARK.sub("", line).strip()
        k = key(line)
        if not k:
            continue
        if k in seen:
            removed += 1
            continue
        seen.add(k)
        kept.append(line)
    return kept, removed


def main():
    if len(sys.argv) > 1:
        with Path(sys.argv[1]).open(encoding="utf-8-sig") as f:
            text = f.read()
    else:
        sys.stdin.reconfigure(encoding="utf-8")
        text = sys.stdin.read()
    kept, removed = dedupe(text)
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(kept))
    print(f"kept {len(kept)}, removed {removed} duplicate line(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
