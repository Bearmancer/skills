# Test-authoring audit (test-audit.py check family)

Mechanical checks over a repo's `test_*.py` files (plus `scripts/*.py` for
waits). Each finding uses the record shape
`{check, path, claim, evidence, severity, fixed}`; `evidence` is `path:line`.
Fix every finding in the same turn, or suppress one line with
`# test-audit: accept <reason>` (a suppression without a reason is itself a
finding in review). Exit 1 means findings exist.

## The checks

- T1 per-test setup: a test that builds a repo or process AND audits/runs it
  (`make_repo`, `git`, `subprocess`, `pytest.main` together with an audit
  entry point). Build seeded repos once per process and copy per test; keep
  exactly one real process launch per entry point. `pytest.main` inside a
  test is allowed only for fixture suites.
- T2 unmocked probes: external-tool or network calls (`gh ...`,
  `dotnet/cargo/go/npm/node --version`, `urllib`/`requests`/`socket`) in a
  unit test whose body shows no mock (`NO_GH`, `fake`, `mock`, `stub`,
  `monkeypatch`, `which(`). Auth and version probes cost ~0.5 s each and
  need the network; the suite sets `WORK_AUDIT_NO_GH=1` globally and fakes
  `gh` only in the L8 tests.
- T3 wait simulation: delay calls, `ping -n` hangs, `timeout=0`. A zero
  timeout makes every git call run `taskkill` (~0.15 s each); a hanging
  `.bat` must hang exactly one call and delegate the rest to the real tool.
  The L6 real-timeout proof and the D2 kill proof are the only accepted hangs.
- T4 duplicated helpers: the same helper/fixture name in two test files, or
  two helpers with >= 85% identical bodies. One copy lives in `conftest.py`.
- T5 slow tests: a test over `--slow-over` seconds (default 5) in the given
  JUnit XML without a `# bench:` note in its body quoting scripts/bench.py
  output (before/after seconds plus the dominant cause).
- T6 weak asserts: `or True`, `assert True`, `raises(Exception)`,
  `except Exception:`, or no assert at all. Every rewritten test keeps a
  mutation proof: it must fail when the code it covers is broken.
- T7 count drift: the collected item count (`--collected`, from bench.py)
  must equal the static prediction (test functions plus parametrize
  expansion). A mismatch means collection changed shape: ignored files,
  import errors, or new parametrization. Conftest `collect_ignore` needs a
  comment saying why.
- T8 shared state: `global` statements, direct `os.environ` writes (use
  `monkeypatch.setenv`), hardcoded temp paths (use `tmp_path`). xdist runs
  tests from many files in one worker process; leaked state fails only
  under `-n auto`, never serially.

## Count note (137 vs 163/165)

AST function counts and pytest item counts differ by design: each
`@pytest.mark.parametrize` case is one item. The suite has 137 top-level
test functions; parametrization (mostly the uv-guard blocked/allowed forms)
expands collection to 163 items, 165 after the two bench tests were added.
T7 verifies this mechanically: prediction must equal collection.
