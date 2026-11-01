import re
import shutil
import time
from pathlib import Path

from . import site
from .phases.ship import default_live_fetch
from .publish import GitPublisher, PublishError

SINGLE_REMOVE_MODES = ("answer", "rules", "recommend")
GENERATED = ("index.html", "assets/course-index.js")
HREF = re.compile(r'href="([^"]*)"')
LIVE_ATTEMPTS = 12
LIVE_DELAY = 15.0


def resolve_footprint(site_root, topic):
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
    if (course / "index.html").is_file():
        found.append(course)
    ledger = site_root / "_ledger" / topic
    if ledger.exists():
        found.append(ledger)
    return found


def _link_tokens(topic):
    return [
        f"answer-{topic}.html",
        f"rules-{topic}.html",
        f"recommend-{topic}.html",
        f"verify-{topic}-",
        f"{topic}/",
    ]


def find_references(site_root, topic, removal):
    tokens = _link_tokens(topic)
    hits = []
    for path in sorted(site_root.rglob("*.html")):
        if path.relative_to(site_root).as_posix() == "index.html":
            continue
        if any(path == r or r in path.parents for r in removal):
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


def _delete(tree_path):
    if tree_path.is_dir() and not tree_path.is_symlink():
        shutil.rmtree(tree_path)
    else:
        tree_path.unlink(missing_ok=True)


def _live_problems(
    fetch,
    base,
    removed,
    generated,
):
    problems = []
    for rel in removed:
        code, _ = fetch(f"{base}/{rel}")
        if code != 404:
            problems.append(f"{rel}: HTTP {code}, want 404")
    for rel, want in generated:
        code, body = fetch(f"{base}/{rel}")
        if code != 200:
            problems.append(f"{rel}: HTTP {code}, want 200")
        elif site.lf(body) != want:
            problems.append(f"{rel}: live bytes differ from the published file")
    return problems


def main(
    site_root,
    topic,
    *,
    site_url,
    dry_run=False,
    force=False,
):
    site_root = Path(site_root)
    try:
        # Read and change the Pages branch through the publisher's own checkout, never the clone's (#349).
        publisher = GitPublisher(site_root)
        stamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
        worktree = publisher.prepare(topic, f"remove-{stamp}")
    except (PublishError, OSError) as exc:
        print(f"error: cannot check out the Pages branch: {exc}")
        return 1
    removal = resolve_footprint(worktree, topic)
    rels = [p.relative_to(worktree).as_posix() for p in removal]
    hits = find_references(worktree, topic, removal)
    if not removal or dry_run or (hits and not force):
        publisher.cleanup()
    if not removal:
        print(f"error: no published footprint for topic {topic!r}; nothing to remove")
        return 1
    if dry_run:
        print(f"would remove {len(removal)} path(s) for topic {topic}:")
        for rel in rels:
            print(f"  {rel}")
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
    try:
        for rel in rels:
            _delete(worktree / rel)
        publisher.commit(f"Remove {topic}")
        result = publisher.publish(regen=site.regenerate_index)
    except (PublishError, OSError) as exc:
        print(f"error: publish failed: {exc}")
        return 1
    base = site_url.rstrip("/")
    generated = [
        (rel, site.lf((worktree / rel).read_bytes()))
        for rel in GENERATED
        if (worktree / rel).is_file()
    ]
    problems = []
    attempts = 0
    for attempt in range(LIVE_ATTEMPTS):
        attempts = attempt + 1
        problems = _live_problems(default_live_fetch, base, rels, generated)
        if not problems or attempt == LIVE_ATTEMPTS - 1:
            break
        time.sleep(LIVE_DELAY)
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
    publisher.cleanup()
    return 0
