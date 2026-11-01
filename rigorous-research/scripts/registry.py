import re
from collections import namedtuple
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "registry" / "registry.yaml"
ROLES_PATH = ROOT / "registry" / "roles.yaml"
ROUTE_KINDS = ("mcp", "cli", "post", "http", "local")
LADDERS = ("discovery", "fetch")
ERROR_CLASSES = ("bad_key", "out_of_credit", "blocked", "rate_limit")


class RegistryError(ValueError):
    pass


Surface = namedtuple(
    "Surface", "id server capability paradigm ladder cost routes wired pool"
)


def load(path=REGISTRY_PATH):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    validate(data)
    return data


def surfaces(reg):
    out = {}
    for sname, server in reg["servers"].items():
        for cname, cap in server["capabilities"].items():
            sid = f"{sname}.{cname}"
            out[sid] = Surface(
                id=sid,
                server=sname,
                capability=cname,
                paradigm=cap["paradigm"],
                ladder=cap["ladder"],
                cost=cap["cost"],
                routes=cap["routes"],
                wired=bool(server.get("wired", False)),
                pool=server.get("pool"),
            )
    return out


def discovery_surfaces(reg, paradigm, wired_only=True):
    return [
        s
        for s in surfaces(reg).values()
        if s.ladder == "discovery"
        and s.paradigm == paradigm
        and (s.wired or not wired_only)
    ]


def round_paradigms(reg, round_no):
    order = reg["round_order"]
    if not 1 <= round_no <= len(order):
        raise RegistryError(f"round {round_no} outside 1..{len(order)}")
    return list(order[round_no - 1])


def validate(reg):
    problems = []
    paradigms = set(reg.get("paradigms", []))
    if reg.get("schema") != 1:
        problems.append("schema must be 1")
    for i, group in enumerate(reg.get("round_order", []), 1):
        for p in group:
            if p not in paradigms:
                problems.append(f"round_order[{i}] unknown paradigm {p}")
    if len(reg.get("round_order", [])) != reg.get("max_rounds"):
        problems.append("round_order length must equal max_rounds")
    sids = set()
    for sname, server in reg.get("servers", {}).items():
        if server.get("keyed") and not server.get("pool"):
            problems.append(f"{sname}: keyed server needs a pool")
        if server.get("keyed"):
            problems.extend(_key_problems(sname, server.get("key")))
        for cname, cap in server.get("capabilities", {}).items():
            sid = f"{sname}.{cname}"
            sids.add(sid)
            if cap.get("paradigm") not in paradigms:
                problems.append(f"{sid}: unknown paradigm {cap.get('paradigm')}")
            if cap.get("ladder") not in LADDERS:
                problems.append(f"{sid}: ladder must be one of {LADDERS}")
            routes = cap.get("routes") or {}
            if not routes:
                problems.append(f"{sid}: no routes")
            for kind in routes:
                if kind not in ROUTE_KINDS:
                    problems.append(f"{sid}: unknown route kind {kind}")
        for cls in server.get("errors") or {}:
            if cls not in ERROR_CLASSES:
                problems.append(f"{sname}: unknown error class {cls}")
        for cls in server.get("unverified", []):
            if cls not in ERROR_CLASSES:
                problems.append(f"{sname}: unknown unverified class {cls}")
    for sid in reg.get("fetch_ladder", []):
        if sid not in sids:
            problems.append(f"fetch_ladder: unknown surface {sid}")
    for i, rnd in enumerate(reg.get("round_order", []), 1):
        if not any(
            cap["paradigm"] in rnd
            and cap["ladder"] == "discovery"
            and server.get("wired")
            for server in reg["servers"].values()
            for cap in server["capabilities"].values()
        ):
            problems.append(f"round {i} {rnd} has no wired discovery surface")
    if problems:
        raise RegistryError("; ".join(problems))


KEY_FIELDS = ("env", "pattern", "header", "prefix", "base_url")


def _key_problems(sname, key):
    if not isinstance(key, dict):
        return [f"{sname}: keyed server needs a key block"]
    out = [f"{sname}: key block missing {f}" for f in KEY_FIELDS if f not in key]
    if out:
        return out
    if not isinstance(key["env"], str) or not key["env"]:
        out.append(f"{sname}: key.env must be a non-empty string")
    try:
        if "acct" not in re.compile(str(key["pattern"])).groupindex:
            out.append(f"{sname}: key.pattern needs a named group acct")
    except re.error as exc:
        out.append(f"{sname}: key.pattern invalid ({exc})")
    if key["base_url"] is not None and not (
        isinstance(key["header"], str) and key["header"]
    ):
        out.append(f"{sname}: key.header required when base_url is set")
    return out


def pools(reg):
    return {s["pool"]: name for name, s in reg["servers"].items() if s.get("keyed")}


def key_info(reg, pool):
    name = pools(reg).get(pool)
    if name is None:
        raise RegistryError(f"unknown pool {pool}")
    srv = reg["servers"][name]
    return {
        **srv["key"],
        "server": name,
        "wired": bool(srv.get("wired")),
        "reset": srv.get("reset", "unknown"),
    }


def classify_error(reg, server, status=None, code=None):
    srv = reg["servers"].get(server)
    if srv is None:
        raise RegistryError(f"unknown server {server}")
    needles = {str(x).lower() for x in (status, code) if x not in (None, "", "-")}
    for cls in ERROR_CLASSES:
        if cls in srv.get("unverified", []):
            continue
        for pattern in (srv.get("errors") or {}).get(cls, []):
            p = str(pattern).lower()
            if any(p == n or p in n for n in needles):
                return cls
    return "unknown"


def load_roles(path=ROLES_PATH):
    return yaml.safe_load(path.read_text(encoding="utf-8"))["roles"]


def checking_roles(path=ROLES_PATH):
    return list(yaml.safe_load(path.read_text(encoding="utf-8"))["checking_roles"])
