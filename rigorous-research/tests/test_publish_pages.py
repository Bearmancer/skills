"""#349: publishing always targets the Pages branch through its own checkout; the clone's branch is never touched."""

import subprocess

from scripts import remove
from scripts.publish import GitPublisher, PublishResult


def git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _clone_on_staging(tmp_path):
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "init", "-q", "-b", "main", str(seed))
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        git(seed, "config", k, v)
    (seed / ".gitignore").write_text("work/\n")
    (seed / "index.html").write_text("home\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "seed")
    git(seed, "push", "-q", str(origin), "main")
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(origin), str(clone))
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        git(clone, "config", k, v)
    git(clone, "checkout", "-q", "-b", "staging")
    (clone / "draft.txt").write_text("staging draft\n")
    git(clone, "add", "draft.txt")
    git(clone, "commit", "-q", "-m", "staging work")
    (clone / "wip.txt").write_text("uncommitted\n")
    (clone / "index.html").write_text("edited on staging\n")
    return origin, clone


def _snapshot(clone):
    return (
        git(clone, "symbolic-ref", "--short", "HEAD"),
        git(clone, "rev-parse", "staging"),
        git(clone, "status", "--porcelain"),
        (clone / "index.html").read_text(),
        (clone / "wip.txt").read_text(),
    )


def _publish_page(clone, rel="answers/verify-x-2026-10-26.html"):
    pub = GitPublisher(clone)
    wt = pub.prepare("x", "r1")
    page = wt / rel
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("page\n")
    pub.commit("Publish x")
    result = pub.publish(
        regen=lambda root: (root / "index.html").write_text("home + x\n")
    )
    return pub, wt, result


def test_a_run_from_another_branch_lands_on_the_pages_branch(tmp_path):
    origin, clone = _clone_on_staging(tmp_path)
    before = _snapshot(clone)
    pub, wt, result = _publish_page(clone)
    assert result.pushed and result.sha == git(origin, "rev-parse", "main")
    assert git(origin, "show", "main:answers/verify-x-2026-10-26.html") == "page"
    assert git(origin, "show", "main:index.html") == "home + x"
    assert "draft.txt" not in git(origin, "ls-tree", "--name-only", "main")
    assert (wt / "index.html").read_text() == "home + x\n"
    assert _snapshot(clone) == before
    pub.revert(result)
    assert git(origin, "show", "main:index.html") == "home"
    assert "answers" not in git(origin, "ls-tree", "--name-only", "main")
    assert _snapshot(clone) == before
    pub.cleanup()
    assert _snapshot(clone) == before
    assert "_revert" not in git(clone, "worktree", "list")


def test_head_is_the_pages_branch_not_the_checkout(tmp_path):
    origin, clone = _clone_on_staging(tmp_path)
    assert GitPublisher(clone).head() == git(origin, "rev-parse", "main")


def test_remove_reads_and_publishes_the_pages_branch(tmp_path, monkeypatch, capsys):
    origin, clone = _clone_on_staging(tmp_path)
    pub, _, _ = _publish_page(clone)
    pub.cleanup()
    before = _snapshot(clone)

    def live(url):
        rel = url.split("/site/", 1)[1]
        if rel.startswith("answers/"):
            return 404, b""
        return 200, git(origin, "show", f"main:{rel}").encode() + b"\n"

    monkeypatch.setattr(remove, "default_live_fetch", live)
    code = remove.main(clone, "x", site_url="https://h.test/site")
    assert code == 0, capsys.readouterr().out
    assert "answers" not in git(origin, "ls-tree", "--name-only", "main")
    assert _snapshot(clone) == before


def test_revert_of_nothing_is_a_no_op(tmp_path):
    _, clone = _clone_on_staging(tmp_path)
    before = _snapshot(clone)
    GitPublisher(clone).revert(PublishResult())
    assert _snapshot(clone) == before


def test_asks_never_land_in_the_published_tree(tmp_path):
    from types import SimpleNamespace

    from scripts import cli

    _, clone = _clone_on_staging(tmp_path)
    pub = GitPublisher(clone)
    wt = pub.prepare("x", "r1")
    ctx = SimpleNamespace(main_root=clone, topic="x", topic_dir=wt / "_ledger" / "x")
    asks = cli.asks_dir(ctx, "r1")
    assert wt not in asks.parents
    asks.mkdir(parents=True)
    (asks / "extract.s1.k1-abc.ask.md").write_text(
        "pasted verify input and raw page text\n"
    )
    assert (
        git(clone, "check-ignore", "-q", str(asks / "extract.s1.k1-abc.ask.md")) == ""
    )
