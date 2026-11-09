"""rigor_clarify - the automatic clarify stage of plan-rigorously.

Run by the agent, never typed by the user. When the fog test fails (the destination cannot be stated in one sentence,
or the first three decisions cannot be stated precisely) planning works a list of decision questions with the user,
in rounds, before it plans. State lives in .rigor/clarify/clarify.yaml; every answer is a ledger event.
Python 3 standard library only.
"""
import os, re, shutil
import railguard as rg
import rigor_exec as rx


def cdir(root):
    return os.path.join(rg.rig(root), "clarify")


def load_c(root):
    p = rg.clarify_file(root)
    return rg.load(p) if os.path.exists(p) else None


def save_c(root, d):
    os.makedirs(cdir(root), exist_ok=True)
    d["heartbeat"] = rg.now()
    rg.save(rg.clarify_file(root), d)


def need(a, allowed=("charting", "open")):
    root = os.path.abspath(a.root)
    d = load_c(root)
    if not d:
        print("REFUSED: no clarify run. It starts only when the fog test fails: clarify init")
        return root, None
    if d["status"] not in allowed:
        print(f"REFUSED: clarify is {d['status']}")
        return root, None
    return root, d


def v_init(a):
    root = os.path.abspath(a.root)
    one, three = a.destination_one_sentence == "yes", a.first_three == "yes"
    rg.ledger_add(root, "note", "clarify_fog_test", f"destination_one_sentence={one}, first_three_decisions={three}", "system")
    if one and three:
        print("fog test passed: no clarifying needed; plan directly")
        return 0
    d = load_c(root)
    if d:
        age = rx.ts_age_minutes(d.get("heartbeat"))
        if d["status"] in ("charting", "open") and age < rg.lim("planning.clarify.heartbeat_stale"):
            print(f"REFUSED: a clarify run is live (heartbeat {age:.0f} min ago)")
            return 2
        print(f"resuming the existing clarify run (status {d['status']})")
        save_c(root, d)
        return 0
    d = {"version": 1, "status": "charting", "idea": a.idea, "destination": {"text": "", "candidates": []},
         "tickets": [], "not_yet_specified": [], "out_of_scope": [], "brief": {}}
    save_c(root, d)
    print("fog test failed: clarify started. Next: clarify destination --text ...")
    return 0


def v_destination(a):
    root, d = need(a, ("charting",))
    if not d:
        return 2
    if a.text:
        d["destination"]["text"] = a.text
    for cnd in a.candidate or []:
        d["destination"]["candidates"].append(cnd)
    save_c(root, d)
    print("destination:", d["destination"]["text"] or "(not stated yet)")
    print("next: ask the user to confirm it; record --kind answer --subject clarify_destination_signed --authority user")
    return 0


def v_reopen(a):
    """Resume a parked or closed clarify effort. Only the user can decide to; it needs an explicit yes."""
    root, d = need(a, ("parked", "closed"))
    if not d:
        return 2
    ok = any(e.get("kind") == "decision" and e.get("subject") == "clarify_reopened" and e.get("authority") == "user"
             and rg.explicit_answer(e.get("reason")) == "yes" for e in rg.load_ledger(root))
    if not ok:
        print("REFUSED: reopening is the user's decision: log --kind decision --subject clarify_reopened --authority user --reason \"yes ...\"")
        return 2
    d["status"] = "open" if d.get("tickets") else "charting"
    save_c(root, d)
    print("clarify reopened:", d["status"])
    return 0


def v_park(a):
    root, d = need(a)
    if not d:
        return 2
    ok = any(e.get("kind") == "decision" and e.get("subject") == "clarify_parked" and e.get("authority") == "user" for e in rg.load_ledger(root))
    if not ok:
        print("REFUSED: parking is the user's decision: log --kind decision --subject clarify_parked --authority user --reason ...")
        return 2
    d["status"] = "parked"
    save_c(root, d)
    print("clarify parked")
    return 0


def v_add(a):
    root, d = need(a)
    if not d:
        return 2
    if not rg._signed(rg.load_ledger(root), "clarify_destination_signed"):
        print("REFUSED: the destination has no explicit user yes (clarify_destination_signed)")
        return 2
    if a.type not in rg.CLARIFY_TYPES:
        print("type must be research or grilling")
        return 2
    ids = [rg.sid(t["id"]) for t in d["tickets"]]
    if a.id in ids:
        print("REFUSED: duplicate id", a.id)
        return 2
    for b in a.blocked_on or []:
        if b not in ids:
            print("REFUSED: blocked_on unknown ticket", b)
            return 2
    if d["status"] == "open":
        print("note: adding to an open map")
    d["tickets"].append({"id": a.id, "title": a.title, "type": a.type, "question": a.question, "blocked_on": list(a.blocked_on or []),
                         "thread": a.thread or "", "status": "open"})
    save_c(root, d)
    print(f"added {a.id}")
    return 0


