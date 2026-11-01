import concurrent.futures as cf
import copy
import hashlib
import inspect
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path

import yaml

_LEARN_PHASES = [
    "infer_mode",
    "ingest",
    "discover",
    "verify",
    "write",
    "conformance",
    "layout",
    "render",
    "gates",
    "publish",
    "live_check",
]
PHASES = {
    "learn": _LEARN_PHASES,
    "rules": _LEARN_PHASES,
    "answer": _LEARN_PHASES,
    "recommend": _LEARN_PHASES,
    "verify": [
        "infer_mode",
        "ingest",
        "extract",
        "verify",
        "render",
        "gates",
        "publish",
        "live_check",
    ],
}
BOOT_PHASES = ["infer_mode"]

DONE, FAILED, SUSPENDED, RUNNING, WAITING = (
    "done",
    "failed",
    "suspended",
    "running",
    "waiting",
)
EXIT = {DONE: 0, FAILED: 1, SUSPENDED: 2, WAITING: 3}


class PoolExhausted(Exception):
    def __init__(self, pool, detail=""):
        super().__init__(f"key pool {pool} exhausted")
        self.pool = pool
        self.detail = detail


class GateFailed(Exception):
    def __init__(self, gate, problems):
        super().__init__(f"gate {gate} failed")
        self.gate = gate
        self.problems = problems


class RateLimited(Exception):
    pass


class PhaseResult:
    def __init__(self, data=None, mode=None):
        self.data = data if data is not None else {}
        self.mode = mode


class RunState:
    def __init__(
        self,
        run_id,
        topic,
        prompt,
        mode=None,
        phase="infer_mode",
        status=RUNNING,
        log=None,
        needs_user=None,
        failure=None,
        created_at="",
        context=None,
    ):
        self.run_id = run_id
        self.topic = topic
        self.prompt = prompt
        self.mode = mode
        self.phase = phase
        self.status = status
        self.log = log if log is not None else []
        self.needs_user = needs_user
        self.failure = failure
        self.created_at = created_at
        self.context = context if context is not None else {}

    def to_yaml(self):
        return yaml.safe_dump(self.__dict__, sort_keys=False, allow_unicode=True)

    @classmethod
    def from_file(cls, path):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            **{k: v for k, v in data.items() if k in inspect.signature(cls).parameters}
        )


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id(clock=now):
    return clock().replace(":", "").replace("-", "")


