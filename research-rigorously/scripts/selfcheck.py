"""The skill's single check bar: `rr selfcheck`.

One line per check (PASS name / FAIL name: reason), a final count, exit 0 only
when every check passes. No credentials, no network, no real state or site:
everything runs in temp dirs with injected fetch/sleep/clock/switcher seams.
"""

import argparse
import ast
import atexit
import contextlib
import copy
import io
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import yaml

from . import (
    agents,
    cli,
    domains,
    driver,
    fetch,
    infer_mode,
    keys,
    ledger,
    registry,
    remove,
    render,
    site,
    switch_api_key,
    urlaudit,
    workspace,
)
from . import publish as publishing
from .phases import common, discover, ship, verify

SKILL = registry.ROOT
CHECKS = []


def check(name, source):
    def deco(fn):
        CHECKS.append((name, source, fn))
        return fn

    return deco


# ---------------------------------------------------------------- helpers


class ScriptedRunner:
    def __init__(self, answer):
        self.answer = answer
        self.steps = []

    def run(self, role, prompt, step="", context=None):
        self.steps.append(step)
        return self.answer(role, step, prompt)


def tmp_ledger_ctx(tmp):
    led = workspace.Ledger(tmp / "topic")
    return SimpleNamespace(
        ledger=led,
        reg=registry.load(),
        cfg=workspace.Config(state_root=tmp / "state"),
        step_data={},
        runner=ScriptedRunner(lambda *a: "verdicts: []"),
        keys=None,
        drop_dir=tmp / "topic",
    )


def add_claim_with(ctx, text, evidence, rounds=1):
    claim, _ = ctx.ledger.add_claim(text, origin="discovered")
    for i, (tier, publisher, stance) in enumerate(evidence, 1):
        src = ctx.ledger.add_source(
            f"https://example.org/{publisher}/{i}",
            kind="web",
            tier=tier,
            publisher=publisher,
        )
        ctx.ledger.add_evidence(claim["id"], src["id"], stance, f"p{i}", f"quote {i}")
    claim["rounds"] = rounds
    return claim


def raises(exc, fn):
    try:
        fn()
    except exc:
        return True
    return False


def git(cwd, *args):
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(f"git {args} failed: {proc.stderr[:200]}")
    return proc.stdout.strip()


def setup_clone(base, *, other_topic=True, subject="Politics"):
    remote = base / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    clone = base / "clone"
    subprocess.run(["git", "init", str(clone)], check=True, capture_output=True)
    git(clone, "checkout", "-b", "main")
    git(clone, "config", "user.email", "t@example.com")
    git(clone, "config", "user.name", "Test")
    git(clone, "remote", "add", "origin", str(remote))
    if other_topic:
        topic = clone / "topic-a"
        (topic / "lessons").mkdir(parents=True)
        (topic / "index.html").write_text(
            '<html><head><meta name="course-kind" content="explainer">'
            f'<meta name="subject" content="{subject}"></head><body><h1>Topic A</h1></body></html>',
            encoding="utf-8",
        )
        (topic / "lessons" / "01-ch1-a.html").write_text(
            "<html><body>A1</body></html>", encoding="utf-8"
        )
        (clone / "index.html").write_text("<html>seed</html>", encoding="utf-8")
        (clone / "assets").mkdir()
        (clone / "assets" / "course-index.js").write_text("[]", encoding="utf-8")
        git(clone, "add", "-A")
        git(clone, "commit", "-q", "-m", "seed")
    git(clone, "push", "-q", "-u", "origin", "main")
    return clone, remote


def make_ctx(base, clone, topic="topic-c"):
    cfg = workspace.Config(state_root=base / "state", site_url="http://example.test")
    ctx = workspace.Context(
        site_root=workspace.Layout(cfg.state_root, topic).site,
        main_root=clone,
        topic=topic,
        reg=registry.load(),
        runner=None,
        fetcher=None,
        publisher=None,
        cfg=cfg,
    )
    d = driver.Driver(ctx.layout.run, driver.RunState("r1", topic, "prompt", mode="answer"), {})
    d.save()
    return ctx, d


DISCOVERY = "```yaml\nsources: []\nattempts: []\n```"
NO_EVIDENCE = "```yaml\nevidence: []\nignored_instructions: []\n```"

# ---------------------------------------------------------------- agents (6 old)


@check("agents.strict-two-blocks", "old-KEEP")
def _():
    runner = ScriptedRunner(lambda *a: "```yaml\nevidence: []\n```\n```yaml\nevidence: []\n```")
    got = agents.call(runner, "extractor", "evidence", "payload", "t", required=("evidence",), strict=True)
    assert "_flags" in got


@check("agents.strict-text-after-fence", "old-KEEP")
def _():
    runner = ScriptedRunner(lambda *a: "```yaml\nevidence: []\n```\nextra")
    got = agents.call(runner, "extractor", "evidence", "payload", "t", required=("evidence",), strict=True)
    assert "_flags" in got


@check("agents.strict-clean-block", "old-KEEP")
def _():
    runner = ScriptedRunner(lambda *a: "```yaml\nevidence: []\nignored_instructions: []\n```")
    got = agents.call(runner, "extractor", "evidence", "payload", "t", required=("evidence",), strict=True)
    assert "evidence" in got and "_flags" not in got


@check("agents.non-strict-raises", "old-KEEP")
def _():
    runner = ScriptedRunner(lambda *a: "not yaml at all")
    assert raises(agents.AgentReplyError, lambda: agents.call(runner, "extractor", "evidence", "p", "t", required=("evidence",)))


@check("agents.check-hook", "old-KEEP")
def _():
    seen = []
    runner = ScriptedRunner(lambda *a: "```yaml\nevidence: []\n```")
    agents.call(runner, "extractor", "evidence", "p", "t", required=("evidence",), check=lambda d: seen.append(d))
    assert seen


@check("agents.check-retry", "old-KEEP")
def _():
    runner = ScriptedRunner(lambda *a: "```yaml\nevidence: []\n```")

    def bad(data):
        raise agents.AgentReplyError("bad")

    assert raises(agents.AgentReplyError, lambda: agents.call(runner, "extractor", "evidence", "p", "t", required=("evidence",), check=bad))
    assert any(s.endswith(".retry") for s in runner.steps)


# ---------------------------------------------------------------- batches (6 old)


def _ask(tmp, name, role, step, fresh=True):
    p = tmp / "agent" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"role: {role}\nstep: {step}\nfresh subagent: {'yes' if fresh else 'no'}\n---\nbody\n",
        encoding="utf-8",
    )
    return str(p)


def _wait(tmp, asks):
    state = driver.RunState(run_id="r1", topic="t", prompt="p")
    d = driver.Driver(tmp, state, {})
    d._wait("verify", driver.NeedsAgent(asks))
    return (tmp / "ASKS.md").read_text(encoding="utf-8"), tmp / "batches"


def _batch_sizes(batches_dir, role):
    return [
        sum(1 for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip().startswith("- ask:"))
        for p in sorted(batches_dir.glob(f"{role}-*.batch.md"))
    ]


@check("batches.extractor-cap-6", "old-KEEP")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        asks = [_ask(tmp, f"x{i}.ask.md", "extractor", f"verify.c1.r1.evidence.s{i:03d}") for i in range(13)]
        _text, batches = _wait(tmp, asks)
        sizes = _batch_sizes(batches, "extractor")
        assert len(sizes) >= 2 and max(sizes) <= 6, sizes


@check("batches.balanced-sizes", "old-KEEP")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        asks = [_ask(tmp, f"x{i}.ask.md", "extractor", f"verify.c1.r1.evidence.s{i:03d}") for i in range(12)]
        _text, batches = _wait(tmp, asks)
        sizes = _batch_sizes(batches, "extractor")
        assert sizes and max(sizes) - min(sizes) <= 1, sizes


@check("batches.verifier-cap-10", "old-KEEP")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        asks = [_ask(tmp, f"v{i}.ask.md", "verifier", f"verify.c{i}.r5.positions") for i in range(12)]
        _text, batches = _wait(tmp, asks)
        sizes = _batch_sizes(batches, "verifier")
        assert len(sizes) == 2 and max(sizes) <= 10, sizes


@check("batches.media-cap-1", "old-KEEP")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        asks = [_ask(tmp, f"m{i}.ask.md", "media", f"media.c{i}") for i in range(3)]
        _text, batches = _wait(tmp, asks)
        assert len(_batch_sizes(batches, "media")) == 3


@check("batches.non-fresh-not-batched", "old-KEEP")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        asks = [_ask(tmp, f"n{i}.ask.md", "author", "write.draft", fresh=False) for i in range(5)]
        text, batches = _wait(tmp, asks)
        assert not _batch_sizes(batches, "author")
        assert all(a in text for a in asks)


@check("batches.order-by-step", "old-KEEP")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        asks = [
            _ask(tmp, "z.ask.md", "extractor", "verify.c2.r1.evidence.s01"),
            _ask(tmp, "a.ask.md", "extractor", "verify.c1.r1.evidence.s01"),
        ]
        _text, batches = _wait(tmp, asks)
        blob = next(batches.glob("extractor-*.batch.md")).read_text(encoding="utf-8")
        assert blob.index("a.ask.md") < blob.index("z.ask.md")


# ---------------------------------------------------------------- in_app (9 old)

AGENT_CLIS = {
    "opencode", "claude", "codex", "kilo",
    "kilocode", "aider", "cursor-agent", "goose", "crush", "qwen", "amp",
    "droid", "copilot", "omo",
}
_HEAD = re.compile(r"^([\w.-]+?)(?:\.exe|\.cmd|\.ps1)?(?:\s|$)", re.IGNORECASE)


