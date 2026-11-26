# Host facts (verified 2026-11-26, uv 0.13.10)

Read when `uv pip` cannot find an interpreter, `externally-managed-environment` appears, a script cannot import something installed, or the uv cache is large.

- `~\.python-version` = `3.13`, so every `uv run` anywhere uses `%APPDATA%\uv\python\cpython-3.13-windows-x86_64-none\python.exe` (3.13.18, x86_64; uv walks up from the cwd).
- `%APPDATA%\uv\uv.toml`: `[pip] python = '<that absolute path>'` + `break-system-packages = true`.
  - `uv pip` never reads `.python-version`; a version request (`python = '3.13'`) resolves against discovered environments, not managed interpreters, and fails - hence the absolute path.
  - The pin rides the junction name (`cpython-3.13-...-none`), which `uv python upgrade` repoints, so it survives upgrades; a patch-versioned pin dangles.
  - Every uv-managed interpreter carries `Lib\EXTERNALLY-MANAGED` (verified 3.12-3.16): uv guarding its own tree, which this policy owns as the one shared store. Without the flag every `uv pip install` dies `externally-managed-environment`.
- PEP 723 cost, measured here: uv caches each headered script's sealed env at `<cache>\environments-v2\<stem>-<hash>`, keyed on deps + `requires-python` + interpreter. A cache hit still pays resolve-validation every run; a header edit mints a new hash and orphans the old env (one script: five generations); a distinct `requires-python` seals a distinct interpreter (one 3.15 env sits beside the 3.13 host), and cross-version dupes are real bytes - ABI-specific wheels cannot hardlink-share. Standing waste: 501 dead envs, 1.1 GB, reclaimable with `uv cache clean`, regenerable by design.
- Libraries live in the shared interpreter: check `uv pip list` before installing. Tools on 3.13: ruff, ty, yt-dlp, arxiv-mcp-server, paper-search-mcp.
- 3.12/3.15/3.16 and the python.org installs remain on PATH; unused - never code against them. After `uv python upgrade --reinstall` the junction moves and `uv pip list` shows nothing: re-run the installs; nothing else changes.
- Doubtful feature: <https://docs.python.org/3/whats-new.html>, or write `probe.py` and `uv run probe.py` - never `python -c`. `C:\Users\Lance\Documents\python-release-notes\` does not exist; never cite it.
