import re
import shutil
import time
from pathlib import Path

from . import site, workspace
from .phases.ship import default_live_fetch, live_check_until
from .publish import HOME_INDEX, GitPublisher, PublishError

SINGLE_REMOVE_MODES = ("answer", "rules", "recommend")
INDEX_PATHS = HOME_INDEX
HREF = re.compile(r'href="([^"]*)"')


def resolve_footprint(site_root, topic):
    """The topic's published files: single pages, verify cards, the course's files."""
    found = []
    for mode in SINGLE_REMOVE_MODES:
        path = site.single_path(site_root, mode, topic)
        if path.is_file():
            found.append(path)
    answers = site_root / "answers"
    if answers.is_dir():
        pattern = re.compile(
            rf"verify-{re.escape(topic)}-\d{{4}}-\d{{2}}-\d{{2}}.*\.html"
        )
        found.extend(
            p
            for p in sorted(answers.iterdir())
            if p.is_file() and pattern.fullmatch(p.name)
        )
    course = site_root / topic
    if course.is_dir():
        found.extend(sorted(p for p in course.rglob("*") if p.is_file()))
    return found


def _link_tokens(topic):
    return [
        f"answer-{topic}.html",
        f"rules-{topic}.html",
        f"recommend-{topic}.html",
        f"verify-{topic}-",
        f"{topic}/",
    ]


def find_references(site_root, topic, removal, skip_root=None):
    tokens = _link_tokens(topic)
    hits = []
    for path in sorted(site_root.rglob("*.html")):
        if path.relative_to(site_root).as_posix() == "index.html":
            continue
        if skip_root is not None and (path == skip_root or skip_root in path.parents):
            continue
        if path in removal:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(site_root).as_posix()
        for match in HREF.finditer(text):
            href = match.group(1)
            if any(token in href for token in tokens):
                hits.append(f"{rel}: {href}")
    return hits


def main(
    site_root,
    topic,
    *,
    site_url,
    dry_run=False,
    force=False,
    state_root=None,
    fetch=None,
    sleep=time.sleep,
):
    site_root = Path(site_root)
    layout = workspace.Layout(state_root, topic)
    removal = resolve_footprint(site_root, topic)
    rels = [p.relative_to(site_root).as_posix() for p in removal]
    skip = site_root / topic
    hits = find_references(site_root, topic, removal, skip_root=skip)
    if not removal:
        print(f"error: no published footprint for topic {topic!r}; nothing to remove")
        return 1
    if dry_run:
        print(f"would remove {len(rels)} path(s) for topic {topic}:")
        for rel in rels:
            print(f"  {rel}")
        if layout.root.exists():
            print(f"  {layout.root} (run state)")
        if hits:
            print(f"{len(hits)} inbound reference(s) would block removal:")
            for hit in hits:
                print(f"  {hit}")
        else:
            print("no inbound references")
        print("dry run: nothing published")
        return 0
    if hits and not force:
        print(
            f"error: {len(hits)} inbound reference(s) to {topic}; "
            "re-run with --force to remove anyway:"
        )
        for hit in hits:
            print(f"  {hit}")
        return 1
    if hits:
        print(f"warning: leaving {len(hits)} inbound reference(s) behind (--force):")
        for hit in hits:
            print(f"  {hit}")

    def change():
        for rel in rels:
            (site_root / rel).unlink(missing_ok=True)
        shutil.rmtree(site_root / topic, ignore_errors=True)
        shutil.rmtree(layout.root, ignore_errors=True)
        site.regenerate_index(site_root)

    targets = sorted(set(rels) | set(INDEX_PATHS))
    publisher = GitPublisher(site_root, state_root=state_root)
    try:
        result = publisher.remove(targets, f"Remove {topic}", change)
    except (PublishError, OSError) as exc:
        print(f"error: publish failed: {exc}")
        return 1

    base = site_url.rstrip("/")
    generated = [
        (rel, site.lf((site_root / rel).read_bytes()))
        for rel in INDEX_PATHS
        if (site_root / rel).is_file()
    ]
    p_problems, attempts = live_check_until(
        fetch or default_live_fetch,
        base,
        {rel: want for rel, want in generated},
        rels,
        sleep,
    )
    problems = p_problems
    print("removed:")
    for rel in rels:
        print(f"  {rel}")
    print("index regenerated")
    print(f"sha: {result.sha}")
    print(f"pushed: {'yes' if result.pushed else 'no'}")
    if problems:
        print(f"live check: FAILED after {attempts} attempt(s):")
        for problem in problems:
            print(f"  {problem}")
        publisher.revert(result)
        print(f"the publish was reverted on {publisher.pages_branch}")
        return 1
    print(
        f"live check: {len(rels)} removed URL(s) 404, "
        f"{len(generated)} generated file(s) match ({attempts} attempt(s))"
    )
    return 0
