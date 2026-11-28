"""The research-rigorously command: `uv run <skill dir>/rr.py <command> ...`.

Dependencies are installed into the uv environment once: `uv pip install pyyaml jsonschema`.
The modules under `scripts/` are imported as the `scripts` package (Python puts this file's
folder on the import path).
"""

from scripts.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
