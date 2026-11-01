import json

import yaml
from jsonschema import Draft202012Validator

from . import ledger

SCHEMA_PATH = ledger.SCHEMA_DIR / "lesson.schema.json"
MODE_LAYOUTS = {
    "learn": (
        "concept",
        "glossary",
        "qa",
        "table",
        "timeline",
        "cause-effect",
        "diagram",
    ),
    "rules": ("concept", "glossary", "table", "decision-tree", "steps", "cheat-sheet"),
    "answer": ("concept",),
    "recommend": ("concept", "table"),
}


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def dump(doc):
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)


def _walk(node):
    if isinstance(node, dict):
        if {"id", "text", "claims"} <= node.keys() and isinstance(node["text"], str):
            yield node
            return
        for key, value in node.items():
            if key == "nodes" or key == "edges":
                continue
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def sentences(doc):
    out = (
        list(_walk(doc["answer"]))
        + list(_walk(doc["body"]))
        + list(_walk(doc.get("extra", [])))
    )
    out += [{"block": "errata", **s} for s in _walk(doc.get("errata", []))]
    return out


def validate(doc):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(
            Draft202012Validator(schema).iter_errors(doc),
            key=lambda e: list(e.absolute_path),
        )
    ]
    if errors:
        return errors
    ids = [s["id"] for s in sentences(doc)]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        errors.append(f"duplicate sentence ids {dupes}")
    if doc["layout"] not in MODE_LAYOUTS[doc["mode"]]:
        errors.append(f"layout {doc['layout']} is not offered in mode {doc['mode']}")
    if doc["layout"] == "diagram":
        node_ids = {n["id"] for n in doc["body"]["nodes"]}
        for e in doc["body"]["edges"]:
            for end in (e["from"], e["to"]):
                if end not in node_ids:
                    errors.append(f"diagram edge references unknown node {end}")
    return errors


def sentence_violations(doc, claims_doc):
    return ledger.check_sentences(sentences(doc), claims_doc)
