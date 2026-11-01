"""Shared fixtures for work-audit characterization tests.

Every repo fixture is a throwaway real git repo under pytest tmp_path.
WORK_AUDIT_STATE_DIR always points under tmp_path, never at real state.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
STATE_REPORT = SCRIPTS / "state-report.py"
RECORD = SCRIPTS / "record.py"
STOP_GUARD = SCRIPTS / "stop-guard.py"

GIT_TIMEOUT = 60
SCRIPT_TIMEOUT = 120

# Session-shared read-only templates: built once, audited once; per-test flows
# copy the report and brief locally. Mutable repos are never shared.
TEMPLATES = {
    "clean": ({"README.md": "# Demo\n", "app.py": "x = 1\n"}, {}),
    "demo-record": (
        {
            "README.md": "# Demo\n\nUse `--fast-mode` here.\n",
            "app.py": 'parser.add_argument("--fast-mode")\n',
        },
        {"app.py": 'parser.add_argument("--fast-mode")\nx = 1\n'},
    ),
    "demo-rigor": (
        {
            "README.md": "# Demo\n\nUse `--fast-mode` here.\n",
            "app.py": 'parser.add_argument("--fast-mode")\nx = 1\n',
        },
        {"app.py": 'parser.add_argument("--fast-mode")\nx = 2\n'},
    ),
}
_SHARED = {}


@pytest.fixture(scope="session", autouse=True)
def _shared_root(tmp_path_factory, force_rmtree):
    """Root of the shared templates and state, under basetemp."""
    root = tmp_path_factory.mktemp("wa-shared")
    (root / "state").mkdir()
    _SHARED.update(root=root, state=root / "state", repos={}, runs={})
    yield
    _SHARED.clear()
    force_rmtree(root)


def _shared_area():
    return _SHARED


def _shared_env():
    area = _shared_area()
    env = dict(
        os.environ,
        WORK_AUDIT_STATE_DIR=str(area["state"]),
        WORK_AUDIT_ROOTS="",
        WORK_AUDIT_NO_GH="1",
        WORK_AUDIT_CONFIG_FILE=str(area["root"] / "no-such.toml"),
    )
    env.pop("WORK_AUDIT_OWNERS", None)
    return env


def _git_session(repo, *args):
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=GIT_TIMEOUT,
        env=_shared_env(),
    )
    assert r.returncode == 0, r.stderr
    return r


def shared_repo(shape):
    """Session template repo (read-only sharing; tests must not mutate it)."""
    area = _shared_area()
    if shape not in area["repos"]:
        files, post = TEMPLATES[shape]
        repo = area["root"] / f"repo-{shape}"
        repo.mkdir(parents=True, exist_ok=True)
        _git_session(repo, "init", "-q")
        for rel, content in files.items():
            p = repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        _git_session(repo, "add", "-A")
        _git_session(
            repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "one"
        )
        for rel, content in post.items():
            (repo / rel).write_text(content, encoding="utf-8")
        area["repos"][shape] = repo.resolve()
    return area["repos"][shape]


def _empty_template():
    """Session-built empty git repo, copied (not re-inited) per test."""
    area = _shared_area()
    if "empty" not in area:
        d = area["root"] / "empty-template"
        d.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(d)], check=True, timeout=GIT_TIMEOUT)
        area["empty"] = d.resolve()
    return area["empty"]


def shared_run(shape, *args):
    """Cached CompletedProcess for a shared read-only repo+args (print-only tests)."""
    area = _shared_area()
    key = (shape, tuple(map(str, args)))
    if key not in area["runs"]:
        repo = shared_repo(shape)
        saved = dict(os.environ)
        os.environ.update(_shared_env())
        try:
            area["runs"][key] = run_script(
                STATE_REPORT, "--roots", repo, *args, cwd=None, extra_env=None
            )
        finally:
            os.environ.clear()
            os.environ.update(saved)
    return area["runs"][key]


def _seed_copy(repo, shape):
    """Copy the session audit report for repo's current tree into test state.
    Fails loudly on tree mismatch (a mutated repo has no session report)."""
    area = _shared_area()
    shared_repo(shape)
    shared_run(shape, "--json")
    saved = dict(os.environ)
    os.environ.update(_shared_env())
    try:
        tmod = fresh_script_module(RECORD)
        tr = tmod.tree(repo)
    finally:
        os.environ.clear()
        os.environ.update(saved)
    session_reports = sorted(
        (area["state"] / ".work-audit-state" / "records").glob("*/*/report.json")
    )
    src = next(
        (
            f
            for f in session_reports
            if json.loads(f.read_text(encoding="utf-8")).get("tree") == tr
        ),
        None,
    )
    assert src is not None, f"no shared report for tree {tr[:10]} (repo mutated?)"
    dmod = fresh_script_module(RECORD)
    dest = dmod.rec_dir(repo) / tr / "report.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = json.loads(src.read_text(encoding="utf-8"))
    doc["repo"] = repo.name  # session template name -> this repo
    dest.write_text(json.dumps(doc), encoding="utf-8")
    return tr


def seeded_brief(repo, shape):
    """Session audit report for repo's tree copied into test state, then brief
    locally with no audit."""
    _seed_copy(repo, shape)
    r = run_record("brief", repo)
    assert r.returncode == 0, r.stderr + r.stdout
    docs = json.loads(r.stdout)
    assert len(docs) == 1
    return docs[0]


def seeded_report(repo, shape):
    """Session --json report for repo's tree copied into test state; the doc."""
    _seed_copy(repo, shape)
    return load_reports(None)[repo.name]


