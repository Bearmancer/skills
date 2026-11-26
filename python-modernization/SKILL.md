---
name: python-modernization
description: Use whenever writing, reviewing, refactoring or explaining any Python (.py, notebooks) or picking a Python run or install command, even when the code looks fine, because model knowledge skews old. Targets Python 3.13 alone and installs through `uv pip install` (libraries) or `uv tool install` (tools) only. Enforces brief untyped syntax and pathlib over os.path, and bans `pyproject.toml`, `uv.lock`, `.venv`, PEP 723 `# /// script` headers, `uv run` flags such as `--with`/`--no-project`, `uv sync`/`uv add`/`uvx` and all static typing. Also answers "is this deprecated" and Python upgrade questions.
---

# Modern Python, enforced

Model knowledge of Python skews old: most training text predates 3.12. This skill overrides
that skew. The rule: **never emit a superseded pattern when a modern, briefer, faster
replacement exists for 3.13.**

This is the Python authority on this host: **one target version, two install commands, no
typing, pathlib, fewest lines**. Environment rules live in `~/.agents/AGENTS.md` "Python" and
are restated here identically, because a doc that disagrees with the guard plugins gets the
caller blocked mid-command.

**Target: CPython 3.13 only** (host runs 3.13.18, x86_64). Treat 3.14/3.15/3.16 features as
unavailable; never write a version switch (`--python 3.12`, `py -V:3.13`). 3.13 rather than
the newer stable is deliberate: `onnxruntime`, needed by `faster-whisper`, publishes no
Windows `cp315` wheel (its ABI tags run `cp311`-`cp314`), and 3.13 runs everything else, so
the choice costs nothing.

## The commands

| Job | Command |
| --- | --- |
| Run a script that lives in a repo or skill | `uv run <file.py> <args>` |
| Get a library a script imports | `uv pip install <pkg>` |
| Get a tool you type as a command (`ruff`, `yt-dlp`, an MCP server) | `uv tool install <pkg>` |

`uv run` takes **no flags** and is never followed by `python` - not for `-m`, not for `-c`, not
bare. A test suite gets a `.py` entry point (`uv run tests/test_stt.py` behind a
`unittest.main()` guard); a tool that exists only as `python -m <tool>` gets installed as a
tool (`uv tool install <pkg>`) and called bare. `uvx`/`uv tool run` is not used - install the
tool once with `uv tool install`, then call it by name.

### `uv tool` versus `uv pip`, for your own scripts

Both fetch from PyPI into an interpreter uv manages; they differ in **who imports the result**.

| | `uv pip install <pkg>` | `uv tool install <pkg>` |
| --- | --- | --- |
| Where it lands | the interpreter `uv run` uses, `%APPDATA%\uv\python\cpython-3.13-...\site-packages` | a private env per tool under `%APPDATA%\uv\tools\<pkg>` |
| What you get | importable modules for every script | one `.exe` entry point in `~\.local\bin` |
| Needs packaging files | no | yes: `pyproject.toml` or `setup.py`. A folder holding only a `.py` fails with "does not appear to be a Python project" |
| Packages with no console entry point | installed normally | dropped, so a plain library is invisible |
| Use for | `requests`, `pyyaml`, `mutagen`, `pytest` - anything your `.py` imports | other people's CLIs (`ruff`, `ty`, `yt-dlp`, MCP servers) |

So: **your own script never goes through `uv tool`.** `uv pip install` its libraries, then run
it with `uv run`. The two are not interchangeable, and a script installed as a tool is the one
thing this layout cannot express.

## Banned, with the reason each ban exists

