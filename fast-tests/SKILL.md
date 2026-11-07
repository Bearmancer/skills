---
name: fast-tests
description: "Use when tests are slow (a suite over 10 s, a test over 5 s, flaky only under xdist) or new tests spawn processes, git repos or external tools. Measure the bottleneck first, then cut."
---

# Fast tests

Bench first: measuring costs less than guessing.

```
uv run --no-project ~/.claude/skills/work-audit/scripts/bench.py <suite-dir> [--with <pkg>] [--workers N] [--slow N]
```

`github-create` imports `ruamel.yaml`: pass `--with ruamel.yaml`. A library cannot go in `uv tool install` (uv drops packages without executables).

It prints process costs, collection time, serial and xdist wall time, per-file and per-test rankings, and spawn counts for the slowest tests. Cut the top cause and rebench; stop when the slowest test is under 5 s solo or the suite meets its target.

## Cost model

The unit is a **spawn**: each launch costs 0.1-0.25 s on this Windows box (`git push` 0.25, `taskkill` 0.15, `uv run` 0.08, Python start 0.05), while in-process work costs about nothing. Suspect any test with more than ~10 spawns.

## Cuts, by measured payoff

- **Template once, copy per test.** Build the seeded repo and bare remote in a session fixture (`tmp_path_factory`), copy per test, and repoint remotes in one call. AI-Config: 8 git calls per test gone, 25 s to 12 s serial; work-audit `make_repo`: ~130 spawns gone.
- **Fail the cheap way.** Simulate "no git" with a PATH that lacks git (instant `OSError`). A zero timeout makes every call start, time out and run `taskkill` (work-audit d1 tests, 15 s to 2 s). Keep the real timeout in one test with one hung fake.
- **Switch off external probes** (`gh`, `dotnet`, network) with an env var in unit tests; one test keeps the real path.
- **Run scripts via `sys.executable`** instead of `uv run` per test; keep one real-uv test per entry point.
- **Compute once, keep the load-bearing refresh.** Cache by key (tool versions by PATH) and share results across checks. Removing a status refresh made the tree hash stale and turned tests red.
- **One helper, one home** in `conftest.py`; duplicated loaders and fixtures drift.

## Parallel

xdist is the first lever: `uv run --no-project --with pytest --with pytest-xdist python -W error -m pytest -q -n auto -p no:cacheprovider` took work-audit from 285 s to 79 s (51-52 s now after later cuts). Worker count is no lever on a 6-core/12-thread chip (12, 8, 6 workers = 72, 72, 82 s). Under load a test runs 2.5-3x slower than solo: judge a test by solo time and the suite by total work.

Write xdist-safe tests: per-test `tmp_path`, no fixed paths or ports, restore `sys.modules` and `sys.path` after any fixture suite (an inner `conftest.py` overwrote `sys.modules['conftest']` in workers and turned five tests red), and build session fixtures once per worker. A failure that appears only under load is a spawn storm: cut spawns; retries only hide it.

## Anti-patterns to flag

- per-test repo or process setup instead of a template
- timeout or sleep simulation of a failure
- unmocked external tools in unit tests
- per-test `uv` launches, or a hook launching `uv` per tool call (~95 ms each)
- duplicated helpers (see "One helper, one home")
- asserts that cannot fail (`or True`, broad `raises(Exception)`, no mutation proof)
- test counts that differ between runs (functions versus parametrized items: 137 versus 184)

`work-audit` ships the matching checks: `scripts/test-audit.py`, described in its `references/test-audit.md`.

## Guardrails

Every rewritten test must still fail when the product breaks: mutate the product, expect red, revert. A test gets faster by doing less setup, never by being deleted, skipped or weakened: its assertions stay whole. Run `python -W error` through `uv`.