def audit_brief(repo):
    """Real audit then brief (unique-shape repos have no session report)."""
    run_state_report("--roots", repo, "--json")
    r = run_record("brief", repo)
    assert r.returncode == 0, r.stderr + r.stdout
    docs = json.loads(r.stdout)
    assert len(docs) == 1
    return docs[0]


def cli_brief(repo, shape):
    """Session audit report copied into test state, then brief locally."""
    return seeded_brief(repo, shape)


def write_cli(repo, rec, tmp_path, tag):
    p = tmp_path / f"{tag}.json"
    p.write_text(json.dumps(rec))
    return run_record("write", p, repo)


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=GIT_TIMEOUT,
    )


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    """Isolate every test from the real machine: state, repo roots and
    home-config scan all point under tmp_path (never ~/Dev or real home)."""
    state = tmp_path / "work-audit-state"
    state.mkdir(exist_ok=True)
    monkeypatch.setenv("WORK_AUDIT_STATE_DIR", str(state))
    roots = tmp_path / "roots"
    roots.mkdir(exist_ok=True)
    monkeypatch.setenv("WORK_AUDIT_ROOTS", str(roots))
    monkeypatch.setenv(
        "WORK_AUDIT_CONFIG_FILE", str(tmp_path / "no-such-work-audit.toml")
    )
    # xdist already runs one audit per core; 16 git threads inside each overload the host
    # and push indices past their caps (#135 review: flaky under -n auto and parallel suites).
    monkeypatch.setenv("WORK_AUDIT_WORKERS", "2")
    # No real gh in tests: auth/api/pr waits cost ~1.5 s per audit and need
    # network. L8's fake-gh tests override this with an empty value.
    monkeypatch.setenv("WORK_AUDIT_NO_GH", "1")
    return state


@pytest.fixture()
def state_dir(_isolated_state):
    return _isolated_state


@pytest.fixture()
def make_repo(tmp_path):
    """Factory: build a throwaway git repo (identity passed per-command, no config writes)."""
    counter = {"n": 0}

    def _make(name=None, files=None):
        counter["n"] += 1
        repo = tmp_path / (name or f"repo-{counter['n']}")
        # Copy the session's prebuilt empty repo: identical state, no spawn.
        shutil.copytree(_empty_template(), repo)
        for rel, content in (files or {}).items():
            p = repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return repo.resolve()

    return _make


@pytest.fixture()
def clean_repo():
    """Session-shared one-commit repo (read-only: tests must not mutate it)."""
    return shared_repo("clean")


def commit_all(repo, message="msg"):
    _git(repo, "add", "-A")
    r = _git(
        repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", message
    )
    assert r.returncode == 0


