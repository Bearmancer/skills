"""Execution verbs against a real git repository and worktree."""
import os, shutil, subprocess, sys
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))
import railguard as r  # noqa: E402
import rigor_exec as x  # noqa: E402

FEEDBACK = "test -f src/limiter.py || exit 1"


def git(cwd, *a):
    return subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=t"] + list(a), cwd=cwd, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def proj(tmp_path):
    root = tmp_path
    (root / "src").mkdir()
    (root / "src" / "handler.py").write_text("def handle():\n    return 1\n")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    args = ["--root", str(root)]
    assert r.main(args + ["start", "demo-rate-limit", "--no-codegraph"]) == 0
    plans = root / ".rigor" / "plans"
    shutil.copy(os.path.join(SKILL, "assets", "spec.yaml"), plans / "spec.yaml")
    plan_path = plans / "demo-rate-limit.plan.yaml"
    shutil.copy(os.path.join(SKILL, "assets", "plan.yaml"), plan_path)
    ev = root / ".rigor" / "evidence" / "P1"
    ev.mkdir(parents=True)
    (ev / "codegraph.md").write_text("handler is the single entry point")
    p = r.load(str(plan_path))
    p["meta"]["status"] = "final"
    t1, t2 = p["phases"][0]["tasks"]
    t1["verify"][0]["run"] = "grep -q retry src/limiter.py"
    t1["verify"][1]["run"] = "test -f src/limiter.py"
    t2["verify"][0]["run"] = "grep -q tier src/handler.py"
    t2["verify"][1]["run"] = "grep -q default src/handler.py"
    p["phases"][0]["checkpoints"][0]["verify"] = ["true"]
    p["final_verification"][0]["verify"]["run"] = "true"
    r.save(str(plan_path), p)
    # satisfy every manual gate and review so check --final can pass
    r.main(args + ["check", str(plan_path)])
    st = r.load_state(str(root))
    for gid, g in r.gate_map(r.load_pack()).items():
        if g["kind"] == "manual":
            r.main(args + ["log", "ok", "--kind", "gate", "--subject", gid, "--status", "passed", "--authority", "user"])
    for role in r.required_reviewers(p, r.load_pack()["routing"]):
        r.main(args + ["log", "", "--kind", "review_complete", "--plan", str(plan_path), "--role", role, "--set-baseline"])
    r.main(args + ["log", "yes", "--kind", "answer", "--subject", "execute_authorized", "--authority", "user"])
    r.main(args + ["log", "yes, confirmed", "--kind", "answer", "--subject", "intent_confirmed", "--authority", "user"])
    r.main(args + ["render", str(plan_path)])
    git(root, "add", "-A")
    return root, args, str(plan_path)


def X(args, *a):
    return r.main(args + ["exec"] + list(a))


def start(proj, extra=()):
    root, args, plan = proj
    return X(args, "start", plan, "--feedback", FEEDBACK, "--delivery", "branch", *extra)


def test_start_refuses_without_feedback_or_delivery(proj, capsys):
    root, args, plan = proj
    assert X(args, "start", plan) == 2
    out = capsys.readouterr().out
    assert "--feedback" in out and "--delivery" in out


def test_start_refuses_dirty_main(proj, capsys):
    root, args, plan = proj
    (root / "src" / "handler.py").write_text("changed\n")
    assert start(proj) == 2
    assert "uncommitted" in capsys.readouterr().out


def test_start_refuses_when_not_authorized(proj, capsys):
    root, args, plan = proj
    st = r.load_state(str(root))
    st["execute_authorized"] = False
    r.save(r.state_path(str(root)), st)
    assert start(proj) == 2
    assert "authorized" in capsys.readouterr().out


