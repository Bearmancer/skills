import argparse
import json
import sys
from pathlib import Path


def work_name(title):
    s = title.strip()
    while True:
        head, sep, tail = s.rpartition(":")
        t = tail.strip()
        numbered = t[:1].isdigit() and ". " in t[:4]
        if not sep or not (t[:1].isalpha() or numbered):
            return s
        s = head.strip()


def strip_movement(title):
    return work_name(title)


def format_contents(extract, performers):
    lines = ["Contents:"]
    for i, disc in enumerate(extract.get("works", [])):
        if i > 0:
            lines.append("")
        cd = disc.get("cd") or (i + 1)
        lines.append(f"Disc {cd}")
        perf = (performers.get(str(cd)) or "").strip()
        suffix = f" [{perf}]" if perf else ""
        seen = set()
        prev_composer = None
        for w in disc.get("works", []):
            composer = (w.get("composer") or "").strip()
            work = strip_movement(w.get("work") or "")
            if not work:
                continue
            key = (composer, work)
            if key in seen:
                continue
            seen.add(key)
            if composer and composer != prev_composer:
                lines.append(f"{composer} \u2014 {work}{suffix}")
                prev_composer = composer
            else:
                lines.append(work)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="Render the Contents: block (Disc N / Composer \u2014 Work [performers]) from extract_release_artists.py JSON."
    )
    ap.add_argument("--extract", required=True, help="extract_release_artists.py output JSON")
    ap.add_argument("--performers", help="JSON mapping disc number to performer string, e.g. {\"1\": \"Berliner Philharmoniker\"}")
    ap.add_argument("--out", help="write the block here instead of stdout")
    args = ap.parse_args()

    extract = json.loads(Path(args.extract).read_text(encoding="utf-8"))
    performers = {}
    if args.performers:
        performers = json.loads(Path(args.performers).read_text(encoding="utf-8"))
    text = format_contents(extract, performers) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        discs = len(extract.get("works", []))
        print(f"wrote {args.out}: {discs} discs", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
