"""Bundle a payload JSON with fill_request.js so one served file drives a whole fill.

Usage: uv run --no-project python make_bundle.py <payload.json> <bundle.json>
Serve the bundle with serve_payload.py; the page fetches {payload, code}, stashes the
payload in #__payload and injects code (see references/browser-fill.md, one-call stage).
"""

import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
code = (Path(__file__).parent / "fill_request.js").read_text(encoding="utf-8")
Path(sys.argv[2]).write_text(json.dumps({"payload": payload, "code": code}, ensure_ascii=False), encoding="utf-8")
print("bundle:", sys.argv[2], "artists:", len(payload["artists"]))