def test_full_run(proj, capsys):
    root, args, plan = proj
    assert start(proj) == 0
    run = x.load_run(str(root))
    wt = run["worktree"]
    assert os.path.isdir(wt) and run["branch"] == "rigor/demo-rate-limit"
    # live run is refused
    assert start(proj) == 2
    assert X(args, "verify", "--baseline") == 0
    # T2 is not ready before T1
    assert X(args, "task", "T2", "--status", "started") == 2
    assert X(args, "task", "T1", "--status", "started") == 0
    # done without evidence refused
    assert X(args, "task", "T1", "--status", "done") == 2
    # red must fail
    assert X(args, "red", "T1", "--cmd", "test -f src/limiter.py && grep -q retry src/limiter.py") == 0
    pw = x.load_run(str(root))["worktree"]
    with open(os.path.join(pw, "src", "limiter.py"), "w") as f:
        f.write("def limit(): return 'retry-after'\n")
    assert X(args, "vtask", "T1") == 0
    assert X(args, "task", "T1", "--status", "done") == 0
    # a checkpoint after T2 holds nothing before T2 finishes; T2 now ready
    assert X(args, "task", "T2", "--status", "started") == 0
    assert X(args, "red", "T2", "--cmd", "grep -q tier src/handler.py") == 0
    with open(os.path.join(pw, "src", "handler.py"), "a") as f:
        f.write("tier = 'default'\n")
    assert X(args, "vtask", "T2") == 0
    assert X(args, "task", "T2", "--status", "done") == 0
    # checkpoint before final check
    assert X(args, "check", "--final") == 1
    assert X(args, "checkpoint", "CP1") == 0
    assert X(args, "verifier", "CP1", "pass", "--agent", "fresh-verifier-1") == 0
    assert X(args, "verify") == 0
    assert X(args, "final", "FV1") == 0
    assert X(args, "check", "--final") == 1  # no whole-branch verifier yet
    assert X(args, "verifier", "branch", "pass", "--agent", "fresh-verifier-2") == 0
    for c in ("C1", "C2"):
        assert X(args, "claim", c, "--status", "established", "--note", "tests pass") == 0
    for role in r.required_reviewers(r.load(plan), r.load_pack()["routing"]):
        assert X(args, "review", role, "approve") == 0
    capsys.readouterr()
    assert X(args, "check", "--final") == 0, capsys.readouterr().out
    assert X(args, "finish") == 0
    out = capsys.readouterr().out
    assert "branch rigor/demo-rate-limit" in out and "Nothing was pushed" in out
    # finished run is reported, not restarted
    assert start(proj) == 0
    assert "already executed" in capsys.readouterr().out
    # main checkout is untouched
    assert not (root / "src" / "limiter.py").exists()


def test_red_must_fail(proj, capsys):
    root, args, plan = proj
    start(proj)
    X(args, "verify", "--baseline")
    X(args, "task", "T1", "--status", "started")
    assert X(args, "red", "T1", "--cmd", "true") == 2
    assert "passed" in capsys.readouterr().out


def test_tdd_requires_red_before_done(proj, capsys):
    root, args, plan = proj
    start(proj)
    X(args, "verify", "--baseline")
    X(args, "task", "T1", "--status", "started")
    with open(os.path.join(x.load_run(str(root))["worktree"], "src", "limiter.py"), "w") as f:
        f.write("retry\n")
    assert X(args, "vtask", "T1") == 0
    assert X(args, "task", "T1", "--status", "done") == 2
    assert "failing test" in capsys.readouterr().out


def test_scope_and_placeholder_rules(proj, capsys):
    root, args, plan = proj
    start(proj)
    X(args, "verify", "--baseline")
    wt = x.load_run(str(root))["worktree"]
    with open(os.path.join(wt, "stray.txt"), "w") as f:
        f.write("TODO later\n")
    capsys.readouterr()
    X(args, "check")
    out = capsys.readouterr().out
    assert "file changed outside the plan: stray.txt" in out
    assert "placeholder" in out


def test_main_checkout_change_detected(proj, capsys):
    root, args, plan = proj
    start(proj)
    (root / "src" / "handler.py").write_text("tampered\n")
    capsys.readouterr()
    X(args, "check")
    assert "main checkout changed" in capsys.readouterr().out


def test_retry_cap_and_same_signature(proj, capsys):
    root, args, plan = proj
    start(proj)
    X(args, "verify", "--baseline")
    X(args, "task", "T1", "--status", "started")
    X(args, "task", "T1", "--status", "failed", "--signature", "abc")
    capsys.readouterr()
    X(args, "task", "T1", "--status", "started")
    X(args, "task", "T1", "--status", "failed", "--signature", "abc")
    assert "STOP RETRYING" in capsys.readouterr().out
    capsys.readouterr()
    assert X(args, "task", "T1", "--status", "started") == 2  # same failure twice: stop is enforced
    assert "same way" in capsys.readouterr().out