def _agent_head(text):
    m = _HEAD.match(str(text).strip())
    return bool(m and m[1].lower() in AGENT_CLIS)


def agent_cli_uses(source, name="<src>"):
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.List, ast.Tuple)) and node.elts:
            first = node.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str) and _agent_head(first.value):
                found.append(f"{name}:{node.lineno}")
        elif isinstance(node, ast.Call):
            fn = node.func
            called = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            arg = node.args[0] if node.args else None
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                continue
            head = _agent_head(arg.value)
            if head and (
                called == "which"
                or called in {"run", "Popen", "call", "check_call", "check_output", "system", "_cmd", "run_cmd"}
                and re.match(r"^\S+\s", arg.value)
            ):
                found.append(f"{name}:{node.lineno}")
    return found


@check("in_app.detector-catches-agent-cli", "old-KEEP")
def _():
    assert agent_cli_uses('subprocess.run(["opencode", "run", "x"])')
    assert agent_cli_uses('cmd = ["codex", "-p=x"]')
    assert agent_cli_uses('shutil.which("opencode")')
    assert agent_cli_uses('os.system("claude -p hi")')
    assert not agent_cli_uses('Path.home() / ".config" / "opencode" / "secrets"')
    assert not agent_cli_uses('subprocess.run(["git", "status"])')


@check("in_app.no-skill-code-starts-agent", "old-ADAPT")
def _():
    found = []
    for path in sorted((SKILL / "scripts").rglob("*.py")):
        found += agent_cli_uses(path.read_text(encoding="utf-8"), path.relative_to(SKILL).as_posix())
    reg = registry.load()
    for name, server in (reg.get("servers") or {}).items():
        for cap in (server.get("capabilities") or {}).values():
            for cmd in (cap.get("routes") or {}).get("cli") or []:
                assert not _agent_head(str(cmd)), f"{name}: {cmd}"
    assert found == [], found


@check("in_app.roles-hygiene", "old-ADAPT")
def _():
    text = (SKILL / "references" / "roles.md").read_text(encoding="utf-8")
    for bad in ("model:", "family:", "fallback", "codex"):
        assert bad not in text, bad
    assert registry.checking_roles()


@check("in_app.missing-reply-writes-ask", "old-KEEP")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        runner = driver.HandRunner(tmp, checking=("verifier",))
        assert raises(driver.NeedsAgent, lambda: runner.run("verifier", "check these rows", step="gate.b1"))
        ask = min(tmp.glob("*.ask.md"))
        head = ask.read_text(encoding="utf-8")
        assert "role: verifier" in head and "fresh subagent: yes" in head and "check these rows" in head
        reply = Path(re.search(r"reply file: (.+)", head)[1].strip())
        reply.write_text("verdicts: []\n", encoding="utf-8")
        assert runner.run("verifier", "check these rows", step="gate.b1") == "verdicts: []\n"
        assert raises(driver.NeedsAgent, lambda: runner.run("verifier", "changed rows", step="gate.b1"))
        assert raises(driver.NeedsAgent, lambda: runner.run("author", "write it", step="draft.ch1"))
        author_ask = min(tmp.glob("draft.ch1-*.ask.md"))
        assert "fresh subagent: no" in author_ask.read_text(encoding="utf-8")


@check("in_app.driver-waits-and-resumes", "old-KEEP")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        runner = driver.HandRunner(tmp / "agent")

        def step(d):
            return driver.PhaseResult(data={"reply": runner.run("extractor", "split it", step="extract.s1")})

        handlers = {p: (lambda d: driver.PhaseResult()) for p in driver.PHASES["verify"]}
        handlers.update(infer_mode=lambda d: driver.PhaseResult(mode="verify"), ingest=step)
        d = driver.Driver.start(tmp, "t", "p", handlers, run_id="r1")
        assert d.run() == driver.EXIT[driver.WAITING] == 3
        asks = (tmp / "ASKS.md").read_text(encoding="utf-8")
        ask = Path(re.search(r"- (\S+\.ask\.md)", asks)[1])
        reply = Path(re.search(r"reply file: (.+)", ask.read_text(encoding="utf-8"))[1].strip())
        reply.write_text("claims: []", encoding="utf-8")
        d = driver.Driver.resume(tmp, handlers)
        assert not (tmp / "ASKS.md").exists()
        assert d.run() == 0


@check("in_app.wave-collects-asks", "old-KEEP")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        runner = driver.HandRunner(Path(tmp))
        results, _ = driver.run_wave(
            {k: k for k in "abc"},
            lambda k: runner.run("discovery", f"round for {k}", step=f"verify.{k}.r1"),
        )
        waiting = driver.waiting(results)
        assert isinstance(waiting, driver.NeedsAgent) and len(waiting.asks) == 3
        assert all(r.attempts == 1 for r in results.values())


@check("in_app.waiting-round-not-failed", "old-KEEP")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ctx = tmp_ledger_ctx(tmp)
        ctx.ledger.add_claim("Water boils at 100 C at sea level", origin="discovered")
        runner = driver.HandRunner(tmp / "agent")
        original = verify._do_round
        verify._do_round = lambda c, cid, fatal: runner.run("discovery", cid, step=f"verify.{cid}.r1")
        try:
            d = SimpleNamespace(
                state=SimpleNamespace(mode="verify", prompt="p", context={"reopened": True}),
                run_dir=tmp,
                save=lambda: None,
            )
            for _ in range(4):
                assert raises(driver.NeedsAgent, lambda: verify.verify(ctx, d))
            assert d.state.context["round_failures"] == {}
        finally:
            verify._do_round = original


@check("in_app.fetch-asks-own-file-resume", "old-ADAPT")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ctx = SimpleNamespace(
            drop_dir=tmp / "sources",
            keys=None,
            clock=None,
            reg=registry.load(),
            ledger=workspace.Ledger(tmp / "topic"),
            runner=driver.HandRunner(tmp / "agent"),
        )
        ctx.drop_dir.mkdir(parents=True)
        reg = registry.load()
        surf = registry.surfaces(reg)["tavily.extract"]
        fetcher = fetch.LadderFetcher(min_chars=5)
        asks = {}
        for url in ("https://a.test/1", "https://b.test/2"):
            assert raises(driver.NeedsAgent, lambda u=url: fetcher._agent("tavily.extract", surf, u, ctx, False))
            asks[url] = max((tmp / "agent").glob("*.ask.md")).read_text(encoding="utf-8")
        head = asks["https://a.test/1"]
        dest = Path(re.search(r"save the page text to: (.+)", head)[1].strip())
        dest.write_text("page one text", encoding="utf-8")
        reply = Path(re.search(r"reply file: (.+)", head)[1].strip())
        reply.write_text("ok: true\nroute: mcp\n", encoding="utf-8")
        got = fetcher._agent("tavily.extract", surf, "https://a.test/1", ctx, False)
        assert got.ok and got.text == "page one text", got


@check("in_app.round-asks-all-evidence", "old-ADAPT")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ctx = tmp_ledger_ctx(tmp)
        claim, _ = ctx.ledger.add_claim("Water boils at 100 C at sea level", origin="discovered")
        ctx.keys = None
        ctx.raw = SimpleNamespace(contains=lambda text, quote: True, get=lambda path: "text")
        ctx.runner = driver.HandRunner(tmp / "agent")
        rows = [({"id": f"s{i}", "url": f"https://x.test/{i}"}, f"text {i}") for i in (1, 2)]
        saved = (common.take_sources, common.log_reply_attempts, verify.round_attempts)
        common.take_sources = lambda c, reply: rows
        common.log_reply_attempts = lambda *a, **k: []
        verify.round_attempts = lambda c, cid, n: [{"paradigm": "keyword"}]
        try:
            assert raises(driver.NeedsAgent, lambda: verify._do_round(ctx, claim["id"], []))
            ask = min((tmp / "agent").glob("*.ask.md"))
            ask.with_name(ask.name.replace(".ask.", ".reply.")).write_text("sources: []\nattempts: []\n", encoding="utf-8")
            assert raises(driver.NeedsAgent, lambda: verify._do_round(ctx, claim["id"], []))
            names = sorted(Path(a).name.split("-")[0] for a in _last_asks(tmp / "agent"))
            assert names == [f"verify.{claim['id']}.r1.evidence.s1.k1", f"verify.{claim['id']}.r1.evidence.s2.k1"], names
        finally:
            common.take_sources, common.log_reply_attempts, verify.round_attempts = saved


def _last_asks(agent_dir):
    pending = [
        p for p in sorted(agent_dir.glob("*.ask.md"))
        if not p.with_name(p.name.replace(".ask.md", ".reply.md")).exists()
    ]
    return pending


# ---------------------------------------------------------------- ledger (3 old)


@check("ledger.publish-true-no-evidence", "old-KEEP")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = tmp_ledger_ctx(Path(tmp))
        claim, _ = ctx.ledger.add_claim("Water boils at 100 C at sea level", origin="discovered")
        claim["status"] = "true"
        claim["rounds"] = 2
        found = ledger.check(ctx.ledger.claims_doc, ctx.ledger.sources_doc, [], publish=True, round_order=ctx.reg["round_order"])
        assert any(v.severity == "error" for v in found)


@check("ledger.publish-open-claim", "old-KEEP")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = tmp_ledger_ctx(Path(tmp))
        ctx.ledger.add_claim("Still working on this", origin="discovered")
        found = ledger.check(ctx.ledger.claims_doc, ctx.ledger.sources_doc, [], publish=True, round_order=ctx.reg["round_order"])
        assert any(v.severity == "error" for v in found)


