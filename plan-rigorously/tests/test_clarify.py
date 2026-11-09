"""Clarify stage, issue drift, planning docs carried into execution, and to-do output."""
import os, subprocess, sys
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import railguard as r  # noqa: E402
import rigor_exec as x  # noqa: E402
from test_railguard import _ctx  # noqa: E402
from test_exec import proj, X, start, git, FEEDBACK  # noqa: E402,F401


def C(args, *a):
    return r.main(args + ["clarify"] + list(a))


def yes(args, subject, reason="yes, confirmed"):
    return r.main(args + ["log", reason, "--kind", "answer", "--subject", subject, "--authority", "user"])


def test_fog_test_passing_needs_no_clarify(tmp_path, capsys):
    args, plan = _ctx(tmp_path)
    assert C(args, "init", "--idea", "rate limit", "--destination-one-sentence", "yes", "--first-three", "yes") == 0
    assert "no clarifying needed" in capsys.readouterr().out
    assert not os.path.exists(r.clarify_file(str(tmp_path)))


def test_full_clarify_run(tmp_path, capsys):
    args, plan = _ctx(tmp_path)
    assert C(args, "init", "--idea", "billing", "--destination-one-sentence", "no", "--first-three", "no") == 0
    assert C(args, "init", "--idea", "billing", "--destination-one-sentence", "no", "--first-three", "no") == 2   # live run
    assert C(args, "destination", "--text", "A billing system with plans and tax", "--candidate", "just invoicing") == 0
    # tickets need the signed destination
    assert C(args, "add", "M1", "--title", "Payment provider", "--type", "grilling", "--question", "Which provider?") == 2
    assert yes(args, "clarify_destination_signed", "sounds fine") == 2   # not explicit
    assert yes(args, "clarify_destination_signed") == 0
    assert C(args, "add", "M1", "--title", "Payment provider", "--type", "grilling", "--question", "Which provider?", "--thread", "payments") == 0
    assert C(args, "add", "M2", "--title", "Tax rules", "--type", "research", "--question", "Which tax rules apply?", "--thread", "tax") == 0
    assert C(args, "add", "M3", "--title", "Plan tiers", "--type", "grilling", "--question", "Which tiers?", "--blocked-on", "M1") == 0
    assert C(args, "add", "M4", "--title", "X", "--type", "task", "--question", "q") == 2          # task type does not exist
    assert C(args, "add", "M5", "--title", "X", "--type", "grilling", "--question", "q", "--blocked-on", "M9") == 2
    assert C(args, "open") == 2                                                                      # chart not signed
    assert yes(args, "clarify_chart_signed") == 0
    assert C(args, "open") == 0
    capsys.readouterr()
    assert C(args, "status") == 0
    out = capsys.readouterr().out
    assert "M1" in out and "M2" in out and "M3 [grilling] Plan tiers" not in out     # M3 is blocked, not on the frontier
    assert "payments: 1 open" in out and "tax: 1 open" in out
    # grilling needs the user's answer in the ledger; blocked tickets wait
    assert C(args, "resolve", "M1", "--gist", "Stripe") == 2
    assert C(args, "resolve", "M3", "--gist", "x") == 2
    r.main(args + ["log", "Stripe", "--kind", "answer", "--subject", "M1", "--authority", "user"])
    assert C(args, "resolve", "M1", "--gist", "Stripe") == 0
    # research needs the record
    assert C(args, "resolve", "M2", "--gist", "VAT") == 2
    assert C(args, "resolve", "M2", "--gist", "VAT", "--restated", "Which tax rules apply?", "--source", "https://example.org/vat", "--unverified", "none") == 0
    r.main(args + ["log", "three tiers", "--kind", "answer", "--subject", "M3", "--authority", "user"])
    assert C(args, "fog", "--add", "refund policy") == 0
    assert C(args, "resolve", "M3", "--gist", "three tiers") == 0
    brief = ["--outcome", "Bill customers", "--user", "Finance", "--why-now", "Launch", "--success", "Invoices paid", "--constraint", "One provider", "--out-of-scope", "Payroll"]
    assert C(args, "close", *brief) == 2                       # fog not empty
    assert C(args, "fog", "--clear", "0") == 0
    assert C(args, "close", *brief) == 0
    spec = r.load(r.spec_path_of(r.load(plan), plan))
    assert spec["intent"]["outcome"] == "Bill customers"
    # clarifying finished after intent confirmation: confirm again
    yes(args, "intent_confirmed")
    rc = r.main(args + ["check", plan, "--final"])
    capsys.readouterr()
    assert r.load(r.clarify_file(str(tmp_path)))["status"] == "closed"


def test_clarify_consistency_rule_catches_tampering(tmp_path, capsys):
    args, plan = _ctx(tmp_path)
    C(args, "init", "--idea", "i", "--destination-one-sentence", "no", "--first-three", "yes")
    yes(args, "clarify_destination_signed")
    C(args, "add", "M1", "--title", "T", "--type", "grilling", "--question", "q")
    p = r.clarify_file(str(tmp_path))
    d = r.load(p)
    d["tickets"][0]["status"] = "closed"
    d["tickets"][0]["resolution"] = {"gist": "edited by hand"}
    r.save(p, d)
    capsys.readouterr()
    r.main(args + ["check", plan])
    assert "closed without a user answer in the ledger" in capsys.readouterr().out


