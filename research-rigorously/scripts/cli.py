"""The `rr` command of the research-rigorously skill, run as `uv run <skill dir>/rr.py <command> ...`.

Runs:
  rr start --site-root <bearmancer.github.io clone> --topic <slug> [--site-url <url>] [--mode learn|rules|answer|verify|recommend] [--kind narrative|explainer] [--subject <name>] [--model <id>] [--max-asks <n>] [--max-claims <n>] [--max-source-chunks <n>] [--state-root <dir>] [--restart] ("<prompt>" | --prompt-file <path>)
  rr resume --topic <slug> [--model <id>] [--state-root <dir>]
  rr remove --site-root <bearmancer.github.io clone> --topic <slug> [--site-url <url>] [--state-root <dir>] [--dry-run] [--force]

Tools:
  rr ledger-check    rr urlaudit    rr keys
  rr gen-routing     rr vendor (request|exa-agent-run|exa-batches|scrapegraph-crawl)
  rr selfcheck

State lives under the state root (default `~/.rigor`): `keystate.json` and `publish.lock` at its top, then one
directory per topic holding `sources/` (one text file per source, `sN.txt`) and `run/` (run.yaml, ASKS.md, asks,
batches, ledger, drafts, lessons, media). No path carries a run id: one run per topic, so resume needs only the
topic, and `site_root` and `site_url` are stored in run.yaml.

A run renders into the run's own `site/` dir, laid out with the site-relative paths its pages will have
(`answers/<file>.html`, `<course>/...`). The gates check that dir. On pass, publish takes
`~/.rigor/publish.lock`, requires the site clone to be on `main` and clean in the paths it writes, pulls
`--ff-only`, copies the rendered files in, and commits exactly those paths. The site root must be a git clone on
`main`; publishing fails clearly otherwise.
No step calls a model: each AI step is written to `<state>/<topic>/run/<step>-<hash>.ask.md` for the agent that
loaded the skill, which writes the reply file and resumes. `--model` records which model answered. `--max-asks`
caps the ask files a non-ship phase may write; at the ceiling the run keeps the open claims that meet the true
rule as `true`, marks the rest `unchecked`, and goes on to the gates.
Exit: 0 done, 1 failed, 2 suspended (NEEDS_YOU.md), 3 waiting on the agent (ASKS.md). When
`RESEARCH_RIGOROUSLY_NOTIFY` names a command, it is run with one message argument whenever a run fails or
suspends, so an unattended run does not stop in silence.
"""

import argparse
import importlib
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_SITE_URL = "https://bearmancer.github.io"
DEFAULT_STATE_ROOT = Path.home() / ".rigor"


class _Lazy:
    """An argparse `choices` container whose members load on first use.

    Keeps `--help` and usage errors from importing the driver and site modules,
    which pull in most of the stdlib and pyyaml.
    """

    def __init__(self, load):
        self._load = load

    def __iter__(self):
        return iter(self._load())

    def __contains__(self, item):
        return item in self._load()


def _phase_modes():
    from . import driver

    return sorted(driver.PHASES)


def _course_kinds():
    from . import site

    return site.KINDS


class Services:
    def __init__(self, runner, fetcher, keys=None, audit_urls=None, live_fetch=None):
        self.runner = runner
        self.fetcher = fetcher
        self.keys = keys
        self.audit_urls = audit_urls
        self.live_fetch = live_fetch


def real_services(main_root, reg, cfg=None):
    from . import urlaudit, workspace
    from .fetch import LadderFetcher
    from .keys import KeyManager

    cfg = cfg if cfg is not None else workspace.Config()
    fetcher = LadderFetcher()
    return Services(
        runner=None,
        fetcher=fetcher,
        keys=KeyManager(reg, workspace.keystate_file(cfg.state_root)),
        audit_urls=lambda urls: urlaudit.audit(urls),
    )


def make_publisher(main_root, cfg=None):
    from .publish import GitPublisher

    return GitPublisher(main_root, state_root=cfg.state_root if cfg else None)


def build_context(
    main_root,
    topic,
    services,
    cfg,
):
    from . import registry
    from .workspace import Context, Layout

    layout = Layout(cfg.state_root, topic)
    publisher = make_publisher(main_root, cfg)
    return Context(
        site_root=layout.site,
        main_root=main_root,
        topic=topic,
        reg=registry.load(),
        runner=services.runner,
        fetcher=services.fetcher,
        publisher=publisher,
        cfg=cfg,
        keys=services.keys,
        audit_urls=services.audit_urls,
        live_fetch=services.live_fetch,
    )


def read_state(run_yaml):
    from . import driver

    return driver.RunState.from_file(run_yaml) if run_yaml.is_file() else None


def wipe_run(layout):
    """Drop everything for the topic's run; `sources/` stays."""
    shutil.rmtree(layout.run, ignore_errors=True)


