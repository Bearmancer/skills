import hashlib
import re
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urldefrag, urlparse

import yaml

from . import ledger, log_attempt

DEFAULT_STATE_ROOT = Path.home() / ".rigor"


def _root(state_root=None):
    return Path(state_root).expanduser() if state_root else DEFAULT_STATE_ROOT


def keystate_file(state_root=None):
    """The one key-state file, shared by every run (ADR 0025)."""
    return _root(state_root) / "keystate.json"


def publish_lock_file(state_root=None):
    """The one publish lock, shared by every run (ADR 0024)."""
    return _root(state_root) / "publish.lock"


class Layout:
    """The one place that maps a topic to the paths of its state.

    Nothing else builds a state path, and no path carries a run id: one run per
    topic. Sources sit beside the run so a start that wipes `run/` keeps them.
    """

    def __init__(self, state_root, topic):
        self.state_root = _root(state_root)
        self.topic = topic
        self.root = self.state_root / topic
        self.sources = self.root / "sources"
        self.run = self.root / "run"
        self.keystate = keystate_file(self.state_root)
        self.publish_lock = publish_lock_file(self.state_root)
        self.link_failures = self.state_root / "link-failures.jsonl"
        self.run_yaml = self.run / "run.yaml"
        self.asks = self.run / "ASKS.md"
        self.report = self.run / "REPORT.md"
        self.needs_you = self.run / "NEEDS_YOU.md"
        self.claims = self.run / "claims.yaml"
        self.sources_yaml = self.run / "sources.yaml"
        self.attempts = self.run / "attempts.jsonl"
        self.batches = self.run / "batches"
        self.drafts = self.run / "drafts"
        self.lessons = self.run / "lessons"
        self.media = self.run / "media"
        self.site = self.run / "site"

    def source_file(self, name):
        """The text file for source `name` (`sN`), one file per source."""
        return self.sources / f"{name}.txt"


class Config:
    def __init__(
        self,
        wave_timeout=1800.0,
        max_sources_per_round=6,
        max_source_chars=60000,
        max_claim_words=45,
        gate_batch=10,
        site_url=None,
        url_audit=True,
        min_rounds_true=2,
        min_text_chars=200,
        max_source_chunks=3,
        max_claims=50,
        max_asks=None,
        max_mis_tasks=3,
        state_root=None,
    ):
        self.state_root = _root(state_root)
        self.max_source_chunks = max_source_chunks
        self.max_claims = max_claims
        self.max_asks = ASKS_PER_CLAIM * max_claims if max_asks is None else max_asks
        self.max_mis_tasks = max_mis_tasks
        self.wave_timeout = wave_timeout
        self.max_sources_per_round = max_sources_per_round
        self.max_source_chars = max_source_chars
        self.max_claim_words = max_claim_words
        self.gate_batch = gate_batch
        self.site_url = site_url
        self.url_audit = url_audit
        self.min_rounds_true = min_rounds_true
        self.min_text_chars = min_text_chars


BUDGET_KEYS = ("max_claims", "max_source_chunks", "max_asks")
# Verification costs about 8 asks per claim (the Bernie run: 322 asks, 40 claims).
ASKS_PER_CLAIM = 8


def apply_budget(cfg, overrides):
    """Resolve the run's budgets once, at run start, whatever the mode."""
    overrides = overrides or {}
    for key in BUDGET_KEYS:
        value = overrides.get(key)
        if value is not None:
            setattr(cfg, key, value)
    if overrides.get("max_asks") is None:
        # An explicit --max-asks wins; otherwise the ceiling follows the claim cap.
        cfg.max_asks = ASKS_PER_CLAIM * cfg.max_claims


