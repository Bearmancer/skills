---
name: python-modernization
description: Use whenever writing, reviewing, refactoring or explaining any Python (.py, notebooks) or picking a Python run or install command, even when the code looks fine, because model knowledge skews old. Targets Python 3.13 alone; installs only via `uv pip install` (libraries) or `uv tool install` (tools). Enforces brief untyped syntax and pathlib over os.path; bans `pyproject.toml`, `uv.lock`, `.venv`, PEP 723 `# /// script` headers, every `uv run` flag, `uv run python`, `uv sync`/`uv add`/`uvx` and all static typing. Also answers "is this deprecated" and Python upgrade questions.
---

# Modern Python, enforced

Model knowledge predates 3.12: never emit a superseded pattern when 3.13 has a briefer one.
Restates `~/.agents/AGENTS.md` "Python" identically - a doc that disagrees with the guard
plugins gets the caller blocked mid-command.

**CPython 3.13 only** (host: 3.13.18 x86_64). 3.14+ features are unavailable; never write a
version switch (`--python`, `py -V:`). Deliberate: `onnxruntime`, needed by `faster-whisper`,
ships no Windows cp315 wheel; 3.13 runs everything else.

Rules: no typing, one run command, pathlib with explicit UTF-8, no packaging files, fewest LOC.

## Commands

| Job | Command |
| --- | --- |
| Run a script | `uv run <file.py> <args>` - no flags, never followed by `python` (no `-m`, no `-c`, no REPL) |
| Library a script imports | `uv pip install <pkg>` |
| Tool you type as a command | `uv tool install <pkg>`, then call it bare |

Test suites get a `.py` entry point (`uv run tests/test_stt.py` behind `unittest.main()`); a
tool that exists only as `python -m <tool>` gets `uv tool install`. Never `uvx`/`uv tool run`.

`uv pip` installs into the shared interpreter's site-packages, importable by every script, no
packaging files needed. `uv tool` builds a private env per tool, one `.exe` in `~\.local\bin`,
requires `pyproject.toml`/`setup.py`, and drops entry-point-less packages. **Your own script
never goes through `uv tool`.**

## Banned

| Forbidden | Why | Instead |
| --- | --- | --- |
| `# /// script` PEP 723 header | sealed env hides every `uv pip` package: a headered script failed `import six` while its headerless neighbor worked | bare `uv run file.py`; deps as a docstring `uv pip install` line |
| `uv run --with <pkg>` | re-resolves an env every run | `uv pip install <pkg>` once |
| any `uv run` flag (`--no-project`, `--script`, `--isolated`, `--quiet`, `--python`, ...) | flags work around a project or env that must not exist | `uv run file.py`; version comes from `.python-version` |
| `uv run python ...` in every form (`-c`, `-m`, REPL, file) | no interpreter appears on a command line on this host | `probe.py` + `uv run probe.py`; `.py` entry points |
| `pyproject.toml`, `uv.lock`, `uv add`, `uv sync`, `uv lock`, `uv init` | a pyproject turns `uv run` into ".venv creation" and hides the shared libraries | a `.py` file plus a docstring install line |
| `uv venv`, `virtualenv`, `.venv`, `venv/` | a second library set to sync by hand | `uv pip install` into the shared interpreter |
| `uvx <pkg>`, `uv tool run <pkg>` | a third way to reach a tool; hides which env it lives in | `uv tool install <pkg>`, bare command |
| `pip`, `pipx`, `python`, `python3`, `py` | resolves to a python.org install `uv run` never sees | the `uv ...` forms above |
| typing: annotations, `import typing`, `from __future__ import annotations`, TypedDict, Protocol, `@dataclass`, `typing.NamedTuple`, PEP 695 `type X =`/`def f[T]`, `cast`, `@overload`, `Final`, `ClassVar`, `Self`, `@override`, `assert_type`, mypy/pyright/pyre | Python here is dynamic and brief; annotations cost maintenance and buy nothing | plain code; runtime checks (`isinstance`, guards, `assert`); `collections.namedtuple`, plain class, or dict; strip checker configs when modernizing |

## Host facts (verified 2026-11-26, uv 0.13.10)

- `~\.python-version` = `3.13`, so every `uv run` anywhere uses
  `%APPDATA%\uv\python\cpython-3.13-windows-x86_64-none\python.exe` (uv walks up from the cwd).