def v_fog(a):
    root, d = need(a)
    if not d:
        return 2
    if a.add:
        d["not_yet_specified"].append(a.add)
    if a.clear is not None:
        if not 0 <= a.clear < len(d["not_yet_specified"]):
            print("no such item")
            return 2
        d["not_yet_specified"].pop(a.clear)
    save_c(root, d)
    print("not yet specified:", len(d["not_yet_specified"]))
    return 0


def v_oos(a):
    root, d = need(a)
    if not d:
        return 2
    d["out_of_scope"].append(a.add)
    save_c(root, d)
    return 0


def v_open(a):
    root, d = need(a, ("charting",))
    if not d:
        return 2
    if not rg._signed(rg.load_ledger(root), "clarify_chart_signed"):
        print("REFUSED: the chart has no explicit user yes (clarify_chart_signed)")
        return 2
    if not d["tickets"]:
        print("REFUSED: no tickets")
        return 2
    d["status"] = "open"
    save_c(root, d)
    print("clarify open")
    return 0


def v_resolve(a):
    root, d = need(a, ("open",))
    if not d:
        return 2
    t = next((x for x in d["tickets"] if rg.sid(x["id"]) == a.id), None)
    if not t:
        print("unknown ticket", a.id)
        return 2
    if t["status"] == "closed":
        print("already closed")
        return 0
    by = {rg.sid(x["id"]): x for x in d["tickets"]}
    if any(by[rg.sid(b)]["status"] != "closed" for b in t.get("blocked_on") or []):
        print("REFUSED: a ticket it is blocked on is still open")
        return 2
    rec = {"gist": a.gist}
    if t["type"] == "grilling":
        if not any(e.get("kind") == "answer" and e.get("subject") == a.id and e.get("authority") == "user" for e in rg.load_ledger(root)):
            print(f"REFUSED: record the user's answer first: log --kind answer --subject {a.id} --authority user")
            return 2
    else:
        if not (a.restated and a.source and a.unverified):
            print("REFUSED: a research record needs --restated, at least one --source, and --unverified (say 'none' if everything was confirmed)")
            return 2
        rec.update({"restated": a.restated, "sources": list(a.source), "unverified": list(a.unverified)})
    t["status"], t["resolution"] = "closed", rec
    save_c(root, d)
    rg.ledger_add(root, "note", f"clarify_resolved:{a.id}", a.gist, "system")
    print(f"{a.id} closed: {a.gist}")
    return 0


def frontier(d):
    by = {rg.sid(x["id"]): x for x in d["tickets"]}
    return [t for t in d["tickets"] if t["status"] == "open" and all(by[rg.sid(b)]["status"] == "closed" for b in t.get("blocked_on") or [])]


def status_line(d):
    threads = {}
    for t in d["tickets"]:
        if t["status"] == "open":
            threads[t.get("thread") or "main"] = threads.get(t.get("thread") or "main", 0) + 1
    parts = ", ".join(f"{k}: {v} open" for k, v in sorted(threads.items())) or "nothing open"
    return f"{parts}; frontier: {', '.join(t['title'] for t in frontier(d)) or 'none'}"


def v_status(a):
    root, d = need(a, ("charting", "open", "closed", "parked"))
    if not d:
        return 2
    print(f"status {d['status']}; {status_line(d)}")
    print("frontier (ask these together in the next round):")
    for t in frontier(d):
        print(f"  {t['id']} [{t['type']}] {t['title']}: {t['question']}")
    for t in d["tickets"]:
        if t["status"] == "closed":
            print(f"  decided: {t['title']}: {t['resolution']['gist']}")
    for i, x in enumerate(d["not_yet_specified"]):
        print(f"  not yet specified [{i}]: {x}")
    for x in d["out_of_scope"]:
        print("  out of scope:", x)
    save_c(root, d)
    return 0


def spec_file(root):
    for name in ("spec.yaml",):
        p = os.path.join(rg.rig(root), "plans", name)
        if os.path.exists(p):
            return p
    return None


def v_close(a):
    root, d = need(a, ("open",))
    if not d:
        return 2
    if any(t["status"] != "closed" for t in d["tickets"]) or d["not_yet_specified"]:
        print("REFUSED: open tickets or unspecified items remain")
        return 2
    brief = {"outcome": a.outcome, "user": a.user, "why_now": a.why_now, "success": a.success, "constraint": a.constraint, "out_of_scope": a.out_of_scope}
    if not all(str(v).strip() for v in brief.values()):
        print("REFUSED: every brief field is required")
        return 2
    d["brief"], d["status"] = brief, "closed"
    save_c(root, d)
    sp = spec_file(root)
    if sp:
        spec = rg.load(sp)
        spec["intent"] = brief
        rg.save(sp, spec)
        print("spec intent seeded; the user must now confirm it (intent_confirmed)")
    rg.ledger_add(root, "note", "clarify_closed", "; ".join(f"{k}={v}" for k, v in brief.items()), "system")
    return 0