def test_block_cascades_to_dependents(proj):
    root, args, plan = proj
    start(proj)
    assert X(args, "task", "T1", "--status", "blocked") == 2  # reason required
    assert X(args, "task", "T1", "--status", "blocked", "--reason", "needs decision") == 0
    run = x.load_run(str(root))
    assert run["tasks"]["T2"]["status"] == "blocked" and run["tasks"]["T2"]["reason"] == "blocked by T1"


def test_interrupted_run_resumes(proj, capsys):
    root, args, plan = proj
    start(proj)
    run = x.load_run(str(root))
    run["heartbeat"] = "2020-01-01T00:00:00Z"
    x.save_run(str(root), run)
    assert start(proj) == 0
    assert "resuming" in capsys.readouterr().out


def test_plan_change_refuses_resume(proj, capsys):
    root, args, plan = proj
    start(proj)
    run = x.load_run(str(root))
    run["heartbeat"] = "2020-01-01T00:00:00Z"
    x.save_run(str(root), run)
    p = r.load(plan)
    p["constraints"].append("new constraint")
    r.save(plan, p)
    assert start(proj) == 2
    assert "changed" in capsys.readouterr().out


def test_amendment_keeps_original(proj):
    root, args, plan = proj
    start(proj)
    assert X(args, "amend", "T1", "--index", "0", "--text", "corrected", "--reason", "count wrong", "--evidence", "grep shows 2", "--authority", "user") == 0
    am = x.load_run(str(root))["amendments"][0]
    assert am["original"].startswith("Requests over the limit") and am["amended"] == "corrected"


def test_exec_ledger_chain_intact(proj):
    root, args, plan = proj
    start(proj)
    X(args, "verify", "--baseline")
    ok, why = r.verify_chain(r.load_ledger(str(root)))
    assert ok, why


def _review_all(args, plan):
    for role in r.required_reviewers(r.load(plan), r.load_pack()["routing"]):
        assert X(args, "review", role, "approve") == 0


def _do_tasks(args, root, plan):
    wt = x.load_run(str(root))["worktree"]
    X(args, "verify", "--baseline")
    for tid, path, text, red in (("T1", "src/limiter.py", "retry\n", "test -f src/limiter.py && grep -q retry src/limiter.py"), ("T2", "src/handler.py", "tier default\n", "grep -q tier src/handler.py")):
        assert X(args, "task", tid, "--status", "started") == 0
        assert X(args, "red", tid, "--cmd", red) == 0
        pw = x.load_run(str(root))["worktree"]
        with open(os.path.join(pw, path), "a") as f:
            f.write(text)
        assert X(args, "vtask", tid) == 0
        assert X(args, "task", tid, "--status", "done") == 0
    assert X(args, "checkpoint", "CP1") == 0
    assert X(args, "verifier", "CP1", "pass", "--agent", "v1") == 0
    assert X(args, "verify") == 0
    assert X(args, "final", "FV1") == 0
    assert X(args, "verifier", "branch", "pass", "--agent", "v2") == 0
    for c in ("C1", "C2"):
        assert X(args, "claim", c, "--status", "established", "--note", "ok") == 0
    _review_all(args, plan)


def test_review_round_cap(proj, capsys):
    root, args, plan = proj
    start(proj)
    _do_tasks(args, root, plan)
    role = r.required_reviewers(r.load(plan), r.load_pack()["routing"])[0]
    for _ in range(2):
        X(args, "review", role, "reject", "--note", "finding")
    capsys.readouterr()
    assert X(args, "review", role, "approve") == 2  # fourth round refused (approve was round 1)
    assert "review rounds" in capsys.readouterr().out


def test_squash_merge_delivery(proj, tmp_path_factory, capsys, monkeypatch):
    root, args, plan = proj
    remote = tmp_path_factory.mktemp("remote")
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    base = git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    git(root, "remote", "add", "origin", "https://github.com/o/r.git")
    git(root, "config", "url.%s.insteadOf" % str(remote), "https://github.com/o/r.git")
    git(root, "push", "-q", "origin", base)
    bindir = tmp_path_factory.mktemp("bin")
    import ghstub
    ghstub.install(bindir)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    assert X(args, "start", plan, "--feedback", FEEDBACK, "--delivery", "squash-merge") == 0
    _do_tasks(args, root, plan)
    capsys.readouterr()
    assert X(args, "finish") == 0
    log = (bindir / "gh.log").read_text()
    assert "api -X POST" in log and "/pulls" in log and '"head": "rigor/demo-rate-limit"' in log and '"base": "%s"' % base in log
    assert "api -X PUT repos/" in log and "/pulls/3/merge" in log and '"merge_method": "squash"' in log
    assert git(root, "branch", "--list", "rigor/demo-rate-limit").strip() == ""
    assert "api -X DELETE repos/o/r/git/refs/heads/rigor/demo-rate-limit" in log