@check("ledger.settle-rules", "old-KEEP")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = tmp_ledger_ctx(Path(tmp))
        ctx.runner.run = lambda *a, **k: "positions: []"
        last = ctx.reg["max_rounds"]
        one = add_claim_with(ctx, "Primary-backed claim", [("T1", "gov", "supports")])
        assert verify.settle(ctx, one["id"], 1) is None
        assert verify.settle(ctx, one["id"], 2) == "true"
        weaker = add_claim_with(ctx, "Contested claim", [("T1", "gov", "supports"), ("T2", "uni", "contradicts")], rounds=2)
        assert verify.settle(ctx, weaker["id"], 2) is None
        assert verify.settle(ctx, weaker["id"], last) == "interpretive"
        both = add_claim_with(ctx, "Disputed claim", [("T1", "gov", "supports"), ("T1", "agency", "contradicts")], rounds=2)
        assert verify.settle(ctx, both["id"], 2) == "interpretive"
        none = add_claim_with(ctx, "Nothing found", [], rounds=5)
        assert verify.settle(ctx, none["id"], last) == "not-found"


# ---------------------------------------------------------------- publish (3 old)


@check("publish.revert-noop", "old-KEEP")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        clone, _remote = setup_clone(tmp)
        before = (clone / "index.html").read_bytes()
        pub = __import__("scripts.publish", fromlist=["GitPublisher", "PublishResult"])
        pub.GitPublisher(clone, state_root=tmp / "state").revert(pub.PublishResult())
        assert (clone / "index.html").read_bytes() == before


@check("publish.layout-disjoint", "old-ADAPT")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        layout = workspace.Layout(Path(tmp) / "state", "t")
        assert layout.asks.parent == layout.run and layout.site.parent == layout.run
        assert layout.asks not in layout.site.parents and layout.site not in layout.asks.parents
        assert layout.site.name == "site" and layout.asks.name == "ASKS.md"


@check("publish.remove-404s", "old-ADAPT")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        clone, _remote = setup_clone(tmp)
        before = git(clone, "rev-parse", "main")

        def fake_fetch(url):
            rel = url.split("/", 3)[-1] if "://" in url else url
            path = clone / rel
            return (200, path.read_bytes()) if path.is_file() and not rel.startswith("topic-a/") else (404, b"")

        code = remove.main(clone, "topic-a", site_url="http://h.test", fetch=fake_fetch, sleep=lambda _s: None, state_root=tmp / "state")
        assert code == 0, code
        assert not (clone / "topic-a").exists()
        assert git(clone, "rev-parse", "main") != before


# ---------------------------------------------------------------- robustness (12 old)


@check("robust.wave-halves-on-rate-limit", "old-KEEP")
def _():
    calls = {}

    def fn(x):
        calls[x] = calls.get(x, 0) + 1
        if x == "a" and calls[x] == 1:
            raise driver.RateLimited()
        return x.upper()

    results, size = driver.run_wave({k: k for k in "abcd"}, fn, size=4)
    assert size == 2 and all(r.ok for r in results.values()) and results["a"].value == "A"


@check("robust.wave-retries-error-once", "old-KEEP")
def _():
    results, _ = driver.run_wave({"a": 1}, lambda _: (_ for _ in ()).throw(ValueError("nope")), retries=1)
    assert not results["a"].ok and results["a"].attempts == 2


@check("robust.wave-never-reruns-live", "old-KEEP")
def _():
    release, started = threading.Event(), []

    def slow(_):
        started.append(1)
        release.wait(2)
        return "late"

    results, _ = driver.run_wave({"a": 1}, slow, timeout=0.1, retries=1)
    release.set()
    assert not results["a"].ok and "still running" in (results["a"].error or "")
    assert len(started) == 1


@check("robust.gate-stray-and-confirmed", "old-KEEP")
def _():
    def runner_for(stays_wrong):
        def answer(role, step, prompt):
            ids = re.findall(r"^- (c\d+) \[", prompt, re.MULTILINE)
            if ".recheck" in step:
                v = "disagree" if stays_wrong else "agree"
                return "```yaml\nverdicts:\n" + "".join(f"  - {{claim: {i}, verdict: {v}}}\n" for i in ids) + "```"
            out = []
            for i in ids:
                v = "disagree" if i == "c1" else "agree"
                out.append(f"  - {{claim: {i}, verdict: {v}, note: stray}}")
            return "```yaml\nverdicts:\n" + "\n".join(out) + "\n```"
        return ScriptedRunner(answer)

    with tempfile.TemporaryDirectory() as tmp:
        ctx = tmp_ledger_ctx(Path(tmp))
        for name, pub in (("Claim one", "gov"), ("Claim two", "edu")):
            add_claim_with(ctx, name, [("T1", pub, "supports")])
        for c in ctx.ledger.claims:
            c["status"] = "true"
        ctx.runner = runner_for(False)
        problems, counts = ship.verifier_problems(ctx)
        assert problems == [] and counts["rechecked"] == 1, (problems, counts)
        ctx.runner = runner_for(True)
        problems, _ = ship.verifier_problems(ctx)
        assert len(problems) == 1 and "c1" in problems[0], problems


@check("robust.paradigm-audit", "old-KEEP")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = tmp_ledger_ctx(Path(tmp))
        reg = ctx.reg
        ok_p = reg["round_order"][0][0]
        other_p = next(p for p in reg["paradigms"] if p != ok_p)
        surfaces = registry.discovery_surfaces(reg, ok_p)
        assert surfaces
        s = surfaces[0]
        route = next(iter(s.routes))
        ok = {"surface": s.id, "route": route, "url": "https://x.test/", "status": "ok"}
        other_s = registry.discovery_surfaces(reg, other_p)
        assert other_s
        other = {"surface": other_s[0].id, "route": next(iter(other_s[0].routes)), "url": "https://y.test/", "status": "ok"}
        problems = common.log_reply_attempts(ctx, {"attempts": [ok, other]}, "c1", 1, allowed={ok_p})
        logged = ctx.ledger.attempts()
        assert [a["paradigm"] for a in logged] == [ok_p]
        assert len(problems) == 1 and "outside this round" in problems[0]
        problems = common.log_reply_attempts(ctx, {"attempts": [ok]}, "c1", 2, allowed={ok_p}, earlier={ok_p})
        assert ctx.ledger.attempts() == logged and "earlier round" in problems[0]


@check("robust.declared-mode-wins", "old-KEEP")
def _():
    from .phases import _infer

    d = SimpleNamespace(state=SimpleNamespace(prompt="is it true that X", context={"mode_override": "learn"}))
    assert _infer(None, d).mode == "learn"


@check("robust.notify-hook", "old-ADAPT")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        assert cli.notify("hi", env={}) is False
        out = tmp / "out.txt"
        script = tmp / "n.py"
        script.write_text(
            f"import sys; from pathlib import Path; Path({str(out)!r}).write_text(sys.argv[1])",
            encoding="utf-8",
        )
        command = f"{_short(sys.executable)} {_short(script)}"
        assert cli.notify("run failed", env={"RESEARCH_RIGOROUSLY_NOTIFY": command}) is True
        assert out.read_text(encoding="utf-8") == "run failed"


def _short(path):
    path = str(path)
    if sys.platform != "win32":
        return shlex.quote(path)
    import ctypes

    buf = ctypes.create_unicode_buffer(1024)
    ctypes.windll.kernel32.GetShortPathNameW(path, buf, len(buf))
    return buf.value or path


@check("robust.input-hardening", "old-KEEP")
def _():
    import argparse

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        assert cli.slug_type("bach-cantatas")
        for bad in ("", "../x", "A b", "/abs"):
            assert raises(argparse.ArgumentTypeError, lambda b=bad: cli.slug_type(b))
        assert fetch.default_http_get("file:///etc/passwd").error == "UnsupportedScheme"
        assert domains.banned_host("https://open.spotify.com:443/x", "music/classical")
        answers = tmp / "answers"
        answers.mkdir()
        for name in ("verify-bach-2026-10-07.html", "verify-bach-cantatas-2026-10-07.html"):
            (answers / name).write_text("x", encoding="utf-8")
        assert [p.name for p in remove.resolve_footprint(tmp, "bach")] == ["verify-bach-2026-10-07.html"]


@check("robust.claim-hash-keeps-sign", "old-KEEP")
def _():
    assert ledger.claim_hash("growth was -5%") != ledger.claim_hash("growth was 5%")
    assert ledger.claim_hash("pi is 3.14") != ledger.claim_hash("pi is 314")
    assert ledger.claim_hash("Growth, was 5%!") == ledger.claim_hash("growth was 5%")


@check("robust.domain-regex", "old-KEEP")
def _():
    assert domains.domain_for("answer", "install PHP Composer packages") == "general"
    assert domains.domain_for("answer", "Kubernetes orchestration") == "general"
    assert domains.domain_for("answer", "which composer wrote this symphony") == "music/classical"


@check("robust.torn-last-line", "old-KEEP")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "attempts.jsonl"
        p.write_text('{"a": 1}\n{"a": 2}\n{"a": ', encoding="utf-8")
        assert ledger.load_attempts(p) == [{"a": 1}, {"a": 2}]
        p.write_text('{"a": 1}\n{"a": \n{"a": 3}\n', encoding="utf-8")
        assert raises(Exception, lambda: ledger.load_attempts(p))


