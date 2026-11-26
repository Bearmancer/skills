
import argparse
import sys

from . import registry

OUT = registry.ROOT / "references" / "routing.md"
COST_ORDER = {"low": 0, "med": 1, "high": 2}


def render(reg):
    surfs = registry.surfaces(reg)
    lines = [
        "# Routing table (generated)",
        "",
        "Generated from `registry/registry.yaml` by `rr gen-routing`. Do not edit by hand.",
        "",
        "Per surface the route order is: MCP tool the host carries, then vendor CLI, then POST script, then HTTP or a local tool. A server's key pool rotates",
        'inside the server (SKILL.md, "Key rotation: single home"); a fallback inside a server is never a new surface. Only agent-answered surfaces carry MCP routes: the agent calls `tools.<server>.<tool>`; Python never does.',
        "",
        "## Rounds",
        "",
        "| Round | Paradigms |",
        "|---|---|",
    ]
    for i, group in enumerate(reg["round_order"], 1):
        lines.append(f"| R{i} | {', '.join(group)} |")

    lines += [
        "",
        "## Pick by capability",
        "",
        "| Capability | Surfaces, cheapest first |",
        "|---|---|",
    ]
    by_cap = {}
    for s in surfs.values():
        by_cap.setdefault(s.capability, []).append(s)
    for cap in sorted(by_cap):
        ordered = sorted(by_cap[cap], key=lambda s: (COST_ORDER.get(s.cost, 3), s.id))
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
            f"{kind}: "
            + ", ".join(
                f"`{registry.mcp_tool(s.server, x) if kind == 'mcp' else x}`"
                for x in names
            )
            for kind, names in s.routes.items()
        )
        lines.append(f"{i}. `{sid}`{'' if s.wired else ' (unwired)'} - {route}")

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
        if not (srv.get("keyed") or srv.get("mcp_key")):
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
        return 0 if OUT.exists() and OUT.read_text(encoding="utf-8") == text else 1
    with OUT.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