def now_stamp(clock=None):
    return (clock() if clock else datetime.now(UTC)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def normalize_url(url):
    return urldefrag(url.strip())[0].rstrip("/").lower()


def tier_for(reg, kind, url=""):
    host = (urlparse(url).hostname or "").lower()
    for domain, tier in (reg.get("tier_overrides") or {}).items():
        if host == domain or host.endswith("." + domain):
            return tier
    for tier, kinds in reg["tiers"].items():
        if kind in kinds:
            return tier
    return "T3"


def source_kinds(reg):
    return [k for kinds in reg["tiers"].values() for k in kinds]


def _atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    for i in range(5):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if i == 4:
                raise
            time.sleep(0.02 * (i + 1))


class Ledger:
    def __init__(self, topic_dir):
        self.dir = topic_dir
        self.claims_path = topic_dir / "claims.yaml"
        self.sources_path = topic_dir / "sources.yaml"
        self.attempts_path = topic_dir / "attempts.jsonl"
        self.lock = threading.RLock()
        self.claims_doc = {"schema": 1, "claims": []}
        self.sources_doc = {"schema": 1, "sources": []}
        self.load()

    def load(self):
        with self.lock:
            if self.claims_path.exists():
                self.claims_doc = ledger.load_claims(self.claims_path) or {
                    "schema": 1,
                    "claims": [],
                }
            if self.sources_path.exists():
                self.sources_doc = ledger.load_sources(self.sources_path) or {
                    "schema": 1,
                    "sources": [],
                }
            self.claims_doc.setdefault("claims", [])
            self.sources_doc.setdefault("sources", [])

    def save(self):
        with self.lock:
            _atomic_write(
                self.sources_path,
                yaml.safe_dump(
                    self.sources_doc, sort_keys=False, allow_unicode=True, width=100
                ),
            )
            _atomic_write(self.claims_path, ledger.dump_claims(self.claims_doc))

    @property
    def claims(self):
        return self.claims_doc["claims"]

    @property
    def sources(self):
        return self.sources_doc["sources"]

    def attempts(self):
        return ledger.load_attempts(self.attempts_path)

    def claim(self, cid):
        for c in self.claims:
            if c["id"] == cid:
                return c
        raise KeyError(cid)

    def source(self, sid):
        for s in self.sources:
            if s["id"] == sid:
                return s
        raise KeyError(sid)

    def sources_by_id(self):
        return {s["id"]: s for s in self.sources}

    def _next(self, prefix, rows):
        top = max((int(r["id"][1:]) for r in rows), default=0)
        return f"{prefix}{top + 1}"

    def add_claim(
        self,
        text,
        origin,
        cluster=None,
        anchors=None,
    ):
        text = " ".join(text.split())
        h = ledger.claim_hash(text)
        with self.lock:
            for c in self.claims:
                if c["hash"] == h:
                    for a in anchors or []:
                        if a not in c.setdefault("anchors", []):
                            c["anchors"].append(a)
                    return c, False
            claim = {
                "id": self._next("c", self.claims),
                "text": text,
                "hash": h,
                "status": "open",
                "origin": origin,
                "rounds": 0,
                "paradigms_tried": [],
                "evidence": [],
            }
            if cluster:
                claim["cluster"] = cluster
            if anchors:
                claim["anchors"] = list(anchors)
            self.claims.append(claim)
            return claim, True

    def add_source(
        self,
        url,
        *,
        kind,
        tier,
        publisher,
        status="read",
        fail_reason=None,
        language=None,
        authority=None,
        cites=None,
        retrieved_at=None,
        content_hash=None,
        raw_path=None,
    ):
        key = normalize_url(url)
        with self.lock:
            existing = next(
                (s for s in self.sources if normalize_url(s["url"]) == key), None
            )
            row = {
                "url": url.strip(),
                "kind": kind,
                "tier": tier,
                "publisher": publisher or "unknown",
                "status": status,
            }
            optional = {
                "language": language,
                "authority": authority,
                "cites": cites,
                "retrieved_at": retrieved_at,
                "content_hash": content_hash,
                "raw_path": raw_path,
            }
            row.update({k: v for k, v in optional.items() if v})
            if status == "failed":
                row["fail_reason"] = fail_reason or "unspecified"
            if existing is not None:
                if existing["status"] == "read" or status == "failed":
                    return existing
                existing.update(row)
                existing.pop("fail_reason", None)
                return existing
            row["id"] = self._next("s", self.sources)
            self.sources.append({"id": row.pop("id"), **row})
            return self.sources[-1]

    def add_evidence(
        self,
        cid,
        source_id,
        stance,
        locator,
        quote,
        **extra,
    ):
        with self.lock:
            claim = self.claim(cid)
            sig = (
                source_id,
                ledger.normalize_text(locator),
                ledger.normalize_text(quote),
                stance,
            )
            for ev in claim["evidence"]:
                if (
                    ev["source"],
                    ledger.normalize_text(ev["locator"]),
                    ledger.normalize_text(ev["quote"]),
                    ev["stance"],
                ) == sig:
                    return False
            entry = {
                "source": source_id,
                "locator": locator,
                "quote": quote,
                "stance": stance,
            }
            entry.update(
                {
                    k: v
                    for k, v in extra.items()
                    if v not in (None, "", False) or k == "text_corroboration" and v
                }
            )
            claim["evidence"].append(entry)
            return True

    def append_attempt(self, record):
        with self.lock:
            log_attempt.append(self.attempts_path, record)

    def next_source_id(self):
        with self.lock:
            return self._next("s", self.sources)

    def add_chapter(self, parent, *, n, source_id, raw_path):
        """Register one chapter of a media source as its own source row (ADR 0038)."""
        with self.lock:
            row = {
                "id": source_id,
                "url": f"{parent['url']}#ch{n}",
                "kind": parent.get("kind") or "unknown",
                "tier": parent["tier"],
                "publisher": parent["publisher"],
                "status": "read",
                "raw_path": raw_path,
            }
            if parent.get("retrieved_at"):
                row["retrieved_at"] = parent["retrieved_at"]
            self.sources.append(row)
            return row

    def clusters(self):
        seen = {}
        for c in self.claims:
            label = c.get("cluster")
            if label:
                seen.setdefault(ledger.normalize_text(label), label)
        return list(seen.values())


class RawStore:
    cue_stamp = re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?\]\s*")

    def __init__(self, layout):
        self.dir = layout.sources

    def put(self, name, text):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{name}.txt").write_text(text, encoding="utf-8", newline="\n")
        return f"{name}.txt", hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def get(self, raw_path):
        if not raw_path:
            return None
        path = self.dir / Path(raw_path).name
        return path.read_text(encoding="utf-8") if path.exists() else None

    @staticmethod
    def contains(text, quote):
        needle = ledger.normalize_text(quote)
        return bool(needle) and needle in ledger.normalize_text(
            RawStore.cue_stamp.sub(" ", text)
        )


