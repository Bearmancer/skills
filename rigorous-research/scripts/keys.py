import subprocess
import sys
import time
from datetime import datetime, timezone

from . import registry
from .driver import PoolExhausted
from .keystate import KeyState, rotate_once

RETRY, NEXT_SURFACE, RATE_LIMITED, GIVE_UP = (
    "retry",
    "next_surface",
    "rate_limited",
    "give_up",
)
ROTATE_CLASSES = ("out_of_credit", "bad_key")


def _utcnow():
    return datetime.now(timezone.utc)


class KeyManager:
    def __init__(
        self,
        reg,
        state_path,
        *,
        run=subprocess.run,
        skill_dir=registry.ROOT,
        now=_utcnow,
        reconnect_wait=5.0,
        sleep=time.sleep,
    ):
        self.reg = reg
        self.state_path = state_path
        self.run = run
        self.skill_dir = skill_dir
        self.now = now
        self.reconnect_wait = reconnect_wait
        self.sleep = sleep
        self._unkeyed_unknown = set()

    def _switch(self, *args):
        proc = self.run(
            [sys.executable, "-m", "scripts.switch_api_key", *args],
            cwd=self.skill_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"switch_api_key {' '.join(args)} failed ({proc.returncode}): {(proc.stderr or '')[:200]}"
            )
        return proc.stdout

    def _pool(self, server):
        srv = self.reg["servers"].get(server)
        if srv is None:
            raise registry.RegistryError(f"unknown server {server}")
        return srv.get("pool") if srv.get("keyed") else None

    def fingerprints(self, pool):
        out = {}
        for line in self._switch("--fingerprints", "--service", pool).splitlines():
            cols = line.rstrip("\r\n").split("\t")
            if len(cols) == 4 and cols[0] == pool:
                out[cols[1]] = {"account": cols[2], "active": cols[3] == "active"}
        return out

    def generation(self, pool):
        return KeyState(self.state_path).generation(pool)

    def guard(self, server):
        pool = self._pool(server)
        if pool is None:
            return
        if KeyState(self.state_path).pool_exhausted(
            pool, list(self.fingerprints(pool)), self.now()
        ):
            raise PoolExhausted(pool, "every key is inside its reset window")

    def _rotate(self, pool, state):
        rows = self.fingerprints(pool)
        fps = list(rows)
        active = next((i for i, fp in enumerate(fps) if rows[fp]["active"]), None)
        reset = registry.key_info(self.reg, pool)["reset"]
        if active is not None:
            state.mark_exhausted(pool, fps[active], self.now(), reset)
            state.refresh()
        if state.pool_exhausted(pool, fps, self.now()):
            raise PoolExhausted(pool, f"{len(fps)} keys exhausted")
        start = active if active is not None else -1
        for offset in range(1, len(fps) + 1):
            idx = (start + offset) % len(fps)
            if state.is_available(pool, fps[idx], self.now()):
                if offset == 1 and active is not None:
                    self._switch("--service", pool, "--next")
                else:
                    self._switch("--service", pool, "--set", rows[fps[idx]]["account"])
                return
        raise PoolExhausted(pool, "no available key")

    def _rotation_decision(self, server, pool, seen_generation):
        rotate_once(
            self.state_path,
            pool,
            seen_generation,
            lambda state: self._rotate(pool, state),
        )
        self.sleep(self.reconnect_wait)
        self.guard(server)
        return RETRY

    def on_failure(
        self,
        server,
        *,
        status=None,
        code=None,
        url="",
        seen_generation=0,
    ):
        pool = self._pool(server)
        cls = registry.classify_error(self.reg, server, status, code)
        if cls == "blocked":
            return NEXT_SURFACE
        if cls == "rate_limit":
            return RATE_LIMITED
        if cls in ROTATE_CLASSES:
            return (
                GIVE_UP
                if pool is None
                else self._rotation_decision(server, pool, seen_generation)
            )
        signature = f"{status}:{code}"
        if pool is None:
            key = (server, signature, url)
            if key in self._unkeyed_unknown:
                return NEXT_SURFACE
            self._unkeyed_unknown.add(key)
            return RETRY
        if KeyState(self.state_path).note_unknown_failure(pool, signature, url):
            return self._rotation_decision(server, pool, seen_generation)
        return RETRY
