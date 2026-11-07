"""#213: a comprehensive scan stays fast without dropping real repos.

Fabricated home: a forest of throwaway clones under the system temp dir, a
package-cache clone, and one working repo. Temp is never walked (purge-safety
clears it by age) and is named in the report; every other tree is scanned.
"""

import tempfile

from conftest import (
    RECORD,
    STATE_REPORT,
    commit_all,
    fresh_script_module,
    load_reports,
    run_state_report,
)

BASE_ENV = {"WORK_AUDIT_NO_GH": "1", "WORK_AUDIT_ROOTS": ""}


def fabricated_home(make_repo, forest=6):
    for i in range(forest):
        make_repo(name=f"home/Temp/forest/clone-{i}", files={"a.py": "x = 1\n"})
    cache = make_repo(name="home/AppData/Local/uv/cache/dep", files={"b.py": "y = 2\n"})
    work = make_repo(name="home/Dev/work", files={"app.py": "z = 3\n"})
    for r in (cache, work):
        commit_all(r)
    return work.parent.parent, cache, work


def test_temp_forest_is_not_walked_and_is_named(make_repo, monkeypatch):
    home, cache, work = fabricated_home(make_repo)
    monkeypatch.setattr(tempfile, "tempdir", str(home / "Temp"))
    r = run_state_report("--roots", home, "--json", extra_env=BASE_ENV)
    assert r.returncode in (0, 1), r.stderr
    assert "git status: 2 repos" in r.stdout
    assert "not scanned:" in r.stdout and str(home / "Temp") in r.stdout
    reports = load_reports(None)
    assert set(reports) == {cache.name, work.name}
    assert reports[work.name]["indices"]["1"]["not_scanned"] == [str(home / "Temp")]


def test_explicit_root_inside_temp_is_still_scanned(make_repo, monkeypatch):
    home, _cache, _work = fabricated_home(make_repo, forest=1)
    clone = home / "Temp" / "forest" / "clone-0"
    commit_all(clone)
    monkeypatch.setattr(tempfile, "tempdir", str(home / "Temp"))
    r = run_state_report("--roots", clone, "--json", extra_env=BASE_ENV)
    assert "git status: 1 repos" in r.stdout
    assert "not scanned" not in r.stdout


def test_discovery_order_is_stable_across_threads(make_repo, monkeypatch):
    names = [f"tree/{a}/{b}" for a in ("b", "A", "c") for b in ("z", "Y", "x")]
    root = [make_repo(name=n) for n in names][0].parent.parent
    monkeypatch.setattr(tempfile, "tempdir", str(root / "no-temp"))
    rc = fresh_script_module(RECORD)
    got = [p.relative_to(root).as_posix() for p in rc.discover_repos(root)]
    assert got == sorted(got, key=lambda s: [x.casefold() for x in s.split("/")])
    assert len(got) == len(names)


def test_caps_grow_with_scope_unless_set(monkeypatch):
    sr = fresh_script_module(STATE_REPORT)
    monkeypatch.delenv("WORK_AUDIT_INDEX_TIMEOUT", raising=False)
    monkeypatch.delenv("WORK_AUDIT_MAX_FILES", raising=False)
    sr.REPOS[:] = [f"r{i}" for i in range(10)]
    assert sr.index_timeout() == sr.INDEX_TIMEOUT + 10 * sr.INDEX_TIMEOUT_PER_REPO
    assert sr.max_files() == max(sr.MAX_FILES, 10 * sr.MAX_FILES_PER_REPO)
    monkeypatch.setenv("WORK_AUDIT_INDEX_TIMEOUT", "5")
    assert sr.index_timeout() == sr.INDEX_TIMEOUT


def test_gh_lists_start_early_and_are_used_once(monkeypatch):
    # #128: the gh list calls run beside the git indices; index 11/14 take the prefetched result.
    from concurrent.futures import ThreadPoolExecutor

    sr = fresh_script_module(STATE_REPORT)
    calls = []
    monkeypatch.setattr(sr, "gh_ok", lambda: True)
    monkeypatch.setattr(sr, "origin_url", lambda r: "https://github.com/o/r")
    monkeypatch.setattr(
        sr, "_gh_call", lambda r, a, deadline=None: calls.append(a) or (0, "[]", "")
    )
    sr.REPOS[:] = ["repo"]
    with ThreadPoolExecutor(2) as ex:
        sr.prefetch_gh(ex)
    assert len(calls) == len(sr.GH_LISTS)
    assert sr.gh_run("repo", *sr.GH_LISTS[0]) == (0, "[]", "")
    assert len(calls) == len(sr.GH_LISTS)  # served from the prefetch, no second call
    sr.gh_run("repo", *sr.GH_LISTS[0])
    assert len(calls) == len(sr.GH_LISTS) + 1  # a prefetched result is used once
