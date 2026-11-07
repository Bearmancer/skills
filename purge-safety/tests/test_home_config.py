"""#216: generated ~/.omo state routes into a scoped purge manifest; protected paths still refuse.

Owner decisions (2026-10-25): a 7-day age gate on every routed row; PURGE for evidence, drafts,
tmp, reports and loose .bak/.old files; OWNER (per-path --override) for plans, ulw-loop and
wayfinder; reports/ children route but never the engine's own manifests and journals.
"""

import json
import os
import subprocess
import sys
import time

import scenarios as sc

DAY = 86400
OLD = time.time() - 30 * DAY
FRESH = time.time() - 1 * DAY


def build_omo(home):
    omo = home / ".omo"
    for rel, when in {
        "evidence/run-1/log.txt": OLD,
        "evidence/run-2/log.txt": FRESH,
        "drafts/d.md": OLD,
        "tmp/scratch.bin": OLD,
        "reports/old-report.md": OLD,
        "reports/Purge Manifest - 2026-01-01 000000.json": OLD,
        "reports/Purge Journal - 2026-01-01 000000.jsonl": OLD,
        "plans/boulder.json": OLD,
        "plans/waves/w1.json": FRESH,
        "ulw-loop/ledger.json": OLD,
        "wayfinder/route.json": OLD,
        "memory/note.md": OLD,
        "agent/sessions/s/x.json": OLD,
        "omo.jsonc": OLD,
        "omo.jsonc.bak": OLD,
        "settings.old": OLD,
        "keep.txt": OLD,
    }.items():
        sc.write(omo / rel, "x", when)
    for rel in ("evidence/run-1", "plans/waves", "evidence/run-2"):
        os.utime(omo / rel, (OLD, OLD))
    os.utime(omo / "evidence/run-2", (FRESH, FRESH))
    return omo


def report(tmp_path, roots):
    entries = [{"root": str(r), "entries": sorted(os.listdir(r))} for r in roots]
    return sc.write(
        tmp_path / "records/report.json",
        json.dumps({"indices": {"4": {"config_root_entries": entries}}}),
    )


