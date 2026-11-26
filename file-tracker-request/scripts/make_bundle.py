# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Bundle a payload JSON with the fill and verify scripts so one served file drives a request.

Usage: uv run make_bundle.py <payload.json> <bundle.json>
The payload must come from build_payload.py (it carries tag_list and lint-clean values).
Serve the bundle with serve_payload.py; the page fetches {payload, code, verify}, stashes
the payload in #__payload and injects code; after Create, inject verify on the view page
(see references/browser-fill.md, one-call stage).
"""

import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if "tag_list" not in payload:
    sys.exit("payload was not built by build_payload.py (no tag_list) - rebuild it")
here = Path(__file__).parent
code = (here / "fill_request.js").read_text(encoding="utf-8")
verify = (here / "verify_request.js").read_text(encoding="utf-8")
Path(sys.argv[2]).write_text(json.dumps({"payload": payload, "code": code, "verify": verify}, ensure_ascii=False),
                             encoding="utf-8")
print("bundle:", sys.argv[2], "artists:", len(payload["artists"]), "tags:", payload["tags"])