- `%APPDATA%\uv\uv.toml`: `[pip] python = '<that absolute path>'` +
  `break-system-packages = true`. `uv pip` never reads `.python-version`; a version request
  (`python = '3.13'`) resolves against discovered environments, not managed interpreters, and
  fails - hence the absolute path, riding the junction name (`cpython-3.13-...-none`), which
  `uv python upgrade` repoints, so the pin survives upgrades (a patch-versioned pin dangles).
  Every uv-managed interpreter carries `Lib\EXTERNALLY-MANAGED` (verified 3.12-3.16): uv
  guarding its own tree, which this policy owns as the one shared store - without the flag every
  `uv pip install` dies `externally-managed-environment`.
- Installed for scripts: pypdf, pyyaml, paramiko, requests, jsonschema, ruamel.yaml, mutagen,
  markdown-it-py, mdit-py-plugins, linkify-it-py, httpx, pytest, pytest-xdist, numpy,
  faster-whisper, sherpa-onnx, av, ctranslate2, onnxruntime, bcrypt, cryptography, pynacl, cffi,
  invoke. Tools on 3.13: ruff, ty, yt-dlp, arxiv-mcp-server, paper-search-mcp.
- PEP 723 cost, measured here: uv caches each headered script's sealed env at
  `<cache>\environments-v2\<stem>-<hash>`, keyed on deps + `requires-python` + interpreter. A
  cache hit still pays resolve-validation every run; a header edit mints a new hash and orphans
  the old env (one script: five generations); a distinct `requires-python` seals a distinct
  interpreter (one 3.15 env sits beside the 3.13 host) and cross-version dupes are real bytes -
  ABI-specific wheels cannot hardlink-share. Standing waste: 501 dead envs, 1.1 GB, reclaimable
  with `uv cache clean`, regenerable by design.
- 3.12/3.15/3.16 and the python.org installs remain on PATH; unused - never code against them.
  After `uv python upgrade --reinstall` the junction moves and `uv pip list` shows nothing:
  re-run the installs; nothing else changes.
