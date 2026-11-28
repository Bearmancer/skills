
import argparse
import http.client
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from . import registry, workspace
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
    line = line.removeprefix("export ")
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


def env_files(path):
    if path.is_file():
        return [(path, None)]
    roots = [path, path.parent]
    for root in roots:
        if not root.is_dir():
            continue
        # Only the <Service>.env files of pools the registry defines; unrelated
        # secrets files are never opened.
        found = sorted(
            file
            for file in root.glob("*.env")
            if _section_service(file.stem) is not None
        )
        if found:
            return [(file, _section_service(file.stem)) for file in found]
    raise FileNotFoundError(f"env file not found: {path}")


def get_dotenv_map(path):
    env_map = DotEnv()
    for source, default_section in env_files(path):
        section = default_section
        lines = source.read_text(encoding="utf-8").splitlines()
        skipped = 0
        for line in lines:
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
                skipped += 1
                continue
            name, val = parsed
            env_map[name] = val
            if section:
                env_map.sections.setdefault(section, {})[name] = val
        if skipped:
            # A bare key with no NAME= is silently unusable; say so once per file,
            # never echo the line or its value.
            print(
                f"warning: {source}: {skipped} line(s) are not NAME=value assignments and were skipped",
                file=sys.stderr,
            )
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


def default_get(url, headers, timeout=15.0):
    """One GET; returns (status, body bytes). Never echoes the request headers."""
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (OSError, ValueError, http.client.HTTPException):
        return 0, b""


def _json(body):
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return {}


def usage_text(service, key, get=default_get):
    """The vendor's own reported usage for one key. Never returns the key."""
    if service == "tavily":
        # https://docs.tavily.com/documentation/api-reference/endpoint/usage
        code, body = get(
            "https://api.tavily.com/usage", {"Authorization": f"Bearer {key}"}
        )
        if code != 200:
            return f"HTTP {code}"
        account = _json(body).get("account") or {}
        usage, limit = account.get("plan_usage"), account.get("plan_limit")
        if usage is None or limit is None:
            return "usage reported"
        return f"{usage}/{limit} credits"
    if service == "scrapegraph":
        # https://docs.scrapegraphai.com/api-reference (credits)
        code, body = get(
            "https://v2-api.scrapegraphai.com/api/credits", {"SGAI-APIKEY": key}
        )
        if code != 200:
            return f"HTTP {code}"
        data = _json(body)
        remaining, used = data.get("remaining"), data.get("used")
        if remaining is None:
            return "usage reported"
        return f"{remaining} left" + (f" ({used} used)" if used is not None else "")
    if service == "apify":
        # https://docs.apify.com/api/v2/users-me-limits-get
        code, body = get(
            "https://api.apify.com/v2/users/me/limits",
            {"Authorization": f"Bearer {key}"},
        )
        if code != 200:
            return f"HTTP {code}"
        data = _json(body).get("data") or {}
        current = data.get("current") or {}
        used = current.get("monthlyUsageUsd")
        limits = data.get("limits") or {}
        limit = limits.get("maxMonthlyUsageUsd") or current.get("maxMonthlyUsageUsd")
        if used is None:
            return "usage reported"
        used = float(used)
        if limit is not None:
            return f"${used:.2f} used / ${float(limit):.2f}"
        return f"${used:.2f} used"
    if service == "brightdata":
        # https://docs.brightdata.com/api-reference/account-management-api/Get_total_balance_through_API
        # A 403 here means the API token lacks the account/billing permission.
        code, body = get(
            "https://api.brightdata.com/customer/balance",
            {"Authorization": f"Bearer {key}"},
        )
        if code == 403:
            return "403: token lacks account-read permission"
        if code != 200:
            return f"HTTP {code}"
        data = _json(body)
        balance, credit = data.get("balance"), data.get("credit")
        if balance is None:
            return "usage reported"
        return f"balance ${balance}" + (
            f" (credit ${credit})" if credit is not None else ""
        )
    if service == "tinyfish":
        # No documented wallet/usage REST endpoint (https://docs.tinyfish.ai):
        # the wallet balance appears only in an INSUFFICIENT_CREDITS error.
        return "n/a (no documented usage endpoint)"
    if service == "exa":
        # Team Management usage needs a service-account key and a key id:
        # https://exa.ai/docs/reference/team-management/get-api-key-usage
        return "n/a (no usage API)"
    if service == "zenrows":
        # https://docs.zenrows.com/academy/production/control-costs
        code, body = get(
            "https://api.zenrows.com/v1/subscriptions/self/details",
            {"X-API-Key": key},
        )
        if code != 200:
            return f"HTTP {code}"
        data = _json(body)
        used, limit = data.get("usage_credits"), data.get("credit_limit")
        if used is None or limit is None:
            return "usage reported"
        pct = data.get("usage_percent")
        period = data.get("period_ends_at")
        return (
            f"{used}/{limit} credits used"
            + (f" ({pct}%)" if pct is not None else "")
            + (f", period ends {period}" if period else "")
        )
    if service == "firecrawl":
        # https://docs.firecrawl.dev/api-reference/endpoint/credit-usage
        code, body = get(
            "https://api.firecrawl.dev/v2/team/credit-usage",
            {"Authorization": f"Bearer {key}"},
        )
        if code != 200:
            return f"HTTP {code}"
        data = _json(body).get("data") or {}
        remaining, plan = data.get("remainingCredits"), data.get("planCredits")
        if remaining is None:
            return "usage reported"
        return f"{remaining} credits left" + (
            f" of {plan} plan" if plan is not None else ""
        )
    return "n/a (no usage API)"