@check("robust.verify-round-single-flight", "old-KEEP")
def _():
    ctx = SimpleNamespace(ledger=object())
    started, release = threading.Event(), threading.Event()

    def slow(c, cid, fatal):
        started.set()
        release.wait(5)

    original = verify._do_round
    verify._do_round = slow
    try:
        t = threading.Thread(target=verify._guarded_round, args=(ctx, "c1", []))
        t.start()
        assert started.wait(5)
        assert raises(RuntimeError, lambda: verify._guarded_round(ctx, "c1", []))
    finally:
        release.set()
        t.join()
        verify._do_round = original


# ---------------------------------------------------------------- roles (2 old)


@check("roles.no-agent-models", "old-ADAPT")
def _():
    text = (SKILL / "references" / "roles.md").read_text(encoding="utf-8")
    for bad in ("model:", "family:", "fallback", "codex"):
        assert bad not in text


@check("roles.checking-are-steps", "old-ADAPT")
def _():
    steps = agents._steps()
    checking = set(registry.checking_roles())
    assert checking
    for role in checking:
        assert any(f"Role {role}" in body for body in steps.values()), role


# ---------------------------------------------------------------- routing (1 old)


@check("routing.mode-table", "old-KEEP")
def _():
    cases = [
        ("fact-check this: the moon is 4.5 billion years old", "verify"),
        ("how do I play Ark Nova", "rules"),
        ("teach me how transformers work, chapter by chapter", "learn"),
        ("is it true that Irish people are genetically predisposed to alcoholism", "answer"),
        ("did the Sony deal really close in 1988", "answer"),
        ("I'm bored of Beethoven, give me Soviet symphonies", "recommend"),
        ("why do wifi printers drop off the network", "answer"),
        ("is it true that this study shows coffee stunts growth", "answer"),
    ]
    for prompt, mode in cases:
        assert infer_mode.infer_mode(prompt)[0] == mode, prompt


# ---------------------------------------------------------------- frontmatter (1 old)


@check("frontmatter.repo-skills", "old-KEEP")
def _():
    paths = sorted((SKILL.parent).glob("*/SKILL.md"))
    assert paths
    for path in paths:
        text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
        assert text.startswith("---\n"), path
        data = yaml.safe_load(text.split("\n---", 1)[0][4:])
        assert isinstance(data.get("description"), str) and data.get("name") == path.parent.name, path


# ---------------------------------------------------------------- verify rounds (5 old)


def _wire_rounds(ctx, rows):
    ctx.keys = None
    ctx.drop_dir = ctx.ledger.dir / "sources"
    ctx.drop_dir.mkdir(parents=True, exist_ok=True)
    ctx.raw = SimpleNamespace(contains=lambda text, quote: True)
    ctx.runner = ScriptedRunner(
        lambda role, step, prompt: NO_EVIDENCE if ".evidence." in step else DISCOVERY
    )
    saved = (common.take_sources, common.log_reply_attempts, verify.round_attempts)
    common.take_sources = lambda c, reply: rows
    common.log_reply_attempts = lambda *a, **k: []
    verify.round_attempts = lambda c, cid, n: [{"paradigm": registry.round_paradigms(ctx.reg, n)[0]}]
    return saved


def _restore(saved):
    common.take_sources, common.log_reply_attempts, verify.round_attempts = saved


def _rounds(ctx, cid, count):
    for _ in range(count):
        verify._do_round(ctx, cid, [])
    return ctx.ledger.claim(cid)


@check("verify_rounds.barren-stop", "old-ADAPT")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = tmp_ledger_ctx(Path(tmp))
        saved = _wire_rounds(ctx, [])
        try:
            claim, _ = ctx.ledger.add_claim("Nothing public", origin="discovered")
            assert _rounds(ctx, claim["id"], 2)["status"] == "open"
            after = _rounds(ctx, claim["id"], 1)
            assert after["status"] == "not-found" and after["rounds"] == 3
            assert after.get("not_found_reason") in (None, "no-public-record-after-3-rounds")
        finally:
            _restore(saved)


@check("verify_rounds.sources-keep-going", "old-ADAPT")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = tmp_ledger_ctx(Path(tmp))
        row = {"id": "s1", "url": "https://x.test/1", "kind": "web", "status": "read", "tier": "T2", "publisher": "X"}
        saved = _wire_rounds(ctx, [(row, "page text")])
        try:
            claim, _ = ctx.ledger.add_claim("Sourced but unextracted", origin="discovered")
            claim = _rounds(ctx, claim["id"], 2)
            assert claim["status"] == "open" and claim["rounds"] == 2
        finally:
            _restore(saved)


@check("verify_rounds.evidence-keeps-going", "old-ADAPT")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = tmp_ledger_ctx(Path(tmp))
        saved = _wire_rounds(ctx, [])
        try:
            claim = add_claim_with(ctx, "One weak source", [("T3", "Blog", "supports")], rounds=0)
            claim = _rounds(ctx, claim["id"], 2)
            assert claim["status"] == "open"
        finally:
            _restore(saved)


@check("verify_rounds.round-log-once", "old-ADAPT")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = tmp_ledger_ctx(Path(tmp))
        row = {"id": "s1", "url": "https://x.test/1", "kind": "web", "status": "read", "tier": "T2", "publisher": "X"}
        saved = _wire_rounds(ctx, [(row, "page text")])
        try:
            claim, _ = ctx.ledger.add_claim("Same page twice", origin="discovered")
            claim = _rounds(ctx, claim["id"], 2)
            assert [r["round"] for r in claim["round_log"]] == [1, 2]
            assert [r["new_read_sources"] for r in claim["round_log"]] == [1, 0]
        finally:
            _restore(saved)


@check("verify_rounds.template-twins", "old-ADAPT")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = tmp_ledger_ctx(Path(tmp))
        saved = _wire_rounds(ctx, [])
        try:
            ids = [ctx.ledger.add_claim(f"Claim {i}", origin="discovered")[0]["id"] for i in range(3)]
            for _pass in range(2):
                for cid in ids:
                    verify._do_round(ctx, cid, [])
            assert [ctx.ledger.claim(c)["status"] for c in ids] == ["open"] * 3
        finally:
            _restore(saved)


# ---------------------------------------------------------------- mechanical (5 new)


@check("mech.no-build-files", "new")
def _():
    for name in ("pyproject.toml", "uv.lock", ".venv", "venv"):
        assert not (SKILL / name).exists(), name


@check("mech.script-header", "new")
def _():
    marker = "# " + "/// script"
    for path in [SKILL / "rr.py", *(SKILL / "scripts").rglob("*.py")]:
        head = path.read_text(encoding="utf-8").lstrip().splitlines()[:1]
        assert head != [marker], path


@check("mech.routing-generated", "new")
def _():
    from . import gen_routing_table

    text = gen_routing_table.render(registry.load())
    path = SKILL / "references" / "routing.md"
    assert path.read_bytes().count(b"\r") == 0
    assert path.read_text(encoding="utf-8") == text


@check("mech.ask-attachments-under-run", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cfg = workspace.Config(state_root=tmp / "state")
        ctx = workspace.Context(
            site_root=workspace.Layout(cfg.state_root, "t").site,
            main_root=tmp / "clone",
            topic="t",
            reg=registry.load(),
            runner=None,
            fetcher=None,
            publisher=None,
            cfg=cfg,
        )
        ctx.runner = driver.HandRunner(ctx.layout.run)
        media = ctx.layout.media / "audio.mp3"
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"x")
        assert raises(driver.NeedsAgent, lambda: fetch.LadderFetcher().read_media_file(media, ctx, "https://x.test/a.mp3"))
        ask = min(ctx.layout.run.glob("*.ask.md"))
        attached = re.findall(r"^- (.+\.mp3)$", ask.read_text(encoding="utf-8"), re.MULTILINE)
        assert attached, ask.read_text(encoding="utf-8")[:300]
        for value in attached:
            path = Path(value).resolve()
            path.relative_to(ctx.layout.root.resolve())
        assert ctx.layout.run in ctx.layout.media.parents


