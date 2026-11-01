# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "jsonschema"]
# ///

if not __package__:
    import sys
    from pathlib import Path

    sys.dont_write_bytecode = True
    parents = Path(__file__).resolve().parents
    sys.path.insert(0, str(next(p for p in parents if p.name == "scripts")))
    import launch

    launch.run(__file__)

import sys

from . import registry

OUT = registry.ROOT / "references" / "routing.md"
FLEET_OUT = registry.ROOT / "references" / "fleet.md"


def render(reg):
    lines = [
        "# Routing table (generated)",
        "",
        "Generated from `registry/registry.yaml` by `scripts/gen_routing_table.py`. Do not edit by hand.",
        "",
        "## Rounds",
        "",
        "| Round | Paradigms |",
        "|---|---|",
    ]
    for i, group in enumerate(reg["round_order"], 1):
        lines.append(f"| R{i} | {', '.join(group)} |")
    lines += ["", "## Fetch ladder", ""]
    lines += [f"{i}. `{sid}`" for i, sid in enumerate(reg["fetch_ladder"], 1)]
    lines += [
        "",
        "## Surfaces",
        "",
        "| Surface | Paradigm | Ladder | Cost | Wired | MCP | CLI | POST/HTTP/local |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in registry.surfaces(reg).values():

        def col(kind):
            return "<br>".join(f"`{x}`" for x in s.routes.get(kind, [])) or "-"

        other = (
            "<br>".join(
                f"{k}: `{x}`"
                for k in ("post", "http", "local")
                for x in s.routes.get(k, [])
            )
            or "-"
        )
        lines.append(
            f"| `{s.id}` | {s.paradigm} | {s.ladder} | {s.cost} | {'yes' if s.wired else 'no'} | {col('mcp')} | {col('cli')} | {other} |"
        )
    lines += [
        "",
        "## Key policy",
        "",
        "Key goes only into the vendor auth header; source order: `~/.config/opencode/secrets/<pool>`, then the env var.",
        "",
        "| Server | Env var | Pool | Auth header | Wired |",
        "|---|---|---|---|---|",
    ]
    for name, srv in reg["servers"].items():
        if srv.get("keyed"):
            k = srv["key"]
            header = f"`{k['header']}: {k['prefix']}<key>`" if k["header"] else "-"
            lines.append(
                f"| {name} | `{k['env']}` | `{srv['pool']}` | {header} | {'yes' if srv.get('wired') else 'no'} |"
            )
    lines += [
        "",
        "## POST scripts",
        "",
        "JSON to stdout; HTTP error: exit 1 with `{status, code, message}` on stderr; redirects refused.",
        "",
        "| Surface | Command |",
        "|---|---|",
    ]
    for s in registry.surfaces(reg).values():
        for cmd in s.routes.get("post", []):
            lines.append(f"| `{s.id}` | `{cmd}` |")
    lines += [
        "",
        "## Error classes",
        "",
        "| Server | Class | Codes | Verified |",
        "|---|---|---|---|",
    ]
    for name, srv in reg["servers"].items():
        if not srv.get("keyed"):
            continue
        for cls in registry.ERROR_CLASSES:
            codes = (srv.get("errors") or {}).get(cls, [])
            verified = cls not in srv.get("unverified", [])
            lines.append(
                f"| {name} | {cls} | {', '.join(f'`{c}`' for c in codes) or '-'} | {'yes' if verified else 'no'} |"
            )
    return "\n".join(lines) + "\n"


def render_fleet(reg):
    surfs = registry.surfaces(reg)
    lines = [
        "# Fleet: route a web call (generated)",
        "",
        "Generated from `registry/registry.yaml` by `scripts/gen_routing_table.py`. Do not edit by hand. Full tables: `routing.md`.",
        "",
        "Per surface the route order is: MCP tool the host carries, then vendor CLI, then POST script. A server's key pool rotates",
        'inside the server (SKILL.md, "Key rotation: single home"); a fallback inside a server is never a new surface.',
        "",
        "## Pick by capability",
        "",
        "| Capability | Surfaces, cheapest first |",
        "|---|---|",
    ]
    cost = {"low": 0, "med": 1, "high": 2}
    by_cap = {}
    for s in surfs.values():
        by_cap.setdefault(s.capability, []).append(s)
    for cap in sorted(by_cap):
        ordered = sorted(by_cap[cap], key=lambda s: (cost.get(s.cost, 3), s.id))
        lines.append(
            f"| {cap} | "
            + ", ".join(
                f"`{s.id}` ({s.cost}{'' if s.wired else ', unwired'})" for s in ordered
            )
            + " |"
        )
    lines += [
        "",
        "## Bot-block chain",
        "",
        "Walk in order per URL; the first step that returns the target content wins. Bot-blocked means 401, 403, 429, 503, a",
        "challenge page or an empty body. A credit or auth failure rotates that server's key first, then the walk moves on.",
        "Every step exhausted: the URL is blocked; never guess its content.",
        "",
    ]
    for i, sid in enumerate(reg["fetch_ladder"], 1):
        s = surfs[sid]
        route = "; ".join(
            f"{kind}: {', '.join(f'`{x}`' for x in names)}"
            for kind, names in s.routes.items()
        )
        lines.append(f"{i}. `{sid}`{'' if s.wired else ' (unwired)'} - {route}")
    lines += [
        "",
        "## POST scripts",
        "",
        "JSON to stdout, HTTP errors exit 1 with `{status, code, message}` on stderr.",
        "",
    ]
    posts = [(s.id, cmd) for s in surfs.values() for cmd in s.routes.get("post", [])]
    lines += [f"- `{sid}`: `{cmd}`" for sid, cmd in posts] or ["- none"]
    return "\n".join(lines) + "\n"


def main():
    reg = registry.load()
    outputs = ((OUT, render(reg)), (FLEET_OUT, render_fleet(reg)))
    if "--check" in sys.argv:
        return (
            0
            if all(
                p.exists() and p.read_text(encoding="utf-8") == text
                for p, text in outputs
            )
            else 1
        )
    for path, text in outputs:
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