def finish_run(ctx, d):
    """After a run: a done run no longer needs its state, sources included."""
    from . import driver

    if d.state.status == driver.DONE:
        shutil.rmtree(ctx.layout.root, ignore_errors=True)


SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def slug_type(value):
    if not SLUG.fullmatch(value):
        raise argparse.ArgumentTypeError(
            f"topic {value!r} is not a lowercase hyphenated slug"
        )
    return value


def notify(message, env=None):
    command = (
        (env if env is not None else os.environ).get("RESEARCH_RIGOROUSLY_NOTIFY", "").strip()
    )
    if not command:
        return False
    try:
        parts = shlex.split(command, posix=sys.platform != "win32")
        if parts:
            parts[0] = shutil.which(parts[0]) or parts[0]
        return (
            subprocess.run([*parts, message], timeout=60, check=False).returncode == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def run_main(
    argv=None,
    services=real_services,
):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--site-root", type=Path, required=True)
    s.add_argument("--topic", required=True, type=slug_type)
    s.add_argument("--site-url", default=DEFAULT_SITE_URL)
    s.add_argument(
        "--mode",
        metavar="MODE",
        choices=_Lazy(_phase_modes),
        help="declare the mode (confirmed in the question batch; values: see the usage docstring or the invalid-choice error); default infers it from the prompt",
    )
    s.add_argument(
        "--kind",
        metavar="KIND",
        choices=_Lazy(_course_kinds),
        help="course kind written into the course index's course-kind meta (learn mode; values: see the invalid-choice error); default keeps the declared kind, else explainer",
    )
    s.add_argument(
        "--allow-kind-downgrade",
        action="store_true",
        help="let a narrative course become an explainer",
    )
    s.add_argument(
        "--subject",
        help="home-index subject for the page; default is the author's choice, reusing an existing subject when one fits",
    )
    s.add_argument(
        "--model", help="the model answering the AI steps, kept in the run state"
    )
    for flag in ("max-claims", "max-source-chunks", "max-asks"):
        s.add_argument(
            f"--{flag}",
            type=int,
            help="run budget (defaults: 50 claims, asks 8x claims (400), 3 chunks per source)",
        )
    s.add_argument(
        "--state-root",
        type=Path,
        default=DEFAULT_STATE_ROOT,
        help="where a topic's state lives (default: ~/.rigor)",
    )
    s.add_argument(
        "--restart",
        action="store_true",
        help="wipe an existing waiting or suspended run/ and start over",
    )
    s.add_argument("prompt", nargs="?")
    s.add_argument("--prompt-file", type=Path)
    r = sub.add_parser("resume")
    r.add_argument("--topic", required=True, type=slug_type)
    r.add_argument(
        "--model", help="the model answering the AI steps, kept in the run state"
    )
    r.add_argument(
        "--state-root",
        type=Path,
        default=DEFAULT_STATE_ROOT,
        help="where a topic's state lives (default: ~/.rigor)",
    )
    d = sub.add_parser("remove")
    d.add_argument("--site-root", type=Path, required=True)
    d.add_argument("--topic", required=True, type=slug_type)
    d.add_argument("--site-url", default=DEFAULT_SITE_URL)
    d.add_argument(
        "--state-root",
        type=Path,
        default=DEFAULT_STATE_ROOT,
        help="where a topic's state lives (default: ~/.rigor)",
    )
    d.add_argument("--dry-run", action="store_true")
    d.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "start":
        if (args.prompt is None) == (args.prompt_file is None):
            ap.error("give a prompt or --prompt-file")
        if args.prompt_file is not None:
            args.prompt = args.prompt_file.read_text(encoding="utf-8").strip()

    if args.cmd == "remove":
        from . import remove

        return remove.main(
            args.site_root.resolve(),
            args.topic,
            site_url=args.site_url,
            dry_run=args.dry_run,
            force=args.force,
            state_root=args.state_root,
        )
    from . import driver, registry, workspace
    from .phases import make_handlers

    layout = workspace.Layout(args.state_root, args.topic)
    previous = read_state(layout.run_yaml)

    if args.cmd == "start":
        if previous is not None:
            if previous.status in (
                driver.RUNNING,
                driver.WAITING,
                driver.SUSPENDED,
            ) and not args.restart:
                print(
                    f"error: a {previous.status} run for {args.topic} is already in {layout.run}; "
                    f"continue it with `rr.py resume --topic {args.topic}`, "
                    "or wipe it and start over with `start --restart` (the sources stay)"
                )
                return 1
            wipe_run(layout)
        main_root = args.site_root.resolve()
        run_id = driver.new_run_id()
        cfg = workspace.Config(state_root=args.state_root, site_url=args.site_url)
        prompt = args.prompt
    else:
        if previous is None:
            print(f"error: no run for {args.topic} in {layout.run} (run.yaml is missing)")
            return 1
        main_root = Path(previous.context["site_root"])
        run_id = previous.run_id
        cfg = workspace.Config(
            state_root=args.state_root, site_url=previous.context.get("site_url")
        )
        prompt = None

    try:
        ctx = build_context(
            main_root, args.topic, services(main_root, registry.load(), cfg), cfg
        )
    except Exception as exc:  # noqa: BLE001 - CLI entry point: any failure is exit 1
        print(f"error: {exc}")
        return 1
    run_dir = ctx.topic_dir
    if args.cmd == "start":
        budget = {
            k: getattr(args, k)
            for k in workspace.BUDGET_KEYS
            if getattr(args, k) is not None
        }
    else:
        budget = previous.context.get("budget") or {}
    workspace.apply_budget(ctx.cfg, budget)
    if ctx.runner is None:
        ctx.runner = driver.HandRunner(
            ctx.layout.run,
            registry.checking_roles(),
            max_asks=ctx.cfg.max_asks,
        )
    handlers = make_handlers(ctx)
    if args.cmd == "start":
        d = driver.Driver.start(run_dir, args.topic, prompt, handlers, run_id=run_id)
        d.state.context["site_root"] = str(main_root)
        d.state.context["site_url"] = cfg.site_url
        if args.mode:
            d.state.context["mode_override"] = args.mode
        if args.kind:
            d.state.context["course_kind"] = args.kind
        if args.subject:
            d.state.context["subject"] = args.subject
        if args.allow_kind_downgrade:
            d.state.context["allow_kind_downgrade"] = True
        d.state.context["budget"] = {
            k: getattr(ctx.cfg, k) for k in workspace.BUDGET_KEYS
        }
        d.save()
    else:
        d = driver.Driver.resume(run_dir, handlers)
    if args.model and args.model not in d.state.context.setdefault("answered_by", []):
        d.state.context["answered_by"].append(args.model)
        d.save()
    code = d.run()
    finish_run(ctx, d)
    summary = f"{d.state.run_id}: {d.state.status} (phase {d.state.phase})"
    print(summary)
    if d.state.status == driver.WAITING:
        print(f"asks: {run_dir / 'ASKS.md'}")
    if d.state.status in (driver.FAILED, driver.SUSPENDED):
        notify(f"research-rigorously {args.topic}: {summary}. See {run_dir}")
    return code


RUN_COMMANDS = ("start", "resume", "remove")
TOOLS = {
    "ledger-check": "scripts.ledger_check",
    "urlaudit": "scripts.urlaudit",
    "keys": "scripts.switch_api_key",
    "gen-routing": "scripts.gen_routing_table",
    "selfcheck": "scripts.selfcheck",
}
VENDOR_SCRIPTS = {
    "exa-agent-run": "scripts.post.exa_agent_run",
    "exa-batches": "scripts.post.exa_batches",
    "scrapegraph-crawl": "scripts.post.scrapegraph_crawl",
}
VENDOR_HELP = (
    "vendor: call a vendor REST API or one of its folded POST scripts.\n\n"
    "  rr vendor <pool> <METHOD> <path> [--body JSON|@file] [--param k=v] [--header k=v]\n"
    "      generic REST call\n"
    "  rr vendor exa-agent-run stop|cancel <run_id>\n"
    "  rr vendor exa-batches start|status|cancel\n"
    "  rr vendor scrapegraph-crawl start|status|stop|resume|delete|pages\n"
)

HELP = """rr: the research-rigorously CLI. Run as `uv run <skill dir>/rr.py <command> ...`.

  rr start ...       start a run (--help for its arguments)
  rr resume ...      resume a topic's run
  rr remove ...      delete a topic's pages and state
  rr ledger-check    check a run's ledger (--publish for the gate)
  rr urlaudit        audit URLs (200 only passes)
  rr keys            rotate or list the masked API key pools
  rr gen-routing     regenerate references/routing.md (--check to verify)
  rr selfcheck       run the skill's own checks (--list, -k <substr>)
  rr vendor          call a vendor REST API or a folded POST script

Run `rr <command> --help` for a command's arguments.
"""


def vendor(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(VENDOR_HELP, end="")
        return 0
    if argv[0] in VENDOR_SCRIPTS:
        module = importlib.import_module(VENDOR_SCRIPTS[argv[0]])
        return module.main(argv[1:]) or 0
    vendor_request = importlib.import_module("scripts.post.vendor_request")
    return vendor_request.main(argv) or 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(HELP, end="", file=sys.stderr)
        return 2
    if argv[0] in ("-h", "--help"):
        print(HELP, end="")
        return 0
    command, rest = argv[0], argv[1:]
    if command in RUN_COMMANDS:
        return run_main(argv)
    if command == "vendor":
        return vendor(rest)
    if command in TOOLS:
        return importlib.import_module(TOOLS[command]).main(rest) or 0
    print(f"rr: unknown command {command!r}\n", end="", file=sys.stderr)
    print(HELP, end="", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
