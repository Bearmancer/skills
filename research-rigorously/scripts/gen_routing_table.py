
import argparse
import sys
from pathlib import Path

from . import registry

OUT = Path(registry.ROOT / "references" / "routing.md")
COST_ORDER = {"low": 0, "med": 1, "high": 2}
ROUTE_WORDS = {
    "mcp": "MCP tool the host carries",
    "cli": "vendor CLI",
    "post": "POST script",
    "http": "HTTP",
    "local": "a local tool",
}


def route_order_sentence():
    words = [ROUTE_WORDS[k] for k in registry.ROUTE_KINDS]
    return ", then ".join(words[:-1]) + f" or {words[-1]}"


def render(reg):
    surfs = registry.surfaces(reg)
    lines = [
        "# Routing table (generated)",
        "",
        "Generated from `registry/registry.yaml` by `rr gen-routing`.",
        "",
        f"Per surface the route order is: {route_order_sentence()}. A server's key pool rotates",
        'inside the server (SKILL.md, "Key rotation: single home"); a fallback inside a server is never a new surface.',
        "Only agent-answered surfaces carry MCP routes (ADR 0035). A `tools.x.y` route is live only where the",
        "host configures server `x`; `Wired` below means enabled in the registry, not host-reachable — check your tool catalog before trying an MCP route.",
        "",
        "## Rounds",
        "",
        "| Round | Paradigms |",
        "|---|---|",
    ]
    for i, group in enumerate(reg["round_order"], 1):
        parts = []
        for p in group:
            has_discovery = bool(registry.discovery_surfaces(reg, p))
            parts.append(p if has_discovery else f"{p} (fetch ladder only)")
        lines.append(f"| R{i} | {', '.join(parts)} |")

    lines += [
        "",
        "## Pick by capability",
        "",
        "| Capability | Surfaces, cheapest first |",
        "|---|---|",
    ]
    by_cap = {}
    for s in surfs.values():
        if s.cost not in COST_ORDER:
            raise ValueError(f"{s.id}: unknown cost {s.cost!r}")
        for name in s.routes.get("mcp", []):
            if "." in name and name.split(".", 1)[0] not in reg["servers"]:
                raise ValueError(f"{s.id}: mcp route {name!r} names unknown server")
        by_cap.setdefault(s.capability, []).append(s)
    for cap in sorted(by_cap):
        ordered = sorted(by_cap[cap], key=lambda s: (COST_ORDER[s.cost], s.id))
        lines.append(
            f"| {cap} | " + ", ".join(f"`{s.id}` ({s.cost})" for s in ordered) + " |"
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
            f"{kind}: "
            + ", ".join(
                f"`{registry.mcp_tool(s.server, x) if kind == 'mcp' else x}`"
                for x in names
            )
            for kind, names in s.routes.items()
        )
        lines.append(f"{i}. `{sid}` - {route}")

    lines += [
        "",
        "## Key policy",
        "",
        "The active key is the User-scope env var; `rr keys` rotates it. A running shell keeps the old value, so run",
        "every CLI route with its key refreshed: `$env:<VAR> = [Environment]::GetEnvironmentVariable('<VAR>', 'User'); <cli ...>`.",
        "POST scripts read HKCU themselves and send the key only in the vendor auth header. An MCP route follows rotation only",
        "when the host config reads the key as `{env:<VAR>}`; a literal key in that config is out of `rr keys`'s reach.",
        "",
        "| Server | Env var | Pool | POST auth header | CLI auth | MCP key (rr keys rotation) | Wired |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, srv in reg["servers"].items():
        if not srv.get("keyed"):
            lines.append(
                f"| {name} | `-` | `-` | - | {srv.get('auth') or '-'} | keyless (no rotation) | "
                f"{'yes' if srv.get('wired') else 'no'} |"
            )
            continue
        k = srv.get("key") or {}
        header = f"`{k['header']}: {k['prefix']}<key>`" if k.get("header") else "-"
        mcp = srv.get("mcp_key")
        if not mcp:
            mcp_col = "-"
        elif mcp.get("keyless"):
            mcp_col = "keyless (no rotation)"
        elif mcp.get("env"):
            mcp_col = f"`{mcp['env']}` env reference (a rotation reaches the MCP only after OpenCode restarts; the server reads the var at launch)"
        else:
            mcp_col = "literal key (rotation cannot reach it)"
        lines.append(
            f"| {name} | `{k.get('env', '-')}` | `{srv.get('pool') or '-'}` | {header} | {srv.get('auth') or '-'} | {mcp_col} | {'yes' if srv.get('wired') else 'no'} |"
        )
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


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Regenerate references/routing.md from registry/registry.yaml."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if routing.md is out of date instead of writing it",
    )
    args = parser.parse_args(argv)

    text = render(registry.load())
    if args.check:
        return 0 if OUT.exists() and OUT.read_bytes() == text.encode("utf-8") else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