_UV_BIN = shutil.which("uv")
# Scripts run through uv; sys.executable only when uv is unavailable inside the sandbox.
SCRIPT_RUNNER = [_UV_BIN, "run", "--no-project"] if _UV_BIN else [sys.executable]
# Resolved-interpreter launches skip the uv resolve (~0.1-0.2 s) while staying
# real cross-process runs; keep exactly one real-uv test per entry point.
PY_RUNNER = [sys.executable]
_CALL_NO = 0


def fresh_script_module(script):
    """Import a skill script as a brand-new module (no sys.modules reuse, no bytecode)."""
    global _CALL_NO
    _CALL_NO += 1
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(
        f"wa_inline_{script.stem}_{_CALL_NO}", str(script)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_script_uv(
    script, *args, cwd=None, extra_env=None, stdin_text=None, runner=None
):
    """Run a skill script end to end in a subprocess (uv by default)."""
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [*(runner or SCRIPT_RUNNER), str(script), *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd) if cwd else None,
        env=env,
        input=stdin_text,
        timeout=SCRIPT_TIMEOUT,
    )


def run_script(
    script, *args, cwd=None, extra_env=None, stdin_text=None, uv=False, py=False
):
    """Run a skill script in-process (fresh module, isolated argv/env/cwd/stdin)
    unless uv=True, which uses a real uv subprocess end to end."""
    if uv or py:
        return run_script_uv(
            script,
            *args,
            cwd=cwd,
            extra_env=extra_env,
            stdin_text=stdin_text,
            runner=SCRIPT_RUNNER if uv else PY_RUNNER,
        )
    import contextlib
    import io
    import traceback

    saved = (
        sys.argv,
        sys.stdin,
        os.getcwd(),
        dict(os.environ),
        sys.dont_write_bytecode,
    )
    if extra_env:
        os.environ.update(extra_env)
    if cwd is not None:
        os.chdir(cwd)
    if stdin_text is not None:
        sys.stdin = io.StringIO(stdin_text)
    sys.argv = [str(script), *map(str, args)]
    sys.dont_write_bytecode = True
    out, err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            fresh_script_module(Path(script)).main()
    except SystemExit as e:
        if isinstance(e.code, int):
            code = e.code
        else:
            if e.code is not None:
                err.write(str(e.code) + "\n")
            code = 0 if not e.code else 1
    except Exception:
        traceback.print_exc()
        code = 1
    finally:
        sys.argv, sys.stdin, old_cwd, old_env, sys.dont_write_bytecode = saved
        os.chdir(old_cwd)
        os.environ.clear()
        os.environ.update(old_env)
    return subprocess.CompletedProcess(
        [str(script), *map(str, args)], code, out.getvalue(), err.getvalue()
    )


def run_state_report(*args, cwd=None, extra_env=None, uv=False, py=False):
    return run_script(STATE_REPORT, *args, cwd=cwd, extra_env=extra_env, uv=uv, py=py)


def run_record(*args, cwd=None, extra_env=None, uv=False, py=False):
    return run_script(RECORD, *args, cwd=cwd, extra_env=extra_env, uv=uv, py=py)


def run_stop_guard(
    *args, cwd=None, extra_env=None, stdin_text=None, uv=False, py=False
):
    return run_script(
        STOP_GUARD,
        *args,
        cwd=cwd,
        extra_env=extra_env,
        stdin_text=stdin_text,
        uv=uv,
        py=py,
    )


def load_reports(state):
    """Load every report.json written under the isolated state dir, keyed by repo name."""
    # scripts append ".work-audit-state" to WORK_AUDIT_STATE_DIR themselves.
    base = Path(os.environ["WORK_AUDIT_STATE_DIR"]) / ".work-audit-state" / "records"
    out = {}
    for f in base.glob("*/*/report.json"):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(doc, dict) and doc.get("repo"):
            out[doc["repo"]] = doc
    return out


def find_report(repo_name):
    """Newest report.json for a repo name (record dirs are basename-plus-hash)."""
    base = Path(os.environ["WORK_AUDIT_STATE_DIR"]) / ".work-audit-state" / "records"
    best, best_mtime = None, -1.0
    for f in base.glob("*/*/report.json"):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(doc, dict) and doc.get("repo") == repo_name:
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            if mtime > best_mtime:
                best, best_mtime = f, mtime
    assert best is not None, f"no report for {repo_name}"
    return best
