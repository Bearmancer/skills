# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""PreToolUse hook command: allow only uv-managed Python.

Reads one tool-call JSON object on stdin (tool_name "Bash" or "PowerShell"
with tool_input.command; tool_input.script and top-level command/script are
also accepted). Splits the command on ; && || | & and newlines (outside
quotes), unwraps powershell -Command / bash -c / cmd /c quoting, and to
block prints exactly
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny",
"permissionDecisionReason":"<one line naming the offending command and the uv replacement>"}}
to stdout and exits 0 when any command starts with bare python, python3,
python.exe, py, py.exe, pip, pip3, pipx or python -m (a full path ending in
one of those counts; uv pip is also blocked). Anything else, including uv
run, uv tool run, uvx, and mere mentions of python inside quoted text, path
arguments or comments, prints nothing and exits 0. Empty or malformed stdin
prints nothing on stdout and exits 0 with a stderr note: a guard never
crashes a tool call.
"""

import json
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BARE_NAMES = {"python", "python3", "py", "pip", "pip3", "pipx"}
PY_VERSION = re.compile(r"^python\d+(\.\d+)*$")
PY_FAMILY = {"python", "python3", "py"}
PIP_FAMILY = {"pip", "pip3", "pipx"}
MAX_UNWRAP = 4
MAX_SHOWN = 400


def split_segments(text):
    segs, cur, quote = [], [], None
    i = 0
    while i < len(text):
        c = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if quote:
            cur.append(c)
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
            cur.append(c)
        elif c == "\r" and nxt == "\n":
            segs.append("".join(cur))
            cur = []
            i += 1
        elif c in "\r\n;":
            segs.append("".join(cur))
            cur = []
        elif c == "&" and nxt == "&":
            segs.append("".join(cur))
            cur = []
            i += 1
        elif c == "&":
            segs.append("".join(cur))
            cur = []
        elif c == "|" and nxt == "|":
            segs.append("".join(cur))
            cur = []
            i += 1
        elif c == "|":
            segs.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    segs.append("".join(cur))
    return segs


def strip_comment(seg):
    if re.match(r"\s*(#|::)", seg) or re.match(r"(?i)\s*rem(\s|$)", seg):
        return ""
    out, quote, i = [], None, 0
    while i < len(seg):
        c = seg[i]
        if quote:
            out.append(c)
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
            out.append(c)
        elif c == "#" and out and out[-1] in " \t":
            break
        else:
            out.append(c)
        i += 1
    return "".join(out)


def strip_outer_quotes(s):
    for _ in range(3):
        s = s.strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
            s = s[1:-1]
        else:
            break
    return s


def unwrap(seg, depth=0):
    if depth >= MAX_UNWRAP:
        return seg
    m = re.match(r"\s*(powershell|pwsh|bash|sh|dash|cmd)\b(.*)$", seg, re.I | re.S)
    if not m:
        return seg
    rest = m.group(2)
    f = re.search(r"(^|\s)(-(command|c)|/c)\s+", rest, re.I)
    if not f:
        return seg
    return unwrap(strip_outer_quotes(rest[f.end() :]), depth + 1)


def first_token(seg):
    seg = seg.strip()
    if seg[:1] in "\"'":
        end = seg.find(seg[0], 1)
        return seg[1:] if end < 0 else seg[1:end]
    return seg.split(None, 1)[0] if seg.split(None, 1) else ""


def base_name(tok):
    base = re.split(r"[\\/]", tok.strip().strip("\"'"))[-1].lower()
    if base.endswith(".exe"):
        base = base[:-4]
    return base


def replacement(seg, base, args):
    if base == "uv":
        rest = args.split(None, 1)
        if rest[:1] == ["pip"]:
            return replacement(seg, "pip", rest[1] if len(rest) > 1 else "")
        return "uv run --no-project ..."
    if base in PY_FAMILY or PY_VERSION.match(base):
        if base == "py":
            m = re.match(r"^(-\d+(\.\d+)?)\s*(.*)$", args, re.S)
            if m and "." in m.group(1):
                rest = m.group(3)
                return f"uv run --no-project python --python {m.group(1)[1:]}" + (
                    " " + rest if rest else ""
                )
            if m:
                rest = m.group(3)
                return "uv run --no-project python" + (" " + rest if rest else "")
        return "uv run --no-project python" + (" " + args if args else "")
    if base in PIP_FAMILY:
        rest = args.split(None, 1)
        if rest[:1] == ["install"] and len(rest) == 2:
            return "uv add " + rest[1]
        if rest[:1] == ["run"] and len(rest) == 2:
            return "uvx " + rest[1]
        return "uv add <package> (or 'uv run --with <package> ...')"
    return "uv run --no-project ..."


def deny_json(reason):
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        separators=(",", ":"),
    )


def check_text(text):
    queue, seen = split_segments(text), 0
    while queue and seen < 64:
        raw = queue.pop(0)
        seen += 1
        seg = strip_comment(raw).strip()
        if not seg:
            continue
        inner = unwrap(seg)
        if inner != seg:
            queue.extend(split_segments(inner))
            continue
        tok = first_token(inner)
        if not tok:
            continue
        base = base_name(tok)
        blocked, why = False, ""
        if base in BARE_NAMES or PY_VERSION.match(base):
            blocked, why = True, inner
        else:
            parts = inner.split(None, 2)
            prog = base_name(parts[0]) if parts else ""
            if prog in ("uv", "uvx"):
                if prog == "uvx":
                    continue
                sub = parts[1].lower() if len(parts) > 1 else ""
                if sub == "pip":
                    blocked, why = True, inner
        if blocked:
            args = inner.split(None, 1)[1] if len(inner.split(None, 1)) > 1 else ""
            shown = why if len(why) <= MAX_SHOWN else why[:MAX_SHOWN] + "..."
            return (
                True,
                f"blocked '{shown}' - use '{replacement(seg, base, args)}' instead",
            )
    return False, None


def decide(obj):
    if not isinstance(obj, dict):
        return False, "uv-guard note: stdin is not a JSON object, allowing"
    tool_input = obj.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    text = tool_input.get(
        "command", tool_input.get("script", obj.get("command", obj.get("script", "")))
    )
    if not isinstance(text, str) or not text.strip():
        return False, "uv-guard note: no command to check, allowing"
    blocked, reason = check_text(text)
    return blocked, reason if blocked else None


def main():
    try:
        raw = sys.stdin.read()
    except Exception as e:
        print(f"uv-guard note: cannot read stdin ({e}), allowing", file=sys.stderr)
        return 0
    if not raw.strip():
        print("uv-guard note: empty stdin, allowing", file=sys.stderr)
        return 0
    try:
        obj = json.loads(raw)
    except ValueError:
        print("uv-guard note: malformed JSON on stdin, allowing", file=sys.stderr)
        return 0
    try:
        blocked, message = decide(obj)
    except Exception as e:
        print(f"uv-guard note: checker failed ({e}), allowing", file=sys.stderr)
        return 0
    if blocked:
        print(deny_json(message), flush=True)
    elif message:
        print(message, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