class Driver:
    def __init__(
        self,
        run_dir,
        state,
        handlers,
        clock=now,
    ):
        self.run_dir = run_dir
        self.state = state
        self.handlers = handlers
        self.clock = clock

    @classmethod
    def start(
        cls,
        run_dir,
        topic,
        prompt,
        handlers,
        run_id=None,
        clock=now,
    ):
        run_dir.mkdir(parents=True, exist_ok=True)
        state = RunState(
            run_id=run_id or new_run_id(clock),
            topic=topic,
            prompt=prompt,
            created_at=clock(),
        )
        d = cls(run_dir, state, handlers, clock)
        d.save()
        return d

    @classmethod
    def resume(cls, run_dir, handlers, clock=now):
        state = RunState.from_file(run_dir / "run.yaml")
        if state.status == DONE:
            return cls(run_dir, state, handlers, clock)
        state.status, state.needs_user, state.failure = RUNNING, None, None
        (run_dir / "NEEDS_YOU.md").unlink(missing_ok=True)
        (run_dir / "ASKS.md").unlink(missing_ok=True)
        d = cls(run_dir, state, handlers, clock)
        d.save()
        return d

    def save(self):
        (self.run_dir / "run.yaml").write_text(self.state.to_yaml(), encoding="utf-8")

    def save_finished(self):
        done = copy.copy(self.state)
        done.status = DONE
        done.phase = "done"
        done.needs_user = None
        done.failure = None
        if done.mode == "verify":
            done.prompt = f"[verify input withheld, sha256 {hashlib.sha256(done.prompt.encode()).hexdigest()[:12]}]"
        (self.run_dir / "run.yaml").write_text(done.to_yaml(), encoding="utf-8")

    def phases(self):
        return PHASES[self.state.mode] if self.state.mode else BOOT_PHASES

    def run(self):
        st = self.state
        if st.status == DONE:
            return EXIT[DONE]
        while st.status == RUNNING:
            phase = st.phase
            handler = self.handlers.get(phase)
            try:
                if handler is None:
                    raise NotImplementedError(f"no handler for phase {phase}")
                result = handler(self) or PhaseResult()
            except NeedsAgent as exc:
                self._wait(phase, exc)
                break
            except PoolExhausted as exc:
                self._suspend(phase, exc)
                break
            except GateFailed as exc:
                self._fail(phase, f"gate {exc.gate} failed", exc.problems)
                break
            except Exception as exc:
                self._fail(
                    phase,
                    f"{type(exc).__name__}: {exc}",
                    traceback.format_exc().splitlines()[-6:],
                )
                break
            st.log.append({"phase": phase, "at": self.clock(), "data": result.data})
            if phase == "infer_mode":
                if result.mode not in PHASES:
                    self._fail(
                        phase, f"infer_mode returned unknown mode {result.mode!r}", []
                    )
                    break
                st.mode = result.mode
            phases = self.phases()
            idx = phases.index(phase)
            if idx + 1 >= len(phases):
                st.status = DONE
                st.phase = "done"
            else:
                st.phase = phases[idx + 1]
            self.save()
        self.save()
        self.write_record()
        return EXIT[st.status]

    def _wait(self, phase, exc):
        st = self.state
        st.status = WAITING
        asks = [str(a) for a in exc.asks]
        # group fresh-subagent asks into batch files
        batches_dir = self.run_dir / "batches"
        batches_dir.mkdir(parents=True, exist_ok=True)
        # parse ask heads
        grouped = {}
        order = []
        for a in asks:
            p = Path(a)
            role = "default"
            step = ""
            fresh = False
            try:
                head = p.read_text(encoding="utf-8").split("---", 1)[0]
                for line in head.splitlines():
                    if line.startswith("role:"):
                        role = line.split(":", 1)[1].strip()
                    elif line.startswith("step:"):
                        step = line.split(":", 1)[1].strip()
                    elif line.startswith("fresh subagent:"):
                        fresh = "yes" in line
            except Exception:
                pass
            if not fresh:
                continue
            grouped.setdefault(role, []).append((step, a, p))
            if role not in order:
                order.append(role)
        # caps
        caps = {"extractor": 6, "verifier": 10, "media": 1}
        floors = {"extractor": 3}
        batch_lines = []
        for role in order:
            items = sorted(grouped[role], key=lambda x: x[0])
            cap = caps.get(role, 6)
            # balanced split
            n = len(items)
            k = max(1, -(-n // cap))  # ceil
            # size budget ~120k chars
            # split into k balanced batches, but also split oversized
            batches = [[] for _ in range(k)]
            for i, it in enumerate(items):
                batches[i % k].append(it)
            for bi, batch in enumerate(batches):
                if not batch:
                    continue
                # size budget check
                total = sum(p.stat().st_size if p.exists() else 0 for _, _, p in batch)
                if total > 120000 and len(batch) > 1:
                    # split each oversized into own
                    for it in batch:
                        _write_batch(batches_dir, role, [it], batch_lines)
                else:
                    _write_batch(batches_dir, role, batch, batch_lines)
        (self.run_dir / "ASKS.md").write_text(
            f"# Run {st.run_id} waits on the agent\n\n- Phase: {phase}\n\n"
            "Answer each ask below (the loading agent itself; `fresh subagent: yes` in a fresh subagent "
            "that sees only that ask file), write its reply file, then resume the run.\n\n"
            + "".join(f"- {a}\n" for a in asks)
            + ("\n## batches\n" + "\n".join(batch_lines) if batch_lines else ""),
            encoding="utf-8",
        )

    def _suspend(self, phase, exc):
        st = self.state
        st.status = SUSPENDED
        st.needs_user = f"Key pool {exc.pool} is exhausted during phase {phase}."
        (self.run_dir / "NEEDS_YOU.md").write_text(
            f"# Run {st.run_id} needs you\n\n"
            f"- Topic: {st.topic}\n- Phase: {phase}\n- Reason: {st.needs_user}\n"
            f"- Detail: {exc.detail or '-'}\n\n"
            "Add keys or wait for the reset window, then resume: re-run the driver on this run directory.\n"
            "State is saved; settled claims are kept.\n",
            encoding="utf-8",
        )

    def _fail(self, phase, reason, problems):
        st = self.state
        st.status = FAILED
        st.failure = {
            "phase": phase,
            "reason": reason,
            "problems": [str(p) for p in problems],
        }
        body = (
            "\n".join(f"- {p}" for p in st.failure["problems"]) or "- (none recorded)"
        )
        (self.run_dir / "REPORT.md").write_text(
            f"# Run {st.run_id} failed\n\n- Topic: {st.topic}\n- Mode: {st.mode}\n- Phase: {phase}\n- Reason: {reason}\n\n## Problems\n\n{body}\n\n"
            "The draft branch keeps the ledger; re-run to resume. If the failed gate is live-check the publish was reverted: start a new run.\n",
            encoding="utf-8",
        )

    def write_record(self, status=None):
        st = self.state
        record = {
            "run_id": st.run_id,
            "topic": st.topic,
            "mode": st.mode,
            "status": status or st.status,
            "phases": [{"phase": e["phase"], "at": e["at"]} for e in st.log],
            "failure": st.failure,
            **(st.context.get("record") or {}),
        }
        (self.run_dir / "RUN_RECORD.yaml").write_text(
            yaml.safe_dump(record, sort_keys=False), encoding="utf-8"
        )


class TaskResult:
    def __init__(self, ok, value=None, error=None, attempts=1, waiting=None):
        self.ok = ok
        self.value = value
        self.error = error
        self.attempts = attempts
        self.waiting = waiting


def run_wave(
    tasks,
    fn,
    size=8,
    timeout=None,
    retries=1,
    max_rate_limit_retries=5,
):
    results = {}
    queue = list(tasks)
    tries = {k: 0 for k in tasks}
    rl_tries = {k: 0 for k in tasks}
    timed_out = {}
    while queue:
        batch, queue = queue[:size], queue[size:]
        halve = False
        live = []
        for key in batch:
            orig = timed_out.pop(key, None)
            if orig is None:
                live.append(key)
            elif not orig.done():
                results[key] = TaskResult(
                    False,
                    error=f"timeout after {timeout}s (original still running, not re-run)",
                    attempts=tries[key],
                )
            elif orig.exception() is None:
                results[key] = TaskResult(True, orig.result(), attempts=tries[key])
            else:
                live.append(key)
        batch = live
        if not batch:
            continue
        pool = cf.ThreadPoolExecutor(max_workers=len(batch))
        try:
            futures = {pool.submit(fn, tasks[k]): k for k in batch}
            for key in batch:
                tries[key] += 1
            done, pending = cf.wait(futures, timeout=timeout)
            for fut in done:
                key = futures[fut]
                try:
                    results[key] = TaskResult(True, fut.result(), attempts=tries[key])
                except NeedsAgent as exc:
                    results[key] = TaskResult(
                        False, error=str(exc), attempts=tries[key], waiting=exc.asks
                    )
                except RateLimited:
                    halve = True
                    rl_tries[key] += 1
                    if rl_tries[key] > max_rate_limit_retries:
                        results[key] = TaskResult(
                            False, error="rate limited", attempts=tries[key]
                        )
                    else:
                        queue.append(key)
                except Exception as exc:
                    if tries[key] <= retries:
                        queue.append(key)
                    else:
                        results[key] = TaskResult(
                            False,
                            error=f"{type(exc).__name__}: {exc}",
                            attempts=tries[key],
                        )
            for fut in pending:
                key = futures[fut]
                if tries[key] <= retries:
                    timed_out[key] = fut
                    queue.append(key)
                else:
                    results[key] = TaskResult(
                        False,
                        error=f"timeout after {timeout}s (still running)",
                        attempts=tries[key],
                    )
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        if halve:
            size = max(1, size // 2)
    return results, size


class NeedsAgent(Exception):
    """AI steps the loading agent has not answered yet (#340). The run waits; nothing is retried."""

    def __init__(self, asks):
        self.asks = [str(a) for a in asks]
        super().__init__(f"waiting on the agent for {len(self.asks)} step(s)")


def waiting(results):
    asks = [a for r in results.values() for a in (r.waiting or [])]
    return NeedsAgent(dict.fromkeys(asks)) if asks else None


def _write_batch(batches_dir, role, batch, batch_lines):
    import hashlib

    names = "".join(f"{s}|{a}" for s, a, _ in batch)
    h = hashlib.sha256(names.encode()).hexdigest()[:8]
    path = batches_dir / f"{role}-{h}.batch.md"
    lines = [f"# Batch {role} ({len(batch)} asks)\n"]
    for step, ask, pp in batch:
        reply = str(ask).replace(".ask.md", ".reply.md")
        lines.append(f"- ask: {ask}")
        lines.append(f"  reply: {reply}")
    lines.append(
        "\nWorker procedure: read each source before answering; start each answer with one line stating what the page is about; never emit an empty list without reading; never script or template replies; leave the reply absent if you cannot answer."
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    batch_lines.append(str(path))


class HandRunner:
    """Hands every AI step to the agent that loaded the skill; the skill never calls a model (#340).

    A step's prompt goes to `<dir>/<step>-<hash>.ask.md`; the agent writes the reply beside it as
    `.reply.md` and resumes the run. The hash covers role, prompt and attached files, so a changed
    payload asks again instead of reusing a stale reply. Checking roles are marked for a fresh subagent.
    """

    def __init__(self, dir, checking=()):
        self.dir = Path(dir)
        self.checking = set(checking)

    def run(self, role, prompt, step="", context=None):
        files = [str(f) for f in (context or {}).get("files", ())]
        digest = hashlib.sha256(
            "\0".join([role, prompt, *files]).encode("utf-8")
        ).hexdigest()[:10]
        name = f"{re.sub(r'[^A-Za-z0-9_.-]', '_', step) or 'step'}-{digest}"
        reply = self.dir / f"{name}.reply.md"
        if reply.exists():
            return reply.read_text(encoding="utf-8")
        ask = self.dir / f"{name}.ask.md"
        self.dir.mkdir(parents=True, exist_ok=True)
        attached = "".join(f"- {f}\n" for f in files)
        ask.write_text(
            f"role: {role}\nstep: {step}\n"
            f"fresh subagent: {'yes' if role in self.checking else 'no'}\n"
            f"reply file: {reply}\n"
            + (f"attached files:\n{attached}" if files else "")
            + f"\n---\n\n{prompt}\n",
            encoding="utf-8",
        )
        raise NeedsAgent([ask])
