import shutil
import subprocess
from collections import namedtuple
from pathlib import Path

from . import workspace
from .keystate import file_lock

PAGES_BRANCH = "main"  # the branch GitHub Pages serves
# Always rebuilt from the clone at publish; the render dir holds one topic only.
HOME_INDEX = ("index.html", "assets/course-index.js")


class PublishError(RuntimeError):
    pass


PublishResult = namedtuple(
    "PublishResult", "sha base branch pushed", defaults=(None, None, None, False)
)


def rendered_files(root):
    """Every file the render phase staged, as site-relative posix paths."""
    root = Path(root)
    return sorted(
        p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
    )


def run_git(cwd, *args, check=True):
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if check and proc.returncode != 0:
        raise PublishError(
            f"git {' '.join(args)} failed ({proc.returncode}): {(proc.stderr or proc.stdout).strip()[:300]}"
        )
    return (proc.stdout or "").strip() if proc.returncode == 0 else ""


def _ok(cwd, *args):
    return (
        subprocess.run(
            ["git", "-C", str(cwd), *args], capture_output=True, check=False
        ).returncode
        == 0
    )


class GitPublisher:
    """Publishes by writing the run's pages into the clone on the Pages branch.

    The clone must be on `main`, clean in the paths the run writes, and
    fast-forwarded before anything is copied. The allowlist is committed by name,
    never `-A`, so unrelated work stays untouched.
    """

    def __init__(
        self,
        main_root,
        remote="origin",
        lock_timeout=600.0,
        git=run_git,
        pages_branch=PAGES_BRANCH,
        state_root=None,
    ):
        self.main_root = Path(main_root)
        if not (self.main_root / ".git").exists():
            raise PublishError(
                f"site root {self.main_root} is not a git clone; clone the site repo first"
            )
        self.remote = remote
        self.lock_timeout = lock_timeout
        self.git = git
        self.pages_branch = pages_branch
        self.state_root = workspace._root(state_root)
        self.has_remote = bool(git(self.main_root, "remote"))

    @property
    def lock_path(self):
        return workspace.publish_lock_file(self.state_root)

    def head(self):
        return self.git(self.main_root, "rev-parse", "HEAD")

    def _require_main(self):
        branch = self.git(self.main_root, "rev-parse", "--abbrev-ref", "HEAD")
        if branch != self.pages_branch:
            raise PublishError(
                f"the site clone is on {branch!r}, not {self.pages_branch!r}: check out "
                f"{self.pages_branch} in {self.main_root} before publishing"
            )

    def _require_clean(self, paths):
        dirty = self.git(self.main_root, "status", "--porcelain", "--", *paths)
        if dirty:
            raise PublishError(
                "the site clone has uncommitted changes in paths this run writes; "
                "commit or discard them first:\n" + dirty
            )

    def _pull(self):
        if self.has_remote:
            self.git(
                self.main_root,
                "pull",
                "--ff-only",
                "-q",
                self.remote,
                self.pages_branch,
            )

    def _commit_push(self, paths, message, base):
        self.git(self.main_root, "add", "--", *paths)
        if not _ok(self.main_root, "diff", "--cached", "--quiet"):
            self.git(self.main_root, "commit", "-q", "-m", message)
        sha = self.git(self.main_root, "rev-parse", "HEAD")
        if self.has_remote:
            self.git(self.main_root, "push", "-q", self.remote, self.pages_branch)
        return PublishResult(
            sha=sha, base=base, branch=self.pages_branch, pushed=self.has_remote
        )

    def apply(self, paths, message, change):
        paths = list(paths)
        with file_lock(self.lock_path, timeout=self.lock_timeout):
            self._require_main()
            self._require_clean(paths)
            self._pull()
            base = self.git(self.main_root, "rev-parse", "HEAD")
            extra = list(change() or ())
            return self._commit_push([*paths, *extra], message, base)

    def publish(self, paths, source_root, message, generated=(), after=None):
        def change():
            for rel in paths:
                dst = self.main_root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(Path(source_root) / rel, dst)
            return after() if after is not None else ()

        return self.apply((*paths, *generated), message, change)

    def remove(self, paths, message, change):
        return self.apply(paths, message, change)

    def revert(self, result):
        """Undo the published commit on main with a revert commit, and push it."""
        if not result or not result.sha or result.sha == result.base:
            return PublishResult()
        with file_lock(self.lock_path, timeout=self.lock_timeout):
            self._require_main()
            self.git(self.main_root, "revert", "--no-edit", result.sha)
            sha = self.git(self.main_root, "rev-parse", "HEAD")
            if self.has_remote:
                self.git(self.main_root, "push", "-q", self.remote, self.pages_branch)
            return PublishResult(
                sha=sha, base=result.sha, branch=self.pages_branch, pushed=self.has_remote
            )

    def cleanup(self):
        return None
