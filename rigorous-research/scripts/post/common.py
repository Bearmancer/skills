import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .. import registry
from ..switch_api_key import DEFAULT_SECRETS_DIR as SECRETS_DIR

UA = "rigorous-research-post-scripts/1"


def _vendors():
    reg = registry.load()
    out = {}
    for pool in registry.pools(reg):
        info = registry.key_info(reg, pool)
        if info["base_url"]:
            out[pool] = (info["base_url"], info["header"], info["prefix"], info["env"])
    return out


VENDORS = _vendors()

PATH_OK = re.compile(r"^/[A-Za-z0-9._~%!$'()*+,;=:@/-]*$")
ENCODED_DOT = re.compile(r"%2e", re.I)
CODE_HEADERS = ("x-brd-error-code", "x-brd-err-code")
MESSAGE_HEADERS = ("x-brd-error", "x-brd-err-msg")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kw):
        return None


OPENER = urllib.request.build_opener(_NoRedirect)


def fail(status, code, message):
    print(
        json.dumps(
            {"status": status, "code": code, "message": message[:500]},
            ensure_ascii=True,
        ),
        file=sys.stderr,
    )
    sys.exit(1)


def load_key(pool):
    path = SECRETS_DIR / pool
    env_var = VENDORS[pool][3]
    try:
        key = path.read_text(encoding="utf-8").strip()
    except OSError:
        key = ""
    key = key or os.environ.get(env_var, "").strip()
    if not key:
        fail(
            "-",
            "key_unreadable",
            f"cannot read {path} (missing or empty) and {env_var} is unset",
        )
    if re.search(r"\s", key):
        fail("-", "key_malformed", f"{path} has whitespace")
    return key


def vendor_code(status, headers, payload):
    code = next((headers.get(h) for h in CODE_HEADERS if headers.get(h)), None)
    message = ""
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            code = code or err.get("code") or err.get("type")
            message = err.get("message") or ""
        elif isinstance(err, str):
            message = err
        code = code or payload.get("tag") or payload.get("code")
        message = message or str(payload.get("message") or "")
    elif isinstance(payload, str):
        message = payload
    message = message or next(
        (headers.get(h) for h in MESSAGE_HEADERS if headers.get(h)), ""
    )
    return str(code or status), message


def parse_body(raw):
    text = raw.decode("utf-8", errors="replace")
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


def call(
    pool,
    method,
    path,
    body=None,
    params=None,
    headers=None,
):
    base, auth_header, prefix, _ = VENDORS[pool]
    if (
        not PATH_OK.match(path)
        or "//" in path
        or ENCODED_DOT.search(path)
        or {".", ".."} & set(path.split("/"))
    ):
        fail("-", "bad_path", "path must be /segment/... with URL-safe characters only")
    for k, v in (headers or {}).items():
        if k.lower() in ("host", auth_header.lower()) or re.search(
            r"[\x00-\x1f\x7f]", f"{k}{v}"
        ):
            fail("-", "bad_header", f"header {k!r} not allowed")
    url = base + path
    if params:
        url += "?" + urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None}
        )
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req_headers = {
        "User-Agent": UA,
        "Accept": "application/json",
        auth_header: prefix + load_key(pool),
    }
    if data is not None:
        req_headers["Content-Type"] = "application/json"
    req_headers.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=req_headers)
    try:
        with OPENER.open(req, timeout=60) as resp:
            payload = parse_body(resp.read())
            if any(resp.headers.get(h) for h in CODE_HEADERS):
                fail(resp.status, *vendor_code(resp.status, resp.headers, payload))
            return resp.status, payload
    except urllib.error.HTTPError as exc:
        payload = parse_body(exc.read())
        fail(exc.code, *vendor_code(exc.code, exc.headers, payload))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        fail("-", "network_error", str(getattr(exc, "reason", exc)))


def emit(status, payload):
    if payload is None or isinstance(payload, str):
        payload = {"status": status, "body": payload}
    print(json.dumps(payload, ensure_ascii=True))


def run(pool, method, path, body=None, **kw):
    emit(*call(pool, method, path, body, **kw))


def load_json_arg(value):
    text = value
    if value.startswith("@"):
        try:
            text = Path(value[1:]).read_text(encoding="utf-8")
        except OSError as exc:
            fail("-", "bad_json_file", f"cannot read {value[1:]}: {exc.strerror}")
    try:
        return json.loads(text)
    except ValueError as exc:
        fail("-", "bad_json", f"invalid JSON argument: {exc}")


def add_id_commands(sub, table):
    parsers = {}
    for name, (method, path) in table.items():
        parsers[name] = sub.add_parser(name)
        parsers[name].add_argument("id")
        parsers[name].set_defaults(method=method, path=path)
    return parsers


def dispatch(pool, args, **kw):
    run(
        pool,
        args.method,
        args.path.format(id=urllib.parse.quote(args.id, safe="")),
        **kw,
    )


def poll(pool, path, params, waits, timeout):
    deadline = time.monotonic() + timeout
    i = 0
    while True:
        time.sleep(waits[min(i, len(waits) - 1)])
        status, payload = call(pool, "GET", path, params=params)
        if status != 202:
            return status, payload
        if time.monotonic() > deadline:
            fail(202, "timeout", f"still pending after {timeout}s")
        i += 1
