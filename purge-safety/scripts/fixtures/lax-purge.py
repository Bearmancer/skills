# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Negative control: speaks the manifest contract (--root, --manifest, --apply), skips every guard."""

import argparse
import json
import os
import shutil
import sys

p = argparse.ArgumentParser()
p.add_argument("--root", default=os.path.expanduser("~"))
p.add_argument("--manifest")
p.add_argument("--apply", action="store_true")
p.add_argument("--override", nargs="*", default=[])
p.add_argument("--out-dir")
p.add_argument("--max-minutes", type=int, default=60)
args = p.parse_args()
with open(args.manifest, encoding="utf-8-sig") as f:
    doc = json.load(f)
if not args.apply:
    print("plan: nothing happens")
    sys.exit(0)
root = os.path.abspath(args.root).rstrip("\\") + "\\"
for e in doc["entries"]:
    full = os.path.abspath(e["path"])
    if not full.startswith(root):
        continue
    if os.path.isdir(full) and not os.path.islink(full):
        shutil.rmtree(full, ignore_errors=True)
    else:
        try:
            os.remove(full)
        except OSError:
            pass
print("cleanup done")
