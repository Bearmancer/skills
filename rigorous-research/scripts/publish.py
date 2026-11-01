import subprocess
from collections import namedtuple

from .keystate import file_lock

GENERATED = ("index.html", "assets/course-index.js")
GIT_ATTEMPTS = 3
PAGES_BRANCH = "main"  # the branch GitHub Pages serves (#349)


class PublishError(RuntimeError):
    pass


PublishResult = namedtuple(
    "PublishResult", "sha base branch pushed", defaults=(None, None, None, False)
)


class LocalPublisher:
    def __init__(self, site_root):
        self.site_root = site_root

    def prepare(self, topic, run_id):
        self.site_root.mkdir(parents=True, exist_ok=True)
        return self.site_root

    def head(self):
        return None

    def commit(self, message):
        return None

    def publish(self, regen=None):
        if regen:
            regen(self.site_root)
        return PublishResult()

    def revert(self, result):
        return None

    def cleanup(self):
        return None


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
    """Publishes to the branch GitHub Pages serves, whatever the clone has checked out (#349).

    Every write goes through a temporary checkout: the run's draft worktree (based on the Pages
    branch) for publish, a detached worktree for revert. The clone's checked-out branch, index and
    working tree are never touched; with a remote, only `refs/remotes/<remote>/<pages>` moves locally.
    """

    def __init__(
        self,
        main_root,
        remote="origin",
        lock_timeout=600.0,
        git=run_git,
        pages_branch=PAGES_BRANCH,
    ):
        self.main_root = main_root
        self.remote = remote
        self.lock_timeout = lock_timeout
        self.git = git
        self.pages_branch = pages_branch
        self.has_remote = bool(git(main_root, "remote"))
        self.branch = None
        self.worktree = None

    @property
    def lock_path(self):
        return self.main_root / "work" / "publish.lock"

    @property
    def pages_ref(self):
        if self.has_remote:
            return f"refs/remotes/{self.remote}/{self.pages_branch}"
        return f"refs/heads/{self.pages_branch}"

    def _fetch(self):
        if self.has_remote:
            self.git(
                self.main_root,
                "fetch",
                "-q",
                self.remote,
                f"+refs/heads/{self.pages_branch}:{self.pages_ref}",
            )

    def prepare(self, topic, run_id):
        if not _ok(self.main_root, "check-ignore", "-q", "work/probe"):
            raise PublishError(
                "work/ is not gitignored in the site repo; add it before running (raw store must never be committed)"
            )
        self.branch = f"draft/{topic}-{run_id}"
        self.worktree = self.main_root / "work" / "_drafts" / f"{topic}-{run_id}"
        if not (self.worktree / ".git").exists():
            self.worktree.parent.mkdir(parents=True, exist_ok=True)
            if _ok(self.main_root, "rev-parse", "--verify", "-q", self.branch):
                self.git(
                    self.main_root, "worktree", "add", str(self.worktree), self.branch
                )
            else:
                self._fetch()
                self.git(
                    self.main_root,
                    "worktree",
                    "add",
                    "-b",
                    self.branch,
                    str(self.worktree),
                    self.pages_ref,
                )
        return self.worktree

    def _wt(self):
        if self.worktree is None or self.branch is None:
            raise PublishError("prepare() was not called")
        return self.worktree

    def _drop_generated(self, wt):
        for rel in GENERATED:
            if _ok(wt, "ls-files", "--error-unmatch", rel):
                self.git(wt, "checkout", "--", rel)
            else:
                (wt / rel).unlink(missing_ok=True)

    def head(self):
        self._fetch()
        return self.git(self.main_root, "rev-parse", self.pages_ref)

    def commit(self, message):
        wt = self._wt()
        self.git(wt, "add", "-A", "--", ".", *(f":(exclude){rel}" for rel in GENERATED))
        if not _ok(wt, "diff", "--cached", "--quiet"):
            self.git(wt, "commit", "-q", "-m", message)
        self._drop_generated(wt)
        return self.git(wt, "rev-parse", "HEAD")

    def _land(self, checkout, base):
        """Move the Pages branch from `base` to the checkout's HEAD; False if it moved meanwhile."""
        if self.has_remote:
            if not _ok(
                checkout,
                "push",
                "-q",
                self.remote,
                f"HEAD:refs/heads/{self.pages_branch}",
            ):
                return False
            self._fetch()
            return True
        new = self.git(checkout, "rev-parse", "HEAD")
        return _ok(self.main_root, "update-ref", self.pages_ref, new, base)

    def publish(self, regen=None):
        wt = self._wt()
        with file_lock(self.lock_path, timeout=self.lock_timeout):
            for attempt in range(GIT_ATTEMPTS):
                self._fetch()
                base = self.git(self.main_root, "rev-parse", self.pages_ref)
                if not _ok(wt, "rebase", "-q", base):
                    self.git(wt, "rebase", "--abort", check=False)
                    raise PublishError(
                        f"draft {self.branch} does not rebase onto {self.pages_branch}; resolve in {wt}"
                    )
                if regen:
                    regen(wt)
                    self.git(wt, "add", "-A")
                    if not _ok(wt, "diff", "--cached", "--quiet"):
                        self.git(wt, "commit", "-q", "-m", "Regenerate home index")
                if self._land(wt, base):
                    new = self.git(wt, "rev-parse", "HEAD")
                    return PublishResult(new, base, self.branch, self.has_remote)
            raise PublishError(
                f"push of {self.pages_branch} was rejected {GIT_ATTEMPTS} times"
            )

    def revert(self, result):
        if not result.sha or not result.base or result.sha == result.base:
            return
        with file_lock(self.lock_path, timeout=self.lock_timeout):
            self._fetch()
            base = self.git(self.main_root, "rev-parse", self.pages_ref)
            tmp = self.main_root / "work" / "_drafts" / f"_revert-{result.sha[:12]}"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            self.git(
                self.main_root, "worktree", "add", "-q", "--detach", str(tmp), base
            )
            try:
                if not _ok(tmp, "revert", "--no-edit", f"{result.base}..{result.sha}"):
                    self.git(tmp, "revert", "--abort", check=False)
                    raise PublishError(
                        f"revert of {result.base}..{result.sha} conflicts; revert by hand on {self.pages_branch}"
                    )
                if not self._land(tmp, base):
                    raise PublishError(
                        f"revert push to {self.pages_branch} was rejected; revert {result.base}..{result.sha} by hand"
                    )
            finally:
                self.git(
                    self.main_root,
                    "worktree",
                    "remove",
                    "--force",
                    str(tmp),
                    check=False,
                )

    def cleanup(self):
        if self.worktree is not None and self.branch is not None:
            self.git(
                self.main_root,
                "worktree",
                "remove",
                "--force",
                str(self.worktree),
                check=False,
            )
            self.git(self.main_root, "branch", "-d", self.branch, check=False)
