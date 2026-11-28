# Host facts (verified 2026-11-28, uv 0.13.10)

Read when `uv pip` cannot find an interpreter, `externally-managed-environment` appears, a package will not import, the uv cache is large, the Python version is not the one expected, or an upgrade ran.

- Interpreter: `uv python find` gives `%APPDATA%\uv\python\cpython-3.13-windows-x86_64-none\python.exe` (3.13.18). That name is a junction that `uv python upgrade` repoints to a newer patch. Packages install into the patch directory (`cpython-3.13.18-...\Lib\site-packages`), so after an upgrade, re-run the `uv pip install` lines.
- Version: `uv run <script.py>` reads the nearest `.python-version` beside the script or above it, not the working directory's. Measured: a 3.12 pin beside a script ran 3.12.16 from `C:\`; an unpinned script ran 3.13.18 from inside that pinned folder. With no pin, the user-level `%APPDATA%\uv\.python-version` (3.13) applies. `uv python find` does use the working directory (pinned folder: 3.12; `C:\`: 3.13).
- `%APPDATA%\uv\uv.toml` sets `[pip] python` to the 3.13 interpreter and `break-system-packages = true`, so `uv pip` installs there. Every uv-managed interpreter has `Lib\EXTERNALLY-MANAGED` (checked on all eight installs); `break-system-packages` lets `uv pip` modify it.
- Which interpreter a script got: `uv run probe.py` printing `sys.executable`.
- Libraries: `uv pip list`. Tools: `uv tool list --show-paths`. The guard blocks `uv tool dir` and allows `install`, `list`, `upgrade` and `uninstall` (python-guard.ts:12, 64).
- Other interpreters: uv-managed 3.12, 3.15 and 3.16 (`uv python list --only-installed`). `python` on PATH resolves to `WindowsApps\python.exe`, which is 3.15.2. `uv run` uses one of these only when a nearer `.python-version` asks for it.
- Cache: `uv cache dir` (here `%LOCALAPPDATA%\uv\cache`). `uv cache prune` removes unused entries; never delete the directory by hand (uv cache docs).
- PEP 723 headers (banned): uv builds each headed script's environment in that cache (uv storage docs), so each headed script adds entries. Packages a run already used are reused, not downloaded again (uv cache docs).
- Doubtful feature: <https://docs.python.org/3/whatsnew/3.13.html>, or write `probe.py` and run `uv run probe.py`; never `python -c`.
