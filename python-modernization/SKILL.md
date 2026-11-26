---
name: python-modernization
description: Use whenever writing, reviewing, refactoring or explaining any Python (.py, notebooks, one-liners) or choosing a Python run or install command, even when the code looks fine, because model knowledge skews old and this host's guards block the usual commands. Also use when a task touches pyproject.toml, uv.lock, .venv, PEP 723 headers, type annotations or uv commands, and for "is this deprecated" and Python upgrade questions. Enforces Python 3.13 only, `uv run <file.py>`, `uv pip install` / `uv tool install`, no typing, pathlib, fewest lines.
---

# Modern Python, enforced

Model knowledge predates 3.12; this skill overrides it. It restates `~/.agents/AGENTS.md` "Python" identically - a doc that disagrees with the guard plugins gets the caller blocked mid-command.

**CPython 3.13 only.** 3.14+ features do not exist here, and a version switch (`--python`, `py -V:`) is never written. Why 3.13: `onnxruntime`, which `faster-whisper` needs, ships no Windows cp315 wheel, and 3.13 runs everything else.

**Rules:** no typing; one run command; pathlib with explicit `encoding="utf-8"`, never bare `open()`; no packaging files; fewest lines - builtins and comprehensions over Python loops, `join` over `+=`, `functools.cache` for pure repeated calls, the right container, stdlib before any dependency, no abstraction nobody calls.

## Commands

| Job | Command |
| --- | --- |
| Run a script | `uv run <file.py> <args>` - no flags, never followed by `python` (no `-m`, no `-c`, no REPL) |
| Library a script imports | `uv pip install <pkg>` |
| Tool you type as a command | `uv tool install <pkg>`, then call it bare |

Test suites get a `.py` entry point (`uv run tests/test_stt.py` behind `unittest.main()`); a tool that exists only as `python -m <tool>` gets `uv tool install`. Never `uvx`/`uv tool run`.

`uv pip` installs into the shared interpreter: importable by every script, no packaging files. `uv tool` builds a private env per tool with one `.exe` in `~\.local\bin`, requires `pyproject.toml`/`setup.py`, and drops packages with no entry point. **A script of your own never goes through `uv tool`.**

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

Environment trouble - `uv pip` finds no interpreter, `externally-managed-environment`, an installed package will not import, a bloated uv cache: read `references/host.md`.

## Catalog (everything here runs on 3.13)

| Superseded | Modern |
| --- | --- |
| `os.path.join(a, b)` | `Path(a) / b` |
| `with open(p) as f: f.read()` / `open(p, "w")` | `Path(p).read_text(encoding="utf-8")` / `.write_text(s, encoding="utf-8")` / `.read_bytes()` / `.write_bytes(b)` |
| `os.path.exists/isfile/isdir(p)` | `Path(p).exists()` / `.is_file()` / `.is_dir()` |
| `os.listdir(p)`, `glob.glob(p + "/*.py")`, `os.walk(p)` | `Path(p).iterdir()`, `.glob("*.py")`, `.rglob("*.py")`, `.walk()` |
| `os.path.basename/splitext/dirname(p)` | `Path(p).name` / `.stem` / `.suffix` / `.parent` |
| `os.makedirs(p, exist_ok=True)`, `os.path.abspath/expanduser(p)` | `Path(p).mkdir(parents=True, exist_ok=True)`, `.resolve()`, `.expanduser()` |
| `"%s" % x`, `"{}".format(x)`, `"a" + str(x)` | f-strings `f"{x}"`; self-documenting `f"{x=}"` |
| Workarounds to reuse quotes / nest f-strings | direct nested quotes, multi-line expressions, backslashes inside f-strings |
| `if k in d: v = d[k] else: v = default` | `d.get(k, default)`; walrus `if (m := pat.search(s)):` to avoid recompute |
| `result = []; for x in xs: result.append(f(x))` | comprehension `[f(x) for x in xs]`; generator `(f(x) for x in xs)` when lazy |
| `s = ""; for p in parts: s += p` | `"".join(parts)` (quadratic vs linear) |
| hand-rolled memo dict | `@functools.cache` or `@functools.lru_cache(maxsize=...)` |
| `re` for simple prefix/suffix/contains tests | `str` methods: `startswith`, `endswith`, `in`, `removeprefix` |
| hand-counted dicts, lists as queues | `collections.Counter`, `defaultdict`, `deque` for ends, `set` for membership |
| Long `if/elif` chain dispatching on a value or shape | `match` / `case` with patterns and guards |
| `{**a, **b}`, `a.copy(); a.update(b)` | `a \| b` (new dict), `a \|= b` (in place) |
| `s[len(p):] if s.startswith(p) else s`, `s.rstrip("x")` hacks | `s.removeprefix(p)`, `s.removesuffix(suf)` |
| `for i in range(len(xs))`, parallel index loops | `enumerate(xs)`, `zip(xs, ys, strict=True)` |
| `zip(xs, xs[1:])` for neighbors; manual chunking loop | `itertools.pairwise(xs)`; `itertools.batched(xs, n)` |
| `try: ... except SomeError: pass` | `with contextlib.suppress(SomeError): ...` |
| nested `with` joined by backslashes | `with (a, b):` |
| `toml`/`tomli` for reading | `tomllib.load(f)` (stdlib, read-only) |
| `asyncio.gather` for fan-out; `wait_for` | `async with asyncio.TaskGroup() as tg:`; `async with asyncio.timeout(s):` |
| `pytz` | `zoneinfo.ZoneInfo("Region/City")` |
| `datetime.utcnow()`, `datetime.utcfromtimestamp()` (deprecated 3.12) | `datetime.now(timezone.utc)`, `datetime.fromtimestamp(ts, timezone.utc)` |
| `distutils`, `imp`, `asyncore`, `asynchat` (removed 3.12) | gone: `importlib`, `asyncio` |
| manual dot product / float stepping; manual dependency ordering | `math.sumprod(a, b)`, `math.nextafter(x, y, steps=n)`; `graphlib.TopologicalSorter` |
| C extension for a hot loop | profile first, then `ctypes`/`cffi`; 3.13 free-threading and JIT are preview and not what this host runs |
| t-strings, `compression.zstd`, `uuid.uuid6/7/8` | **not on 3.13** - do not write them; `zstandard` would need a `uv pip install` the stdlib cannot answer |

## Script shape

A script is a `.py` file whose docstring names what a fresh machine needs, then the run line. No shebang: `#!/usr/bin/env python3` resolves through PATH, which is not how this host runs scripts.

```python
"""Needs: uv pip install requests
Usage: uv run fetch.py <url>"""
```

## Review mode

Report each substitution that matters as `path:line  old -> new`, then give the full modernized snippet:

```
- a.py:12  `def f(x: int) -> int:`     ->  `def f(x):`  (typing ban)
- b.py:3   `uv run --with httpx s.py`  ->  `uv pip install httpx`, then `uv run s.py`
- c.py:1   `# /// script` header       ->  delete it; deps move to a `uv pip install` docstring line
```
