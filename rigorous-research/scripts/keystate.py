import contextlib
import hashlib
import json
import sys
import time
from datetime import datetime, timedelta, timezone

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

UNKNOWN_WINDOW = timedelta(hours=24)
UNKNOWN_URLS_TO_ROTATE = 2


def fingerprint(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _parse(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _stamp(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reset_at(exhausted_at, reset):
    if reset == "monthly":
        year, month = (
            (exhausted_at.year + 1, 1)
            if exhausted_at.month == 12
            else (exhausted_at.year, exhausted_at.month + 1)
        )
        return exhausted_at.replace(
            year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    return exhausted_at + UNKNOWN_WINDOW


class LockTimeout(TimeoutError):
    pass


def _try_lock(fh):
    if sys.platform == "win32":
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(fh):
    if sys.platform == "win32":
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def file_lock(path, timeout=60.0, poll=0.05):
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = path.open("a+b", buffering=0)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                _try_lock(fh)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise LockTimeout(f"lock {path.name} busy") from None
                time.sleep(poll)
        try:
            yield
        finally:
            _unlock(fh)
    finally:
        fh.close()


def _replace(src, dst, attempts=5):
    for i in range(attempts):
        try:
            src.replace(dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.02 * (i + 1))


class KeyState:
    def __init__(self, path):
        self.path = path
        self.lock_dir = path.parent / f"{path.stem}.locks"
        self.refresh()

    def _read(self):
        data = (
            json.loads(self.path.read_text(encoding="utf-8"))
            if self.path.exists()
            else {}
        )
        for section in ("keys", "generation", "unknown"):
            data.setdefault(section, {})
        return data

    def _mutate(self, fn):
        with file_lock(self.lock_dir / "state.lock", timeout=10.0):
            self.data = self._read()
            result = fn(self.data)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self.data, indent=1, sort_keys=True), encoding="utf-8"
            )
            _replace(tmp, self.path)
            return result

    def refresh(self):
        with file_lock(self.lock_dir / "state.lock", timeout=10.0):
            self.data = self._read()

    def mark_exhausted(self, pool, fp, now=None, reset="unknown"):
        stamp = _stamp(now or datetime.now(timezone.utc))

        def mark(d):
            d["keys"].setdefault(pool, {})[fp] = {"exhausted_at": stamp, "reset": reset}

        self._mutate(mark)

    def is_available(self, pool, fp, now=None):
        entry = self.data["keys"].get(pool, {}).get(fp)
        if entry is None:
            return True
        now = now or datetime.now(timezone.utc)
        return now >= reset_at(
            _parse(entry["exhausted_at"]), entry.get("reset", "unknown")
        )

    def available(self, pool, fps, now=None):
        return [fp for fp in fps if self.is_available(pool, fp, now)]

    def pool_exhausted(self, pool, fps, now=None):
        return bool(fps) and not self.available(pool, fps, now)

    def generation(self, pool):
        return int(self.data["generation"].get(pool, 0))

    def bump_generation(self, pool):
        def bump(d):
            d["generation"][pool] = int(d["generation"].get(pool, 0)) + 1
            d["unknown"].pop(pool, None)

        self._mutate(bump)

    def note_unknown_failure(self, pool, signature, url):
        ufp = fingerprint(url)

        def note(d):
            urls = d["unknown"].setdefault(pool, {}).setdefault(signature, [])
            if ufp not in urls:
                urls.append(ufp)
            return len(urls) >= UNKNOWN_URLS_TO_ROTATE

        return bool(self._mutate(note))


@contextlib.contextmanager
def rotation_lock(lock_dir, pool, timeout=60.0, poll=0.05):
    with file_lock(lock_dir / f"rotate-{pool}.lock", timeout=timeout, poll=poll):
        yield


def rotate_once(
    state_path,
    pool,
    seen_generation,
    rotate,
    timeout=60.0,
):
    lock_dir = KeyState(state_path).lock_dir
    with rotation_lock(lock_dir, pool, timeout=timeout):
        state = KeyState(state_path)
        if state.generation(pool) != seen_generation:
            return False
        rotate(state)
        state.bump_generation(pool)
        return True