class Context:
    def __init__(
        self,
        site_root,
        main_root,
        topic,
        reg,
        runner,
        fetcher,
        publisher,
        cfg=None,
        keys=None,
        audit_urls=None,
        live_fetch=None,
        clock=None,
        sleep=time.sleep,
    ):
        self.site_root = site_root
        self.main_root = main_root
        self.topic = topic
        self.reg = reg
        self.runner = runner
        self.fetcher = fetcher
        self.publisher = publisher
        self.cfg = cfg if cfg is not None else Config()
        self.keys = keys
        self.audit_urls = audit_urls
        self.live_fetch = live_fetch
        self.clock = clock
        self.sleep = sleep
        self.layout = Layout(self.cfg.state_root, self.topic)
        # Both exist before any ask is written: asks and fetch drops name them.
        self.layout.sources.mkdir(parents=True, exist_ok=True)
        self.layout.run.mkdir(parents=True, exist_ok=True)
        self.topic_dir = self.layout.run
        self.ledger = Ledger(self.topic_dir)
        self.raw = RawStore(self.layout)
        # Where an agent saves a page it fetched; the driver admits it as sN.txt.
        self.drop_dir = self.layout.sources
        self.step_data = {}

    def stamp(self):
        return now_stamp(self.clock)

    def work_file(self, name):
        path = self.layout.run / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
