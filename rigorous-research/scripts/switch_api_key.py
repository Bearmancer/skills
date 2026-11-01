# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///

import argparse
import ctypes
import os
import re
import sys
import uuid
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

try:
    import winreg
except ImportError:
    winreg = None


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
DEFAULT_SECRETS_DIR = Path.home() / ".config" / "opencode" / "secrets"
MATERIALIZE_SERVICES = sorted(
    pool for pool in SERVICE_MAP if registry.key_info(_REG, pool)["wired"]
)


def write_secret(secrets_dir, svc, value):
    secrets_dir.mkdir(parents=True, exist_ok=True)
    target = secrets_dir / svc
    tmp = secrets_dir / f".{svc}.{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_text(value, encoding="utf-8", newline="")
        tmp.replace(target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return target


def materialize_secret(dotenv, svc, secrets_dir, dry_run=False):
    if (secrets_dir / svc).exists():
        return f"{svc}: exists"
    pool = get_pool(dotenv, svc)
    value = get_active_value(SERVICE_MAP[svc].env_var)
    if not value and pool:
        value = pool[sorted(pool)[0]]
    if not value:
        raise ValueError(f"{svc}: no active key or pool account; file not created")
    if dry_run:
        return f"{svc}: WHATIF create (no write)"
    write_secret(secrets_dir, svc, value)
    return f"{svc}: created"


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


def _get_user_env_var(name):
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value)
    except (FileNotFoundError, OSError):
        return None


def _set_user_env_var(name, value):
    if winreg is None:
        return
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def _broadcast_env_change():
    if winreg is None:
        return
    try:
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x1A
        SMTO_ABORTIFHUNG = 2
        result = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            1000,
            ctypes.byref(result),
        )
    except Exception:
        pass


def get_active_value(env_var):
    v = _get_user_env_var(env_var)
    if not v:
        v = os.environ.get(env_var)
    return v


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
            "Rotate a masked pool of API keys. The active key is written to "
            "~/.config/opencode/secrets/<service> (read by OpenCode via {file:}) "
            "and to a User-scope environment variable."
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
    parser.add_argument("--secrets-dir", default=str(DEFAULT_SECRETS_DIR))
    parser.add_argument(
        "--materialize",
        action="store_true",
        help="create every missing secrets file (--service all, or one service)",
    )
    args = parser.parse_args(argv)
    if args.service is None:
        if not args.fingerprints:
            parser.error("--service is required")
        args.service = "all"

    try:
        dotenv = get_dotenv_map(Path(args.env_path))
        secrets_dir = Path(args.secrets_dir)

        if args.fingerprints:
            targets = sorted(SERVICE_MAP) if args.service == "all" else [args.service]
            for row in fingerprint_rows(dotenv, targets):
                print(row)
            sys.exit(0)

        if args.materialize:
            targets = MATERIALIZE_SERVICES if args.service == "all" else [args.service]
            failed = False
            for svc in targets:
                try:
                    print(materialize_secret(dotenv, svc, secrets_dir, args.dry_run))
                except ValueError as exc:
                    failed = True
                    print(str(exc), file=sys.stderr)
            sys.exit(1 if failed else 0)

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
        if not args.dry_run:
            write_secret(secrets_dir, args.service, pool[target_acct])
        if active_acct == target_acct:
            print(f"{args.service}: already active {target_acct}({target_fp})")
            sys.exit(0)

        if args.dry_run:
            print(f"{args.service}: WHATIF -> {target_acct}({target_fp}). (no write)")
        else:
            _set_user_env_var(env_var, pool[target_acct])
            os.environ[env_var] = pool[target_acct]
            _broadcast_env_change()
            if active_acct:
                from_desc = f"{active_acct}({get_fingerprint(pool[active_acct])})"
            else:
                from_desc = "UNSET"
            print(
                f"{args.service}: {from_desc} -> {target_acct}({target_fp}). "
                "Secrets file updated; the OpenCode config watcher reconnects the MCP server."
            )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
