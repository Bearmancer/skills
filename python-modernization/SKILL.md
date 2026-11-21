---
name: python-modernization
description: Use whenever writing, reviewing, refactoring or explaining any Python (.py, pyproject.toml, uv.lock, notebooks) or picking a Python environment or run command. Enforces modern brief Python 3.9-3.15, bans superseded patterns and all static typing, uv only with no venvs, pathlib over os.path. Also for "is this deprecated" and Python upgrade questions.
---

# Modern Python, enforced

Model knowledge of Python skews old: most training text predates 3.12. This skill overrides
that skew. The rule: **never emit a superseded pattern when a modern, briefer, faster
replacement exists for the project's Python version.** If the replacement needs a newer
interpreter than the project has, say so once (one line, with the version) and still write
the modern form rather than silently falling back.

This is the single Python authority on this host. It absorbs environment setup (the old
`python-env` skill is retired) and adds four house mandates: **brevity, no typing, pathlib,
maximal speed**, all on **uv**.

Source of truth: the *What's New* essays for 3.9-3.16 saved at
`C:\Users\Lance\Documents\python-release-notes\3.9.md` ... `3.16.md` (collected 2026-11-18).
Release dates: 3.9 (2020-10-05), 3.10 (2021-10-04), 3.11 (2022-10-24), 3.12 (2023-10-02),
3.13 (2024-10-07), 3.14 (2025-10-07), 3.15 (2026-10-09). **Latest stable is 3.15.**
**3.16 is alpha (`3.16.0a2`), not beta** - treat it as preview, use only on request.
Catalog rows tagged `[baseline]` are long-established modernizations; `[notes]` rows trace
to the saved essays (open the matching `3.X.md` to confirm a detail before relying on it).

## House mandates (non-negotiable)

1. **No typing, at all.** No annotations, no `typing`, no type checkers. Python here is
   dynamic and brief; annotations are noise that costs maintenance and buys nothing for
   this style. See the ban table.
2. **uv only, never a venv.** Never `python -m venv`, `uv venv`, `virtualenv`, `pipenv`,
   `poetry`, `conda create`; never leave a `.venv/` behind. uv manages the interpreter.
3. **pathlib for every filesystem touch.** No `os.path` string surgery, no `open(str)`
   when a `Path` method does it in one call.
4. **pyproject.toml for libraries; `--with`/`--script` for one-off CLIs.** A real importable
   package is a uv project with `pyproject.toml`. A throwaway script uses inline deps.
5. **Brevity and speed first.** Fewer lines, fewer allocations, C-speed builtins over
   Python loops. Don't add a dependency the stdlib already covers.

## Workflow

1. **Find the target version.** Check, in order: `pyproject.toml` `requires-python`,
   `.python-version`, `uv.lock`, then `uv run python --version`. Nothing found: assume
   **3.15** and say so in one line. Treat **3.16 as alpha preview**.
2. **Write modern by default.** Apply the catalog without narrating each substitution.
   Modern, brief, untyped, pathlib-based code is the default, not a talking point.
3. **Self-audit.** Walk the catalog over what you wrote. Any filesystem code must use
   pathlib; any annotation or `typing` import must be removed; any venv/`pip install`
   command must become uv.
4. **Review/migrate mode** (user hands you existing code): report superseded patterns,
   then give the corrected code in the format at the bottom.

## Language and brevity