- Doubtful feature: <https://docs.python.org/3/whats-new.html>, or write `probe.py` and
  `uv run probe.py` - never `python -c`. `C:\Users\Lance\Documents\python-release-notes\`
  does not exist; never cite it.

## Workflow

Assume 3.13. Write modern from the tables without narrating substitutions. Self-audit: pathlib
for file code, no annotations, no `uv run` flag, no interpreter after `uv run`, no header, no
packaging file, nothing newer than 3.13. Reviewing existing code: report superseded patterns,
then give the corrected code in the format at the bottom.

## Language and brevity

| Superseded | Modern | Since |
| --- | --- | --- |
| `"%s" % x`, `"{}".format(x)`, `"a" + str(x)` | f-strings `f"{x}"`; self-documenting `f"{x=}"` | baseline (debug `=` 3.8) |
| Workarounds to reuse quotes / nest f-strings | Direct nested quotes, multi-line expressions, backslashes inside f-strings | 3.12 (PEP 701) |
| `if k in d: v = d[k] else: v = default` | `d.get(k, default)`; walrus `if (m := pat.search(s)):` to avoid recompute | baseline (walrus 3.8) |
| Long `if/elif` chains dispatching on a value or shape | `match` / `case` with patterns and guards | 3.10 (PEP 634) |
| `{**a, **b}`, `a.copy(); a.update(b)` | `a \| b` (new dict) and `a \|= b` (in place) | 3.9 (PEP 584) |
| `s[len(p):] if s.startswith(p) else s`, `s.rstrip("x")` hacks | `s.removeprefix(p)`, `s.removesuffix(suf)` | 3.9 |
| `result = []; for x in xs: result.append(f(x))` | Comprehension `[f(x) for x in xs]`; generator `(f(x) for x in xs)` when lazy | baseline (inlined 3.12, PEP 709) |
| `for i in range(len(xs))`, parallel index loops | `enumerate(xs)`, `zip(xs, ys, strict=True)` | baseline (`strict=` 3.10) |
| `try: ... except SomeError: pass` | `with contextlib.suppress(SomeError): ...` | baseline |
| Manual `open()`/`close()`, nested `with` via backslashes | `with` block; parenthesized multi-context `with (a, b):` | baseline (parenthesized 3.10) |
| `s = ""; for p in parts: s += p` | `"".join(parts)` (quadratic vs linear) | baseline |
| Hand-rolled memo dict | `@functools.cache` or `@functools.lru_cache(maxsize=...)` | baseline (`cache` 3.9) |
| `datetime.utcnow()`, `datetime.utcfromtimestamp()` | `datetime.now(timezone.utc)`, `datetime.fromtimestamp(ts, timezone.utc)` | deprecated 3.12 |
| `distutils`, `imp`, `asyncore`, `asynchat` | gone on 3.13: `importlib`, `asyncio` | removed 3.12 (PEP 632) |

## Standard library and speed

| Superseded | Modern | Since |
| --- | --- | --- |
| Manual chunking loop | `itertools.batched(xs, n)` | 3.12 |
| `zip(xs, xs[1:])` for neighbors | `itertools.pairwise(xs)` | 3.10 |
| Third-party `toml`/`tomli` for reading | `tomllib.load(f)` (stdlib, read-only) | 3.11 |
| `asyncio.gather` for structured fan-out; `wait_for` | `async with asyncio.TaskGroup() as tg:`; `async with asyncio.timeout(s):` | 3.11 |
| `pytz` | `zoneinfo.ZoneInfo("Region/City")` | 3.9 |
| Manual dot product / float stepping | `math.sumprod(a, b)`, `math.nextafter(x, y, steps=n)` | 3.12 |
| `re` for simple prefix/suffix/contains tests | `str` methods (`startswith`, `endswith`, `in`, `removeprefix`) | baseline |
| Hand-counted dicts / lists-as-queues | `collections.Counter`, `defaultdict`, `deque` | baseline |
| Manual dependency ordering | `graphlib.TopologicalSorter` | 3.9 |
| C-API extension for a hot loop | `ctypes`/`cffi` only if a real profile demands it; 3.13 free-threading and JIT are preview and not what this host runs | 3.13 preview |
| 3.14+ ideas (t-strings, `compression.zstd`, `uuid.uuid6/7/8`) | **Not available on 3.13**; `zstandard` would need a `uv pip install` the stdlib answer cannot give | unavailable |

Speed habits: builtins and comprehensions (C loop) over Python-level loops; `join` over `+=`;
`cache` pure repeated calls; right container (`deque` for ends, `set` for membership); no
premature abstraction; stdlib before dependency.

## Filesystem: pathlib

| Superseded | Modern |
| --- | --- |
| `os.path.join(a, b)` | `Path(a) / b` |
| `with open(p) as f: f.read()` | `Path(p).read_text(encoding="utf-8")` / `.read_bytes()` |
| `with open(p, "w") as f: f.write(s)` | `Path(p).write_text(s, encoding="utf-8")` / `.write_bytes(b)` |
| `os.path.exists/isfile/isdir(p)` | `Path(p).exists()` / `.is_file()` / `.is_dir()` |
| `os.listdir(p)`, `glob.glob(p + "/*.py")` | `Path(p).iterdir()`, `.glob("*.py")`, `.rglob("*.py")` |
| `os.path.basename/splitext/dirname(p)` | `Path(p).name` / `.stem` / `.suffix` / `.parent` |
| `os.makedirs(p, exist_ok=True)` | `Path(p).mkdir(parents=True, exist_ok=True)` |
| `os.walk(p)` | `Path(p).walk()` (3.12) |
| `os.path.abspath/expanduser(p)` | `Path(p).resolve()` / `.expanduser()` |

## Shape of a script

```python
"""Fetch a page to disk.

Needs: uv pip install requests
Usage: uv run fetch.py <url> [--out FILE]
"""

import sys
from pathlib import Path

import requests

out = Path(sys.argv[2] if len(sys.argv) > 2 else "page.html")
out.write_text(requests.get(sys.argv[1], timeout=30).text, encoding="utf-8")
```

Docstring names the run command and every `uv pip install` a fresh machine needs; pathlib does
the file work; no shebang - `#!/usr/bin/env python3` resolves through PATH, which is not how
this host runs scripts.

## Review / migrate output

```
Superseded -> 3.13 modern
- path:line  old: `os.path.join(a, b)`        ->  `Path(a) / b`
- path:line  old: `def f(x: int) -> int:`     ->  `def f(x):`  (typing ban)
- path:line  old: `uv run --with httpx s.py`  ->  `uv pip install httpx`, then `uv run s.py`
- path:line  old: `# /// script` header       ->  delete it; deps move to a `uv pip install` line
```

Then the full modernized snippet; keep the report to the substitutions that matter.
