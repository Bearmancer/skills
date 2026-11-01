"""#340: the skill never launches another harness; the loading agent answers every AI step."""

import ast
from types import SimpleNamespace
import re
from pathlib import Path

import pytest
import yaml

from scripts import driver

SKILL = Path(__file__).resolve().parent.parent
AGENT_CLIS = {
    "opencode",
    "agy",
    "antigravity",
    "claude",
    "codex",
    "gemini",
    "kilo",
    "kilocode",
    "aider",
    "cursor-agent",
    "goose",
    "crush",
    "qwen",
    "amp",
    "droid",
    "copilot",
    "omo",
}
_HEAD = re.compile(r"^([\w.-]+?)(?:\.exe|\.cmd|\.ps1)?(?:\s|$)", re.I)


def _agent_head(text):
    m = _HEAD.match(text.strip())
    return m and m[1].lower() in AGENT_CLIS


def agent_cli_uses(source, name="<src>"):
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.List, ast.Tuple)) and node.elts:
            first = node.elts[0]
            if (
                isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and _agent_head(first.value)
            ):
                found.append(
                    f"{name}:{node.lineno}: command list starts {first.value!r}"
                )
        elif isinstance(node, ast.Call):
            fn = node.func
            called = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            arg = node.args[0] if node.args else None
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                continue
            if called == "which" and _agent_head(arg.value):
                found.append(f"{name}:{node.lineno}: looks up {arg.value!r} on PATH")
            elif (
                called
                in {
                    "run",
                    "Popen",
                    "call",
                    "check_call",
                    "check_output",
                    "system",
                    "_cmd",
                    "run_cmd",
                }
                and re.match(r"^\S+\s", arg.value)
                and _agent_head(arg.value)
            ):
                found.append(f"{name}:{node.lineno}: runs {arg.value!r}")
    return found


def test_the_detector_catches_an_agent_cli():
    assert agent_cli_uses('subprocess.run(["opencode", "run", "x"])')
    assert agent_cli_uses('cmd = ["agy", "-p=x"]')
    assert agent_cli_uses('shutil.which("opencode")')
    assert agent_cli_uses('os.system("claude -p hi")')
    assert not agent_cli_uses('Path.home() / ".config" / "opencode" / "secrets"')
    assert not agent_cli_uses('subprocess.run(["git", "status"])')


def test_no_skill_code_starts_an_agent_cli():
    found = []
    for path in sorted((SKILL / "scripts").rglob("*.py")):
        found += agent_cli_uses(
            path.read_text(encoding="utf-8"), path.relative_to(SKILL).as_posix()
        )
    reg = yaml.safe_load(
        (SKILL / "registry" / "registry.yaml").read_text(encoding="utf-8")
    )
    for name, server in (reg.get("servers") or {}).items():
        for surface in (server.get("surfaces") or {}).values():
            for cmd in ((surface or {}).get("routes") or {}).get("cli") or []:
                if _agent_head(str(cmd)):
                    found.append(f"registry.yaml {name}: cli route {cmd!r}")
    assert found == []


def test_roles_carry_no_model_ids_families_or_fallbacks():
    text = (SKILL / "registry" / "roles.yaml").read_text(encoding="utf-8")
    roles = yaml.safe_load(text)["roles"]
    for cfg in roles.values():
        assert not {"model", "family", "fallback", "agy", "example", "id_status"} & set(
            cfg
        )
    assert "agy_fallback" not in text


def test_a_missing_reply_writes_an_ask_and_waits(tmp_path):
    runner = driver.HandRunner(tmp_path, checking=("verifier",))
    with pytest.raises(driver.NeedsAgent) as got:
        runner.run("verifier", "check these rows", step="gate.b1")
    ask = Path(got.value.asks[0])
    head = ask.read_text(encoding="utf-8")
    assert "role: verifier" in head and "fresh subagent: yes" in head
    assert "check these rows" in head
    reply = Path(re.search(r"reply file: (.+)", head)[1].strip())
    reply.write_text("verdicts: []\n", encoding="utf-8")
    assert (
        runner.run("verifier", "check these rows", step="gate.b1") == "verdicts: []\n"
    )
    with pytest.raises(driver.NeedsAgent):
        runner.run("verifier", "changed rows", step="gate.b1")
    with pytest.raises(driver.NeedsAgent) as got:
        runner.run("author", "write it", step="draft.ch1")
    assert "fresh subagent: no" in Path(got.value.asks[0]).read_text(encoding="utf-8")


def test_the_driver_waits_on_the_agent_and_resumes(tmp_path):
    runner = driver.HandRunner(tmp_path / "agent")

    def infer(d):
        return driver.PhaseResult(mode="verify")

    def step(d):
        return driver.PhaseResult(
            data={"reply": runner.run("extractor", "split it", step="extract.s1")}
        )

    handlers = {p: (lambda d: driver.PhaseResult()) for p in driver.PHASES["verify"]}
    handlers.update(infer_mode=infer, ingest=step)
    d = driver.Driver.start(tmp_path, "t", "p", handlers, run_id="r1")
    assert d.run() == driver.EXIT[driver.WAITING] == 3
    assert d.state.status == driver.WAITING and d.state.phase == "ingest"
    asks = (tmp_path / "ASKS.md").read_text(encoding="utf-8")
    ask = Path(re.search(r"- (\S+\.ask\.md)", asks)[1])
    reply = Path(
        re.search(r"reply file: (.+)", ask.read_text(encoding="utf-8"))[1].strip()
    )
    reply.write_text("claims: []", encoding="utf-8")
    d = driver.Driver.resume(tmp_path, handlers)
    assert not (tmp_path / "ASKS.md").exists()
    assert d.run() == 0