| Forbidden | Why | Use instead |
| --- | --- | --- |
| `# /// script` PEP 723 header | uv builds a sealed env for the script, so `uv pip` packages vanish: a headered script failed `import six` while the headerless file beside it imported it | bare `uv run file.py` |
| `uv run --with <pkg>` | re-resolves an env on every run, the cost the header was meant to remove | `uv pip install <pkg>` once |
| `uv run --no-project`, `--script`, `--isolated`, `--quiet`, `--python` | flags exist to work around a project or env that should not be there | `uv run file.py`; version comes from `.python-version` |
| `pyproject.toml`, `uv.lock`, `uv add`, `uv sync`, `uv lock`, `uv init` | a `pyproject.toml` in the tree turns `uv run` into "Creating virtual environment at: .venv" and the installed libraries stop being visible | a `.py` file plus a `uv pip install` line in its docstring |
| `uv venv`, `virtualenv`, `.venv`, `venv/` | a venv is a second library set to keep in sync by hand, and it hides the shared one | `uv pip install` into the default interpreter |
| `uvx <pkg>`, `uv tool run <pkg>` | a third way to reach a tool, and it hides which env the tool lives in | `uv tool install <pkg>`, then the bare command |
| `pip install`, `pipx`, `python`, `python3`, `py` | bypasses the one interpreter; `py`/`python` resolve to a python.org install that is not where `uv run` looks | the `uv ...` forms above |

## Host facts (verified 2026-11-26, uv 0.13.10)

- `C:\Users\Lance\.python-version` contains `3.13`, so every `uv run` anywhere uses
  `%APPDATA%\uv\python\cpython-3.13-windows-x86_64-none\python.exe` (3.13.18, 64-bit). uv
  finds that file by walking up from the working directory.
- `%APPDATA%\uv\uv.toml` pins `uv pip` to the interpreter `uv run` uses:
  `[pip] python = '<abs path>\cpython-3.13-windows-x86_64-none\python.exe'` plus
  `break-system-packages = true`. `uv pip` never reads `.python-version`, so without the pin it
  errors "No virtual environment found" or targets a stray interpreter. The path must be
  absolute: a version request (`python = '3.13'`) resolves against discovered environments,
  not managed interpreters, and fails. The pin rides the junction name, not the patch-versioned
  folder (`cpython-3.13.18-...`): `uv python upgrade` repoints the junction and the pin
  survives; a patch-path pin dangles after every upgrade.
- `break-system-packages` is needed because every uv-managed interpreter here carries a
  `Lib\EXTERNALLY-MANAGED` marker (verified 3.12 through 3.16). It is uv's install, not a
  Windows system Python - the marker is uv guarding its own tree, and this policy deliberately
  owns that tree as the one shared store. Without the flag every `uv pip install` dies with
  `externally-managed-environment`.
- Already installed for scripts: pypdf, pyyaml, paramiko, requests, jsonschema, ruamel.yaml,
  mutagen, markdown-it-py, mdit-py-plugins, linkify-it-py, httpx, pytest, pytest-xdist, numpy,
  faster-whisper, sherpa-onnx, av, ctranslate2, onnxruntime, and the security stack
  (bcrypt, cryptography, pynacl, cffi, invoke).
- PEP 723 cost, measured on this host: uv caches each headered script's sealed env at
  `<cache>\environments-v2\<stem>-<hash>`, keyed on deps + `requires-python` + interpreter. A
  cache hit still pays resolve-validation every run; a header edit mints a new hash and
  orphans the old env (one script here: five generations). A distinct `requires-python` seals a
  distinct interpreter - one 3.15 env sits beside the 3.13 host - and cross-version dupes are
  real bytes, since ABI-specific wheels cannot hardlink-share. Running total: 501 dead envs,
  1.1 GB, reclaimable with `uv cache clean` and regenerable by design. The sealed env also
  cannot see the shared site-packages, which is the ban's real reason: a header re-declares a
  parallel dependency set.
- Tools live on 3.13 as of 2026-11-26: `ruff` 0.17.6, `ty` 0.0.111, `yt-dlp` 2026.11.23,
  `arxiv-mcp-server` 0.8.2, `paper-search-mcp` 0.1.4.
- 3.12/3.15/3.16 remain in `%APPDATA%\uv\python` and the python.org installs are still on
  PATH. They are unused by this policy; do not code against them.
- After `uv python upgrade --reinstall`, the 3.13 junction moves to a new patch folder and
  `uv pip list` shows nothing: re-run the installs. Nothing else changes.
