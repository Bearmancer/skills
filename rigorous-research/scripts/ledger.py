import hashlib
import json
import re
import unicodedata
from collections import namedtuple
from pathlib import Path

import yaml

from . import registry

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schema"
MAX_QUOTE_WORDS = 25
MAX_ROUNDS = 5
CREDIBLE_TIERS = ("T1", "T2")
CLAIM_ID = re.compile(r"^c[0-9]+$")


class Violation(
    namedtuple("Violation", "rule claim message severity", defaults=("error",))
):
    def __str__(self):
        where = self.claim or "-"
        return f"[{self.severity}] {self.rule} {where}: {self.message}"


def normalize_text(text):
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"(?<=\d)[.,](?=\d)", "_", text)
    text = re.sub(r"(?<![\w.])[-\u2212](?=\d)", "neg", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def claim_hash(text):
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()[:16]


def _load_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _normalize_status(claims):
    for c in claims.get("claims", []):
        if c.get("status") is True:
            c["status"] = "true"
        elif c.get("status") is False:
            c["status"] = "untrue"
    return claims


def load_claims(path):
    return _normalize_status(_load_yaml(path))


def load_sources(path):
    return _load_yaml(path)


def load_attempts(path):
    if not path.exists():
        return []
    rows = []
    lines = [
        ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    for i, line in enumerate(lines):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if i < len(lines) - 1:
                raise
    return rows


def dump_claims(data):
    class _Dumper(yaml.SafeDumper):
        pass

    def _str(dumper, value):
        if value in ("true", "false", "null", "yes", "no", "on", "off"):
            return dumper.represent_scalar("tag:yaml.org,2002:str", value, style='"')
        return dumper.represent_scalar("tag:yaml.org,2002:str", value)

    _Dumper.add_representer(str, _str)
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True)


def _schema_errors(schema_name, data):
    from jsonschema import Draft202012Validator

    schema = json.loads((SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    out = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        out.append(f"{loc}: {err.message}")
    return out


def _words(text):
    return len(text.split())


def _supporting(
    claim,
    sources,
    tiers=None,
):
    return _by_stance(claim, sources, "supports", tiers)


def _contradicting(
    claim,
    sources,
    tiers=None,
):
    return _by_stance(claim, sources, "contradicts", tiers)


def _by_stance(claim, sources, stance, tiers):
    out = []
    for ev in claim.get("evidence", []):
        src = sources.get(ev["source"])
        if src is None or src.get("status") != "read":
            continue
        if ev["stance"] != stance:
            continue
        if tiers is not None and src["tier"] not in tiers:
            continue
        out.append((ev, src))
    return out


def _meets_bar(pairs):
    if any(src["tier"] == "T1" for _, src in pairs):
        return True
    credible = [(ev, src) for ev, src in pairs if src["tier"] in CREDIBLE_TIERS]
    publishers = {src["publisher"].strip().lower() for _, src in credible}
    has_rationale = any(
        (ev.get("independence_rationale") or "").strip() for ev, _ in credible
    )
    return len(credible) >= 2 and len(publishers) >= 2 and has_rationale


supporting = _supporting
contradicting = _contradicting
meets_bar = _meets_bar


def check(
    claims_doc,
    sources_doc,
    attempts=None,
    publish=False,
    round_order=None,
):
    v = []
    for msg in _schema_errors("claims.schema.json", claims_doc):
        v.append(Violation("schema", None, f"claims.yaml {msg}"))
    for msg in _schema_errors("sources.schema.json", sources_doc):
        v.append(Violation("schema", None, f"sources.yaml {msg}"))
    if v:
        return v

    sources = {s["id"]: s for s in sources_doc["sources"]}
    if len(sources) != len(sources_doc["sources"]):
        v.append(Violation("unique-source-id", None, "duplicate source id"))
    for s in sources.values():
        if s["status"] == "failed" and not s.get("fail_reason"):
            v.append(
                Violation(
                    "failed-source-reason",
                    None,
                    f"{s['id']} failed without fail_reason",
                )
            )

    ids = set()
    for c in claims_doc["claims"]:
        cid = c["id"]
        if cid in ids:
            v.append(Violation("unique-claim-id", cid, "duplicate claim id"))
        ids.add(cid)
        if c["hash"] != claim_hash(c["text"]):
            v.append(Violation("hash", cid, "hash does not match normalised text"))
        if len(set(c["paradigms_tried"])) != len(c["paradigms_tried"]):
            v.append(
                Violation("paradigms-unique", cid, "paradigms_tried has duplicates")
            )
        if c["rounds"] > MAX_ROUNDS:
            v.append(
                Violation(
                    "max-rounds", cid, f"{c['rounds']} rounds exceeds {MAX_ROUNDS}"
                )
            )
        for ev in c["evidence"]:
            if ev["source"] not in sources:
                v.append(
                    Violation("evidence-source", cid, f"unknown source {ev['source']}")
                )
            elif sources[ev["source"]]["status"] != "read":
                v.append(
                    Violation("evidence-source", cid, f"{ev['source']} was not read")
                )
            if _words(ev["quote"]) > MAX_QUOTE_WORDS:
                v.append(
                    Violation(
                        "quote-length", cid, f"quote over {MAX_QUOTE_WORDS} words"
                    )
                )
        v.extend(_check_status(c, sources, publish))

    if attempts is not None:
        v.extend(check_rotation(attempts, round_order or _default_round_order()))
        v.extend(check_log_matches_ledger(attempts, claims_doc))
    return v


def _check_status(
    c,
    sources,
    publish,
):
    cid, status = c["id"], c["status"]
    out = []
    sup = _supporting(c, sources)
    con = _contradicting(c, sources)
    sup_cred = _supporting(c, sources, CREDIBLE_TIERS)
    con_cred = _contradicting(c, sources, CREDIBLE_TIERS)

    if status == "open":
        if publish:
            out.append(Violation("open-at-publish", cid, "claim still open"))
        return out

    if status in ("true", "untrue") and c["rounds"] < 1:
        out.append(
            Violation("rounds-required", cid, f"{status} needs at least one round")
        )

    match status:
        case "true":
            if not _meets_bar(sup):
                out.append(
                    Violation(
                        "true-bar",
                        cid,
                        "needs one T1 source, or two T1/T2 sources from distinct publishers with an independence_rationale",
                    )
                )
            if con_cred:
                out.append(
                    Violation(
                        "true-contradicted",
                        cid,
                        "credible contradicting evidence; status should be interpretive",
                    )
                )
            if "visual-read" in c.get("tags", []):
                out.extend(_check_visual_read(c, sup))
        case "untrue":
            if not _meets_bar(con):
                out.append(
                    Violation(
                        "untrue-bar",
                        cid,
                        "contradicting evidence does not meet the truth bar",
                    )
                )
            if sup_cred:
                out.append(
                    Violation(
                        "untrue-supported",
                        cid,
                        "credible supporting evidence; status should be interpretive",
                    )
                )
        case "interpretive":
            positions = c.get("positions", [])
            if len(positions) < 2:
                out.append(
                    Violation(
                        "interpretive-positions", cid, "needs at least 2 positions"
                    )
                )
            for p in positions:
                if not any(
                    sources.get(s, {}).get("tier") in CREDIBLE_TIERS
                    for s in p["sources"]
                ):
                    out.append(
                        Violation(
                            "interpretive-source",
                            cid,
                            "each position needs a T1/T2 source",
                        )
                    )
                for s in p["sources"]:
                    if s not in sources:
                        out.append(
                            Violation("interpretive-source", cid, f"unknown source {s}")
                        )
        case "not-found":
            if c["rounds"] != MAX_ROUNDS:
                out.append(
                    Violation(
                        "not-found-rounds", cid, f"not-found needs {MAX_ROUNDS} rounds"
                    )
                )
            if _meets_bar(sup) or _meets_bar(con):
                out.append(
                    Violation(
                        "not-found-evidence",
                        cid,
                        "evidence meets the truth bar; pick another status",
                    )
                )
            if sup_cred and con_cred:
                out.append(
                    Violation(
                        "not-found-evidence",
                        cid,
                        "credible evidence on both sides; status should be interpretive",
                    )
                )
    return out


def _check_visual_read(claim, supporting):
    read_by = {ev["read_by"] for ev, _ in supporting if ev.get("read_by")}
    corroborated = any(ev.get("text_corroboration") for ev, _ in supporting)
    if len(read_by) >= 2 or (read_by and corroborated):
        return []
    return [
        Violation(
            "visual-read",
            claim["id"],
            "needs two separate visual reads, or one visual read plus text corroboration",
        )
    ]


def _default_round_order():
    return registry.load()["round_order"]


def check_rotation(attempts, round_order):
    out = []
    by_claim = {}
    for a in attempts:
        if a.get("ladder") != "discovery" or not CLAIM_ID.match(a["claim"]):
            continue
        by_claim.setdefault(a["claim"], {}).setdefault(int(a["round"]), set()).add(
            a["paradigm"]
        )
    for cid, rounds in by_claim.items():
        seen = set()
        for rno in sorted(rounds):
            used = rounds[rno]
            repeat = used & seen
            if repeat:
                out.append(
                    Violation(
                        "rotation-repeat",
                        cid,
                        f"round {rno} reuses paradigm {sorted(repeat)}",
                    )
                )
            if 1 <= rno <= len(round_order):
                stray = used - set(round_order[rno - 1])
                if stray:
                    out.append(
                        Violation(
                            "rotation-order",
                            cid,
                            f"round {rno} used {sorted(stray)}, expected {round_order[rno - 1]}",
                        )
                    )
            seen |= used
    return out


def check_log_matches_ledger(attempts, claims_doc):
    logged = {}
    for a in attempts:
        if a.get("ladder") == "discovery" and CLAIM_ID.match(a["claim"]):
            logged.setdefault(a["claim"], {}).setdefault(int(a["round"]), set()).add(
                a["paradigm"]
            )
    out = []
    for c in claims_doc["claims"]:
        if c["status"] == "open":
            continue
        cid = c["id"]
        rounds = logged.get(cid, {})
        top = max(rounds, default=0)
        if c["rounds"] != top:
            out.append(
                Violation(
                    "rounds-log-mismatch",
                    cid,
                    f"ledger says {c['rounds']} rounds, attempts.jsonl logs {top}",
                )
            )
        missing = [r for r in range(1, top + 1) if r not in rounds]
        if missing:
            out.append(
                Violation(
                    "rounds-log-gap",
                    cid,
                    f"no discovery attempt logged for round(s) {missing}",
                )
            )
        used = set().union(*rounds.values()) if rounds else set()
        if set(c["paradigms_tried"]) != used:
            out.append(
                Violation(
                    "paradigms-log-mismatch",
                    cid,
                    f"ledger paradigms_tried {sorted(c['paradigms_tried'])} != logged {sorted(used)}",
                )
            )
    return out


def prose_claims_missing(extracted_texts, claims_doc):
    known = {c["hash"] for c in claims_doc["claims"]}
    return [t for t in extracted_texts if claim_hash(t) not in known]


def check_sentences(sentences, claims_doc):
    by_id = {c["id"]: c for c in claims_doc["claims"]}
    want = {"plain": "true", "debate": "interpretive", "errata": "untrue"}
    out = []
    for s in sentences:
        block = s.get("block", "plain")
        if block not in want:
            out.append(
                Violation(
                    "sentence-block", None, f"{s.get('id')}: unknown block {block}"
                )
            )
            continue
        mapped = s.get("claims", [])
        if not mapped:
            out.append(
                Violation("sentence-unmapped", None, f"{s.get('id')}: no mapped claim")
            )
        for cid in mapped:
            c = by_id.get(cid)
            if c is None:
                out.append(
                    Violation("sentence-claim", cid, f"{s.get('id')}: unknown claim")
                )
            elif c["status"] != want[block]:
                out.append(
                    Violation(
                        "sentence-status",
                        cid,
                        f"{s.get('id')}: {block} block needs {want[block]}, claim is {c['status']}",
                    )
                )
    return out