def _finish_everything_but_verifiers(proj):
    root, args, plan = proj
    start(proj)
    X(args, "verify", "--baseline")
    pw = x.load_run(str(root))["worktree"]
    X(args, "task", "T1", "--status", "started")
    X(args, "red", "T1", "--cmd", "test -f src/limiter.py && grep -q retry src/limiter.py")
    open(os.path.join(pw, "src", "limiter.py"), "w").write("def limit(): return 'retry-after'\n")
    X(args, "vtask", "T1"); X(args, "task", "T1", "--status", "done")
    X(args, "task", "T2", "--status", "started")
    X(args, "red", "T2", "--cmd", "grep -q tier src/handler.py")
    open(os.path.join(pw, "src", "handler.py"), "a").write("tier = 'default'\n")
    X(args, "vtask", "T2"); X(args, "task", "T2", "--status", "done")
    X(args, "checkpoint", "CP1"); X(args, "verify"); X(args, "final", "FV1")
    for c in ("C1", "C2"):
        X(args, "claim", c, "--status", "established", "--note", "ok")
    for role in r.required_reviewers(r.load(plan), r.load_pack()["routing"]):
        X(args, "review", role, "approve")


def test_finish_refused_without_fresh_verifiers(proj, capsys):
    root, args, plan = proj
    _finish_everything_but_verifiers(proj)
    capsys.readouterr()
    assert X(args, "check", "--final") == 1
    out = capsys.readouterr().out
    assert "X_verifiers" in out and "X_verifier_branch" in out
    assert X(args, "finish") == 1


def test_verifier_refusals(proj, capsys):
    root, args, plan = proj
    start(proj)
    assert X(args, "verifier", "CP1", "pass", "--agent", "v") == 2      # checkpoint has not passed
    assert X(args, "verifier", "branch", "pass", "--agent", "v") == 2   # final verification not passed
    assert X(args, "verifier", "nope", "pass", "--agent", "v") == 2     # unknown scope


def test_next_phase_held_until_verified():
    plan = {"phases": [{"id": "P1", "tasks": [{"id": "T1"}], "checkpoints": [{"id": "CP1", "after_task": "T1"}]},
                       {"id": "P2", "tasks": [{"id": "T2"}]}]}
    run = {"checkpoints": {"CP1": {"passed": True, "tree": "a"}}, "verifiers": {}}
    assert x.held_by_checkpoint(plan, run, "T2") == "CP1"
    run["verifiers"]["CP1"] = {"verdict": "pass", "tree": "b"}      # verified different content
    assert x.held_by_checkpoint(plan, run, "T2") == "CP1"
    run["verifiers"]["CP1"] = {"verdict": "fail", "tree": "a"}
    assert x.held_by_checkpoint(plan, run, "T2") == "CP1"
    run["verifiers"]["CP1"] = {"verdict": "pass", "tree": "a"}
    assert x.held_by_checkpoint(plan, run, "T2") is None


def test_away_blocks_queues_and_user_unblocks(proj, capsys):
    root, args, plan = proj
    start(proj, ("--away",))
    X(args, "verify", "--baseline")
    for _ in range(2):
        X(args, "task", "T1", "--status", "started")
        X(args, "task", "T1", "--status", "failed", "--signature", "abc")
    run = x.load_run(str(root))
    assert run["tasks"]["T1"]["status"] == "blocked" and run["queue"][0]["id"] == "Q1"
    assert X(args, "task", "T2", "--status", "started") == 2   # dependent cannot start
    capsys.readouterr()
    assert X(args, "check", "--final") == 1
    assert "X_queue" in capsys.readouterr().out
    assert X(args, "answer", "Q1", "--text", "retry with a smaller change", "--unblock") == 0
    run = x.load_run(str(root))
    assert run["tasks"]["T1"]["status"] == "pending" and run["tasks"]["T1"]["attempts"] == 0
    assert X(args, "task", "T1", "--status", "started") == 0


