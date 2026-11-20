# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///

import argparse
import os
import re
import sys
from pathlib import Path

if not __package__:
    import sys
    from pathlib import Path

    sys.dont_write_bytecode = True
    parents = Path(__file__).resolve().parents
    sys.path.insert(0, str(next(p for p in parents if p.name == "scripts")))
    import launch

    launch.run(__file__)

from . import registry
from .keystate import fingerprint
from .userenv import broadcast_change, get_active_value, set_user


class ServiceInfo:
    def __init__(self, env_var, pool_pattern):
        self.env_var = env_var
        self.pool_pattern = pool_pattern


_REG = registry.load()
SERVICE_MAP = {
    pool: ServiceInfo(
        registry.key_info(_REG, pool)["env"], registry.key_info(_REG, pool)["pattern"]
    )
    for pool in registry.pools(_REG)
}
SERVICE_CHOICES = [*sorted(SERVICE_MAP), "all"]
SECTION_ALIASES = {"scrapegraphai": "scrapegraph"}


class DotEnv(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sections = {}


def _parse_assignment(line):
    if line.startswith("export "):
        line = line[len("export ") :]
    idx = line.find("=")
    if idx < 1:
        return None
    name = line[:idx].strip()
    val = line[idx + 1 :].strip()
    if len(val) >= 2 and (
        (val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")
    ):
        val = val[1:-1].strip()
    return (name, val) if name else None


def _section_service(title):
    key = re.sub(r"[^a-z0-9]", "", title.lower())
    key = SECTION_ALIASES.get(key, key)
    return key if key in SERVICE_MAP else None


def get_dotenv_map(path):
    if not path.exists():
        raise FileNotFoundError(f"env file not found: {path}")
    env_map = DotEnv()
    section = None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line[0] in "#;":
            heading = re.match(r"^(#+)\s*(.*)$", line)
            if heading and "=" not in heading.group(2):
                if len(heading.group(1)) == 1:
                    section = None
                elif len(heading.group(1)) == 2:
                    section = _section_service(heading.group(2))
            continue
        parsed = _parse_assignment(line)
        if not parsed:
            continue
        name, val = parsed
        env_map[name] = val
        if section:
            env_map.sections.setdefault(section, {})[name] = val
    return env_map


def get_pool(dotenv, svc):
    pattern = re.compile(SERVICE_MAP[svc].pool_pattern, re.IGNORECASE)
    pool = {}
    for k, v in dotenv.items():
        m = pattern.match(k)
        if m:
            acct = m.group("acct")
            if acct and v:
                pool[acct] = v
    for k, v in getattr(dotenv, "sections", {}).get(svc, {}).items():
        m = pattern.match(k)
        acct = m.group("acct") if m else k
        if acct and v:
            pool[acct] = v
    return pool


def get_fingerprint(value):
    return fingerprint(value)


def get_active_account(pool, active):
    if not active:
        return None
    for k, v in pool.items():
        if v == active:
            return k
    return None


def show_pool_state(dotenv, svc):
    env_var = SERVICE_MAP[svc].env_var
    pool = get_pool(dotenv, svc)
    active = get_active_value(env_var)
    active_acct = get_active_account(pool, active)
    parts = []
    for n in sorted(pool.keys()):
        fp = get_fingerprint(pool[n])
        parts.append(f"{n}({fp})*" if n == active_acct else f"{n}({fp})")
    if active_acct:
        state = f"active={active_acct}"
    elif active:
        state = "active=NOT-IN-POOL"
    else:
        state = "active=UNSET"
    return f"{svc:<11} {state:<22} pool: {' '.join(parts)}"


TAB = chr(9)


def fingerprint_rows(dotenv, pools):
    rows = []
    for svc in pools:
        pool = get_pool(dotenv, svc)
        active = get_active_account(pool, get_active_value(SERVICE_MAP[svc].env_var))
        rows += [
            TAB.join(
                [svc, get_fingerprint(pool[n]), n, "active" if n == active else "-"]
            )
            for n in sorted(pool)
        ]
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Rotate a masked pool of API keys. The active key is the User-scope "
            "environment variable each CLI and POST script reads."
        )
    )
    parser.add_argument("--service", choices=SERVICE_CHOICES)
    parser.add_argument("--list", action="store_true")
    parser.add_argument(
        "--fingerprints",
        action="store_true",
        help="print pool, fingerprint, account, active flag per key",
    )
    parser.add_argument("--set", dest="set_account", default=None)
    parser.add_argument("--next", action="store_true")
    parser.add_argument("--env-path", default=str(Path.home() / ".secrets" / ".env"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.service is None:
        if not args.fingerprints:
            parser.error("--service is required")
        args.service = "all"

    try:
        dotenv = get_dotenv_map(Path(args.env_path))

        if args.fingerprints:
            targets = sorted(SERVICE_MAP) if args.service == "all" else [args.service]
            for row in fingerprint_rows(dotenv, targets):
                print(row)
            sys.exit(0)

        if args.service == "all":
            if args.set_account or args.next:
                raise ValueError("'-all' supports listing only (no -Set/-Next)")
            for svc in SERVICE_MAP:
                print(show_pool_state(dotenv, svc))
            sys.exit(0)

        if args.list or (not args.set_account and not args.next):
            print(show_pool_state(dotenv, args.service))
            sys.exit(0)

        env_var = SERVICE_MAP[args.service].env_var
        pool = get_pool(dotenv, args.service)
        if not pool:
            raise ValueError(f"pool empty for {args.service}: move to next chain step")
        names = sorted(pool.keys())
        active = get_active_value(env_var)
        active_acct = get_active_account(pool, active)

        target_acct = args.set_account
        if not target_acct:
            if active_acct:
                i = names.index(active_acct)
                target_acct = names[(i + 1) % len(names)]
            else:
                target_acct = names[0]
        if target_acct not in pool:
            raise ValueError(
                f"account '{target_acct}' not in {args.service} pool: {', '.join(names)}"
            )

        target_fp = get_fingerprint(pool[target_acct])
        if active_acct == target_acct:
            print(f"{args.service}: already active {target_acct}({target_fp})")
            sys.exit(0)

        if args.dry_run:
            print(f"{args.service}: WHATIF -> {target_acct}({target_fp}). (no write)")
        else:
            set_user(env_var, pool[target_acct])
            os.environ[env_var] = pool[target_acct]
            broadcast_change()
            if active_acct:
                from_desc = f"{active_acct}({get_fingerprint(pool[active_acct])})"
            else:
                from_desc = "UNSET"
            print(
                f"{args.service}: {from_desc} -> {target_acct}({target_fp}). "
                f"User env var {env_var} updated; CLIs and POST scripts read it on their next start."
            )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