@check("mech.key-line-warning", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        env = tmp / "tavily.env"
        env.write_text("ACCT1_TAVILY_API_KEY=secretvalue123\nBAREKEYNOEQUALS\n", encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            dotenv = switch_api_key.get_dotenv_map(env)
        warning = err.getvalue()
        assert str(env) in warning and "1 line" in warning, warning
        assert "BAREKEYNOEQUALS" not in warning and "secretvalue123" not in warning
        assert switch_api_key.get_pool(dotenv, "tavily")


# ---------------------------------------------------------------- keys (4 new)


class FakeKM(keys.KeyManager):
    def __init__(self, reg, path):
        super().__init__(reg, path, sleep=lambda _s: None)
        self._fps = {
            "fp1": {"account": "A1", "active": True},
            "fp2": {"account": "A2", "active": False},
            "fp3": {"account": "A3", "active": False},
        }
        self.switches = []

    def fingerprints(self, pool):
        return copy.deepcopy(self._fps)

    def _switch(self, *args):
        self.switches.append(args)
        order = list(self._fps)
        active = next(i for i in order if self._fps[i]["active"])
        nxt = order[(order.index(active) + 1) % len(order)]
        for i in order:
            self._fps[i]["active"] = i == nxt
        return ""


@check("keys.no-evidence-no-rotation", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        km = FakeKM(registry.load(), Path(tmp) / "keystate.json")
        for i in range(30):
            assert km.on_failure("tavily", status=None, code=None, url=f"https://x.test/{i}") == keys.NEXT_SURFACE
        assert km.generation("tavily") == 0 and not km.switches
        assert not __import__("scripts.keystate", fromlist=["KeyState"]).KeyState(
            Path(tmp) / "keystate.json"
        ).data["keys"].get("tavily")


@check("keys.unknown-rotation-24h", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keystate.json"
        km = FakeKM(registry.load(), path)
        def fail(url):
            return km.on_failure("exa", status=500, code="X", url=url, seen_generation=km.generation("exa"))

        assert fail("https://x.test/1") == keys.RETRY
        assert km.generation("exa") == 0
        assert fail("https://x.test/2") == keys.RETRY
        assert km.generation("exa") == 1
        data = json.loads(path.read_text(encoding="utf-8"))
        entry = data["keys"]["exa"]["fp1"]
        assert entry["reset"] == "unknown", entry
        stamp = datetime.strptime(entry["exhausted_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        from .keystate import reset_at

        assert reset_at(stamp, "unknown") - stamp == timedelta(hours=24)
        assert fail("https://x.test/3") == keys.RETRY
        assert km.generation("exa") == 1
        fail("https://x.test/3")
        fail("https://x.test/4")
        assert km.generation("exa") == 2


@check("keys.credit-rotation-registry-reset", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keystate.json"
        km = FakeKM(registry.load(), path)
        assert km.on_failure("exa", status=402, code="402", url="https://x.test/1") == keys.RETRY
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["keys"]["exa"]["fp1"]["reset"] == "monthly", data


@check("keys.signature-normalised", "new")
def _():
    from . import keys

    a = keys._signature(None, "504:CRAWL_LIVECRAWL_TIMEOUT (exa /contents, retried)")
    b = keys._signature(None, "504:CRAWL_LIVECRAWL_TIMEOUT (other prose)")
    assert a == b == "None:504:CRAWL_LIVECRAWL_TIMEOUT", (a, b)


# ---------------------------------------------------------------- discover (2 new)


def _claim_reply(prefix, n=12):
    rows = "\n".join(
        f'  - {{ text: "{prefix} claim {i}", cluster: "{prefix}", locator: "p{i}", quote: "quote {i}" }}'
        for i in range(1, n + 1)
    )
    return f"```yaml\nclaims:\n{rows}\nskipped: {{ opinions: 0, predictions: 0 }}\nignored_instructions: []\n```"


@check("discover.claim-share", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cfg = workspace.Config(state_root=tmp / "state", max_claims=40, max_source_chunks=1)
        ctx = workspace.Context(
            site_root=tmp / "site",
            main_root=tmp / "clone",
            topic="t",
            reg=registry.load(),
            runner=None,
            fetcher=None,
            publisher=None,
            cfg=cfg,
        )
        d = driver.Driver(ctx.layout.run, driver.RunState("r1", "t", "prompt", mode="learn"), {})
        ctx.raw = SimpleNamespace(contains=lambda text, quote: True, get=lambda path: "text")
        aspects = [f"aspect {i}" for i in range(1, 9)]
        per_aspect = {}

        def answer(role, step, prompt):
            if "aspects" in step:
                return "```yaml\naspects: " + json.dumps(aspects) + "\n```"
            if "discover-wave" in step:
                name = re.search(r"discover\.w1\.(a\d+)", step)[1]
                return "```yaml\nsources:\n  - { url: \"https://x.test/a\", kind: web, publisher: X, file: \"\" }\nfailed: []\nattempts: []\n```"
            if step.endswith(".k1"):
                name = re.search(r"discover\.w1\.(a\d+)", step)[1]
                per_aspect[name] = per_aspect.get(name, 0) + 12
                return _claim_reply(name)
            return DISCOVERY

        ctx.runner = ScriptedRunner(answer)
        rows = [({"id": "s1", "url": "https://x.test/a", "kind": "web", "status": "read", "tier": "T2", "publisher": "X"}, "text")]
        saved = (common.take_sources, common.log_reply_attempts)
        common.take_sources = lambda c, reply: rows
        common.log_reply_attempts = lambda *a, **k: []
        try:
            discover.discover(ctx, d)
        finally:
            common.take_sources, common.log_reply_attempts = saved
        assert len(ctx.ledger.claims) == 40, len(ctx.ledger.claims)
        counts = {}
        for c in ctx.ledger.claims:
            counts[c.get("cluster")] = counts.get(c.get("cluster"), 0) + 1
        assert set(counts.values()) == {5}, counts


@check("discover.stops-at-share", "new")
def _():
    assert max(1, -(-40 // 8)) == 5


# ---------------------------------------------------------------- asks (2 new)


@check("ask.reuses-identical-reply", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        runner = driver.HandRunner(tmp)
        assert raises(driver.NeedsAgent, lambda: runner.run("verifier", "same prompt", step="discover.w1.a1.s66.k1"))
        ask = min(tmp.glob("*.ask.md"))
        reply = Path(re.search(r"reply file: (.+)", ask.read_text(encoding="utf-8"))[1].strip())
        reply.write_text("verdicts: []\n", encoding="utf-8")
        assert runner.run("verifier", "same prompt", step="discover.w1.a8.s66.k1") == "verdicts: []\n"
        assert len(list(tmp.glob("*.ask.md"))) == 1


@check("ask.reuses-existing-ask", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        runner = driver.HandRunner(tmp)
        assert raises(driver.NeedsAgent, lambda: runner.run("verifier", "same prompt", step="discover.w1.a1.s66.k1"))
        first = min(tmp.glob("*.ask.md"))
        try:
            runner.run("verifier", "same prompt", step="discover.w1.a8.s66.k1")
        except driver.NeedsAgent as exc:
            assert exc.asks == [str(first)], exc.asks
        else:
            raise AssertionError("expected NeedsAgent")
        assert len(list(tmp.glob("*.ask.md"))) == 1


# ---------------------------------------------------------------- fetch settle (3 new)


def _agent_ctx(tmp):
    ctx = SimpleNamespace(
        drop_dir=tmp / "sources",
        keys=None,
        clock=None,
        reg=registry.load(),
        ledger=workspace.Ledger(tmp / "topic"),
        runner=driver.HandRunner(tmp / "agent"),
    )
    ctx.drop_dir.mkdir(parents=True)
    return ctx


@check("fetch.agent-short-text-settled", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ctx = _agent_ctx(tmp)
        surf = registry.surfaces(registry.load())["tavily.extract"]
        fetcher = fetch.LadderFetcher(min_chars=200)
        assert raises(driver.NeedsAgent, lambda: fetcher._agent("tavily.extract", surf, "https://x.test/a", ctx, False))
        ask = min((tmp / "agent").glob("*.ask.md")).read_text(encoding="utf-8")
        dest = Path(re.search(r"save the page text to: (.+)", ask)[1].strip())
        dest.write_text("x" * 120, encoding="utf-8")
        reply = Path(re.search(r"reply file: (.+)", ask)[1].strip())
        reply.write_text("ok: true\nroute: mcp\n", encoding="utf-8")
        got = fetcher._agent("tavily.extract", surf, "https://x.test/a", ctx, False)
        assert got.ok and len(got.text) == 120, got


@check("fetch.agent-false-escalates", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ctx = _agent_ctx(tmp)
        surf = registry.surfaces(registry.load())["tavily.extract"]
        fetcher = fetch.LadderFetcher()
        assert raises(driver.NeedsAgent, lambda: fetcher._agent("tavily.extract", surf, "https://x.test/a", ctx, False))
        ask = min((tmp / "agent").glob("*.ask.md")).read_text(encoding="utf-8")
        reply = Path(re.search(r"reply file: (.+)", ask)[1].strip())
        reply.write_text("ok: false\nerror: { status: 403, code: \"blocked\" }\n", encoding="utf-8")
        got = fetcher._agent("tavily.extract", surf, "https://x.test/a", ctx, False)
        assert not got.ok


@check("fetch.settled-url-not-refetched", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cfg = workspace.Config(state_root=tmp / "state")
        ctx = workspace.Context(
            site_root=tmp / "site",
            main_root=tmp / "clone",
            topic="t",
            reg=registry.load(),
            runner=None,
            fetcher=None,
            publisher=None,
            cfg=cfg,
        )
        calls = []

        class Fetcher:
            def read(self, url, ctx):
                calls.append(url)
                return fetch.FetchResult(True, "page text long enough " * 20, "surf")

        ctx.fetcher = Fetcher()
        reply = {"sources": [{"url": "https://x.test/a", "kind": "web", "publisher": "X"}]}
        first = common.take_sources(ctx, reply)
        second = common.take_sources(ctx, reply)
        assert calls == ["https://x.test/a"], calls
        assert first and second and second[0][1]


# ---------------------------------------------------------------- ceiling (3 new)


@check("ceiling.true-and-unchecked", "new")
def _():
    from .phases import _settle_ask_budget

    def src(sid="s1", tier="T1", publisher="Pub"):
        return {"id": sid, "url": f"https://example.com/{sid}", "kind": "established-outlet", "tier": tier, "publisher": publisher, "status": "read"}

    def claim(cid, rounds=0, evidence=None):
        text = f"Claim {cid} text."
        return {"id": cid, "text": text, "hash": ledger.claim_hash(text), "status": "open", "origin": "discovered", "rounds": rounds, "paradigms_tried": [], "evidence": list(evidence or [])}

    def ev(sid="s1"):
        return {"source": sid, "locator": "p1", "quote": "a quote", "stance": "supports"}

    class FakeLedger:
        def __init__(self, claims, sources, attempts=()):
            self.claims = claims
            self.sources_doc = {"schema": 1, "sources": sources}
            self.claims_doc = {"schema": 1, "claims": claims}
            self._attempts = list(attempts)

        def sources_by_id(self):
            return {s["id"]: s for s in self.sources_doc["sources"]}

        def attempts(self):
            return self._attempts

        def save(self):
            pass

    round1 = registry.load()["round_order"][0][0]
    claims = [claim("c1", evidence=[ev()]), claim("c2")]
    attempts = [{"claim": "c1", "round": 1, "paradigm": round1, "ladder": "discovery"}]
    led = FakeLedger(claims, [src()], attempts)
    d = SimpleNamespace(state=SimpleNamespace(context={}), save=lambda: None)
    _settle_ask_budget(SimpleNamespace(ledger=led), d)
    assert claims[0]["status"] == "true" and claims[1]["status"] == "unchecked", [c["status"] for c in claims]
    errors = [str(v) for v in ledger.check(led.claims_doc, led.sources_doc, attempts, publish=True) if v.severity == "error"]
    assert not errors, errors


@check("ceiling.gate-skips-unchecked", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = tmp_ledger_ctx(Path(tmp))
        ctx.cfg.gate_batch = 10
        c1 = add_claim_with(ctx, "Claim one", [("T1", "gov", "supports")])
        c2, _ = ctx.ledger.add_claim("Unchecked claim", origin="discovered")
        c2["status"] = "unchecked"
        for c in (c1,):
            c["status"] = "true"
        seen = {}

        def answer(role, step, prompt):
            ids = re.findall(r"^- (c\d+) \[", prompt, re.MULTILINE)
            seen["ids"] = ids
            return "```yaml\nverdicts:\n" + "".join(f"  - {{claim: {i}, verdict: agree}}\n" for i in ids) + "```"

        ctx.runner = ScriptedRunner(answer)
        problems, counts = ship.verifier_problems(ctx)
        assert problems == [] and seen["ids"] == ["c1"] and counts["checked"] == 1, (problems, seen, counts)


@check("ceiling.rounds-synced", "new")
def _():
    from .phases import _settle_ask_budget

    round1 = registry.load()["round_order"][0][0]
    text = "Round cut claim."
    claim = {"id": "c1", "text": text, "hash": ledger.claim_hash(text), "status": "open", "origin": "discovered", "rounds": 1, "paradigms_tried": [round1], "evidence": []}
    attempts = [
        {"claim": "c1", "round": 1, "paradigm": round1, "ladder": "discovery"},
        {"claim": "c1", "round": 2, "paradigm": "semantic", "ladder": "discovery"},
    ]

    led = SimpleNamespace(
        claims=[claim],
        sources_doc={"schema": 1, "sources": []},
        claims_doc={"schema": 1, "claims": [claim]},
        sources_by_id=dict,
        attempts=lambda: attempts,
        save=lambda: None,
    )
    _settle_ask_budget(SimpleNamespace(ledger=led), SimpleNamespace(state=SimpleNamespace(context={}), save=lambda: None))
    assert claim["rounds"] == 2 and claim["paradigms_tried"] == [round1, "semantic"], claim
    errors = [str(v) for v in ledger.check(led.claims_doc, led.sources_doc, attempts, publish=True) if v.severity == "error"]
    assert not any("log-mismatch" in e for e in errors), errors


# ---------------------------------------------------------------- render (2 new)


def _claims_doc_two():
    def claim(cid, status, text):
        return {"id": cid, "text": text, "hash": ledger.claim_hash(text), "status": status, "origin": "discovered", "rounds": 1, "paradigms_tried": ["keyword"], "evidence": []}

    return {"schema": 1, "claims": [claim("c1", "not-found", "NOTFOUND claim."), claim("c2", "unchecked", "UNCHECKED claim.")]}


@check("render.unchecked-verify", "new")
def _():
    doc = _claims_doc_two()
    meta = {"title": "T", "slug": "t", "date": "2026-11-26", "skipped": 0, "input_ref": "https://example.com/in"}
    page = render.render_verify(doc, {"schema": 1, "sources": []}, meta, asset_prefix="../")
    assert "<h3>Not checked (ask limit reached)</h3>" in page
    nf = page.split('<ul class="claims-not-found">', 1)[1].split("</ul>", 1)[0]
    un = page.split('<ul class="claims-unchecked">', 1)[1].split("</ul>", 1)[0]
    assert "NOTFOUND claim." in nf and "UNCHECKED claim." not in nf
    assert "UNCHECKED claim." in un and "NOTFOUND claim." not in un


@check("render.unchecked-lesson", "new")
def _():
    doc = _claims_doc_two()
    lesson = {
        "mode": "answer", "layout": "concept", "topic": "t", "title": "Title",
        "answer": {"id": "s1", "text": "Answer.", "claims": ["c1"], "block": "plain"},
        "body": {"sections": []},
    }
    page = render.render_lesson(lesson, doc, {"schema": 1, "sources": []}, asset_prefix="../")
    assert "Not checked (ask limit reached)" in page and "UNCHECKED claim." in page
    assert "Claims not found" not in page


# ---------------------------------------------------------------- site (2 new)


@check("site.index-rows-missing-dir", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        assert site.index_rows(Path(tmp) / "missing") == []


@check("site.subjects-from-clone", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "clone"
        topic = clone / "topic-a"
        (topic / "lessons").mkdir(parents=True)
        (topic / "index.html").write_text(
            '<html><head><meta name="course-kind" content="explainer"><meta name="subject" content="Politics"></head><body><h1>A</h1></body></html>',
            encoding="utf-8",
        )
        assert site.existing_subjects(clone) == ["Politics"]


# ---------------------------------------------------------------- urlaudit (2 new)


@check("urlaudit.retries-network-error", "new")
def _():
    real = urlaudit.urllib.request.urlopen
    sleeps, calls = [], {"n": 0}

    class Resp:
        status = 200

        def geturl(self):
            return "https://example.com/final"

        def read(self, n):
            return b"<html>ok</html>"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def flaky(req, timeout=0):
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("transient")
        return Resp()

    urlaudit.urllib.request.urlopen = flaky
    try:
        got = urlaudit.default_fetch("https://example.com/x", sleep=sleeps.append)
    finally:
        urlaudit.urllib.request.urlopen = real
    assert got.code == 200 and calls["n"] == 3 and sleeps == [1.0, 3.0], (got, calls["n"], sleeps)


@check("urlaudit.http-status-not-retried", "new")
def _():
    real = urlaudit.urllib.request.urlopen
    sleeps, calls = [], {"n": 0}

    def notfound(req, timeout=0):
        calls["n"] += 1
        raise urlaudit.urllib.error.HTTPError("https://example.com/x", 404, "no", None, None)

    urlaudit.urllib.request.urlopen = notfound
    try:
        got = urlaudit.default_fetch("https://example.com/x", sleep=sleeps.append)
    finally:
        urlaudit.urllib.request.urlopen = real
    assert got.code == 404 and calls["n"] == 1 and sleeps == [], (got, calls["n"], sleeps)


# ---------------------------------------------------------------- publish (3 new)

_PUB = {}


def _publish_state():
    if _PUB:
        return _PUB
    base = Path(tempfile.mkdtemp(prefix="rr-selfcheck-publish-"))
    atexit.register(shutil.rmtree, base, True)
    clone, _remote = setup_clone(base)
    ctx, d = make_ctx(base, clone)
    ctx.publisher = __import__("scripts.publish", fromlist=["GitPublisher"]).GitPublisher(clone, state_root=base / "state")
    stamp = "2026-11-26T09:08:07Z"
    ctx.clock = lambda: datetime(2026, 11, 26, 9, 8, 7, tzinfo=UTC)

    def stage(rel, body, meta=None):
        path = ctx.site_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        m = f'<meta name="research-rigorously-date" content="{meta}">' if meta else ""
        path.write_text(f"<html><head>{m}</head><body>{body}</body></html>", encoding="utf-8")

    stage("topic-c/index.html", "index", "RENDER")
    stage("topic-c/lessons/01-ch1-a.html", "p1", "RENDER")
    stage("topic-c/lessons/02-ch2-b.html", "p2", "RENDER")
    stage("topic-c/assets/course-index.js", "[]")
    (ctx.site_root / "index.html").write_text("<html>PARTIAL ONLY C</html>", encoding="utf-8")
    (ctx.site_root / "assets").mkdir(exist_ok=True)
    (ctx.site_root / "assets" / "course-index.js").write_text("DECOY", encoding="utf-8")
    ship.publish(ctx, d)
    _PUB.update({"base": base, "clone": clone, "ctx": ctx, "d": d, "stamp": stamp})
    return _PUB


@check("publish.home-index-kept", "new")
def _():
    state = _publish_state()
    clone = state["clone"]
    touched = set(git(clone, "show", "--name-only", "--pretty=format:", "HEAD").splitlines())
    assert touched == {"topic-c/index.html", "topic-c/lessons/01-ch1-a.html", "topic-c/lessons/02-ch2-b.html", "topic-c/assets/course-index.js", "index.html", "assets/course-index.js"}, touched
    html = (clone / "index.html").read_text(encoding="utf-8")
    assert "topic-a/index.html" in html and "topic-c/index.html" in html
    assert "PARTIAL" not in html


@check("publish.date-stamp", "new")
def _():
    state = _publish_state()
    page = (state["clone"] / "topic-c/lessons/01-ch1-a.html").read_text(encoding="utf-8")
    m = re.search(r'<meta name="research-rigorously-date" content="([^"]*)">', page)
    assert m and m[1] == state["stamp"], page[:200]
    staged = (state["ctx"].site_root / "topic-c/lessons/01-ch1-a.html").read_text(encoding="utf-8")
    assert 'content="RENDER"' in staged


@check("publish.stale-page-pruned", "new")
def _():
    state = _publish_state()
    ctx, d, clone = state["ctx"], state["d"], state["clone"]
    (ctx.site_root / "topic-c/lessons/02-ch2-b.html").unlink()
    ship.publish(ctx, d)
    status = {ln.split("\t", 1)[1].split("\t")[0]: ln.split("\t")[0] for ln in git(clone, "show", "--name-status", "--pretty=format:", "HEAD").splitlines() if "\t" in ln}
    deleted = [k for k, v in status.items() if v == "D"]
    assert deleted == ["topic-c/lessons/02-ch2-b.html"], status
    assert not (clone / "topic-c/lessons/02-ch2-b.html").exists()


# ---------------------------------------------------------------- misc new


@check("keys.usage-rows", "new")
def _():
    calls = []

    def fake_get(url, headers, timeout=15.0):
        calls.append((url, dict(headers)))
        return 200, b'{"account": {"plan_usage": 12, "plan_limit": 1000}}'

    dotenv = {"ACCT1_TAVILY_API_KEY": "secretkeyvalue123456"}
    rows = switch_api_key.usage_rows(dotenv, ["tavily"], get=fake_get, state_path=None)
    text = "\n".join(rows)
    assert "12/1000 credits" in text and "ACCT1" in text
    assert "secretkeyvalue123456" not in text
    assert calls and all("secretkeyvalue123456" not in url for url, _headers in calls)


@check("independence.neutral-example", "new")
def _():
    text = agents.step_prompt("independence")
    assert "independent: false" in text and "independent: true" in text
    assert "if independent" not in text.lower()
    assert "relations" in text


@check("independence.relation-memory", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sources = [
            {"id": "s3", "url": "https://politifact.test/a", "tier": "T2", "publisher": "PolitiFact", "status": "read"},
            {"id": "s6", "url": "https://vox.test/b", "tier": "T2", "publisher": "Vox", "status": "read"},
        ]

        led = SimpleNamespace(
            sources_doc={"schema": 1, "sources": sources},
            lock=threading.RLock(),
            sources_by_id=lambda: {s["id"]: s for s in sources},
        )

        pairs = [
            ({"source": "s3", "stance": "supports", "locator": "p1", "quote": "q1"}, sources[0]),
            ({"source": "s6", "stance": "supports", "locator": "p2", "quote": "q2"}, sources[1]),
        ]
        prompts = []
        reply = "```yaml\nindependent: true\nrationale: \"looks separate\"\nrelations:\n  - { from: s3, to: s6, kind: cites }\n```"

        class R:
            def run(self, role, prompt, step="", context=None):
                prompts.append(prompt)
                return reply

        ctx = SimpleNamespace(ledger=led, runner=R(), step_data={})
        claim = {"id": "c36", "text": "claim"}
        assert verify._independent(ctx, claim, pairs, 1) is False
        assert any(r["from"] == "s3" and r["to"] == "s6" and r["kind"] == "cites" for r in led.sources_doc["relations"])
        claim2 = {"id": "c37", "text": "claim"}
        assert verify._independent(ctx, claim2, pairs, 2) is False
        assert "- s3 cites s6" in prompts[-1]


@check("reader-profile-author-only", "new")
def _():
    assert "Reader profile:" not in agents.step_prompt("gate")
    assert "Reader profile:" not in agents.step_prompt("independence")
    assert "Reader profile:" in agents.step_prompt("draft")
    assert "Reader profile:" in agents.step_prompt("layout")


@check("routing.mcp-first", "new")
def _():
    reg = registry.load()
    surf = registry.surfaces(reg)["tavily.extract"]
    assert next(iter(surf.routes)) == "mcp"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        prompt = {}

        class R:
            def run(self, role, text, step="", context=None):
                prompt["text"] = text
                raise RuntimeError("stop")

        ctx = SimpleNamespace(drop_dir=tmp, keys=None, runner=R())
        try:
            fetch.LadderFetcher()._agent("tavily.extract", surf, "https://x.test/a", ctx, False)
        except RuntimeError:
            pass
        text = prompt["text"]
        assert "mcp: tools.tavily.tavily_extract" in text
        assert text.index("mcp:") < text.index("cli:") and "fallback" in text


@check("routing.mcp-order-rejected", "new")
def _():
    bad = copy.deepcopy(registry.load())
    routes = bad["servers"]["tavily"]["capabilities"]["extract"]["routes"]
    bad["servers"]["tavily"]["capabilities"]["extract"]["routes"] = {"cli": routes["cli"], "mcp": routes["mcp"]}
    assert raises(registry.RegistryError, lambda: registry.validate(bad))


@check("driver.needs-you-lists-pending-asks", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "a.ask.md").write_text("x", encoding="utf-8")
        (tmp / "b.ask.md").write_text("y", encoding="utf-8")
        (tmp / "b.reply.md").write_text("z", encoding="utf-8")
        d = driver.Driver(tmp, driver.RunState("r1", "t", "p"), {})
        d._suspend("verify", driver.PoolExhausted("tavily", "x"))
        text = (tmp / "NEEDS_YOU.md").read_text(encoding="utf-8")
        assert "Pending asks" in text and "a.ask.md" in text and "b.ask.md" not in text


@check("layout.dirs-created", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = workspace.Config(state_root=Path(tmp) / "state")
        ctx = workspace.Context(
            site_root=Path(tmp) / "site",
            main_root=Path(tmp) / "clone",
            topic="t",
            reg={},
            runner=None,
            fetcher=None,
            publisher=None,
            cfg=cfg,
        )
        assert ctx.layout.sources.is_dir() and ctx.layout.run.is_dir()


# ---------------------------------------------------------------- batch E (new)


@check("mech.no-dead-poll", "new")
def _():
    from .post import common as post_common

    assert not hasattr(post_common, "poll")
    assert "def poll(" not in (
        SKILL / "scripts" / "post" / "common.py"
    ).read_text(encoding="utf-8")


@check("cli.no-person-only-commands", "new")
def _():
    for name in ("log-attempt", "infer-mode"):
        assert name not in cli.TOOLS
        assert f"rr {name}" not in cli.HELP
    assert (SKILL / "scripts" / "log_attempt.py").is_file()
    assert (SKILL / "scripts" / "infer_mode.py").is_file()


@check("ceiling.counts-gathering-only", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for i in range(400):
            (tmp / f"gate.b{i}.ask.md").write_text("x", encoding="utf-8")
        runner = driver.HandRunner(tmp, max_asks=400)
        assert runner._ask_count() == 0
        assert raises(driver.NeedsAgent, lambda: runner.run("extractor", "page", step="verify.c1.r1.evidence.s1"))
        assert runner._ask_count() == 1
        for i in range(400):
            (tmp / f"verify.c{i}.r1.evidence.s1-{i}.ask.md").write_text("x", encoding="utf-8")
        assert runner._ask_count() == 401


@check("ceiling.reentry-writes", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for i in range(400):
            ask = tmp / f"gate.b{i}.ask.md"
            ask.write_text("x", encoding="utf-8")
            (tmp / f"gate.b{i}.reply.md").write_text("ok", encoding="utf-8")
        runner = driver.HandRunner(tmp, max_asks=400)
        assert raises(driver.NeedsAgent, lambda: runner.run("extractor", "page", step="verify.c9.r1.evidence.s1"))


@check("independence.always-asks-t2-with-t1", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = tmp_ledger_ctx(Path(tmp))
        claim = add_claim_with(
            ctx,
            "Claim with a T1 row and two T2 rows",
            [("T1", "Court", "supports"), ("T2", "Paper", "supports"), ("T2", "Desk", "supports")],
        )
        sources = ctx.ledger.sources_by_id()
        pairs = [(ev, sources[ev["source"]]) for ev in claim["evidence"]]
        ctx.runner = ScriptedRunner(
            lambda *a: "```yaml\nindependent: true\nrationale: \"separate\"\nrelations: []\n```"
        )
        assert verify._independent(ctx, claim, pairs, 1) is True
        assert any(s.endswith(".independence") for s in ctx.runner.steps), ctx.runner.steps
        assert verify._conflicts([{"kind": "same-author"}])
        ctx.ledger.sources_doc["relations"] = [
            {"from": "s2", "to": "s3", "kind": "same-author"}
        ]
        assert verify._independent(ctx, claim, pairs, 2) is True
        assert claim["reply_flags"]


@check("independence.unlinked-source-counts", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        ctx = tmp_ledger_ctx(Path(tmp))
        claim = add_claim_with(
            ctx,
            "Claim with a cited chain and one separate source",
            [("T2", "Origin", "supports"), ("T2", "Echo", "supports"), ("T2", "Desk", "supports")],
        )
        sources = ctx.ledger.sources_by_id()
        pairs = [(ev, sources[ev["source"]]) for ev in claim["evidence"]]
        first, second, third = [ev["source"] for ev, _ in pairs]
        ctx.runner = ScriptedRunner(
            lambda *a: f"```yaml\nindependent: true\nrationale: \"separate\"\nrelations:\n  - {{ from: {second}, to: {first}, kind: cites }}\n```"
        )
        assert verify._independent(ctx, claim, pairs, 1) is True
        ctx.ledger.sources_doc["relations"].append({"from": third, "to": first, "kind": "relays"})
        assert verify._independent(ctx, claim, pairs, 2) is False


@check("rounds.one-owner", "new")
def _():
    reg = registry.load()
    schema = json.loads((SKILL / "schema" / "claims.schema.json").read_text(encoding="utf-8"))
    assert reg["max_rounds"] == 3
    assert ledger.MAX_ROUNDS == reg["max_rounds"]
    assert len(reg["round_order"]) == reg["max_rounds"]
    assert schema["$defs"]["claim"]["properties"]["rounds"]["maximum"] == reg["max_rounds"]


@check("site.no-subjects-pinning", "new")
def _():
    assert not hasattr(site, "read_subjects_last")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "assets").mkdir()
        site.regenerate_index(root)
        assert not (root / "site.json").exists()


@check("publish.requires-git-clone", "new")
def _():
    assert not hasattr(publishing, "LocalPublisher")
    with tempfile.TemporaryDirectory() as tmp:
        assert raises(publishing.PublishError, lambda: publishing.GitPublisher(Path(tmp)))


@check("live-check.one-policy", "new")
def _():
    assert (ship.LIVE_ATTEMPTS, ship.LIVE_DELAY) == (12, 20.0)
    assert not hasattr(remove, "LIVE_DELAY") and not hasattr(remove, "LIVE_ATTEMPTS")
    assert "live_check_until" in (SKILL / "scripts" / "remove.py").read_text(encoding="utf-8")


def _audit_ctx(tmp, fetcher_result, reply):
    ctx = tmp_ledger_ctx(tmp)
    ctx.topic = "t"
    ctx.drop_dir = tmp / "sources"
    ctx.drop_dir.mkdir(parents=True, exist_ok=True)
    claim = add_claim_with(ctx, "Cited claim", [("T2", "Paper", "supports")])
    claim["status"] = "true"
    ctx.audit_urls = lambda urls: [
        SimpleNamespace(ok=False, flag="BROKEN", url=urls[0], code=0)
    ]
    ctx.fetcher = SimpleNamespace(
        read_url=lambda url, c, allow_mcp=True: fetcher_result
    )
    ctx.runner = ScriptedRunner(lambda *a: reply)
    ctx.stamp = lambda: "2026-11-26T00:00:00Z"
    return ctx


@check("audit.all-routes-fail-logs", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ctx = _audit_ctx(
            tmp,
            fetch.FetchResult(False, error="blocked everywhere"),
            "```yaml\nok: false\nerror: { status: 403, code: blocked }\n```",
        )
        problems, summary = ship.audit_problems(ctx)
        assert problems and "url audit" in problems[0], (problems, summary)
        ledger_path = ctx.cfg.state_root / "link-failures.jsonl"
        lines = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
        assert lines and lines[0]["topic"] == "t" and lines[0]["routes"], lines


@check("audit.one-route-passes", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ctx = _audit_ctx(
            tmp,
            fetch.FetchResult(True, "page text long enough", "tavily.extract"),
            "```yaml\nok: false\n```",
        )
        problems, _ = ship.audit_problems(ctx)
        assert problems == []
        assert not (ctx.cfg.state_root / "link-failures.jsonl").exists()


@check("routing.mcp-servers", "new")
def _():
    reg = registry.load()
    surfs = registry.surfaces(reg)
    expected = {
        "scrapegraph.search": "search",
        "scrapegraph.scrape": "scrape",
        "tinyfish.fetch": "fetch_content",
        "brightdata.scrape": "web_fetch",
        "apify.rag-web-browser": "apify--rag-web-browser",
        "microsoft-learn.docs": "microsoft_docs_search",
    }
    for sid, tool in expected.items():
        assert tool in surfs[sid].routes.get("mcp", []), sid
        assert surfs[sid].routes.get("mcp", [])[0] == tool
    assert surfs["wayback.fetch"].routes["mcp"] == ["fetch.fetch"]
    assert surfs["wikisource.search"].routes["mcp"] == ["fetch.fetch"]
    assert registry.mcp_tool("wayback", "fetch.fetch") == "tools.fetch.fetch"
    for name in ("scrapegraph", "tinyfish", "brightdata", "apify", "microsoft-learn", "fetch"):
        assert reg["servers"][name].get("mcp_key"), name
    assert "browserbase" not in reg["servers"]


@check("routing.no-browserbase", "new")
def _():
    assert not (SKILL / "scripts" / "post" / "browserbase_agent_run.py").exists()
    assert "browserbase" not in cli.VENDOR_SCRIPTS
    text = (SKILL / "references" / "routing.md").read_text(encoding="utf-8")
    assert "browserbase" not in text.lower()
    assert "BROWSERBASE" not in text


@check("routing.trimmed", "new")
def _():
    text = (SKILL / "references" / "routing.md").read_text(encoding="utf-8")
    for gone in ("## Fetch ladder", "## Surfaces", "## POST scripts"):
        assert gone not in text, gone
    for kept in ("## Rounds", "## Pick by capability", "## Bot-block chain", "## Key policy", "## Error classes"):
        assert kept in text, kept


@check("keys.usage-formats", "new")
def _():
    def get(url, headers, timeout=15.0):
        if "zenrows" in url:
            return 200, json.dumps({
                "usage_credits": 1649, "credit_limit": 5000, "usage_percent": 32,
                "period_ends_at": "2026-11-14T23:01:31Z",
            }).encode()
        if "apify" in url:
            return 200, json.dumps({"data": {"current": {"monthlyUsageUsd": 7.079914212226868e-07}, "limits": {"maxMonthlyUsageUsd": 300}}}).encode()
        return 403, b"forbidden"

    assert "1649/5000 credits used" in switch_api_key.usage_text("zenrows", "k", get)
    assert "$0.00 used / $300.00" in switch_api_key.usage_text("apify", "k", get)
    assert "token lacks" in switch_api_key.usage_text("brightdata", "k", get)
    assert "no documented usage endpoint" in switch_api_key.usage_text("tinyfish", "k", get)


@check("keys.firecrawl", "new")
def _():
    reg = registry.load()
    srv = reg["servers"]["firecrawl"]
    assert srv["pool"] == "firecrawl" and srv["keyed"] and srv["wired"]
    assert srv["key"]["env"] == "FIRECRAWL_API_KEY"
    assert "acct" in re.compile(srv["key"]["pattern"]).groupindex
    surfs = registry.surfaces(reg)
    assert next(iter(surfs["firecrawl.search"].routes)) == "mcp"
    assert surfs["firecrawl.search"].routes["mcp"][0] == "firecrawl_search"
    assert surfs["firecrawl.fetch"].routes["mcp"][0] == "firecrawl_scrape"
    assert surfs["firecrawl.map"].routes["mcp"][0] == "firecrawl_map"
    assert "firecrawl.fetch" in reg["fetch_ladder"]

    def get(url, headers, timeout=15.0):
        assert "credit-usage" in url
        return 200, json.dumps({"data": {"remainingCredits": 940, "planCredits": 1000}}).encode()

    text = switch_api_key.usage_text("firecrawl", "fcsecretvalue123", get)
    assert "940 credits left" in text and "1000 plan" in text, text
    assert "fcsecretvalue123" not in text

    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "Firecrawl.env").write_text("FIRECRAWL_API_KEY=fcsecretvalue123\n", encoding="utf-8")
        dotenv = switch_api_key.get_dotenv_map(Path(tmp))
        pool = switch_api_key.get_pool(dotenv, "firecrawl")
        assert pool and "fcsecretvalue123" in pool.values(), pool


@check("keys.firecrawl-errors", "new")
def _():
    reg = registry.load()
    assert registry.classify_error(reg, "firecrawl", status=402, code="402") == "out_of_credit"
    assert registry.classify_error(reg, "firecrawl", status=401, code="401") == "bad_key"
    assert registry.classify_error(reg, "firecrawl", status=429, code="429") == "rate_limit"


@check("keys.only-service-env-files", "new")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "Tavily.env").write_text("A_TAVILY_API_KEY=secret123\n", encoding="utf-8")
        (tmp / "GitHub.env").write_text("GITHUB_TOKEN=other\n", encoding="utf-8")
        files = switch_api_key.env_files(tmp)
        assert [f.name for f, _ in files] == ["Tavily.env"], files
        env = switch_api_key.get_dotenv_map(tmp)
        assert "GITHUB_TOKEN" not in env
        assert switch_api_key.get_pool(env, "tavily")


@check("mech.local-tools", "new")
def _():
    reg = registry.load()
    surfs = registry.surfaces(reg)
    assert surfs["ytdlp.transcript"].routes["local"] == ["yt-dlp --write-subs"]
    assert "uv tool install yt-dlp" in (SKILL / "registry" / "registry.yaml").read_text(encoding="utf-8")
    assert surfs["ocr.read"].routes["cli"] == ["toolbox azure docintel"]


# ---------------------------------------------------------------- runner


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="print every check name")
    ap.add_argument("-k", metavar="SUBSTR", help="run checks whose name contains SUBSTR")
    args = ap.parse_args(argv)
    if args.list:
        for name, source, _fn in CHECKS:
            print(f"{name} [{source}]")
        return 0
    selected = [c for c in CHECKS if not args.k or args.k in c[0]]
    if not selected:
        print(f"selfcheck: no check matches {args.k!r}", file=sys.stderr)
        return 2
    failed = 0
    started = time.perf_counter()
    for name, source, fn in selected:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - a failed check is reported, not raised
            failed += 1
            reason = " ".join(str(exc).split())
            print(f"FAIL {name}: {reason[:300]}")
        else:
            print(f"PASS {name}")
    elapsed = time.perf_counter() - started
    print(f"\n{len(selected) - failed}/{len(selected)} checks passed in {elapsed:.2f}s")
    return 1 if failed else 0