- Source for a doubtful feature: <https://docs.python.org/3/whats-new.html>, or a probe file -
  write `probe.py` (`import sys`, print what you need) and `uv run probe.py`. Never `python -c`,
  not even under `uv run`: no interpreter appears on a command line on this host. The
  previously cited `C:\Users\Lance\Documents\python-release-notes\` folder does not exist on
  this machine; do not trust a citation to it.

## House mandates (non-negotiable)

1. **No typing, at all.** No annotations, no `typing`, no type checkers. Python here is
   dynamic and brief; annotations cost maintenance and buy nothing for this style.
2. **One run command:** `uv run <file.py> <args>`, no flags, never a venv, never `--with`.
3. **pathlib for every filesystem touch**, with explicit `encoding="utf-8"`. No `os.path`
   string surgery, no bare `open()`.
4. **No packaging files of ours, ever.** No `pyproject.toml`, `uv.lock`, `.venv`, or PEP 723
   header. A script is a `.py` file plus a `uv pip install` line naming what it needs.
5. **Fewest lines, whatever the complexity.** Fewer allocations, C-speed builtins over Python
   loops, stdlib before any dependency, no abstraction nobody calls.

## Workflow

1. **Assume 3.13.** To confirm what a run really uses, `uv run` a two-line probe script that
   prints `sys.version` and `sys.executable`.
2. **Write modern by default.** Apply the catalog without narrating each substitution.
3. **Self-audit.** Walk the catalog over what you wrote: pathlib for file code, no
   annotations, no `uv run` flag, no script header, no packaging file, nothing newer than
   3.13.
4. **Review/migrate mode** (user hands you existing code): report superseded patterns, then
   give the corrected code in the format at the bottom.

## Language and brevity

| Superseded | Modern | Since |
| --- | --- | --- |
| `"%s" % x`, `"{}".format(x)`, `"a" + str(x)` | f-strings `f"{x}"`; self-documenting `f"{x=}"` | `[baseline]` (debug `=` 3.8) |
| Workarounds to reuse quotes / nest f-strings | Direct nested quotes, multi-line expressions, backslashes inside f-strings | 3.12 (PEP 701) |
| `if k in d: v = d[k] else: v = default` | `d.get(k, default)`; walrus `if (m := pat.search(s)):` to avoid recompute | `[baseline]` (walrus 3.8) |
| Long `if/elif` chains dispatching on a value or shape | `match` / `case` with patterns and guards | 3.10 (PEP 634) |
| `{**a, **b}`, `a.copy(); a.update(b)` | `a \| b` (new dict) and `a \|= b` (in place) | 3.9 (PEP 584) |
| `s[len(p):] if s.startswith(p) else s`, `s.rstrip("x")` hacks | `s.removeprefix(p)`, `s.removesuffix(suf)` | 3.9 |
| `result = []; for x in xs: result.append(f(x))` | Comprehension `[f(x) for x in xs]`; generator `(f(x) for x in xs)` when lazy | `[baseline]` (inlined 3.12, PEP 709) |
| `for i in range(len(xs))`, parallel index loops | `enumerate(xs)`, `zip(xs, ys, strict=True)` | `[baseline]` (`strict=` 3.10) |
| `try: ... except SomeError: pass` | `with contextlib.suppress(SomeError): ...` | `[baseline]` |
| Manual `open()`/`close()`, nested `with` via backslashes | `with` block; parenthesized multi-context `with (a, b):` | `[baseline]` (parenthesized 3.10) |
| `s = ""; for p in parts: s += p` | `"".join(parts)` (quadratic vs linear) | `[baseline]` |
| Hand-rolled memo dict | `@functools.cache` or `@functools.lru_cache(maxsize=...)` | `[baseline]` (`cache` 3.9) |
| `typing.NamedTuple`, `@dataclass` (annotation-based) | `collections.namedtuple`, plain class, or dict | `[baseline]` (see typing ban) |
| `datetime.utcnow()`, `datetime.utcfromtimestamp()` | `datetime.now(timezone.utc)`, `datetime.fromtimestamp(ts, timezone.utc)` | deprecated 3.12 |
| `distutils`, `imp`, `asyncore`, `asynchat` | gone (probe: `import distutils` raises ModuleNotFoundError on 3.13): `importlib`, `asyncio` | removed 3.12 (PEP 632) |

## Standard library and speed

| Superseded | Modern | Since |
| --- | --- | --- |
| Manual chunking loop | `itertools.batched(xs, n)` | 3.12 (probe: present) |
| `zip(xs, xs[1:])` for neighbors | `itertools.pairwise(xs)` | 3.10 `[baseline]` |
| Third-party `toml`/`tomli` for reading | `tomllib.load(f)` (stdlib, read-only) | 3.11 (probe: present) |
| `asyncio.gather` for structured fan-out; `wait_for` | `async with asyncio.TaskGroup() as tg:`; `async with asyncio.timeout(s):` | 3.11 (probe: present) |
| `pytz` | `zoneinfo.ZoneInfo("Region/City")` | 3.9 `[baseline]` |
| Manual dot product / float stepping | `math.sumprod(a, b)`, `math.nextafter(x, y, steps=n)` | 3.12 `[baseline]` |
| `re` for simple prefix/suffix/contains tests | `str` methods (`startswith`, `endswith`, `in`, `removeprefix`) | `[baseline]` |
| Hand-counted dicts / lists-as-queues | `collections.Counter`, `defaultdict`, `deque` | `[baseline]` |
| Manual dependency ordering | `graphlib.TopologicalSorter` | 3.9 `[baseline]` |
| C-API extension for a hot loop | `ctypes`/`cffi` only if a real profile demands it; the free-threaded 3.13 build and the 3.13 JIT are preview, opt-in, and not what this host runs | 3.13 (preview) |
| 3.14+ ideas (t-strings, `compression.zstd`, `uuid.uuid6/7/8`, `optimize()` probe) | **Not available on 3.13.** Do not write them; `zstandard` is absent from `sys.stdlib_module_names` (probe) and would need a `uv pip install` that the stdlib answer cannot give | unavailable |

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

The docstring names the run command and any library a fresh machine must `uv pip install`;
`pathlib` does the file work; nothing else in the file mentions environments. No shebang:
`#!/usr/bin/env python3` resolves through PATH, which is not how this host runs scripts.

