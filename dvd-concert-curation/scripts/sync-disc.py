"""Set the "disc" field of each tags.json under <root> to its folder path relative to <root>.

Usage: uv run sync-disc.py report|apply <root> <journal.jsonl>
       uv run sync-disc.py undo <root> <journal.jsonl>
"""

import json
import sys
from datetime import datetime
from pathlib import Path


def rows(root):
    for path in sorted(root.rglob("tags.json")):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        want = str(path.parent.relative_to(root))
        if "disc" in data and data["disc"] != want:
            yield path, data, want


def apply(root, journal, write):
    for path, data, want in rows(root):
        print(f"{data['disc']} -> {want}")
        if not write:
            continue
        old = path.read_bytes()
        with journal.open("a", encoding="utf-8") as log:
            log.write(json.dumps({"path": str(path), "old": old.decode("utf-8"), "time": datetime.now().isoformat()}, ensure_ascii=False) + "\n")
        text = json.dumps(data | {"disc": want}, indent=2, ensure_ascii=False)
        path.write_bytes((text + "\n").encode("utf-8"))


def undo(journal):
    for line in reversed(journal.read_text(encoding="utf-8").splitlines()):
        row = json.loads(line)
        Path(row["path"]).write_bytes(row["old"].encode("utf-8"))
        print(f"restored {row['path']}")


if len(sys.argv) != 4 or sys.argv[1] not in ("report", "apply", "undo") or not Path(sys.argv[2]).is_dir():
    sys.exit(__doc__)
mode, root, journal = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
if mode == "undo":
    undo(journal)
else:
    apply(root, journal, mode == "apply")
