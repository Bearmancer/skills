"""Run with: uv run --project <skill-dir> pytest"""
import copy, glob, os, shutil, subprocess, sys
import pytest, yaml

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))
import railguard as r  # noqa: E402

PACK_ROOT = os.path.dirname(SKILL)
YAMLS = sorted(f for f in glob.glob(os.path.join(PACK_ROOT, "**", "*.yaml"), recursive=True) if os.sep + "evals" + os.sep not in f)


@pytest.mark.parametrize("path", YAMLS)
def test_parser_matches_pyyaml(path):
    assert r.load(path) == yaml.safe_load(open(path, encoding="utf-8"))


def test_pack_self_check():
    assert r.check_pack() == 0


def _ctx(tmp_path):
    assets = os.path.join(SKILL, "assets")
    for sub in ("src",):
        os.makedirs(tmp_path / sub)
    (tmp_path / "src" / "handler.py").write_text("x")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "i"], cwd=tmp_path, check=True)
    args = ["--root", str(tmp_path)]
    assert r.main(args + ["start", "demo-rate-limit", "--no-codegraph"]) == 0
    plans = tmp_path / ".rigor" / "plans"
    shutil.copy(os.path.join(assets, "spec.yaml"), plans / "spec.yaml")
    shutil.copy(os.path.join(assets, "plan.yaml"), plans / "demo-rate-limit.plan.yaml")
    ev = tmp_path / ".rigor" / "evidence" / "P1"
    ev.mkdir(parents=True)
    (ev / "codegraph.md").write_text("handler is the single entry point")
    return args, str(plans / "demo-rate-limit.plan.yaml")


def test_good_plan_has_no_errors(tmp_path, capsys):
    args, plan = _ctx(tmp_path)
    r.main(args + ["check", plan])
    out = capsys.readouterr().out
    assert "FAILED" not in out.replace("FINAL CHECK FAILED", "")


@pytest.mark.parametrize("mutate,needle", [
    (lambda p: p["gaps"].append({"id": "G3", "text": "x", "reason": "y"}), "gap G3 has no task"),
    (lambda p: p["phases"][0]["tasks"][0].__setitem__("depends", ["T2"]), "cycle"),
    (lambda p: p["phases"][0]["tasks"][0].__setitem__("size", "L"), "must be split"),
    (lambda p: p["phases"][0].__setitem__("checkpoints", []), "must end with a checkpoint"),
    (lambda p: p["phases"][0]["tasks"][0].pop("surfaces"), "surfaces must be a non-empty list"),
])
def test_broken_plan_is_caught(tmp_path, capsys, mutate, needle):
    args, plan = _ctx(tmp_path)
    p = r.load(plan)
    mutate(p)
    r.save(plan, p)
    assert r.main(args + ["check", plan]) == 1
    assert needle in capsys.readouterr().out


def test_ledger_tamper_detected(tmp_path):
    args, plan = _ctx(tmp_path)
    r.main(args + ["log", "ok", "--kind", "note"])
    lp = tmp_path / ".rigor" / "ledger.yaml"
    lp.write_text(lp.read_text().replace("run started", "run tampered"))
    ok, _ = r.verify_chain(r.load_ledger(str(tmp_path)))
    assert not ok


def test_start_refuses_existing_incomplete_plan(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "plan.md").write_text("- [ ] open\n")
    assert r.main(["--root", str(tmp_path), "start", "other", "--no-codegraph"]) == 2
    assert (tmp_path / "tasks" / "plan.md").read_text() == "- [ ] open\n"


def test_bound_reads_as_its_number_and_units_are_checked():
    assert r._bound({"max": 3}) == 3
    assert r._bound({"max": 240, "unit": "minutes"}) == 240
    assert r._bound({"min": 1, "max": 5}) == {"min": 1, "max": 5}
    assert r.lim("execution.delegation.inline.tasks") == 3
    assert r.lim("execution.retries.attempts") == 3


