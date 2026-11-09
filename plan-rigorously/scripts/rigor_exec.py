"""rigor_exec - execution verbs and rules for the execute-rigorously skill.

Loaded by railguard.py as `railguard exec <verb>`. Python 3 standard library only.
State lives in .rigor/exec/run.yaml; every change is also a hash-chained ledger event.
"""
import contextlib, datetime, glob, io, os, re, shutil, sys
import railguard as rg

CAP = rg.lim("execution.retries.attempts")
SAME_SIG = rg.lim("execution.retries.same_failure")
HARNESS_REPAIRS = rg.lim("execution.retries.harness_repairs")
STALE_MINUTES = rg.lim("execution.heartbeat.stale")
DELIVERY = ("branch", "squash-merge")  # branch = the user did not authorize delivery; squash-merge = commit, push, PR, squash merge, delete both branches
MAX_ROUNDS = rg.lim("execution.review.rounds_per_role")
RED_EXIT = rg.lim("execution.red.exit_code")
PARALLEL = rg.lim("execution.delegation.subagent.parallel")
PER_PLAN = rg.lim("execution.worktree.per_plan")
GIT_TIMEOUT = rg.lim("execution.engine.git_timeout")
DELIVERY_TIMEOUT = rg.lim("execution.engine.delivery_timeout")
SIG_LINES = rg.lim("execution.engine.signature_lines")
SIG_CHARS = rg.lim("execution.engine.signature_chars")
REPORT_LINES = rg.lim("execution.report.lines")
XREF = os.path.join(os.path.dirname(rg.PACK), "execute-rigorously", "references")

XRULES = {}


def xrule(name):
    def deco(fn):
        XRULES[name] = fn
        return fn
    return deco


E, W = rg.E, rg.W


# ------------------------------------------------------------------ helpers
def run_path(root):
    return os.path.join(rg.rig(root), "exec", "run.yaml")


def load_run(root):
    p = run_path(root)
    return rg.load(p) if os.path.exists(p) else None


def save_run(root, run):
    rg.save(run_path(root), run)