def test_not_away_does_not_queue(proj):
    root, args, plan = proj
    start(proj)
    X(args, "verify", "--baseline")
    for _ in range(2):
        X(args, "task", "T1", "--status", "started")
        X(args, "task", "T1", "--status", "failed", "--signature", "abc")
    run = x.load_run(str(root))
    assert run["queue"] == [] and run["tasks"]["T1"]["status"] == "failed"


def test_execution_task_creates_planned_doc_in_the_branch_not_main(proj, capsys):
    root, args, plan = proj
    p = r.load(plan)
    sf = r.spec_path_of(p, plan)
    sp = r.load(sf)
    sp["decisions"][0]["adr"] = {"hard_to_reverse": True, "surprising": True, "real_tradeoff": True, "file": "docs/adr/0001-x.md"}
    r.save(sf, sp)
    p["phases"][0]["tasks"][0]["files"].append({"path": "docs/adr/0001-x.md", "op": "create", "verified_at": "2026-11-08"})
    p["phases"][0]["tasks"][0]["verify"].append({"run": "test -f docs/adr/0001-x.md", "expect": "ADR file exists", "kind": "happy", "proves": [0]})
    r.save(plan, p)
    for role in r.required_reviewers(r.load(plan), r.load_pack()["routing"]):
        r.main(args + ["log", "", "--kind", "review_complete", "--plan", plan, "--role", role, "--set-baseline"])
    assert r.main(args + ["render", plan]) == 0
    assert r.main(args + ["check", plan, "--final"]) == 0
    git(root, "add", "-A")
    assert start(proj) == 0
    _do_tasks_with_doc(args, root, plan)
    run = x.load_run(str(root))
    assert "docs/adr/0001-x.md" in git(root, "show", "--stat", "--format=", run["branch"])
    assert not (root / "docs").exists()          # main checkout never received it


def _do_tasks_with_doc(args, root, plan):
    X(args, "verify", "--baseline")
    pw = x.load_run(str(root))["worktree"]
    X(args, "task", "T1", "--status", "started")
    X(args, "red", "T1", "--cmd", "test -f src/limiter.py && grep -q retry src/limiter.py")
    open(os.path.join(pw, "src", "limiter.py"), "a").write("retry\n")
    os.makedirs(os.path.join(pw, "docs", "adr"), exist_ok=True)
    open(os.path.join(pw, "docs", "adr", "0001-x.md"), "w").write("# Fixed window\nChosen for simplicity.\n")
    assert X(args, "vtask", "T1") == 0
    assert X(args, "task", "T1", "--status", "done") == 0


# ---------------------------------------------------------------- hardening
def test_open_question_blocks_dependent_task(proj, capsys):
    root, args, plan = proj
    p = r.load(plan)
    p["questions"] = [{"id": "Q9", "text": "which store?", "status": "open", "blocking_or_deferrable": "deferrable", "blocks": ["T1"]}]
    p["phases"][0]["tasks"][0]["blocked_on"] = ["Q9"]
    r.save(plan, p)
    run = {"tasks": {"T1": {"status": "pending"}, "T2": {"status": "pending"}}}
    assert "T1" not in x.ready(r.load(plan), {"tasks": run["tasks"], "checkpoints": {}, "verifiers": {}})


def test_red_refuses_harness_exit_codes_unless_declared(proj, capsys):
    root, args, plan = proj
    start(proj); X(args, "verify", "--baseline"); X(args, "task", "T1", "--status", "started")
    capsys.readouterr()
    assert X(args, "red", "T1", "--cmd", "grep -q retry src/missing.py") == 2     # exit 2: missing file, not an assertion
    assert "harness or collection error" in capsys.readouterr().out
    assert X(args, "red", "T1", "--cmd", "grep -q retry src/missing.py", "--expect-exit", "2") == 0


def test_vtask_refuses_undeclared_files(proj, capsys):
    root, args, plan = proj
    start(proj); X(args, "verify", "--baseline")
    wt = x.load_run(str(root))["worktree"]
    X(args, "task", "T1", "--status", "started")
    X(args, "red", "T1", "--cmd", "test -f src/limiter.py && grep -q retry src/limiter.py")
    open(os.path.join(wt, "src", "limiter.py"), "w").write("retry\n")
    open(os.path.join(wt, "pyproject.toml"), "w").write("x")
    capsys.readouterr()
    assert X(args, "vtask", "T1") == 1
    assert "pyproject.toml" in capsys.readouterr().out
    os.remove(os.path.join(wt, "pyproject.toml"))
    assert X(args, "vtask", "T1") == 0


