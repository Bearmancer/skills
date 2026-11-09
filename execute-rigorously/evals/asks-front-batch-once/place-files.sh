#!/usr/bin/env bash
# Builds a small git project with a reviewed, final plan ready to execute.
set -eu
RG="${RIGOR_SKILL_DIR:-$HOME/.claude/skills/plan-rigorously}/scripts"
mkdir -p src tests
printf 'def handle():\n    return 1\n' > src/handler.py
printf '# demo\n' > NOTES.md
git init -q && git add -A && git -c user.email=e@x -c user.name=e commit -q -m init
python3 - "$RG" "0" <<'PY'
import sys, shutil, os
sys.path.insert(0, sys.argv[1])
import railguard as r
root = os.getcwd(); args = ["--root", root]
skill = os.path.dirname(sys.argv[1])
r.main(args + ["start", "demo-rate-limit", "--no-codegraph"])
plans = os.path.join(root, ".rigor", "plans")
shutil.copy(os.path.join(skill, "assets", "spec.yaml"), os.path.join(plans, "spec.yaml"))
pp = os.path.join(plans, "demo-rate-limit.plan.yaml")
shutil.copy(os.path.join(skill, "assets", "plan.yaml"), pp)
os.makedirs(os.path.join(root, ".rigor", "evidence", "P1"), exist_ok=True)
open(os.path.join(root, ".rigor", "evidence", "P1", "codegraph.md"), "w").write("handler is the single entry point")
p = r.load(pp)
p["meta"]["status"] = "draft" if sys.argv[2] == "1" else "final"
t1, t2 = p["phases"][0]["tasks"]
t1["verify"][0]["run"] = "grep -q retry src/limiter.py"
t1["verify"][1]["run"] = "test -f src/limiter.py"
t2["verify"][0]["run"] = "grep -q tier src/handler.py"
t2["verify"][1]["run"] = "grep -q default src/handler.py"
p["phases"][0]["checkpoints"][0]["verify"] = ["true"]
p["final_verification"][0]["verify"]["run"] = "true"
r.save(pp, p)
r.main(args + ["check", pp])
for gid, g in r.gate_map(r.load_pack()).items():
    if g["kind"] == "manual":
        r.main(args + ["log", "ok", "--kind", "gate", "--subject", gid, "--status", "passed", "--authority", "user"])
for role in r.required_reviewers(p, r.load_pack()["routing"]):
    r.main(args + ["log", "", "--kind", "review_complete", "--plan", pp, "--role", role, "--set-baseline"])
r.main(args + ["log", "yes", "--kind", "answer", "--subject", "execute_authorized", "--authority", "user"])
r.main(args + ["log", "yes, confirmed", "--kind", "answer", "--subject", "intent_confirmed", "--authority", "user"])
r.main(args + ["render", pp])
PY
