# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "jsonschema"]
# ///
"""CLI entry: start or resume a run.

  uv run <skill dir>/scripts/cli.py start --site-root <bearmancer.github.io clone> --topic <slug> [--site-url <url>] [--mode learn|rules|answer|verify|recommend] [--kind narrative|explainer] [--subject <name>] [--model <id>] "<prompt>"
  uv run <skill dir>/scripts/cli.py resume [--model <id>] <run_dir>
  uv run <skill dir>/scripts/cli.py doctor [--site-root <clone>]
  uv run <skill dir>/scripts/cli.py remove --site-root <bearmancer.github.io clone> --topic <slug> [--site-url <url>] [--dry-run] [--force]

A run works in a draft worktree of the site repo (`<site>/work/_drafts/<topic>-<run>`), so its run directory lives under
that worktree. The draft is based on, and publishes to, the Pages branch (`main`) whatever the clone has checked
out (#349). A site root that is not a git repo is written in place.
No step calls a model: each AI step is written to `<site>/work/<topic>/agent/<run>/*.ask.md` (gitignored: asks carry
raw source text and the verify input, which are never published) for the agent that loaded the skill, which writes
the reply file and resumes (#340). `--model` records which model answered.
Exit: 0 done, 1 failed, 2 suspended (NEEDS_YOU.md), 3 waiting on the agent (ASKS.md). When `DEEP_RESEARCH_NOTIFY` names a
command, it is run with one message argument whenever a run fails or suspends, so an unattended run does not stop in silence.
"""

if not __package__:
    import sys
    from pathlib import Path

    sys.dont_write_bytecode = True
    parents = Path(__file__).resolve().parents
    sys.path.insert(0, str(next(p for p in parents if p.name == "scripts")))
    import launch

    launch.run(__file__)

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_SITE_URL = "https://bearmancer.github.io"


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


def real_services(main_root, reg):
    from . import urlaudit
    from .fetch import LadderFetcher
    from .keys import KeyManager

    fetcher = LadderFetcher()
    return Services(
        runner=None,
        fetcher=fetcher,
        keys=KeyManager(reg, main_root / "work" / "keystate.json"),
        audit_urls=lambda urls: urlaudit.audit(
            urls,
            recheck=lambda u: True,
        ),
    )


def make_publisher(main_root):
    from .publish import GitPublisher, LocalPublisher

    return (
        GitPublisher(main_root)
        if (main_root / ".git").exists()
        else LocalPublisher(main_root)
    )


def build_context(
    main_root,
    topic,
    run_id,
    services,
    site_url=None,
):
    from . import registry
    from .workspace import Config, Context

    publisher = make_publisher(main_root)
    return Context(
        site_root=publisher.prepare(topic, run_id),
        main_root=main_root,
        topic=topic,
        reg=registry.load(),
        runner=services.runner,
        fetcher=services.fetcher,
        publisher=publisher,
        cfg=Config(site_url=site_url),
        keys=services.keys,
        audit_urls=services.audit_urls,
        live_fetch=services.live_fetch,
    )


def asks_dir(ctx, run_id):
    # Under the gitignored raw store, never in the published tree: asks hold raw page text and the verify input.
    return ctx.main_root / "work" / ctx.topic / "agent" / run_id


SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def slug_type(value):
    if not SLUG.fullmatch(value):
        raise argparse.ArgumentTypeError(
            f"topic {value!r} is not a lowercase hyphenated slug"
        )
    return value


def notify(message, env=None):
    command = (
        (env if env is not None else os.environ).get("DEEP_RESEARCH_NOTIFY", "").strip()
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


def doctor(site_root, which=shutil.which):
    out = []
    for tool, why in (
        ("uv", "runs the scripts package"),
        ("git", "draft worktrees and publishing"),
    ):
        found = which(tool)
        out.append((tool, bool(found), found or f"not on PATH: {why}"))
    if site_root is not None:
        git = (site_root / ".git").exists()
        out.append(("site root", site_root.is_dir(), str(site_root)))
        out.append(
            (
                "site git repo",
                git,
                "publishes through draft branches"
                if git
                else "no .git: pages are written in place, nothing is pushed",
            )
        )
    return out


def locate(run_dir):
    topic_dir = run_dir.parent.parent
    tree = topic_dir.parent.parent
    in_draft = tree.parent.name == "_drafts" and tree.parent.parent.name == "work"
    return (tree.parents[2] if in_draft else tree), topic_dir.name, run_dir.name


def main(
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
        help="course kind declared in course.json (learn mode; values: see the invalid-choice error); default keeps the declared kind, else explainer",
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
        "--model", help="the model answering the AI steps, kept in the run record"
    )
    s.add_argument("prompt")
    r = sub.add_parser("resume")
    r.add_argument("--site-url", default=DEFAULT_SITE_URL)
    r.add_argument(
        "--model", help="the model answering the AI steps, kept in the run record"
    )
    r.add_argument("run_dir", type=Path)
    c = sub.add_parser("doctor")
    c.add_argument("--site-root", type=Path)
    d = sub.add_parser("remove")
    d.add_argument("--site-root", type=Path, required=True)
    d.add_argument("--topic", required=True, type=slug_type)
    d.add_argument("--site-url", default=DEFAULT_SITE_URL)
    d.add_argument("--dry-run", action="store_true")
    d.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "doctor":
        results = doctor(args.site_root.resolve() if args.site_root else None)
        for name, ok, detail in results:
            print(f"{'ok  ' if ok else 'FAIL'} {name}: {detail}")
        return 0 if all(ok for name, ok, _ in results if name != "site git repo") else 1
    if args.cmd == "remove":
        from . import remove

        return remove.main(
            args.site_root.resolve(),
            args.topic,
            site_url=args.site_url,
            dry_run=args.dry_run,
            force=args.force,
        )
    from . import driver, registry
    from .phases import make_handlers

    if args.cmd == "start":
        main_root, topic, run_id = (
            args.site_root.resolve(),
            args.topic,
            driver.new_run_id(),
        )
    else:
        main_root, topic, run_id = locate(args.run_dir.resolve())
    ctx = build_context(
        main_root, topic, run_id, services(main_root, registry.load()), args.site_url
    )
    run_dir = ctx.topic_dir / "runs" / run_id
    if ctx.runner is None:
        ctx.runner = driver.HandRunner(asks_dir(ctx, run_id), registry.checking_roles())
    handlers = make_handlers(ctx)
    if args.cmd == "start":
        d = driver.Driver.start(run_dir, topic, args.prompt, handlers, run_id=run_id)
        if args.mode:
            d.state.context["mode_override"] = args.mode
        if args.kind:
            d.state.context["course_kind"] = args.kind
        if args.subject:
            d.state.context["subject"] = args.subject
        if args.allow_kind_downgrade:
            d.state.context["allow_kind_downgrade"] = True
        d.save()
    else:
        d = driver.Driver.resume(run_dir, handlers)
    if args.model and args.model not in d.state.context.setdefault("answered_by", []):
        d.state.context["answered_by"].append(args.model)
        d.save()
    code = d.run()
    if d.state.status == driver.DONE:
        ctx.publisher.cleanup()
    summary = f"{d.state.run_id}: {d.state.status} (phase {d.state.phase})"
    print(summary)
    if d.state.status == driver.WAITING:
        print(f"asks: {run_dir / 'ASKS.md'}")
    if d.state.status in (driver.FAILED, driver.SUSPENDED):
        notify(f"rigorous-research {topic}: {summary}. See {run_dir}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
