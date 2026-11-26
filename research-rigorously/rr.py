# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "jsonschema"]
# ///
"""The research-rigorously command: `uv run <skill dir>/rr.py <command> ...`.

This header lists every dependency of the skill; the modules under `scripts/` carry none and
are imported as the `scripts` package (Python puts this file's folder on the import path).
"""

from scripts.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
