import hashlib
import json
import re
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urldefrag, urlparse

import yaml

from . import ledger, log_attempt


class Config:
    def __init__(
        self,
        wave_size=8,
        wave_timeout=1800.0,
        max_waves=6,
        saturation_waves=2,
        max_sources_per_round=6,
        max_source_chars=60000,
        max_claim_words=45,
        gate_batch=10,
        site_url=None,
        live_attempts=12,
        live_delay=20.0,
        url_audit=True,
        min_rounds_true=2,
        min_text_chars=200,
        media_pages=4,
    ):
        self.wave_size = wave_size
        self.wave_timeout = wave_timeout
        self.max_waves = max_waves
        self.saturation_waves = saturation_waves
        self.max_sources_per_round = max_sources_per_round
        self.max_source_chars = max_source_chars
        self.max_claim_words = max_claim_words
        self.gate_batch = gate_batch
        self.site_url = site_url
        self.live_attempts = live_attempts
        self.live_delay = live_delay
        self.url_audit = url_audit
        self.min_rounds_true = min_rounds_true
        self.min_text_chars = min_text_chars
        self.media_pages = media_pages


def now_stamp(clock=None):
    return (clock() if clock else datetime.now(timezone.utc)).strftime(
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
        self.archive_path = topic_dir / "attempts.archive.jsonl"
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

    def archive_attempts(self, cid):
        with self.lock:
            rows = self.attempts()
            keep = [r for r in rows if r["claim"] != cid]
            moved = [r for r in rows if r["claim"] == cid]
            if not moved:
                return 0
            with self.archive_path.open("a", encoding="utf-8") as fh:
                for r in moved:
                    fh.write(json.dumps(r, ensure_ascii=True, sort_keys=True) + "\n")
            _atomic_write(
                self.attempts_path,
                "".join(
                    json.dumps(r, ensure_ascii=True, sort_keys=True) + "\n"
                    for r in keep
                ),
            )
            return len(moved)

    def clusters(self):
        seen = {}
        for c in self.claims:
            label = c.get("cluster")
            if label:
                seen.setdefault(ledger.normalize_text(label), label)
        return list(seen.values())


class RawStore:
    cue_stamp = re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?\]\s*")

    def __init__(self, main_root, topic):
        self.main_root = main_root
        self.dir = main_root / "work" / topic / "raw"
        self.rel = f"work/{topic}/raw"

    def put(self, name, text):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{name}.txt").write_text(text, encoding="utf-8", newline="\n")
        return f"{self.rel}/{name}.txt", hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()[:16]

    def get(self, raw_path):
        if not raw_path:
            return None
        path = self.main_root / raw_path
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
        self.topic_dir = self.site_root / "_ledger" / self.topic
        self.ledger = Ledger(self.topic_dir)
        self.raw = RawStore(self.main_root, self.topic)
        self.inbox = self.raw.dir.parent / "inbox"
        self.step_data = {}

    def stamp(self):
        return now_stamp(self.clock)

    def work_file(self, name):
        path = self.main_root / "work" / self.topic / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