def test_a_wave_collects_every_ask_before_waiting(tmp_path):
    runner = driver.HandRunner(tmp_path)
    results, _ = driver.run_wave(
        {k: k for k in "abc"},
        lambda k: runner.run("discovery", f"round for {k}", step=f"verify.{k}.r1"),
    )
    waiting = driver.waiting(results)
    assert isinstance(waiting, driver.NeedsAgent) and len(waiting.asks) == 3
    assert all(r.attempts == 1 for r in results.values())


def test_a_waiting_round_is_not_a_failed_round(ledger_ctx, tmp_path, monkeypatch):
    from types import SimpleNamespace

    from scripts.phases import verify

    ledger_ctx.ledger.add_claim(
        "Water boils at 100 C at sea level", origin="discovered"
    )
    ledger_ctx.keys = None
    runner = driver.HandRunner(tmp_path / "agent")
    monkeypatch.setattr(
        verify,
        "_do_round",
        lambda ctx, cid, fatal: runner.run("discovery", cid, step=f"verify.{cid}.r1"),
    )
    d = SimpleNamespace(
        state=SimpleNamespace(mode="verify", prompt="p", context={"reopened": True}),
        run_dir=tmp_path,
        save=lambda: None,
    )
    for _ in range(4):
        with pytest.raises(driver.NeedsAgent):
            verify.verify(ledger_ctx, d)
    assert d.state.context["round_failures"] == {}


def test_fetch_asks_save_to_their_own_file_and_survive_a_resume(tmp_path, reg):
    from types import SimpleNamespace

    from scripts import registry
    from scripts.fetch import LadderFetcher
    from scripts.workspace import Ledger

    ctx = SimpleNamespace(
        reg=reg,
        inbox=tmp_path / "inbox",
        keys=None,
        clock=None,
        ledger=Ledger(tmp_path / "topic"),
        runner=driver.HandRunner(tmp_path / "agent"),
    )
    surf = registry.surfaces(reg)["tavily.extract"]
    fetcher = LadderFetcher(min_chars=5)
    asks = {}
    for url in ("https://a.test/1", "https://b.test/2"):
        with pytest.raises(driver.NeedsAgent) as got:
            fetcher._agent("tavily.extract", surf, url, ctx, False)
        asks[url] = Path(got.value.asks[0]).read_text(encoding="utf-8")
    dests = {
        u: Path(re.search(r"save the page text to: (.+)", a)[1].strip())
        for u, a in asks.items()
    }
    assert len(set(dests.values())) == 2
    dests["https://a.test/1"].write_text("page one text", encoding="utf-8")
    reply = Path(re.search(r"reply file: (.+)", asks["https://a.test/1"])[1].strip())
    reply.write_text("ok: true\nroute: cli\n", encoding="utf-8")
    got = fetcher._agent("tavily.extract", surf, "https://a.test/1", ctx, False)
    assert got.ok and got.text == "page one text"


def test_a_round_asks_for_every_source_s_evidence_at_once(
    ledger_ctx, tmp_path, monkeypatch
):
    from scripts.phases import common, verify

    claim, _ = ledger_ctx.ledger.add_claim(
        "Water boils at 100 C at sea level", origin="discovered"
    )
    ledger_ctx.keys = None
    ledger_ctx.inbox = tmp_path / "inbox"
    ledger_ctx.raw = SimpleNamespace(contains=lambda text, quote: True)
    ledger_ctx.runner = driver.HandRunner(tmp_path / "agent")
    rows = [
        ({"id": f"s{i}", "url": f"https://x.test/{i}"}, f"text {i}") for i in (1, 2)
    ]
    monkeypatch.setattr(common, "take_sources", lambda ctx, reply: rows)
    monkeypatch.setattr(common, "log_reply_attempts", lambda *a, **k: [])
    monkeypatch.setattr(
        verify, "round_attempts", lambda ctx, cid, n: [{"paradigm": "keyword"}]
    )
    with pytest.raises(driver.NeedsAgent) as got:
        verify._do_round(ledger_ctx, claim["id"], [])
    ask = Path(got.value.asks[0])
    ask.with_name(ask.name.replace(".ask.", ".reply.")).write_text(
        "sources: []\nattempts: []\n", encoding="utf-8"
    )
    with pytest.raises(driver.NeedsAgent) as got:
        verify._do_round(ledger_ctx, claim["id"], [])
    assert sorted(Path(a).name.split("-")[0] for a in got.value.asks) == [
        f"verify.{claim['id']}.r1.evidence.s1.k1",
        f"verify.{claim['id']}.r1.evidence.s2.k1",
    ]