def test_baseline_can_be_set_once(proj, capsys):
    root, args, plan = proj
    start(proj)
    assert X(args, "verify", "--baseline") == 0
    assert X(args, "verify", "--baseline") == 2


def test_followup_files_do_not_widen_scope_and_can_be_settled(proj, capsys):
    root, args, plan = proj
    start(proj); X(args, "verify", "--baseline")
    wt = x.load_run(str(root))["worktree"]
    os.makedirs(os.path.join(wt, "evil"), exist_ok=True)
    open(os.path.join(wt, "evil", "x.py"), "w").write("x=1\n")
    X(args, "followup", "later", "--file", "evil/x.py")
    capsys.readouterr()
    X(args, "check")
    assert "file changed outside the plan: evil/x.py" in capsys.readouterr().out
    assert X(args, "followup", "--settle", "0", "--status", "reported") == 0
    assert x.load_run(str(root))["followups"][0]["status"] == "reported"


def test_amend_needs_user_authority(proj):
    root, args, plan = proj
    start(proj)
    base = ["amend", "T1", "--index", "0", "--text", "t", "--reason", "r", "--evidence", "e"]
    assert X(args, *base, "--authority", "system") == 2
    assert X(args, *base, "--authority", "user") == 0


def test_review_role_validated_and_accept_best(proj, capsys):
    root, args, plan = proj
    start(proj); _do_tasks(args, root, plan) if False else None
    role = r.required_reviewers(r.load(plan), r.load_pack()["routing"])[0]
    assert X(args, "review", "made-up-role", "approve") == 2
    for _ in range(3):
        X(args, "review", role, "reject", "--note", "finding")
    assert X(args, "review", role, "approve") == 2                       # cap
    assert X(args, "review", role, "approve", "--accept-best") == 2     # needs the note
    assert X(args, "review", role, "approve", "--accept-best", "--note", "naming of helper unresolved") == 0
    assert x.load_run(str(root))["reviews"][role]["accepted_best"] is True


def test_away_limit_blocks_dependents_too(proj):
    root, args, plan = proj
    start(proj, ("--away",)); X(args, "verify", "--baseline")
    for _ in range(2):
        X(args, "task", "T1", "--status", "started")
        X(args, "task", "T1", "--status", "failed", "--signature", "abc")
    assert x.load_run(str(root))["tasks"]["T2"]["status"] == "blocked"


def test_finish_refused_with_uncommitted_worktree_changes(proj, capsys):
    root, args, plan = proj
    start(proj); _do_tasks(args, root, plan)
    wt = x.load_run(str(root))["worktree"]
    open(os.path.join(wt, "src", "handler.py"), "a").write("sneaky = 1\n")
    capsys.readouterr()
    assert X(args, "finish") == 1
    assert "GX_close" in capsys.readouterr().out
    capsys.readouterr()
    X(args, "check", "--final")
    assert "uncommitted changes" in capsys.readouterr().out


def test_verifier_must_differ_from_implementers_and_earlier_verifiers(proj, capsys):
    root, args, plan = proj
    _finish_everything_but_verifiers(proj)
    run = x.load_run(str(root)); run["tasks"]["T1"]["agents"] = ["impl-1"]; x.save_run(str(root), run)
    assert X(args, "verifier", "CP1", "pass", "--agent", "impl-1") == 2
    assert X(args, "verifier", "CP1", "pass", "--agent", "v1") == 0
    assert X(args, "verifier", "branch", "pass", "--agent", "v1") == 2      # not fresh: already verified CP1
    assert X(args, "verifier", "branch", "pass", "--agent", "v2") == 0


def test_discard_frees_the_worktree_and_keeps_commits(proj, capsys):
    root, args, plan = proj
    start(proj); _do_tasks(args, root, plan)
    assert X(args, "discard", "--reason", "restart") == 0
    assert "discarded" in git(root, "branch", "--list", "rigor/*")
    assert not os.path.exists(os.path.join(str(root), ".rigor", "exec", "wt"))