def adapter(tmp_path, home, rep, *extra):
    repo = tmp_path / "work/proj"
    repo.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **sc.env_for(home)}
    proc = subprocess.run(
        [
            sys.executable,
            str(sc.ADAPTER_PY),
            "--report",
            str(rep),
            "--repo",
            str(repo),
            *extra,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    )
    manifests = sorted(
        (tmp_path / "records").glob("Purge Manifest - work-audit home-config - *.json")
    )
    doc = json.loads(manifests[0].read_text(encoding="utf-8")) if manifests else None
    return proc, doc


def engine(tmp_path, home, *args):
    env = {**os.environ, **sc.env_for(home)}
    return subprocess.run(
        [
            sys.executable,
            str(sc.ENGINE_PY),
            *map(str, args),
            "--lock-file",
            str(tmp_path / "p.lock"),
            "--out-dir",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    )


def rel_rows(doc, omo):
    return {
        os.path.relpath(e["path"], omo).replace("\\", "/"): e["verdict"]
        for e in doc["entries"]
    }


def test_generated_state_routes_with_owner_split_and_age_gate(tmp_path):
    home = sc.empty_home(tmp_path)
    omo = build_omo(home)
    proc, doc = adapter(tmp_path, home, report(tmp_path, [omo]), "--home-config")
    assert proc.returncode == 0, proc.stderr
    assert doc["root"] == str(omo)
    assert rel_rows(doc, omo) == {
        "evidence/run-1": "PURGE",
        "drafts/d.md": "PURGE",
        "tmp/scratch.bin": "PURGE",
        "reports/old-report.md": "PURGE",
        "plans/boulder.json": "OWNER",
        "ulw-loop/ledger.json": "OWNER",
        "wayfinder/route.json": "OWNER",
        "omo.jsonc.bak": "PURGE",
        "settings.old": "PURGE",
    }
    assert all(
        "(files " in e["reason"] and "newest " in e["reason"] for e in doc["entries"]
    )
    # Young executor-adjacent state stays out, and plan review sees it.
    assert (
        "held  OWNER " + str(omo / "plans" / "waves") + " :: inside the 7-day age gate"
        in proc.stdout
    )
    assert (
        "held  PURGE "
        + str(omo / "evidence" / "run-2")
        + " :: inside the 7-day age gate"
        in proc.stdout
    )
    assert f"home-config root: {omo}" in proc.stdout


def test_engine_files_memory_agent_and_config_never_route(tmp_path):
    home = sc.empty_home(tmp_path)
    omo = build_omo(home)
    _, doc = adapter(tmp_path, home, report(tmp_path, [omo]), "--home-config")
    rows = rel_rows(doc, omo)
    assert not [
        r
        for r in rows
        if r.startswith(("reports/Purge ", "memory", "agent"))
        or r in ("omo.jsonc", "keep.txt")
    ]


def test_age_gate_flag(tmp_path):
    home = sc.empty_home(tmp_path)
    omo = build_omo(home)
    _, doc = adapter(
        tmp_path, home, report(tmp_path, [omo]), "--home-config", "--home-age-days", "0"
    )
    rows = rel_rows(doc, omo)
    assert rows["evidence/run-2"] == "PURGE" and rows["plans/waves"] == "OWNER"


def test_home_folder_is_never_a_root(tmp_path):
    home = sc.empty_home(tmp_path)
    build_omo(home)
    renamed = tmp_path / ".omo"  # an omo-named folder that IS the home folder
    renamed.mkdir()
    for root, env_home in ((home, home), (renamed, renamed)):
        proc, doc = adapter(
            tmp_path, env_home, report(tmp_path, [root]), "--home-config"
        )
        assert proc.returncode == 0 and doc is None
        assert "home-config:" in proc.stdout


def test_without_the_flag_nothing_routes(tmp_path):
    home = sc.empty_home(tmp_path)
    omo = build_omo(home)
    proc, doc = adapter(tmp_path, home, report(tmp_path, [omo]))
    assert proc.returncode == 0 and doc is None and "home-config" not in proc.stdout


def test_engine_plans_and_applies_the_home_manifest(tmp_path):
    home = sc.empty_home(tmp_path)
    omo = build_omo(home)
    _, doc = adapter(tmp_path, home, report(tmp_path, [omo]), "--home-config")
    manifest = next(
        (tmp_path / "records").glob("Purge Manifest - work-audit home-config - *.json")
    )
    plan = engine(tmp_path, home, "--root", omo, "--manifest", manifest)
    assert plan.returncode == 1  # the OWNER rows wait for an override
    assert plan.stdout.count("owner verdict, needs --override") == 3
    owner = [
        omo / "plans" / "boulder.json",
        omo / "ulw-loop" / "ledger.json",
        omo / "wayfinder" / "route.json",
    ]
    apply = engine(
        tmp_path,
        home,
        "--root",
        omo,
        "--manifest",
        manifest,
        "--apply",
        "--override",
        *owner,
    )
    assert apply.returncode in (0, 2), apply.stdout + apply.stderr
    assert "removed=9  refused=0  failed=0" in apply.stdout
    for e in doc["entries"]:
        assert not os.path.lexists(e["path"])
    # The generated subdirs themselves, young state, protected state and the engine's own files remain.
    for rel in (
        "plans/waves/w1.json",
        "evidence/run-2/log.txt",
        "memory/note.md",
        "agent/sessions/s/x.json",
        "omo.jsonc",
        "keep.txt",
        "reports/Purge Journal - 2026-01-01 000000.jsonl",
    ):
        assert (omo / rel).exists(), rel


def test_protected_paths_still_refuse_under_the_omo_root(tmp_path):
    home = sc.empty_home(tmp_path)
    omo = build_omo(home)
    rows = [
        sc.row(omo, "memory"),
        sc.row(omo, "agent/sessions"),
        sc.row(omo, "omo.jsonc"),
    ]
    manifest = sc.manifest(tmp_path / "hand.json", rows, omo)
    proc = engine(tmp_path, home, "--root", omo, "--manifest", manifest, "--apply")
    assert proc.returncode == 3
    assert proc.stdout.count("protected path") == 3
    assert (
        (omo / "memory/note.md").exists()
        and (omo / "agent/sessions/s/x.json").exists()
        and (omo / "omo.jsonc").exists()
    )
