---
name: python-modernization
description: Use whenever writing, reviewing, refactoring, running or explaining any Python (.py, notebooks, one-liners, tests with pytest or unittest), when a run fails with ModuleNotFoundError or ImportError, or when choosing a `uv run`, `uv pip install` or `uv tool install` command, even when the code looks fine, because older Python habits are common and this host's guards block the usual commands. Also use when a task touches pyproject.toml, uv.lock, .venv, PEP 723 headers or type annotations, and for "is this deprecated" and Python upgrade questions. Enforces Python 3.13 only, pathlib, no typing, fewest lines.
---

# Modern Python, enforced

This skill extends the Python rule in `~/.agents/AGENTS.md` ("Code and guards") with stricter bans of its own, such as typing and `uv run python`. The python-guard plugin enforces only part of this, so follow the skill even where a command is let through.

**CPython 3.13 only.** 3.14+ is installed on this box (3.15.2, 3.16.0a2) and never used; a version switch (`--python`, `py -V:`) is never written, and a nearer `.python-version` overrides the 3.13 default. Why 3.13: `faster-whisper` needs `onnxruntime`, and the latest `onnxruntime` (1.32.0) lists no Windows cp315 wheel.

## Commands

| Job | Command |
| --- | --- |
| Run a script | `uv run <file.py> <args>` - no flags, never followed by `python` (no `-m`, no `-c`, no REPL) |
| Library a script imports | `uv pip install <pkg>` |
| Tool you type as a command | `uv tool install <pkg>`, then call it bare |

Test suites get a `.py` entry point (`uv run tests/test_stt.py` behind `unittest.main()`); a tool that exists only as `python -m <tool>` gets `uv tool install`. Never `uvx`/`uv tool run`.

`uv tool install` gives each tool a private environment; each console or script entry point becomes an executable in `~\.local\bin` (paper-search-mcp installs two: `paper-search` and `paper-search-mcp`). A package with no such entry point installs no command. **A script of your own never goes through `uv tool`.**

## Banned

| Forbidden | Why | Instead |
| --- | --- | --- |
| `# /// script` PEP 723 header | uv builds that script's environment from the header's dependencies (uv scripts docs), one cache entry per script (uv storage docs); packages a run already used are reused, not downloaded again (uv cache docs) | bare `uv run file.py`; deps as a docstring `uv pip install` line |
| `uv run --with <pkg>` | per-invocation dependencies (uv scripts docs), not the shared interpreter | `uv pip install <pkg>` once |
| any `uv run` flag (`--no-project`, `--script`, `--isolated`, `--quiet`, `--python`, ...) | flags work around a project or env that must not exist | `uv run file.py`; version comes from `.python-version` |
| `uv run python ...` in every form (`-c`, `-m`, REPL, file) | no interpreter appears on a command line on this host | `probe.py` + `uv run probe.py`; `.py` entry points |
| `pyproject.toml`, `uv.lock`, `uv add`, `uv sync`, `uv lock`, `uv init` | a pyproject makes `uv run` create a `.venv` (uv storage docs) and install the project first (uv scripts docs) | a `.py` file plus a docstring install line |
| `uv venv`, `virtualenv`, `.venv`, `venv/` | a second library set to sync by hand | `uv pip install` into the shared interpreter |
| `uvx <pkg>`, `uv tool run <pkg>` | a temporary environment per call (uv tools docs) | `uv tool install <pkg>`, bare command |
| `pip`, `pipx`, `python`, `python3`, `py` | resolve to interpreters `uv run` does not use; `python` first resolves to `WindowsApps\python.exe` | the `uv ...` forms above |
| typing: annotations, `import typing`, `from __future__ import annotations`, TypedDict, Protocol, `@dataclass`, `typing.NamedTuple`, PEP 695 `type X =`/`def f[T]`, `cast`, `@overload`, `Final`, `ClassVar`, `Self`, `@override`, `assert_type`, mypy/pyright/pyre | Python here is dynamic and brief; annotations cost maintenance and buy nothing | plain code; runtime checks (`isinstance`, guards, `assert`); `collections.namedtuple`, plain class, or dict; strip checker configs when modernizing |

The guard also rejects `.py` writes and edits that call bare `open()`, add a PEP 723 header, or use `os.path`, `os.listdir`, `os.walk`, `os.mkdir`, `os.makedirs`, `os.remove`, `os.unlink` or `shutil` in a file that does not import `pathlib`.

Environment trouble - `uv pip` finds no interpreter, `externally-managed-environment`, an installed package will not import, the uv cache is large, the Python version is not the expected one, or an upgrade ran: read `references/host.md`.

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
| Workarounds to reuse quotes / nest f-strings | direct nested quotes, multi-line expressions with comments, backslashes inside f-strings |
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
| manual `open()`/`close()`; nested `with` joined by backslashes | `with Path(p).open(encoding="utf-8") as f:`; `with (a, b):` |
| `toml`/`tomli` for reading | `tomllib.loads(Path(p).read_text(encoding="utf-8"))` (stdlib, read-only) |
| `asyncio.gather` for fan-out; `wait_for` | `async with asyncio.TaskGroup() as tg:`; `async with asyncio.timeout(s):` |
| `pytz` | `zoneinfo.ZoneInfo("Region/City")`; on Windows install `tzdata` first (`uv pip install tzdata`): without it ZoneInfo raised ZoneInfoNotFoundError on this host |
| `datetime.utcnow()`, `datetime.utcfromtimestamp()` (deprecated 3.12) | `datetime.now(timezone.utc)`, `datetime.fromtimestamp(ts, timezone.utc)` |
| `imp` (removed 3.12) | `importlib` |
| `asyncore`, `asynchat` (removed 3.12) | `asyncio` |
| `distutils` (removed 3.12) | `shutil.which` for `find_executable`; `sysconfig` for `distutils.sysconfig` |
| manual dot product / float stepping; manual dependency ordering | `math.sumprod(a, b)`, `math.nextafter(x, y, steps=n)`; `graphlib.TopologicalSorter` |

**Not on 3.13**, so do not write them: t-strings, `compression.zstd`, `uuid.uuid6/7/8`. For zstd, install the third-party package (`uv pip install zstandard`).

Beyond the catalog: `array` or `memoryview` for numeric buffers (a `memoryview` slice shares its buffer; a `bytearray` slice copies); avoid needless copies; stdlib before a dependency; no abstraction nobody calls; fewest lines. Write modern by default and apply the catalog without narrating each substitution.

For a hot loop, profile first. `ctypes` is stdlib but bypasses Python's memory safety (ctypes docs); `cffi` is a third-party package (`uv pip install cffi`). In 3.13 the free-threaded build and the JIT are experimental (What's New 3.13), and this host runs the GIL build (`Py_GIL_DISABLED` is 0).

## Script shape

A script is a `.py` file whose docstring names what a fresh machine needs, then the run line. No shebang: this host runs scripts with `uv run`.

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