# ---------------------------------------------------------------- intent, fog, proposals, rounds, scope, glossary, docs
def _final_ctx(tmp_path):
    args, plan = _ctx(tmp_path)
    r.main(args + ["log", "yes, confirmed", "--kind", "answer", "--subject", "intent_confirmed", "--authority", "user"])
    return args, plan


def _out(args, plan, capsys, *extra):
    capsys.readouterr()
    rc = r.main(args + ["check", plan] + list(extra))
    return rc, capsys.readouterr().out


def test_intent_needs_every_field_and_explicit_yes(tmp_path, capsys):
    args, plan = _ctx(tmp_path)
    _, out = _out(args, plan, capsys, "--final")
    assert "intent restate not confirmed" in out
    assert r.main(args + ["log", "sounds good", "--kind", "answer", "--subject", "intent_confirmed", "--authority", "user"]) == 2
    assert "explicit yes" in capsys.readouterr().out
    r.main(args + ["log", "yes, confirmed", "--kind", "answer", "--subject", "intent_confirmed", "--authority", "user"])
    p = r.load(plan)
    spec_file = r.spec_path_of(p, plan)
    sp = r.load(spec_file)
    sp["intent"]["why_now"] = ""
    r.save(spec_file, sp)
    _, out = _out(args, plan, capsys)
    assert "intent.why_now is empty" in out