def test_park_is_the_users_decision(tmp_path):
    args, plan = _ctx(tmp_path)
    C(args, "init", "--idea", "i", "--destination-one-sentence", "no", "--first-three", "no")
    assert C(args, "park") == 2
    r.main(args + ["log", "not now", "--kind", "decision", "--subject", "clarify_parked", "--authority", "user"])
    assert C(args, "park") == 0
    assert r.load(r.clarify_file(str(tmp_path)))["status"] == "parked"


def _stub_gh(tmp_path_factory, monkeypatch, body_for):
    bindir = tmp_path_factory.mktemp("bin")
    import ghstub
    ghstub.install(bindir, body_for)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    return bindir


@pytest.mark.parametrize("new_body,level", [
    ('"Which provider?\\n\\nBlocked on: nothing\\nType: grilling\\n"', "none"),
    ('"Which provider?\\n\\nBlocked on: nothing\\nType: grilling\\nok"', "note"),
    ('"Which provider? also consider invoicing\\n\\nBlocked on: nothing\\nType: grilling\\n"', "ask"),
    ('"completely rewritten body that shares almost nothing"', "block"),
])
def test_issue_drift_is_sized(tmp_path, tmp_path_factory, monkeypatch, capsys, new_body, level):
    args, plan = _ctx(tmp_path)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:o/r.git"], cwd=tmp_path, check=True)
    C(args, "init", "--idea", "i", "--destination-one-sentence", "no", "--first-three", "yes")
    yes(args, "clarify_destination_signed")
    C(args, "add", "M1", "--title", "Provider", "--type", "grilling", "--question", "Which provider?")
    yes(args, "clarify_chart_signed")
    C(args, "open")
    _stub_gh(tmp_path_factory, monkeypatch, '""')
    assert C(args, "mirror", "--yes") == 0
    mirror = r.load(os.path.join(str(tmp_path), ".rigor", "clarify", "mirror.yaml"))
    assert mirror["issues"]["M1"]["number"] == 7
    _stub_gh(tmp_path_factory, monkeypatch, new_body)
    capsys.readouterr()
    lvl, msgs = r.drift(str(tmp_path))
    assert lvl == level, (lvl, msgs)
    if level in ("ask", "block"):
        assert C(args, "drift") == 1
        r.main(args + ["log", "fine", "--kind", "decision", "--subject", "drift_accepted", "--authority", "user"])
        assert r.drift(str(tmp_path))[0] == "note"


def test_exec_todo_lists_every_unit(proj, capsys):
    root, args, plan = proj
    start(proj)
    capsys.readouterr()
    assert X(args, "todo") == 0
    rows = [l.split("\t") for l in capsys.readouterr().out.splitlines()[1:]]
    kinds = {k[1] for k in rows}
    assert {"phase", "task", "checkpoint", "verifier", "review", "final", "delivery"} <= kinds
    assert all(k[0] == "pending" for k in rows)


def test_republish_does_not_mistake_its_own_task_issues_for_duplicates(tmp_path, tmp_path_factory, monkeypatch, capsys):
    import json
    args, plan = _ctx(tmp_path)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:o/r.git"], cwd=tmp_path, check=True)
    bindir = _stub_gh(tmp_path_factory, monkeypatch, '""')
    assert r.main(args + ["publish", plan, "--yes"]) == 0
    slug = r.load(plan)["meta"]["slug"]
    st = r.load_state(str(tmp_path))
    nums = list((st["publish"]["tasks"] or {}).values())
    parent_n = st["publish"]["parent"]
    listing = [{"number": parent_n, "title": f"plan: {slug}"}] + [{"number": n, "title": f"[{slug}] task T{i}: x"} for i, n in enumerate(nums)]
    (bindir / "issues.json").write_text(json.dumps(listing))
    r.main(args + ["log", "stub returns empty bodies", "--kind", "decision", "--subject", "drift_accepted", "--authority", "user"])
    capsys.readouterr()
    assert r.main(args + ["publish", plan, "--yes"]) == 0     # updates the parent; own task issues are not duplicates
    assert "NEEDS DECISION" not in capsys.readouterr().out
    creates = [l for l in (bindir / "gh.log").read_text().splitlines() if l.startswith("gh api -X POST repos/o/r/issues --input")]
    assert len(creates) == 3                                   # parent + 2 tasks from the first publish only
    (bindir / "issues.json").write_text(json.dumps([{"number": 55, "title": f"plan: {slug} again"}]))
    assert r.main(args + ["publish", plan, "--yes"]) == 3      # a genuinely similar foreign issue still asks


def test_reopen_after_park_needs_the_users_yes(tmp_path):
    args, plan = _ctx(tmp_path)
    C(args, "init", "--idea", "i", "--destination-one-sentence", "no", "--first-three", "yes")
    r.main(args + ["log", "park it", "--kind", "decision", "--subject", "clarify_parked", "--authority", "user"])
    assert C(args, "park") == 0
    assert C(args, "reopen") == 2
    r.main(args + ["log", "yes, resume", "--kind", "decision", "--subject", "clarify_reopened", "--authority", "user"])
    assert C(args, "reopen") == 0
    assert r.load(os.path.join(str(tmp_path), ".rigor", "clarify", "clarify.yaml"))["status"] == "charting"