def ts_age_minutes(ts):
    try:
        t = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
        return (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() / 60.0
    except (TypeError, ValueError):
        return 1e9


def git(wt, *args, check=False):
    rc, out = rg.run_cmd(["git", "-C", wt] + list(args), timeout=GIT_TIMEOUT)
    return rc, out


def stage(wt):
    git(wt, "add", "-A")
    rc, out = git(wt, "write-tree")
    return out.strip() if rc == 0 else ""


def head(wt):
    rc, out = git(wt, "rev-parse", "HEAD")
    return out.strip() if rc == 0 else ""


def tree_of(wt, rev):
    rc, out = git(wt, "rev-parse", rev + "^{tree}")
    return out.strip() if rc == 0 else ""


def sh(cmd, cwd, timeout=None):
    return rg.run_cmd(["bash", "-c", cmd], cwd=cwd, timeout=timeout or rg.lim("execution.engine.command_timeout"))


def ident(wt):
    return [] if git(wt, "config", "user.email")[1].strip() else ["-c", "user.name=rigor", "-c", "user.email=rigor@localhost"]


def phase_ids(plan):
    return [rg.sid(ph["id"]) for ph in plan.get("phases") or []]


def phase_of(plan, tid):
    for ph, t in rg.all_tasks(plan):
        if rg.sid(t["id"]) == tid:
            return rg.sid(ph["id"])


def open_wts(run):
    return [run["worktree"]]


def task_wt(run, plan, tid):
    return run["worktree"]


def active_wt(run):
    return run["worktree"]


def ensure_phase(root, run, plan, phid):
    return True


def tasks_by_id(plan):
    return {rg.sid(t["id"]): (ph, t) for ph, t in rg.all_tasks(plan)}


def order(plan):
    return [rg.sid(t["id"]) for _, t in rg.all_tasks(plan)]


def surfaces(plan):
    """Distinct surface names the plan declares on its tasks."""
    s = set()
    for _, t in rg.all_tasks(plan):
        s.update(str(x) for x in (t.get("surfaces") or []))
    return s


def topology(plan):
    n, sf = len(order(plan)), len(surfaces(plan))
    if n > rg.lim("execution.delegation.inline.tasks") or sf > rg.lim("execution.delegation.inline.surfaces"):
        return "subagent"
    return "inline"


def planned_files(plan):
    out = set()
    for _, t in rg.all_tasks(plan):
        for f in t.get("files") or []:
            p = f.get("path") if isinstance(f, dict) else f
            if p:
                out.add(p)
    return out


def sig_of(text):
    t = re.sub(r"\d+(\.\d+)?\s*(ms|s|sec|seconds)\b", "", text or "")
    t = re.sub(r"0x[0-9a-f]+|\b\d{4,}\b", "", t)
    lines = [l.strip() for l in t.splitlines() if re.search(r"(FAIL|ERROR|Error|error|assert)", l)]
    return rg.sha_text("\n".join(lines[-SIG_LINES:]) if lines else t[-SIG_CHARS:])[:16]


def failures_in(cmd, rc, out):
    if rc == 0:
        return []
    items = [f"{cmd} :: exit {rc}"]
    for l in out.splitlines():
        if re.search(r"\b(FAILED|FAIL|ERROR)\b", l):
            items.append(re.sub(r"\d+(\.\d+)?\s*(ms|s)\b", "", l.strip())[:rg.lim("execution.engine.failure_item")])
    return items


def ctx_for(root, run=None):
    c = rg.Ctx()
    c.root = root
    c.run = run if run is not None else load_run(root)
    c.state = rg.load_state(root)
    c.ledger = rg.load_ledger(root)
    c.pack = rg.load_pack()
    c.routing = c.pack["routing"]
    c.xrouting = rg.load(os.path.join(XREF, "exec-routing.yaml"))
    c.final = False
    c.plan = rg.load(os.path.join(root, c.run["plan"])) if c.run else {}
    c.wt = c.run["worktree"] if c.run else ""
    return c


def touch(root, run):
    run["heartbeat"] = rg.now()
    save_run(root, run)


def need_run(a):
    root = os.path.abspath(a.root)
    run = load_run(root)
    if not run:
        print("REFUSED: no run. Start with: railguard exec start <plan> --feedback CMD --delivery MODE")
        return root, None
    if run.get("finished"):
        print("run already finished; nothing to do")
        return root, None
    return root, run


def log(root, kind, subject, reason="", authority="system", before=None, after=None):
    return rg.ledger_add(root, kind, subject, reason, authority, before, after)


def seq(run):
    run["seq"] = int(run.get("seq", 0)) + 1
    return run["seq"]


def phase_end_checkpoints(plan):
    """The last checkpoint of each phase: where a fresh independent verifier must attest."""
    out = {}
    for ph in plan.get("phases") or []:
        cps = ph.get("checkpoints") or []
        if cps:
            out[rg.sid(cps[-1]["id"])] = ph
    return out


def verified(run, cid):
    rec, v = run["checkpoints"].get(cid) or {}, (run.get("verifiers") or {}).get(cid) or {}
    return bool(rec.get("passed") and v.get("verdict") == "pass" and v.get("tree") == rec.get("tree"))


def held_by_checkpoint(plan, run, tid):
    od = order(plan)
    ends = phase_end_checkpoints(plan)
    for ph in plan.get("phases") or []:
        for cp in ph.get("checkpoints") or []:
            at, cid = rg.sid(cp.get("after_task")), rg.sid(cp["id"])
            if at in od and tid != at and od.index(tid) > od.index(at):
                if not (run["checkpoints"].get(cid) or {}).get("passed"):
                    return cid
                if cid in ends and phase_of(plan, tid) != rg.sid(ends[cid].get("id")) and not verified(run, cid):
                    return cid
    return None


def open_questions(plan):
    return {rg.sid(q.get("id")) for q in plan.get("questions") or [] if q.get("status") == "open"}


def block_cascade(run, tb, tid, reason):
    """Block a task and, transitively, every task that depends on it."""
    run["tasks"][tid]["status"] = "blocked"
    run["tasks"][tid]["reason"] = reason
    stack = [tid]
    while stack:
        cur = stack.pop()
        for t2, (_, t) in tb.items():
            if cur in [rg.sid(d) for d in t.get("depends") or []] and run["tasks"][t2]["status"] != "blocked":
                run["tasks"][t2]["status"] = "blocked"
                run["tasks"][t2]["reason"] = f"blocked by {cur}"
                stack.append(t2)


def dirty_paths(wt):
    paths = set()
    for args in (("diff", "--name-only", "HEAD"), ("ls-files", "--others", "--exclude-standard")):
        rc, out = git(wt, *args)
        paths |= {l.strip() for l in out.splitlines() if l.strip() and not l.startswith(".rigor/")}
    return sorted(paths)


def ready(plan, run):
    out = []
    for tid, (ph, t) in tasks_by_id(plan).items():
        st = run["tasks"][tid]["status"]
        if st in ("done", "blocked"):
            continue
        deps = [rg.sid(d) for d in t.get("depends") or []]
        if any(run["tasks"][d]["status"] != "done" for d in deps if d in run["tasks"]):
            continue
        if {rg.sid(x) for x in t.get("blocked_on") or []} & open_questions(plan):
            continue  # an unanswered question this task depends on
        if held_by_checkpoint(plan, run, tid):
            continue
        out.append(tid)
    return out


# ------------------------------------------------------------------ verbs
def v_start(a):
    root = os.path.abspath(a.root)
    plan_file = os.path.abspath(a.plan)
    if not os.path.exists(plan_file):
        print("REFUSED: plan file not found")
        return 2
    run = load_run(root)
    if run:
        if run.get("finished"):
            print("already executed: run finished", run.get("finished_at"), "- nothing to do")
            return 0
        age = ts_age_minutes(run.get("heartbeat"))
        if age < run.get("stale_minutes", STALE_MINUTES):
            print(f"REFUSED: a run is live (heartbeat {age:.0f} min ago). Only one loop may drive a plan.")
            return 2
        plan = rg.load(plan_file)
        if rg.plan_hash(plan) != run["plan_hash"]:
            print("REFUSED: the plan changed since this run began. Ask the user, then 'exec discard --reason ...'.")
            return 2
        touch(root, run)
        log(root, "note", "exec resume", f"resumed interrupted run (heartbeat {age:.0f} min old)", "system")
        print("resuming interrupted run on branch", run["branch"], "in", run["worktree"])
        return 0
    plan = rg.load(plan_file)
    st = rg.load_state(root)
    probs = []
    if (plan.get("meta") or {}).get("status") != "final":
        probs.append("plan.meta.status is not final")
    if st.get("execute_authorized") is not True:
        probs.append("execution was not authorized (answer execute_authorized in the planning front batch)")
    if st.get("render_plan_hash") != rg.plan_hash(plan):
        probs.append("plan has changed since it was last rendered; run render after the final check")
    buf = io.StringIO()
    ca = argparse_ns(root=root, plan=plan_file, final=True, pack=False, repo=None)
    with contextlib.redirect_stdout(buf):
        rc = rg.cmd_check(ca)
    if rc != 0:
        probs.append("railguard check --final does not pass")
    if not a.feedback:
        probs.append("no --feedback command given (the user must confirm how to verify the repository)")
    if a.delivery not in DELIVERY:
        probs.append("--delivery must be one of " + ", ".join(DELIVERY))
    if not os.path.isdir(os.path.join(root, ".git")) and not os.path.isfile(os.path.join(root, ".git")):
        probs.append("project root is not a git repository")
    snap = rg.snapshot(root)
    if snap.get("kind") == "git" and snap.get("porcelain") and not a.allow_dirty:
        probs.append("main checkout has uncommitted changes (ask the user; --allow-dirty)")
    if probs:
        print("REFUSED:")
        for p in probs:
            print("  -", p)
        return 2
    slug = (plan.get("meta") or {}).get("slug", "plan")
    branch = f"rigor/{slug}"
    wt = os.path.join(rg.rig(root), "exec", "wt")
    rc, out = git(root, "rev-parse", "HEAD")
    if rc != 0:
        print("REFUSED: repository has no commit to branch from")
        return 2
    base = out.strip()
    bb = git(root, "rev-parse", "--abbrev-ref", "HEAD")[1].strip()
    if bb in ("", "HEAD"):
        print("REFUSED: main checkout is on a detached HEAD; check out the branch the work should land on")
        return 2
    if os.path.exists(wt):
        print("REFUSED: worktree path exists:", wt)
        return 2
    os.makedirs(os.path.dirname(wt), exist_ok=True)
    rc, out = git(root, "worktree", "add", "-b", branch, wt, base)
    if rc != 0:
        print("REFUSED: could not create worktree:", out)
        return 2
    if a.topology == "inline" and topology(plan) == "subagent":
        print("REFUSED: this plan is too large for inline execution (see execution.delegation); the topology cannot be overridden down")
        return 2
    topo = a.topology or topology(plan)
    run = {"slug": slug, "plan": os.path.relpath(plan_file, root), "plan_hash": rg.plan_hash(plan), "started": rg.now(),
           "heartbeat": rg.now(), "stale_minutes": STALE_MINUTES, "finished": False, "branch": branch, "worktree": wt,
           "base": base, "base_branch": bb, "delivery": a.delivery, "away": bool(a.away), "queue": [], "verifiers": {},
           "review_rounds": {}, "delivered": False, "feedback": list(a.feedback), "topology": topo,
           "root_snapshot": snap, "baseline": None, "seq": 0, "start_ok": True,
           "tasks": {t: {"status": "pending", "attempts": 0, "harness_used": 0} for t in order(plan)},
           "checkpoints": {}, "last_verify": None, "reviews": {}, "claims": {}, "final": {},
           "followups": [], "noticed": [], "amendments": []}
    save_run(root, run)
    log(root, "note", "exec start", f"branch {branch} from {base[:10]}, topology {topo}, delivery {a.delivery}", "user")
    print(f"started: branch {branch}, worktree {os.path.relpath(wt, root)}, topology {topo}, delivery {a.delivery}")
    print("next: railguard exec verify --baseline")
    return 0


class argparse_ns:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def run_feedback(run, root):
    results = []
    for cmd in run["feedback"]:
        rc, out = sh(cmd, active_wt(run))
        results.append((cmd, rc, out))
    return results


def v_verify(a):
    root, run = need_run(a)
    if not run:
        return 2
    plan = rg.load(os.path.join(root, run["plan"]))
    res = run_feedback(run, root)
    items = []
    for cmd, rc, out in res:
        items += failures_in(cmd, rc, out)
    t = stage(active_wt(run))
    if a.baseline:
        if run.get("baseline") is not None:
            print("REFUSED: the baseline was already recorded and cannot be replaced")
            return 2
        run["baseline"] = sorted(set(items))
        log(root, "tool_run", "feedback baseline", f"{len(set(items))} pre-existing failure item(s)", "system")
        print(f"baseline recorded: {len(set(items))} failure item(s)")
    else:
        base = set(run.get("baseline") or [])
        pf = planned_files(plan)
        new = sorted(i for i in set(items) if i not in base or any(p in i for p in pf))
        old = sorted(i for i in set(items) if i not in new)
        run["last_verify"] = {"tree": t, "new": new, "baseline_only": old, "ts": rg.now()}
        log(root, "tool_run", "feedback verify", f"new failures {len(new)}, baseline-only {len(old)}", "system")
        print(f"verify: {len(new)} new failure(s), {len(old)} baseline-only")
        for i in new:
            print("  NEW", i)
    touch(root, run)
    return 0


def v_next(a):
    root, run = need_run(a)
    if not run:
        return 2
    plan = rg.load(os.path.join(root, run["plan"]))
    touch(root, run)
    rd = ready(plan, run)
    tb = tasks_by_id(plan)
    left = [t for t, v in run["tasks"].items() if v["status"] not in ("done", "blocked")]
    if not left:
        pend = [c_ for c_ in phase_end_checkpoints(plan) if not (run["checkpoints"].get(c_) or {}).get("passed") or not verified(run, c_)]
        print("all tasks done or blocked." + (f" Still pending: checkpoint or fresh verifier at {', '.join(sorted(pend))}." if pend else "") + " Then review, close, exec finish.")
        return 0
    if not rd:
        held = {t: held_by_checkpoint(plan, run, t) for t in left}
        hs = sorted({h for h in held.values() if h})
        need_cp = [h for h in hs if not (run["checkpoints"].get(h) or {}).get("passed")]
        need_vf = [h for h in hs if h not in need_cp]
        msg = "no task ready."
        if need_cp:
            msg += f" Run checkpoint(s): {', '.join(need_cp)}."
        if need_vf:
            msg += f" Fresh verifier pass needed: {', '.join(need_vf)} (exec verifier <id> pass --agent NAME)."
        if not hs:
            msg += " Remaining tasks wait on blocked or unfinished dependencies."
        print(msg)
        qopen = [q for q in run.get("queue", []) if not q.get("answer")]
        if qopen:
            print(f"{len(qopen)} question(s) queued for the user (see exec check)")
        return 0
    print(f"topology: {run['topology']}   ready: {len(rd)}")
    for tid in rd:
        ph, t = tb[tid]
        print(f"  {tid} [{t.get('size')}] {t.get('title')}  attempts {run['tasks'][tid]['attempts']}/{CAP}")
    return 0


def v_task(a):
    root, run = need_run(a)
    if not run:
        return 2
    plan = rg.load(os.path.join(root, run["plan"]))
    tb = tasks_by_id(plan)
    tid = rg.sid(a.id)
    if tid not in tb:
        print("unknown task", tid)
        return 2
    tr = run["tasks"][tid]
    wt = task_wt(run, plan, tid)
    if a.report is not None:
        if len(a.report.strip().splitlines()) > REPORT_LINES:
            print(f"REFUSED: report is longer than {REPORT_LINES} lines; summarize it")
            return 2
        tr["report"] = a.report
    if a.status == "started":
        if tid not in ready(plan, run):
            print(f"REFUSED: {tid} is not ready (dependencies, blocked, or a checkpoint holds it)")
            return 2
        if tr["attempts"] >= CAP:
            print(f"REFUSED: {tid} has reached the retry cap {CAP}; block it with --status blocked --reason")
            return 2
        if tr.get("sig_run", 0) >= SAME_SIG:
            print(f"REFUSED: {tid} failed the same way {SAME_SIG} times in a row; block it, or have the user amend it")
            return 2
        running = [t_ for t_, v in run["tasks"].items() if v["status"] == "started" and t_ != tid]
        if len(running) >= PARALLEL:
            print(f"REFUSED: {', '.join(running)} is still started; tasks run {PARALLEL} at a time")
            return 2
        if run["topology"] == "subagent" and not a.agent:
            print("REFUSED: subagent topology needs --agent <implementer id> on every task start")
            return 2
        if not ensure_phase(root, run, plan, phase_of(plan, tid)):
            return 2
        wt = task_wt(run, plan, tid)
        tr["attempts"] += 1
        tr["status"] = "started"
        if a.agent:
            tr.setdefault("agents", []).append(a.agent)
        tr.setdefault("first_dispatch", rg.now())
        print(f"{tid} started, attempt {tr['attempts']}/{CAP}")
    elif a.status == "failed":
        s = a.signature or sig_of(a.output or "")
        if a.harness and tr["harness_used"] < HARNESS_REPAIRS:
            tr["harness_used"] += 1
            tr["attempts"] = max(0, tr["attempts"] - 1)
            print(f"harness failure: free repair {tr['harness_used']}/{HARNESS_REPAIRS} granted; attempt not counted")
        tr["status"] = "failed"
        tr["sig_run"] = tr.get("sig_run", 0) + 1 if tr.get("last_signature") == s else 1
        same = tr["sig_run"] >= SAME_SIG
        tr["last_signature"] = s
        stop = same or tr["attempts"] >= CAP
        print(f"{tid} failed (signature {s})")
        if stop:
            why = f"same failure {SAME_SIG} times in a row" if same else "retry cap reached" if tr["attempts"] >= CAP else "stop"
            print(f"STOP RETRYING: {why}. Block the task: exec task {tid} --status blocked --reason ...")
            if run.get("away"):
                block_cascade(run, tb, tid, f"limit hit while the user was away: {why}")
                queue_question(root, run, tid, f"{tid} hit a limit ({why}). Decide: retry with a changed approach, amend the task, or leave it blocked.")
    elif a.status == "blocked":
        if not a.reason:
            print("a reason is required to block")
            return 2
        block_cascade(run, tb, tid, a.reason)
        log(root, "note", f"task {tid} blocked", a.reason, "system")
        print(f"{tid} blocked (dependents blocked too)")
    elif a.status == "done":
        vt = tr.get("vtask") or {}
        if not vt.get("ok"):
            print(f"REFUSED: no passing exec vtask {tid} on record")
            return 2
        if (plan.get("evidence_path") or {}).get("test_strategy") == "tdd":
            red = tr.get("red")
            if not red or red["seq"] > vt["seq"]:
                print(f"REFUSED: tdd needs a recorded failing test (exec red {tid} --cmd ...) before the green verify")
                return 2
        if stage(wt) != vt["tree"]:
            print("REFUSED: files changed since the verify; run exec vtask again")
            return 2
        git(wt, *ident(wt), "commit", "-q", "--allow-empty", "-m", f"{tid}: {tb[tid][1].get('title')}")
        tr["status"] = "done"
        tr["done_seq"] = seq(run)
        tr["commit"] = head(wt)
        log(root, "note", f"task {tid} done", f"commit {tr['commit'][:10]}", "system")
        print(f"{tid} done at {tr['commit'][:10]}")
    touch(root, run)
    return 0


def v_red(a):
    root, run = need_run(a)
    if not run:
        return 2
    tid = rg.sid(a.id)
    plan = rg.load(os.path.join(root, run["plan"]))
    if tid not in run["tasks"] or not ensure_phase(root, run, plan, phase_of(plan, tid)):
        print("unknown task or phase cannot start")
        return 2
    rc, out = sh(a.cmd, task_wt(run, plan, tid))
    if rc == 0:
        print("REFUSED: the test passed; red needs a failing test (and it must fail for the right reason)")
        return 2
    if rc != RED_EXIT and a.expect_exit != rc:
        print(f"REFUSED: exit {rc} looks like a harness or collection error, not a failed assertion (an assertion failure exits {RED_EXIT}). "
              f"If this runner really reports failures with exit {rc}, say so with --expect-exit {rc}.")
        return 2
    run["tasks"][tid]["red"] = {"cmd": a.cmd, "rc": rc, "tail": out[-rg.lim("execution.engine.output_tail"):], "seq": seq(run)}
    log(root, "tool_run", f"red {tid}", f"exit {rc}", "system")
    touch(root, run)
    print(f"red recorded for {tid} (exit {rc})")
    return 0


def v_vtask(a):
    root, run = need_run(a)
    if not run:
        return 2
    plan = rg.load(os.path.join(root, run["plan"]))
    tid = rg.sid(a.id)
    t = tasks_by_id(plan)[tid][1]
    ok, rows = True, []
    allowed = {f.get("path") if isinstance(f, dict) else f for f in t.get("files") or []}
    extra = [p for p in dirty_paths(task_wt(run, plan, tid)) if p not in allowed]
    if extra:
        print(f"REFUSED: {tid} changed files its plan does not declare: {', '.join(extra)}. Revert them, or record exec noticed / exec followup.")
        return 1
    for v in t.get("verify") or []:
        rc, out = sh(v["run"], task_wt(run, plan, tid))
        rows.append({"run": v["run"], "rc": rc})
        if rc != 0:
            ok = False
            print(f"FAIL {v['run']} (exit {rc})\n{out[-rg.lim("execution.engine.output_tail"):]}")
    tree = stage(task_wt(run, plan, tid))
    run["tasks"][tid]["vtask"] = {"ok": ok, "tree": tree, "seq": seq(run), "results": rows}
    log(root, "tool_run", f"vtask {tid}", "passed" if ok else "failed", "system")
    touch(root, run)
    print(f"vtask {tid}: {'PASS' if ok else 'FAIL'} ({len(rows)} command(s))")
    return 0 if ok else 1


def v_checkpoint(a):
    root, run = need_run(a)
    if not run:
        return 2
    plan = rg.load(os.path.join(root, run["plan"]))
    cp = next((c for ph in plan.get("phases") or [] for c in ph.get("checkpoints") or [] if rg.sid(c.get("id")) == a.id), None)
    if not cp:
        print("unknown checkpoint", a.id)
        return 2
    if run["tasks"].get(rg.sid(cp["after_task"]), {}).get("status") != "done":
        print("REFUSED: the checkpoint's task is not done")
        return 2
    ok = True
    cwt = task_wt(run, plan, rg.sid(cp["after_task"]))
    for cmd in cp.get("verify") or []:
        rc, out = sh(cmd, cwt)
        if rc != 0:
            ok = False
            print(f"FAIL {cmd} (exit {rc})\n{out[-rg.lim("execution.engine.output_tail"):]}")
    run["checkpoints"][a.id] = {"passed": ok, "tree": stage(cwt), "seq": seq(run)}
    log(root, "gate", f"checkpoint {a.id}", "passed" if ok else "failed", "rule:checkpoint")
    touch(root, run)
    print(f"checkpoint {a.id}: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def queue_question(root, run, subject, text):
    q = run.setdefault("queue", [])
    if any(x["subject"] == subject and not x.get("answer") for x in q):
        return
    qid = "Q%d" % (len(q) + 1)
    q.append({"id": qid, "subject": subject, "text": text, "asked": rg.now()})
    log(root, "note", f"question {qid}", text, "system")
    print(f"queued {qid} for the user: {text}")


def v_verifier(a):
    """Record that a fresh, independent verifier re-ran the plan's checks at a phase-end checkpoint or on the whole branch."""
    root, run = need_run(a)
    if not run:
        return 2
    plan = rg.load(os.path.join(root, run["plan"]))
    scope = a.scope
    ends = phase_end_checkpoints(plan)
    if scope == "branch":
        cur = stage(run["worktree"])
        bad = [f.get("id") for f in plan.get("final_verification") or []
               if not (run["final"].get(rg.sid(f["id"])) or {}).get("ok") or run["final"][rg.sid(f["id"])]["tree"] != cur]
        if bad:
            print("REFUSED: final verification has not passed at the current content:", ", ".join(map(str, bad)))
            return 2
        tree = cur
    elif scope in ends:
        rec = run["checkpoints"].get(scope) or {}
        if not rec.get("passed"):
            print("REFUSED: the checkpoint has not passed; run exec checkpoint first")
            return 2
        tree = rec["tree"]
    else:
        print(f"unknown scope {scope}: use a phase-end checkpoint ({', '.join(sorted(ends)) or 'none'}) or branch")
        return 2
    if a.verdict == "fail" and not a.note:
        print("a failing verdict needs --note")
        return 2
    implementers = {x for v in run["tasks"].values() for x in v.get("agents", [])}
    earlier = {v["agent"] for k, v in (run.get("verifiers") or {}).items() if k != scope}
    if a.agent in implementers or a.agent in earlier:
        print(f"REFUSED: verifier {a.agent} already implemented or verified in this run; a fresh verifier is a different agent")
        return 2
    run.setdefault("verifiers", {})[scope] = {"verdict": a.verdict, "agent": a.agent, "tree": tree, "seq": seq(run), "note": a.note or ""}
    log(root, "gate", f"verifier {scope}", f"{a.verdict} by {a.agent} {a.note or ''}".strip(), "rule:verifier")
    touch(root, run)
    print(f"verifier {scope}: {a.verdict.upper()} (agent {a.agent})")
    return 0 if a.verdict == "pass" else 1


def v_answer(a):
    root, run = need_run(a)
    if not run:
        return 2
    q = next((x for x in run.get("queue", []) if x["id"] == a.id), None)
    if not q:
        print("unknown question", a.id)
        return 2
    q["answer"], q["answered"] = a.text, rg.now()
    log(root, "decision", f"answer {a.id}", a.text, "user")
    if a.unblock and q["subject"] in run["tasks"]:
        tr = run["tasks"][q["subject"]]
        tr.update({"status": "pending", "attempts": 0, "harness_used": 0, "sig_run": 0})
        tr.pop("reason", None)
        print(f"{q['subject']} unblocked with fresh attempts by the user's decision")
    touch(root, run)
    print(f"{a.id} answered")
    return 0


def todo_items(plan, run):
    """Every unit of work as a to-do: phases with their tasks, checkpoints, verifier passes, reviews, final items, delivery."""
    def st_task(v):
        return {"done": "completed", "started": "in_progress", "failed": "in_progress", "blocked": "blocked"}.get(v["status"], "pending")
    items = []
    ends = phase_end_checkpoints(plan)
    for ph in plan.get("phases") or []:
        pid = rg.sid(ph["id"])
        ts = [rg.sid(t["id"]) for t in ph.get("tasks") or []]
        sts = [st_task(run["tasks"][t]) for t in ts]
        cps_ok = all((run["checkpoints"].get(rg.sid(cp["id"])) or {}).get("passed") and (rg.sid(cp["id"]) not in ends or verified(run, rg.sid(cp["id"]))) for cp in ph.get("checkpoints") or [])
        ps = "completed" if sts and all(x == "completed" for x in sts) and cps_ok else "in_progress" if sts and all(x == "completed" for x in sts) else "in_progress" if any(x in ("completed", "in_progress") for x in sts) else "pending"
        items.append((ps, "phase", pid, ph.get("title") or pid, ""))
        for t in ph.get("tasks") or []:
            tid = rg.sid(t["id"])
            items.append((st_task(run["tasks"][tid]), "task", tid, t.get("title", tid), pid))
        for cp in ph.get("checkpoints") or []:
            cid = rg.sid(cp["id"])
            rec = run["checkpoints"].get(cid) or {}
            items.append(("completed" if rec.get("passed") else "pending", "checkpoint", cid, f"checkpoint {cid}", pid))
            if cid in ends:
                items.append(("completed" if verified(run, cid) else "pending", "verifier", cid, f"fresh verifier at {cid}", pid))
    for role in sorted(set(run.get("reviews") or {}) | set(rg.required_reviewers(plan, rg.load_pack()["routing"]))):
        items.append(("completed" if role in run["reviews"] else "pending", "review", role, f"{role} review", ""))
    for fv in plan.get("final_verification") or []:
        fid = rg.sid(fv["id"])
        items.append(("completed" if (run["final"].get(fid) or {}).get("ok") else "pending", "final", fid, f"final verification {fid}", ""))
    bv = (run.get("verifiers") or {}).get("branch") or {}
    items.append(("completed" if bv.get("verdict") == "pass" else "pending", "verifier", "branch", "fresh verifier on the whole branch", ""))
    items.append(("completed" if run.get("delivered") or (run.get("finished") and run["delivery"] == "branch") else "pending", "delivery", run["delivery"], f"delivery: {run['delivery']}", ""))
    return items


def v_todo(a):
    root, run = need_run(a)
    if not run:
        return 2
    plan = rg.load(os.path.join(root, run["plan"]))
    print("status\tkind\tid\ttitle\tparent")
    for it in todo_items(plan, run):
        print("\t".join(it))
    return 0


def v_final(a):
    root, run = need_run(a)
    if not run:
        return 2
    plan = rg.load(os.path.join(root, run["plan"]))
    fv = next((f for f in plan.get("final_verification") or [] if rg.sid(f.get("id")) == a.id), None)
    if not fv:
        print("unknown final verification item", a.id)
        return 2
    rc, out = sh((fv.get("verify") or {}).get("run", "false"), run["worktree"])
    run["final"][a.id] = {"ok": rc == 0, "tree": stage(run["worktree"]), "seq": seq(run)}
    log(root, "tool_run", f"final {a.id}", "passed" if rc == 0 else "failed", "system")
    touch(root, run)
    print(f"final {a.id}: {'PASS' if rc == 0 else 'FAIL'}")
    if rc != 0:
        print(out[-rg.lim("execution.engine.output_tail"):])
    return 0 if rc == 0 else 1


def v_claim(a):
    root, run = need_run(a)
    if not run:
        return 2
    if a.status not in ("established", "limited", "refuted") or not a.note:
        print("claim needs --status established|limited|refuted and --note")
        return 2
    run["claims"][a.id] = {"status": a.status, "note": a.note, "ts": rg.now()}
    log(root, "note", f"claim {a.id}", f"{a.status}: {a.note}", "system")
    touch(root, run)
    print(f"claim {a.id} {a.status}")
    return 0


def v_review(a):
    root, run = need_run(a)
    if not run:
        return 2
    plan = rg.load(os.path.join(root, run["plan"]))
    required = rg.required_reviewers(plan, rg.load_pack()["routing"])
    if a.role not in required:
        print(f"REFUSED: {a.role} is not a reviewer this plan requires ({', '.join(required)})")
        return 2
    n = run["review_rounds"].get(a.role, 0)
    if a.accept_best:
        if n < MAX_ROUNDS or not a.note:
            print(f"--accept-best is only for a role that used its {MAX_ROUNDS} rounds, and needs --note naming the open findings")
            return 2
        h = head(run["worktree"])
        run["reviews"][a.role] = {"head": h, "tree": tree_of(run["worktree"], "HEAD"), "ts": rg.now(), "accepted_best": True, "note": a.note}
        log(root, "deviation", f"review {a.role} accepted best version", a.note, "user")
        touch(root, run)
        print(f"{a.role}: best version accepted by the user without consensus; open findings are listed in the final report")
        return 0
    if n >= MAX_ROUNDS:
        print(f"REFUSED: {a.role} already had {MAX_ROUNDS} review rounds. Present the best version and ask the user; if they accept it: exec review {a.role} approve --accept-best --note \"<open findings>\".")
        if run.get("away"):
            queue_question(root, run, a.role, f"{a.role} has used {MAX_ROUNDS} review rounds without approval. Accept the best version, or direct a change.")
            touch(root, run)
        return 2
    run["review_rounds"][a.role] = n + 1
    h = head(run["worktree"])
    if a.verdict == "approve":
        run["reviews"][a.role] = {"head": h, "tree": tree_of(run["worktree"], "HEAD"), "ts": rg.now()}
        log(root, "review_complete", a.role, "", "system", None, h)
        print(f"{a.role} approved head {h[:10]}")
    else:
        if not a.note:
            print("a rejection needs --note")
            return 2
        log(root, "review_finding", a.role, a.note, "rule:review")
        run["reviews"].pop(a.role, None)
        print(f"{a.role} rejected: fix in one pass, then re-review (sized to the change)")
    touch(root, run)
    return 0


def v_amend(a):
    root, run = need_run(a)
    if not run:
        return 2
    plan = rg.load(os.path.join(root, run["plan"]))
    tid = rg.sid(a.task)
    acc = tasks_by_id(plan)[tid][1].get("acceptance") or []
    if not (a.reason and a.evidence and a.authority == "user" and 0 <= a.index < len(acc)):
        print("amend needs --index (valid), --text, --reason, --evidence and --authority user (only the user changes an acceptance criterion)")
        return 2
    run["tasks"][tid]["sig_run"] = 0  # the user changed the task, so a repeated-failure stop no longer applies
    run["amendments"].append({"task": tid, "index": a.index, "original": acc[a.index], "amended": a.text,
                              "reason": a.reason, "evidence": a.evidence, "authority": a.authority, "ts": rg.now()})
    log(root, "deviation", f"amend {tid}[{a.index}]", a.reason, a.authority)
    touch(root, run)
    print("amendment recorded; original kept verbatim")
    return 0


def v_followup(a):
    root, run = need_run(a)
    if not run:
        return 2
    if a.settle is not None:
        if not (0 <= a.settle < len(run["followups"])) or a.status == "open":
            print("--settle needs a valid follow-up index and --status done|reported")
            return 2
        run["followups"][a.settle]["status"] = a.status
        run["followups"][a.settle]["reason"] = a.reason or run["followups"][a.settle].get("reason", "")
        log(root, "note", "followup settled", f"#{a.settle} {a.status}", "system")
        touch(root, run)
        print(f"followup {a.settle} is now {a.status}")
        return 0
    if not a.text:
        print("a follow-up needs text (or --settle N)")
        return 2
    run["followups"].append({"text": a.text, "files": list(a.file or []), "status": a.status, "reason": a.reason or ""})
    log(root, "note", "followup", a.text, "system")
    touch(root, run)
    print("followup recorded")
    return 0


def v_noticed(a):
    root, run = need_run(a)
    if not run:
        return 2
    run["noticed"].append({"text": a.text, "ts": rg.now()})
    log(root, "note", "noticed", a.text, "system")
    touch(root, run)
    print("noticed item recorded; not edited")
    return 0


def v_discard(a):
    root = os.path.abspath(a.root)
    run = load_run(root)
    if not run:
        print("no run")
        return 0
    if not a.reason:
        print("a reason is required")
        return 2
    dest = run_path(root).replace("run.yaml", f"run.discarded.{rg.now().replace(':', '')}.yaml")
    os.replace(run_path(root), dest)
    log(root, "deviation", "exec discard", a.reason, "user")
    # free the worktree path so a fresh start works; the committed work is kept on a renamed branch
    kept = f"{run['branch']}-discarded-{rg.now().replace(':', '').replace('-', '')}"
    git(root, "worktree", "remove", "--force", run["worktree"])
    rc, _ = git(root, "branch", "-m", run["branch"], kept)
    print("run archived to", os.path.relpath(dest, root), "- worktree removed;", ("commits kept on branch " + kept) if rc == 0 else "branch " + run["branch"] + " left as it was")
    return 0


def deliver(root, run, plan):
    mode, wt, br, base = run["delivery"], run["worktree"], run["branch"], run["base_branch"]
    if mode == "branch":
        print("delivery: branch only. Nothing was pushed.")
        return True
    repo = rg.origin_repo(root)
    if not repo:
        print("delivery stopped: origin is not a GitHub remote")
        return False
    rc, out = rg.run_cmd(["git", "-C", wt, "push", "-u", "origin", br], timeout=DELIVERY_TIMEOUT)
    log(root, "tool_run", "deliver push", f"rc={rc} {out[-rg.lim('execution.engine.output_tail'):]}", "user")
    print(f"deliver push: rc={rc}")
    if rc != 0:
        print(out[-rg.lim("execution.engine.output_tail"):])
        print("delivery stopped; fix and run exec finish again")
        return False
    title = f"{run['slug']}: {len(run['tasks'])} planned task(s)"
    body = "Executed from plan " + run["plan"] + "\n\n" + "\n".join(f"- {t}: {v['status']}" for t, v in run["tasks"].items())
    # reuse an open PR for this branch so a retry after a failed merge does not fail on create
    steps_log = []
    rc, prs = rg.gh_json("GET", f"repos/{repo}/pulls?state=open&head={repo.split('/')[0]}:{br}", None, False, steps_log)
    pr = prs[0] if rc == 0 and isinstance(prs, list) and prs else None
    if pr is None:
        rc, pr = rg.gh_json("POST", f"repos/{repo}/pulls", {"title": title, "head": br, "base": base, "body": body}, False, steps_log)
    log(root, "tool_run", "deliver pr create", f"rc={rc} number={(pr or {}).get('number')}", "user")
    print(f"deliver pr create: rc={rc} #{(pr or {}).get('number')}")
    if rc != 0 or not (pr or {}).get("number"):
        print("delivery stopped; fix and run exec finish again")
        return False
    rc, res = rg.gh_json("PUT", f"repos/{repo}/pulls/{pr['number']}/merge", {"merge_method": "squash"}, False, steps_log)
    log(root, "tool_run", "deliver pr merge", f"rc={rc} merged={(res or {}).get('merged')}", "user")
    print(f"deliver pr merge: rc={rc} merged={(res or {}).get('merged')}")
    if rc != 0 or not (res or {}).get("merged"):
        print((res or {}).get("message", ""))
        print("delivery stopped; fix and run exec finish again")
        return False
    if True:
        git(root, "worktree", "remove", "--force", wt)
        git(root, "branch", "-D", br)
        rc, _ = rg.gh_json("DELETE", f"repos/{repo}/git/refs/heads/{br}", None, False, [])
        log(root, "tool_run", "deliver delete branches", f"remote rc={rc}", "user")
        print("local branch deleted; remote branch", "deleted" if rc == 0 else "not deleted (delete it on GitHub)")
        print(f"merged into {base} by squash. Update your main checkout with: git pull")
    return True


def evaluate(root, final):
    run = load_run(root)
    if not run:
        return None, None
    c = ctx_for(root, run)
    c.final = final
    gates = rg.load(os.path.join(XREF, "exec-gates.yaml"))["gates"]
    lint = {r["id"]: r for r in rg.load(os.path.join(XREF, "exec-lint-rules.yaml"))["rules"]}
    res = {}
    for g in gates:
        msgs, bad, pend = [], 0, False
        for rid in g["rules"]:
            if rid in XRULES:
                if lint[rid].get("final_only") and not final:
                    pend = True
                    continue
                out = XRULES[rid](c)
            else:
                out = rg.RULES[rid](c)
            for sev, m in out:
                msgs.append(f"{sev.upper()} {rid}: {m}")
                bad += sev == "error"
        res[g["id"]] = ("failed" if bad else "pending" if pend else "passed", msgs)
    return res, c


def v_check(a):
    root = os.path.abspath(a.root)
    res, c = evaluate(root, a.final)
    if res is None:
        print("no run")
        return 2
    for gid, (s, msgs) in res.items():
        print(f"{s.upper():8} {gid}")
        for m in msgs:
            print("           " + m)
    bad = [g for g, (s, _) in res.items() if s == "failed"]
    notpassed = [g for g, (s, _) in res.items() if s != "passed"]
    run = c.run
    done = sum(1 for v in run["tasks"].values() if v["status"] == "done")
    print(f"tasks: {done}/{len(run['tasks'])} done, {sum(1 for v in run['tasks'].values() if v['status'] == 'blocked')} blocked")
    if a.final and notpassed:
        print("FINAL CHECK FAILED:", ", ".join(notpassed))
        return 1
    return 1 if bad else 0


def v_finish(a):
    root = os.path.abspath(a.root)
    run = load_run(root)
    if not run:
        print("no run")
        return 2
    plan = rg.load(os.path.join(root, run["plan"]))
    if run.get("finished"):
        if run["delivery"] != "branch" and not run.get("delivered"):
            print("run finished; retrying delivery")
            ok = deliver(root, run, plan)
            run["delivered"] = ok
            save_run(root, run)
            return 0 if ok else 1
        print("already finished")
        return 0
    res, c = evaluate(root, True)
    notpassed = [g for g, (s, _) in res.items() if s != "passed"]
    if notpassed:
        print("REFUSED: gates not passed:", ", ".join(notpassed), "(run exec check --final)")
        return 1
    lvl, dm = rg.drift(root)
    if lvl in ("ask", "block"):
        print(f"REFUSED: published issues were changed outside the plan ({lvl}):")
        for m_ in dm:
            print("  ", m_)
        print("record the user's decision with: railguard log \"<why>\" --kind decision --subject drift_accepted --authority user")
        return 1
    run["finished"] = True
    run["finished_at"] = rg.now()
    save_run(root, run)
    log(root, "note", "exec finish", f"branch {run['branch']} at {head(run['worktree'])[:10]}", "system")
    print(f"finished. branch {run['branch']} (worktree {run['worktree']})")
    rul = [e for e in c.ledger if e.get("kind") == "decision" and str(e.get("reason", "")).startswith("Ruling")]
    print(f"rulings: {len(rul)}; noticed: {len(run['noticed'])}; followups: {len(run['followups'])}")
    for r_ in rul:
        print("  ruling:", r_["reason"])
    for n in run["noticed"]:
        print("  noticed:", n["text"])
    for f in run["followups"]:
        print(f"  followup [{f['status']}]:", f["text"])
    if a.remove_worktree and run["delivery"] == "branch":
        rc, out = git(root, "worktree", "remove", "--force", run["worktree"])
        print("worktree removed" if rc == 0 else "worktree not removed: " + out)
    ok = deliver(root, run, plan)
    run["delivered"] = ok
    save_run(root, run)
    return 0 if ok else 1


# ------------------------------------------------------------------ rules
@xrule("X_start")
def x_start(c):
    out = []
    if (c.plan.get("meta") or {}).get("status") != "final":
        out.append(E("plan is not final"))
    if c.state.get("execute_authorized") is not True:
        out.append(E("execution not authorized"))
    if not c.run.get("start_ok"):
        out.append(E("run did not pass the start conditions"))
    return out


@xrule("X_feedback")
def x_feedback(c):
    out = []
    if not c.run.get("feedback"):
        out.append(E("no feedback commands recorded"))
    if c.run.get("baseline") is None:
        out.append(E("no feedback baseline recorded: exec verify --baseline"))
    return out


@xrule("X_run_state")
def x_run_state(c):
    return [] if c.run else [E("no run")]


@xrule("X_worktree")
def x_worktree(c):
    wt, br = c.run["worktree"], c.run["branch"]
    if not os.path.isdir(wt):
        return [E("worktree missing")]
    if os.path.abspath(wt) == os.path.abspath(c.root):
        return [E("worktree is the main checkout")]
    rc, out = git(wt, "rev-parse", "--abbrev-ref", "HEAD")
    return [] if out.strip() == br else [E(f"worktree is on {out.strip()!r}, not {br}")]


@xrule("X_main_untouched")
def x_main(c):
    old, new = c.run.get("root_snapshot") or {}, rg.snapshot(c.root)
    if old.get("kind") == "git":
        if (old.get("porcelain"), old.get("diff_sha"), old.get("head")) != (new.get("porcelain"), new.get("diff_sha"), new.get("head")):
            return [E("the main checkout changed since exec start")]
    elif old.get("files_sha") != new.get("files_sha"):
        return [E("the main checkout changed since exec start")]
    return []


@xrule("X_tasks_done")
def x_tasks_done(c):
    return [E(f"task {t} is {v['status']}") for t, v in c.run["tasks"].items() if v["status"] not in ("done", "blocked")]


@xrule("X_blocked")
def x_blocked(c):
    out, tb = [], tasks_by_id(c.plan)
    for t, v in c.run["tasks"].items():
        if v["status"] == "blocked" and not v.get("reason"):
            out.append(E(f"task {t} blocked without a reason"))
        if v["status"] == "done":
            for d in tb[t][1].get("depends") or []:
                if c.run["tasks"].get(rg.sid(d), {}).get("status") == "blocked":
                    out.append(E(f"task {t} done but its dependency {d} is blocked"))
    return out


@xrule("X_order")
def x_order(c):
    out, tb = [], tasks_by_id(c.plan)
    for t, v in c.run["tasks"].items():
        if v["status"] == "done":
            for d in tb[t][1].get("depends") or []:
                dv = c.run["tasks"].get(rg.sid(d), {})
                if dv.get("status") != "done" or dv.get("done_seq", 0) > v.get("done_seq", 0):
                    out.append(E(f"task {t} finished before its dependency {d}"))
    return out


@xrule("X_evidence")
def x_evidence(c):
    out = []
    tdd = (c.plan.get("evidence_path") or {}).get("test_strategy") == "tdd"
    for t, v in c.run["tasks"].items():
        if v["status"] != "done":
            continue
        vt = v.get("vtask") or {}
        if not vt.get("ok"):
            out.append(E(f"task {t} done without a passing verify"))
        elif tree_of(c.wt, v["commit"]) != vt.get("tree"):
            out.append(E(f"task {t}: verify evidence does not match the committed content"))
        if tdd and (not v.get("red") or v["red"]["seq"] > vt.get("seq", 0)):
            out.append(E(f"task {t}: no failing test recorded before the green verify"))
    return out


@xrule("X_attempts")
def x_attempts(c):
    return [E(f"task {t} reached {v['attempts']} attempts and is still {v['status']}") for t, v in c.run["tasks"].items()
            if v["attempts"] >= CAP and v["status"] in ("failed", "started")]


def _changed_files(c):
    seen = []
    for wt in open_wts(c.run):
        stage(wt)
        rc, out = git(wt, "diff", "--cached", "--name-only", c.run["base"])
        seen += [l for l in out.splitlines() if l and not l.startswith(".rigor/") and l not in seen]
    return seen


@xrule("X_scope")
def x_scope(c):
    allowed = planned_files(c.plan)  # follow-up files are informational and never widen scope
    return [E(f"file changed outside the plan: {f}") for f in _changed_files(c) if f not in allowed]


def _added(c):
    lines, seen = [], set()
    for wt in open_wts(c.run):
        stage(wt)
        rc, out = git(wt, "diff", "--cached", "-U0", c.run["base"])
        cur = ""
        for l in out.splitlines():
            if l.startswith("+++ "):
                cur = l[6:]
            elif l.startswith("+") and not l.startswith("+++") and (cur, l) not in seen:
                seen.add((cur, l))
                lines.append((cur, l[1:]))
    return lines


PLACE = re.compile(r"(\btest\.skip\b|\bit\.skip\b|\bxit\(|\bxdescribe\(|pytest\.mark\.skip|unittest\.skip|\bTODO\b|\bFIXME\b|NotImplemented)")
DEBUG = re.compile(r"(console\.log\(|\bdebugger\b|\bpdb\.set_trace|\bbreakpoint\(\)|import pdb)")


@xrule("X_placeholders")
def x_place(c):
    return [E(f"{f}: placeholder or skip marker: {l.strip()[:80]}") for f, l in _added(c) if PLACE.search(l)]


@xrule("X_debug_output")
def x_debug(c):
    return [W(f"{f}: debug output: {l.strip()[:80]}") for f, l in _added(c) if DEBUG.search(l)]


@xrule("X_deviation")
def x_dev(c):
    cur = rg.plan_hash(c.plan)
    if cur == c.run["plan_hash"]:
        return []
    ok = any(e.get("kind") == "plan_change" and e.get("after") == cur and e.get("reason") and rg.AUTH_RE.match(str(e.get("authority"))) for e in c.ledger)
    return [] if ok else [E("the plan changed during the run without a logged plan_change")]


@xrule("X_checkpoints")
def x_cps(c):
    out, od = [], order(c.plan)
    for ph in c.plan.get("phases") or []:
        for cp in ph.get("checkpoints") or []:
            cid, at = rg.sid(cp["id"]), rg.sid(cp.get("after_task"))
            rec = c.run["checkpoints"].get(cid) or {}
            if c.run["tasks"].get(at, {}).get("status") == "done" and not rec.get("passed"):
                out.append(E(f"checkpoint {cid} has not passed"))
            if rec.get("passed"):
                for t in od[od.index(at) + 1:] if at in od else []:
                    v = c.run["tasks"][t]
                    if v["status"] == "done" and v.get("done_seq", 0) < rec.get("seq", 0):
                        out.append(E(f"task {t} finished before checkpoint {cid} passed"))
            elif at in od:
                for t in od[od.index(at) + 1:]:
                    if c.run["tasks"][t]["status"] == "done":
                        out.append(E(f"task {t} finished while checkpoint {cid} had not passed"))
    return out


@xrule("X_verifiers")
def x_verifiers(c):
    """A phase-end checkpoint needs a fresh verifier pass before the next phase starts and before finish."""
    out, od, ends = [], order(c.plan), phase_end_checkpoints(c.plan)
    for cid, ph in ends.items():
        cp = next(x for x in ph["checkpoints"] if rg.sid(x["id"]) == cid)
        at = rg.sid(cp.get("after_task"))
        rec = c.run["checkpoints"].get(cid) or {}
        if not rec.get("passed"):
            continue
        ok = verified(c.run, cid)
        later = [t for t in od[od.index(at) + 1:] if phase_of(c.plan, t) != rg.sid(ph.get("id")) and c.run["tasks"][t]["status"] == "done"] if at in od else []
        if later and not ok:
            out.append(E(f"phase-end checkpoint {cid}: later tasks finished without a fresh verifier pass"))
        elif c.final and not ok:
            out.append(E(f"phase-end checkpoint {cid} has no fresh verifier pass at its content"))
    return out


@xrule("X_verifier_branch")
def x_vbranch(c):
    v = (c.run.get("verifiers") or {}).get("branch") or {}
    if v.get("verdict") != "pass" or v.get("tree") != stage(c.wt):
        return [E("no fresh verifier pass on the whole branch at the current content (exec verifier branch pass --agent NAME)")]
    return []


@xrule("X_queue")
def x_queue(c):
    return [E(f"question {q['id']} is unanswered: {q['text']}") for q in c.run.get("queue", []) if not q.get("answer")]


@xrule("X_clean_tree")
def x_clean(c):
    out = []
    for wt in open_wts(c.run):
        d = dirty_paths(wt)
        if d:
            out.append(E(f"worktree has uncommitted changes that would not be delivered: {', '.join(d[:5])}"))
    return out


@xrule("X_regression")
def x_reg(c):
    lv = c.run.get("last_verify")
    if not lv:
        return [E("no feedback verify recorded: exec verify")]
    out = []
    if lv["tree"] != stage(c.wt):
        out.append(E("the last feedback verify is older than the current content"))
    out += [E(f"new failure: {i}") for i in lv["new"]]
    return out


def _change_frac(c, old_head):
    rc, out = git(c.wt, "diff", "--shortstat", old_head, "HEAD")
    nums = [int(x) for x in re.findall(r"(\d+) (?:insertion|deletion)", out)]
    rc2, out2 = git(c.wt, "diff", "--shortstat", c.run["base"], "HEAD")
    tot = max(sum(int(x) for x in re.findall(r"(\d+) (?:insertion|deletion)", out2)), 1)
    return sum(nums) / tot


@xrule("X_review")
def x_review(c):
    roles = rg.required_reviewers(c.plan, c.routing)
    h, out = head(c.wt), []
    th = {"lint_only": rg.lim("execution.review.re_review.diff_only"), "targeted": rg.lim("execution.review.re_review.touched_files")}
    for r in roles:
        rec = c.run["reviews"].get(r)
        if not rec:
            out.append(E(f"{r} has not approved"))
            continue
        if rec.get("accepted_best"):
            out.append(W(f"{r}: best version accepted by the user without consensus: {rec.get('note')}"))
        if rec["head"] == h:
            continue
        f = _change_frac(c, rec["head"])
        if f <= th["lint_only"]:
            continue
        if f <= th["targeted"] and r != "critic":
            continue
        out.append(E(f"{r} approved {rec['head'][:8]}; {f:.0%} of the branch changed since, re-review needed"))
    return out


@xrule("X_review_rounds")
def x_rounds(c):
    return [E(f"{r_}: {n} review rounds used and not approved; the user must accept the best version (exec review {r_} approve --accept-best)")
            for r_, n in c.run.get("review_rounds", {}).items() if n >= MAX_ROUNDS and r_ not in c.run["reviews"]]


@xrule("X_final_verification")
def x_fv(c):
    cur = stage(c.wt)
    out = []
    for fv in c.plan.get("final_verification") or []:
        rec = c.run["final"].get(rg.sid(fv["id"]))
        if not rec or not rec["ok"] or rec["tree"] != cur:
            out.append(E(f"final verification {fv['id']} has not passed at the current content"))
    return out


@xrule("X_claims")
def x_claims(c):
    out = []
    for cl in (c.plan.get("evidence_path") or {}).get("claims") or []:
        rec = c.run["claims"].get(rg.sid(cl["id"]))
        if not rec:
            out.append(E(f"claim {cl['id']} not closed"))
        elif rec["status"] == "refuted":
            out.append(E(f"claim {cl['id']} is refuted"))
    return out


@xrule("X_followups")
def x_follow(c):
    return [E(f"follow-up still open: {f['text'][:60]}") for f in c.run["followups"] if f["status"] == "open"]


@xrule("X_amendments")
def x_amend(c):
    out = []
    for am in c.run["amendments"]:
        for k in ("original", "amended", "reason", "evidence", "authority", "ts"):
            if not am.get(k):
                out.append(E(f"amendment on {am.get('task')} missing {k}"))
    return out


# ------------------------------------------------------------------ pack check and CLI
def check_exec_pack():
    errs = []
    if not os.path.isdir(XREF):
        return ["execute-rigorously/references not found"]
    gates = rg.load(os.path.join(XREF, "exec-gates.yaml"))["gates"]
    lint = rg.load(os.path.join(XREF, "exec-lint-rules.yaml"))["rules"]
    ids = {r["id"] for r in lint}
    for r in ids - set(XRULES):
        errs.append(f"exec rule {r} has no implementation")
    for r in set(XRULES) - ids:
        errs.append(f"exec rule {r} implemented but not in exec-lint-rules.yaml")
    gids = {g["id"] for g in gates}
    cov = set()
    for g in gates:
        for r in g["rules"]:
            cov.add(r)
            if r not in ids and r not in rg.RULES:
                errs.append(f"exec gate {g['id']} references unknown rule {r}")
    for r in lint:
        if r["gate"] not in gids:
            errs.append(f"exec rule {r['id']} references unknown gate {r['gate']}")
    for r in ids - cov:
        errs.append(f"exec rule {r} is not attached to any gate")
    ex = rg.load(os.path.join(XREF, "execute.yaml"))
    for st in ex.get("stages") or []:
        for g in st.get("gates") or []:
            if g not in gids:
                errs.append(f"exec stage {st['id']} references unknown gate {g}")
    mp = os.path.join(XREF, "exec-merge-ledger.yaml")
    if os.path.exists(mp):
        ml = rg.load(mp)
        rid = [r["id"] for r in ml["rows"]]
        if len(rid) != len(set(rid)):
            errs.append("duplicate ids in exec-merge-ledger")
        cids = {c["id"] for c in ml.get("conflicts") or []}
        for r in ml["rows"]:
            d = r.get("disp")
            if r.get("src") not in set(ml["sources"]):
                errs.append(f"{r['id']}: unknown source {r.get('src')}")
            if d not in ("enforced", "merged", "skipped", "deferred"):
                errs.append(f"{r['id']}: bad disposition {d}")
                continue
            if d == "enforced":
                if r.get("by") not in ("script", "contract", "detective") or not r.get("ref"):
                    errs.append(f"{r['id']}: enforced needs by and ref")
                elif r["by"] == "script" and r["ref"] not in ids | set(rg.RULES) | gids:
                    errs.append(f"{r['id']}: unknown script ref {r['ref']}")
            if d == "merged" and not r.get("into"):
                errs.append(f"{r['id']}: merged needs into")
            if d in ("skipped", "deferred") and not r.get("reason"):
                errs.append(f"{r['id']}: {d} needs reason")
            if str(r.get("rel", "")).startswith("c:") and r["rel"][2:] not in cids:
                errs.append(f"{r['id']}: unknown conflict {r['rel']}")
        for cf in ml.get("conflicts") or []:
            for x in cf.get("rows") or []:
                if x not in rid:
                    errs.append(f"conflict {cf['id']} references unknown row {x}")
            if not cf.get("resolution"):
                errs.append(f"conflict {cf['id']} has no resolution")
            if cf.get("decided_by") != "user" or not cf.get("decision"):
                errs.append(f"conflict {cf['id']} was not decided by the user")
    else:
        errs.append("exec-merge-ledger.yaml missing")
    return errs


def add_parser(sub):
    s = sub.add_parser("exec", help="execution verbs")
    es = s.add_subparsers(dest="xverb", required=True)
    p = es.add_parser("start"); p.add_argument("plan"); p.add_argument("--feedback", action="append"); p.add_argument("--delivery"); p.add_argument("--away", action="store_true"); p.add_argument("--allow-dirty", action="store_true"); p.add_argument("--topology", choices=["inline", "subagent"])
    p = es.add_parser("verify"); p.add_argument("--baseline", action="store_true")
    es.add_parser("next")
    p = es.add_parser("task"); p.add_argument("id"); p.add_argument("--status", required=True, choices=["started", "done", "failed", "blocked"]); p.add_argument("--signature"); p.add_argument("--output"); p.add_argument("--harness", action="store_true"); p.add_argument("--reason"); p.add_argument("--agent"); p.add_argument("--report")
    p = es.add_parser("red"); p.add_argument("id"); p.add_argument("--cmd", required=True); p.add_argument("--expect-exit", type=int)
    p = es.add_parser("vtask"); p.add_argument("id")
    p = es.add_parser("checkpoint"); p.add_argument("id")
    p = es.add_parser("verifier"); p.add_argument("scope"); p.add_argument("verdict", choices=["pass", "fail"]); p.add_argument("--agent", required=True); p.add_argument("--note")
    p = es.add_parser("answer"); p.add_argument("id"); p.add_argument("--text", required=True); p.add_argument("--unblock", action="store_true")
    es.add_parser("todo")
    p = es.add_parser("final"); p.add_argument("id")
    p = es.add_parser("claim"); p.add_argument("id"); p.add_argument("--status"); p.add_argument("--note")
    p = es.add_parser("review"); p.add_argument("role"); p.add_argument("verdict", choices=["approve", "reject"]); p.add_argument("--note"); p.add_argument("--accept-best", action="store_true")
    p = es.add_parser("amend"); p.add_argument("task"); p.add_argument("--index", type=int, required=True); p.add_argument("--text", required=True); p.add_argument("--reason"); p.add_argument("--evidence"); p.add_argument("--authority", required=True)
    p = es.add_parser("followup"); p.add_argument("text", nargs="?"); p.add_argument("--settle", type=int); p.add_argument("--file", action="append"); p.add_argument("--status", default="open", choices=["open", "done", "reported"]); p.add_argument("--reason")
    p = es.add_parser("noticed"); p.add_argument("text")
    p = es.add_parser("discard"); p.add_argument("--reason")
    p = es.add_parser("check"); p.add_argument("--final", action="store_true")
    p = es.add_parser("finish"); p.add_argument("--remove-worktree", action="store_true")


def run(a):
    fn = {"start": v_start, "verify": v_verify, "next": v_next, "task": v_task, "red": v_red, "vtask": v_vtask,
          "checkpoint": v_checkpoint, "todo": v_todo, "verifier": v_verifier, "answer": v_answer, "final": v_final, "claim": v_claim, "review": v_review, "amend": v_amend,
          "followup": v_followup, "noticed": v_noticed, "discard": v_discard, "check": v_check, "finish": v_finish}[a.xverb]
    return fn(a)