def test_not_yet_specified_blocks_final(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    sf = r.spec_path_of(r.load(plan), plan)
    sp = r.load(sf)
    sp["not_yet_specified"] = ["how billing tiers map to limits"]
    r.save(sf, sp)
    _, out = _out(args, plan, capsys, "--final")
    assert "not yet specified: how billing tiers" in out and "ERROR R_fog" in out


def test_failed_fog_test_requires_closed_clarify(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    sf = r.spec_path_of(r.load(plan), plan)
    sp = r.load(sf)
    sp["fog_test"]["first_three_decisions"] = False
    r.save(sf, sp)
    _, out = _out(args, plan, capsys)
    assert "fog test failed" in out


def test_language_required(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    sf = r.spec_path_of(r.load(plan), plan)
    sp = r.load(sf)
    sp["meta"]["language"] = ""
    r.save(sf, sp)
    _, out = _out(args, plan, capsys)
    assert "meta.language is not recorded" in out


def test_out_of_scope_term_blocks_until_user_decides(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    p = r.load(plan)
    p["phases"][0]["tasks"][0]["title"] = "Distributed limiter across a cluster"
    r.save(plan, p)
    _, out = _out(args, plan, capsys)
    assert "touches out-of-scope O1" in out
    r.main(args + ["log", "user widened scope", "--kind", "decision", "--subject", "scope_change:O1", "--authority", "user"])
    _, out = _out(args, plan, capsys)
    assert "touches out-of-scope" not in out


def test_avoided_glossary_term_warns(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    p = r.load(plan)
    p["phases"][0]["tasks"][0]["title"] = "Bucket limiter with retry hint"
    r.save(plan, p)
    _, out = _out(args, plan, capsys)
    assert "uses 'bucket'; the glossary prefers 'window'" in out


def test_proposal_needs_user_confirmation(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    r.main(args + ["log", "I chose 2 surfaces", "--kind", "decision", "--subject", "surfaces_cap", "--authority", "proposal"])
    _, out = _out(args, plan, capsys, "--final")
    assert "agent's proposal and has no user confirmation" in out
    r.main(args + ["log", "no", "--kind", "decision", "--subject", "surfaces_cap", "--authority", "user"])
    _, out = _out(args, plan, capsys, "--final")
    assert "agent's proposal" in out                      # a user 'no' does not confirm
    r.main(args + ["log", "yes, but only for now", "--kind", "decision", "--subject", "surfaces_cap", "--authority", "user"])
    _, out = _out(args, plan, capsys, "--final")
    assert "agent's proposal" in out                      # a hedged yes does not confirm
    r.main(args + ["log", "yes", "--kind", "decision", "--subject", "surfaces_cap", "--authority", "user"])
    _, out = _out(args, plan, capsys, "--final")
    assert "agent's proposal" not in out


def test_stalled_rounds_force_step_back(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    for i in range(3):
        r.main(args + ["log", "resolved=0 asked=4", "--kind", "round", "--subject", str(i + 1)])
    _, out = _out(args, plan, capsys)
    assert "3 question rounds in a row resolved nothing" in out
    r.main(args + ["log", "go on", "--kind", "answer", "--subject", "step_back", "--authority", "user"])
    _, out = _out(args, plan, capsys)
    assert "resolved nothing" not in out


def test_adr_candidate_needs_a_plan_task_that_writes_it(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    sf = r.spec_path_of(r.load(plan), plan)
    sp = r.load(sf)
    sp["decisions"][0]["adr"] = {"hard_to_reverse": True, "surprising": True, "real_tradeoff": True, "file": "docs/adr/0001-fixed-window.md"}
    r.save(sf, sp)
    _, out = _out(args, plan, capsys)
    assert "no plan task writes docs/adr/0001-fixed-window.md" in out
    p = r.load(plan)
    p["phases"][0]["tasks"][0]["files"].append({"path": "docs/adr/0001-fixed-window.md", "op": "create", "verified_at": "2026-11-08"})
    r.save(plan, p)
    _, out = _out(args, plan, capsys)
    assert "no plan task writes" not in out


def test_business_fact_needs_a_task_that_writes_its_doc(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    sf = r.spec_path_of(r.load(plan), plan)
    sp = r.load(sf)
    sp["business_facts"] = [{"id": "B1", "text": "Refunds within 30 days", "file": "docs/business/refunds.md"}]
    r.save(sf, sp)
    _, out = _out(args, plan, capsys)
    assert "business fact B1: no plan task writes docs/business/refunds.md" in out
    sp["business_facts"][0]["file"] = "src/refunds.md"
    r.save(sf, sp)
    _, out = _out(args, plan, capsys)
    assert "business fact B1: needs a file path under docs/business/" in out


def test_glossary_promotion_needs_a_task_that_writes_glossary(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    sf = r.spec_path_of(r.load(plan), plan)
    sp = r.load(sf)
    sp["promote_glossary"] = True
    r.save(sf, sp)
    _, out = _out(args, plan, capsys)
    assert "glossary promotion: no plan task writes GLOSSARY.md" in out
    p = r.load(plan)
    p["phases"][0]["tasks"][0]["files"].append({"path": "GLOSSARY.md", "op": "create", "verified_at": "2026-11-08"})
    r.save(plan, p)
    _, out = _out(args, plan, capsys)
    assert "glossary promotion" not in out


def test_planning_writing_any_repo_file_including_docs_is_caught(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    os.makedirs(tmp_path / "docs")
    (tmp_path / "docs" / "note.md").write_text("planning wrote this")
    _, out = _out(args, plan, capsys)
    assert "changed outside .rigor" in out


def test_todo_lists_stages_phases_and_tasks(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    capsys.readouterr()
    assert r.main(args + ["todo", plan]) == 0
    out = capsys.readouterr().out
    assert "stage\tground" in out.replace(" ", "") or "\tstage\t" in out
    assert "\tphase\tPH1" in out and "\ttask\tT1" in out


# ---------------------------------------------------------------- integrity hardening
def test_confirm_subjects_need_user_authority_and_an_unhedged_yes(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    for reason, auth in (("yes", "system"), ("yes but not sure", "user"), ("sure", "user")):
        assert r.main(args + ["log", reason, "--kind", "answer", "--subject", "execute_authorized", "--authority", auth]) == 2
    assert r.main(args + ["log", "yes (confirmed in the question tool)", "--kind", "answer", "--subject", "execute_authorized", "--authority", "user"]) == 0
    assert r.load_state(str(tmp_path))["execute_authorized"] is True
    assert r.main(args + ["log", "no", "--kind", "answer", "--subject", "execute_authorized", "--authority", "user"]) == 0
    assert r.load_state(str(tmp_path))["execute_authorized"] is False


def test_plan_change_refuses_system_authority(tmp_path):
    args, plan = _final_ctx(tmp_path)
    assert r.main(args + ["log", "why", "--kind", "plan_change", "--authority", "system"]) == 2
    assert r.main(args + ["log", "why", "--kind", "plan_change", "--authority", "user"]) == 0


def test_non_skippable_gate_cannot_be_skipped(tmp_path):
    args, plan = _final_ctx(tmp_path)
    assert r.main(args + ["log", "nah", "--kind", "gate", "--subject", "G_ground", "--status", "skipped", "--authority", "user"]) == 2
    assert r.main(args + ["log", "no remote", "--kind", "gate", "--subject", "G_publish", "--status", "skipped", "--authority", "rule:publish"]) == 2  # authority not in skip_authority
    assert r.main(args + ["log", "no remote", "--kind", "gate", "--subject", "G_publish", "--status", "skipped", "--authority", "user"]) == 0


def test_tier_floor_from_risk_signals_and_size(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    p = r.load(plan)
    p["meta"]["tier"] = 0
    p["risk_signals"] = ["schema_change"]
    r.save(plan, p)
    _, out = _out(args, plan, capsys)
    assert "meta.tier 0 is below the floor 2" in out
    p["meta"]["tier"] = 2
    r.save(plan, p)
    _, out = _out(args, plan, capsys)
    assert "below the floor" not in out


def test_ledger_truncation_is_detected_and_parallel_logs_survive(tmp_path, capsys):
    import subprocess as sp
    args, plan = _final_ctx(tmp_path)
    n0 = len(r.load_ledger(str(tmp_path)))
    procs = [sp.Popen([sys.executable, os.path.join(SKILL, "scripts", "railguard.py")] + args + ["log", f"p{i}", "--kind", "note"], stdout=sp.DEVNULL) for i in range(12)]
    for p in procs:
        p.wait()
    assert len(r.load_ledger(str(tmp_path))) == n0 + 12
    led = r.load(r.ledger_path(str(tmp_path)))
    led["events"] = led["events"][:-3]
    r.save(r.ledger_path(str(tmp_path)), led)
    _, out = _out(args, plan, capsys)
    assert "ledger head does not match" in out


def test_slug_instead_of_path_is_a_refusal_not_a_traceback(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    assert r.main(args + ["check", "demo-rate-limit"]) == 2
    assert "file not found" in capsys.readouterr().out


def test_scope_euphemisms_are_caught(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    for phrase in ("Basic search for now", "Search in the next release", "Search post-launch"):
        p = r.load(plan)
        p["phases"][0]["tasks"][0]["title"] = phrase
        r.save(plan, p)
        _, out = _out(args, plan, capsys)
        assert "reduced-scope word" in out, phrase


def test_modify_of_a_file_another_task_creates_is_allowed(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    p = r.load(plan)
    p["phases"][0]["tasks"][0]["files"].append({"path": "src/brand_new.py", "op": "create", "verified_at": "2026-11-08"})
    p["phases"][0]["tasks"][1]["files"].append({"path": "src/brand_new.py", "op": "modify", "verified_at": "2026-11-08"})
    r.save(plan, p)
    _, out = _out(args, plan, capsys)
    assert "modify target missing src/brand_new.py" not in out


def test_dry_run_publish_does_not_satisfy_the_publish_rule(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    st = r.load_state(str(tmp_path))
    st["publish"] = {"repo": "o/r", "dry_run": True, "parent": None, "tasks": {}}
    r.save(r.state_path(str(tmp_path)), st)
    _, out = _out(args, plan, capsys)
    assert "not published to GitHub" in out


def test_task_size_caps_files(tmp_path, capsys):
    args, plan = _final_ctx(tmp_path)
    p = r.load(plan)
    p["phases"][0]["tasks"][0]["size"] = "XS"
    p["phases"][0]["tasks"][0]["files"] = [{"path": f"src/a{i}.py", "op": "create", "verified_at": "2026-11-08"} for i in range(3)]
    r.save(plan, p)
    _, out = _out(args, plan, capsys)
    assert "size XS allows 1 file(s), has 3" in out