def repo_of(root):
    rc, url = rg.run_cmd(["git", "-C", root, "config", "--get", "remote.origin.url"])
    m = re.search(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?$", url or "")
    return f"{m.group(1)}/{m.group(2)}" if rc == 0 and m else None


def v_mirror(a):
    root, d = need(a, ("open", "closed"))
    if not d:
        return 2
    repo = repo_of(root)
    if not repo:
        print("no GitHub remote: nothing to mirror (the local clarify file is the record)")
        return 0
    dry = not a.yes
    mp = os.path.join(cdir(root), "mirror.yaml")
    m = rg.load(mp) if os.path.exists(mp) else {"repo": repo, "issues": {}}
    if not dry:
        lvl, dm = rg.drift(root)
        if lvl in ("ask", "block"):
            print(f"REFUSED: mirrored issues were changed outside the plan ({lvl}); mirroring now would overwrite them:")
            for x in dm:
                print("  ", x)
            print("record the user's decision with: railguard log \"<why>\" --kind decision --subject drift_accepted --authority user")
            return 1
    log, tmp = [], os.path.join(rg.rig(root), "tmp")
    os.makedirs(tmp, exist_ok=True)
    for t in d["tickets"]:
        i = rg.sid(t["id"])
        body = f"{t['question']}\n\nBlocked on: {', '.join(t.get('blocked_on') or []) or 'nothing'}\nType: {t['type']}\n"
        if t["status"] == "closed":
            r = t["resolution"]
            body += f"\nDecision: {r['gist']}\n"
            if r.get("sources"):
                body += "Sources:\n" + "\n".join(f"- {x}" for x in r["sources"]) + "\nUnverified:\n" + "\n".join(f"- {x}" for x in r["unverified"]) + "\n"
        bf = os.path.join(tmp, f"clarify-{i}.md")
        open(bf, "w", encoding="utf-8").write(body)
        labels = [f"clarify:{t['type']}"] + ([f"clarify:thread:{t['thread']}"] if t.get("thread") else [])
        for lb in labels:
            rg.gh_json("POST", f"repos/{repo}/labels", {"name": lb}, dry, log)
        ex = m["issues"].get(i)
        if ex:
            rg.gh_json("PATCH", f"repos/{repo}/issues/{ex['number']}", {"body": body}, dry, log)
            if t["status"] == "closed":
                rg.gh_json("POST", f"repos/{repo}/issues/{ex['number']}/comments", {"body": t["resolution"]["gist"]}, dry, log)
                rg.gh_json("PATCH", f"repos/{repo}/issues/{ex['number']}", {"state": "closed"}, dry, log)
            ex["body"] = body
        else:
            rc, j = rg.gh_json("POST", f"repos/{repo}/issues", {"title": f"[clarify] {i}: {t['title']}", "body": body, "labels": labels}, dry, log)
            if (j or {}).get("number") and not dry:
                m["issues"][i] = {"number": j["number"], "body": body}
    if not dry:
        m["repo"] = repo
        rg.save(mp, m)
    print(("DRY RUN (add --yes)" if dry else "MIRRORED"), "->", repo)
    for l in log:
        print("  ", l)
    return 0


def v_drift(a):
    root = os.path.abspath(a.root)
    lvl, msgs = rg.drift(root)
    for m in msgs:
        print(" ", m)
    print("drift:", lvl)
    return 1 if lvl in ("ask", "block") else 0


def add_parser(sub):
    s = sub.add_parser("clarify", help="automatic clarify stage (run by the agent)")
    cs = s.add_subparsers(dest="cverb", required=True)
    p = cs.add_parser("init"); p.add_argument("--idea", required=True); p.add_argument("--destination-one-sentence", choices=["yes", "no"], required=True); p.add_argument("--first-three", choices=["yes", "no"], required=True)
    p = cs.add_parser("destination"); p.add_argument("--text"); p.add_argument("--candidate", action="append")
    cs.add_parser("park")
    cs.add_parser("reopen")
    p = cs.add_parser("add"); p.add_argument("id"); p.add_argument("--title", required=True); p.add_argument("--type", required=True); p.add_argument("--question", required=True); p.add_argument("--blocked-on", action="append"); p.add_argument("--thread")
    p = cs.add_parser("fog"); p.add_argument("--add"); p.add_argument("--clear", type=int)
    p = cs.add_parser("oos"); p.add_argument("--add", required=True)
    cs.add_parser("open")
    p = cs.add_parser("resolve"); p.add_argument("id"); p.add_argument("--gist", required=True); p.add_argument("--restated"); p.add_argument("--source", action="append"); p.add_argument("--unverified", action="append")
    cs.add_parser("status")
    p = cs.add_parser("close")
    for k in ("outcome", "user", "why-now", "success", "constraint", "out-of-scope"):
        p.add_argument("--" + k, required=True)
    p = cs.add_parser("mirror"); p.add_argument("--yes", action="store_true")
    cs.add_parser("drift")


def run(a):
    return {"init": v_init, "destination": v_destination, "park": v_park, "reopen": v_reopen, "add": v_add, "fog": v_fog, "oos": v_oos, "open": v_open,
            "resolve": v_resolve, "status": v_status, "close": v_close, "mirror": v_mirror, "drift": v_drift}[a.cverb](a)