| Superseded | Modern | Since |
| --- | --- | --- |
| `"%s" % x`, `"{}".format(x)`, `"a" + str(x)` | f-strings `f"{x}"`; self-documenting `f"{x=}"` | `[baseline]` (debug `=` 3.8) |
| Workarounds to reuse quotes / nest f-strings | Direct nested quotes, multi-line expressions, comments, backslashes inside f-strings | 3.12 (PEP 701) |
| `if k in d: v = d[k] else: v = default` | `d.get(k, default)`; walrus `if (m := pat.search(s)):` to avoid recompute | `[baseline]` (walrus 3.8) |
| Long `if/elif` chains dispatching on a value or shape | `match` / `case` with patterns and guards | 3.10 (PEP 634) |
| `{**a, **b}`, `a.copy(); a.update(b)` | `a \| b` (new dict) and `a \|= b` (in place) | 3.9 (PEP 584) |
| `s[len(p):] if s.startswith(p) else s`, `s.rstrip("x")` hacks | `s.removeprefix(p)`, `s.removesuffix(suf)` | 3.9 |
| `result = []; for x in xs: result.append(f(x))` | Comprehension `[f(x) for x in xs]`; generator `(f(x) for x in xs)` when lazy | `[baseline]` (inlined/fast 3.12, PEP 709) |
| `for i in range(len(xs))`, parallel index loops | `enumerate(xs)`, `zip(xs, ys, strict=True)` | `[baseline]` (`strict=` 3.10) |
| `try: ... except SomeError: pass` | `with contextlib.suppress(SomeError): ...` | `[baseline]` |
| Manual `open()`/`close()`, nested `with` via backslashes | `with` block; parenthesized multi-context `with (a, b):` | `[baseline]` (parenthesized 3.10) |
| `s = ""; for p in parts: s += p` | `"".join(parts)` (quadratic vs linear) | `[baseline]` |
| Hand-rolled memo dict | `@functools.cache` (unbounded) or `@functools.lru_cache(maxsize=...)` | `[baseline]` (`cache` 3.9) |
| `typing.NamedTuple`, `@dataclass` (annotation-based) | `collections.namedtuple("P", "x y")`, plain class, or dict | `[baseline]` (see typing ban) |
| `datetime.utcnow()`, `datetime.utcfromtimestamp()` | `datetime.now(timezone.utc)`, `datetime.fromtimestamp(ts, timezone.utc)` | deprecated 3.12 `[notes]` |
| `distutils`, `imp`, `asyncore`, `asynchat` | Removed: use `setuptools`/`hatchling` via pyproject, `importlib`, `asyncio` | removed 3.12 (PEP 632) `[notes]` |

## Standard library and speed

| Superseded | Modern | Since |
| --- | --- | --- |
| Manual chunking loop | `itertools.batched(xs, n)` | 3.12 `[notes]` |
| `zip(xs, xs[1:])` for neighbors | `itertools.pairwise(xs)` | 3.10 `[baseline]` |
| Third-party `toml`/`tomli` for reading | `tomllib.load(f)` (stdlib, read-only) | 3.11 `[notes]` |
| `asyncio.gather` for structured fan-out; `wait_for` | `async with asyncio.TaskGroup() as tg:`; `async with asyncio.timeout(s):` | 3.11 `[notes]` |
| `pytz` | `zoneinfo.ZoneInfo("Region/City")` | 3.9 `[baseline]` |
| Manual dot product / float stepping | `math.sumprod(a, b)`, `math.nextafter(x, y, steps=n)` | 3.12 `[notes]` |
| `re` for simple prefix/suffix/contains tests | `str` methods (`startswith`, `endswith`, `in`, `removeprefix`) | `[baseline]` |
| Hand-counted dicts / lists-as-queues | `collections.Counter`, `defaultdict`, `deque` | `[baseline]` |
| Manual dependency ordering | `graphlib.TopologicalSorter` | 3.9 `[baseline]` |
| Old interpreter for hot code | Newest stable (3.11+ faster CPython; 3.12 comprehension inlining). 3.13/3.14 experimental JIT and free-threading are **preview, opt-in** | `[notes]` |
| `zlib`/`bz2`/`lzma` only, third-party zstd | `compression.zstd` (stdlib); t-strings `t"..."` for safe templating (PEP 750); `uuid.uuid6/7/8` | 3.14 `[notes]` (confirm in 3.14.md) |

Speed habits: prefer builtins and comprehensions (C loop) over Python-level loops; `join`
over `+=`; `cache` pure repeated calls; pick the right container (`deque` for ends, `set`
for membership, `array`/`memoryview` for numeric buffers); avoid premature abstraction and
needless copies; reach for the stdlib before adding a dependency.

## Filesystem: pathlib