def keystate_mark(state_path, pool, fp):
    """The skill's own mark for one key, read-only: never marks or clears."""
    try:
        data = json.loads(Path(state_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "none"
    entry = (data.get("keys") or {}).get(pool, {}).get(fp)
    if not entry:
        return "none"
    return f"exhausted_at={entry.get('exhausted_at')} reset={entry.get('reset')}"


def usage_rows(dotenv, services, get=default_get, state_path=None):
    rows = []
    for svc in services:
        pool = get_pool(dotenv, svc)
        if not pool:
            rows.append(f"{svc:<12} pool empty")
            continue
        for n in sorted(pool):
            fp = get_fingerprint(pool[n])
            mark = keystate_mark(state_path, svc, fp) if state_path else "none"
            rows.append(
                f"{svc:<12} {n}({fp})  {usage_text(svc, pool[n], get):<26}  state: {mark}"
            )
    return rows


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


def main(argv=None, get=default_get):
    parser = argparse.ArgumentParser(
        description=(
            "Rotate a masked pool of API keys. The active key is the User-scope "
            "environment variable each CLI and POST script reads."
        )
    )
    parser.add_argument("--service", choices=SERVICE_CHOICES)
    parser.add_argument("--list", action="store_true")
    parser.add_argument(
        "--usage",
        action="store_true",
        help="show each key's vendor-reported usage next to its keystate mark",
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=workspace.keystate_file().parent,
        help="where keystate.json lives (default: ~/.rigor)",
    )
    parser.add_argument(
        "--fingerprints",
        action="store_true",
        help="print pool, fingerprint, account, active flag per key",
    )
    parser.add_argument("--set", dest="set_account", default=None)
    parser.add_argument("--next", action="store_true")
    parser.add_argument("--env-path", default=str(Path.home() / ".secrets"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.service is None:
        if not (args.fingerprints or args.usage):
            parser.error("--service is required")
        args.service = "all"

    try:
        dotenv = get_dotenv_map(Path(args.env_path))

        if args.usage:
            targets = sorted(SERVICE_MAP) if args.service == "all" else [args.service]
            for row in usage_rows(
                dotenv,
                targets,
                get=get,
                state_path=workspace.keystate_file(args.state_root),
            ):
                print(row)
            sys.exit(0)

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
    except Exception as exc:  # noqa: BLE001 - CLI entry point: any failure is exit 1
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
