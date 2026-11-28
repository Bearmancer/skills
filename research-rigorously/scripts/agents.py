import re
from functools import lru_cache

import yaml

from . import registry

ROLES_MD = registry.ROOT / "references" / "roles.md"
_FENCE = re.compile(r"```(?:ya?ml)?\s*\n(.*?)```", re.DOTALL)
_STEP = re.compile(r"^## step: (?P<key>[\w-]+)\s*$", re.MULTILINE)
_CHECKING = re.compile(r"^Checking roles:\s*(?P<roles>.+?)\s*$", re.MULTILINE)
_UNANSWERABLE = re.compile(r"^\s*UNANSWERABLE:\s*(?P<reason>.*)$")


class AgentReplyError(ValueError):
    pass


class Unanswerable(Exception):
    """The agent answered `UNANSWERABLE: <reason>`: the ask cannot be done.

    Not a reply to parse and not worth re-asking: each caller turns it into the
    failure path its role already has.
    """

    def __init__(self, reason=""):
        self.reason = reason.strip() or "no reason given"
        super().__init__(self.reason)


def unanswerable(text):
    """The reason from a reply whose first non-blank line is `UNANSWERABLE: <reason>`."""
    for line in str(text).splitlines():
        if line.strip():
            match = _UNANSWERABLE.match(line)
            return (match["reason"].strip() or "no reason given") if match else None
    return None


@lru_cache(maxsize=1)
def _steps():
    text = ROLES_MD.read_text(encoding="utf-8")
    marks = list(_STEP.finditer(text))
    out = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out[m["key"]] = text[m.end() : end].strip()
    return out


@lru_cache(maxsize=1)
def checking_roles():
    """Role names marked for a fresh subagent, from the roles.md header line."""
    m = _CHECKING.search(ROLES_MD.read_text(encoding="utf-8"))
    if not m:
        return []
    return [name.strip() for name in m["roles"].split(",") if name.strip()]


@lru_cache(maxsize=1)
def _reader_profile():
    m = re.search(
        r"^## Reader profile\s*\n(.*?)(?=^## )",
        ROLES_MD.read_text(encoding="utf-8"),
        re.DOTALL | re.MULTILINE,
    )
    return m[1].split(":", 1)[1].strip() if m else ""


# Steps that write prose; only these get the reader profile (ADR 0014).
AUTHOR_STEPS = frozenset({"draft", "course", "layout", "conformance"})


def step_prompt(key):
    try:
        prompt = _steps()[key]
    except KeyError:
        raise AgentReplyError(f"no step prompt {key!r} in roles.md") from None
    return (
        f"{prompt}\nReader profile: {_reader_profile()}"
        if key in AUTHOR_STEPS
        else prompt
    )


def source_block(text):
    return "<source>\n" + text.replace("</source>", r"<\/source>") + "\n</source>"


def parse_reply(text):
    reason = unanswerable(text)
    if reason is not None:
        raise Unanswerable(reason)
    blocks = _FENCE.findall(text)
    body = blocks[-1] if blocks else text
    try:
        data = yaml.safe_load(body)
    except yaml.YAMLError as exc:
        raise AgentReplyError(f"reply is not valid YAML: {str(exc)[:200]}") from exc
    if not isinstance(data, dict):
        raise AgentReplyError("reply is not a YAML mapping")
    return data


def call(
    runner,
    role,
    key,
    payload,
    step,
    context=None,
    required=(),
    strict=False,
    check=None,
):
    prompt = f"{step_prompt(key)}\n\n---\n\n{payload}"
    last = None
    for attempt in range(2):
        text = runner.run(
            role,
            prompt
            if attempt == 0
            else f"{prompt}\n\n---\n\nYour previous reply was rejected: {last}. Reply again, YAML only.",
            step if attempt == 0 else f"{step}.retry",
            context,
        )
        try:
            reason = unanswerable(text)
            if reason is not None:
                raise Unanswerable(reason)
            if strict:
                # exactly one fenced block, nothing after closing fence
                fences = re.findall(r"```", text)
                if len(fences) != 2:
                    raise AgentReplyError("strict: expected exactly one fenced block")
                idx = text.rfind("```")
                tail = text[idx + 3 :].strip()
                if tail:
                    raise AgentReplyError("strict: content after closing fence")
            data = parse_reply(text)
            missing = [k for k in required if k not in data]
            if missing:
                raise AgentReplyError(f"reply lacks {missing}")
            if check is not None:
                check(data)
            return data
        except AgentReplyError as exc:
            last = exc
    if strict:
        return {"_flags": [str(last)]}
    raise AgentReplyError(f"{step}: {last}")