| Superseded | Modern |
| --- | --- |
| `os.path.join(a, b)` | `Path(a) / b` |
| `with open(p) as f: f.read()` | `Path(p).read_text()` / `.read_bytes()` |
| `with open(p, "w") as f: f.write(s)` | `Path(p).write_text(s)` / `.write_bytes(b)` |
| `os.path.exists/isfile/isdir(p)` | `Path(p).exists()` / `.is_file()` / `.is_dir()` |
| `os.listdir(p)`, `glob.glob(p + "/*.py")` | `Path(p).iterdir()`, `.glob("*.py")`, `.rglob("*.py")` |
| `os.path.basename/splitext/dirname(p)` | `Path(p).name` / `.stem` / `.suffix` / `.parent` |
| `os.makedirs(p, exist_ok=True)` | `Path(p).mkdir(parents=True, exist_ok=True)` |
| `os.walk(p)` | `Path(p).walk()` (3.12) |
| `os.path.abspath/expanduser(p)` | `Path(p).resolve()` / `.expanduser()` |

## Environment and packaging: uv

| Superseded | Modern |
| --- | --- |
| `python -m venv .venv`, `uv venv`, `virtualenv`, `pipenv`, `poetry`, `conda create` | **Banned.** uv manages the interpreter; no `.venv` left behind |
| `pip install X` into system/user site | `uv add X` (project), `uv run --with X ...` (one-off), `uv tool install X` (CLI tool) |
| `python script.py` (bare, deps assumed) | PEP 723 header in the script + `uv run script.py` |
| `uv run --no-project --with <deps> python script.py` | PEP 723 header + `uv run script.py` (owner 2026-11-20: flags too noisy) |
| Running a library project ad hoc | `uv sync` then `uv run python -m pkg` |
| `setup.py` / `setup.cfg` / `requirements.txt` for a new library | `pyproject.toml` (uv project) |
| Installing Python system-wide | `uv python install 3.15`, `uv run --python 3.15 ...` |

There is exactly one uv (`~/.local/bin/uv.exe`); do not install a second. Interpreters are
uv-managed and provisioned per need. If a stray `.venv` appears, delete it.

### Library project: `pyproject.toml`

```toml
[project]
name = "mypkg"
version = "0.1.0"
requires-python = ">=3.15"
dependencies = ["httpx>=0.27"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Set up and run: `uv sync`, then `uv run python -c "import mypkg; mypkg.main()"`. Add a
dependency with `uv add <pkg>` (updates `pyproject.toml` + `uv.lock`). Hand off a real import
and one call, not just a README snippet.

### One-off CLI script: PEP 723 inline metadata

```python
# /// script
# requires-python = ">=3.15"
# dependencies = ["httpx"]
# ///
from pathlib import Path
import httpx

data = httpx.get("https://example.com").text
Path("out.txt").write_text(data)
```

Run with plain `uv run script.py` (`--quiet` hides the first-run "Installed N packages" line); the
header absorbs `--with`, `--python` and `--no-project`. `uv run --with httpx python -c ...` is only
for a throwaway one-liner with no file. Do not turn a throwaway script into a
packaged project, and do not use `--with` as a substitute for a real library's pyproject.

## Banned: typing (turn it off)

| Remove / never write | Instead |
| --- | --- |
| `x: int`, `def f(a: int) -> str:` | No annotations; plain `x = ...`, `def f(a):` |
| `from typing import List, Dict, Optional, ...` / `import typing` | Nothing; use builtins dynamically (`list`, `dict`) |
| `from __future__ import annotations` | Remove |
| `class X(TypedDict)`, `class X(Protocol)` | Plain dict; duck typing / `isinstance` at runtime |
| `@dataclass`, `typing.NamedTuple` (need annotations) | `collections.namedtuple`, plain class, or dict |
| `type Alias = ...`, `def f[T](...)` (PEP 695) | Remove; no static generics |
| `cast`, `@overload`, `Final`, `ClassVar`, `Self`, `@override`, `assert_type` | Remove |
| mypy / pyright / pyre config and runs | Do not add or run them; strip their config and annotations when modernizing |

Why: this house style is dynamic and brief. Annotations and checkers add lines and
ceremony without serving the goal here. Where a runtime guarantee matters, check it
(`isinstance`, a guard, an `assert`) rather than annotating it.

## Review / migrate output

Report findings, then the corrected code:

```
Superseded -> modern (version)
- path:line  old: `os.path.join(a, b)`  ->  `Path(a) / b`
- path:line  old: `def f(x: int) -> int:`  ->  `def f(x):`  (typing ban)
```

Then give the full modernized snippet. Keep the report to the substitutions that matter;
do not narrate every line.