## Banned: typing (turn it off)

| Remove / never write | Instead |
| --- | --- |
| `x: int`, `def f(a: int) -> str:` | No annotations; plain `x = ...`, `def f(a):` |
| `from typing import List, Dict, Optional, ...` / `import typing` | Nothing; use builtins dynamically |
| `from __future__ import annotations` | Remove |
| `class X(TypedDict)`, `class X(Protocol)` | Plain dict; duck typing / `isinstance` at runtime |
| `@dataclass`, `typing.NamedTuple` (need annotations) | `collections.namedtuple`, plain class, or dict |
| `type Alias = ...`, `def f[T](...)` (PEP 695, 3.12) | Remove; no static generics |
| `cast`, `@overload`, `Final`, `ClassVar`, `Self`, `@override`, `assert_type` | Remove |
| mypy / pyright / pyre config and runs | Do not add or run them; strip their config and annotations when modernizing |

Where a runtime guarantee matters, check it (`isinstance`, a guard, an `assert`) rather than
annotating it.

## Review / migrate output

Report findings, then the corrected code:

```
Superseded -> 3.13 modern
- path:line  old: `os.path.join(a, b)`        ->  `Path(a) / b`
- path:line  old: `def f(x: int) -> int:`     ->  `def f(x):`  (typing ban)
- path:line  old: `uv run --with httpx s.py`  ->  `uv pip install httpx`, then `uv run s.py`
- path:line  old: `# /// script` header       ->  delete it; deps move to a `uv pip install` line
```

Then give the full modernized snippet. Keep the report to the substitutions that matter.
