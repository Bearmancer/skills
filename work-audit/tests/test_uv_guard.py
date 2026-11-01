"""Tests for scripts/uv-guard.py (PreToolUse hook command).

Output contract: to block, print exactly
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny",
"permissionDecisionReason":"<one line>"}} to stdout and exit 0; to allow,
print nothing and exit 0; malformed stdin prints nothing on stdout and exits
0 with a stderr note. Every case drives the script as a subprocess (resolved interpreter; one case
uses real uv run) with JSON on stdin.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from conftest import PY_RUNNER, SCRIPT_RUNNER, SCRIPT_TIMEOUT

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
UV_GUARD = SCRIPTS / "uv-guard.py"


def guard(payload, raw=None, uv=False):
    env = dict(os.environ)
    text = raw if raw is not None else json.dumps(payload)
    return subprocess.run(
        [*(SCRIPT_RUNNER if uv else PY_RUNNER), str(UV_GUARD)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        input=text,
        timeout=SCRIPT_TIMEOUT,
    )


def hook(command=None, script=None):
    arguments = {}
    if command is not None:
        arguments["command"] = command
    if script is not None:
        arguments["script"] = script
    return {"tool_name": "Bash", "tool_input": arguments}


def deny_of(r):
    assert r.returncode == 0
    assert r.stderr.strip() == ""
    assert r.stdout.strip().count("\n") == 0
    doc = json.loads(r.stdout)
    assert set(doc) == {"hookSpecificOutput"}
    specific = doc["hookSpecificOutput"]
    assert set(specific) == {
        "hookEventName",
        "permissionDecision",
        "permissionDecisionReason",
    }
    assert specific["hookEventName"] == "PreToolUse"
    assert specific["permissionDecision"] == "deny"
    reason = specific["permissionDecisionReason"]
    assert reason and "\n" not in reason
    return reason


BLOCKED = [
    "python script.py",
    "python3 --version",
    'python.exe -c "print(1)"',
    "py -3 script.py",
    "py.exe script.py",
    "pip install requests",
    "pip3 install requests",
    "pipx run black",
    "python -m pytest tests/",
    'PYTHON -c "print(1)"',
    "C:\\Python312\\python.exe script.py",
    "C:/Python312/Scripts/pip.exe install requests",
    "/usr/bin/python3 --version",
    "uv pip install requests",
    '"python" script.py',
]


@pytest.mark.parametrize("command", BLOCKED)
def test_blocked_forms_deny_on_stdout(command):
    reason = deny_of(guard(hook(command=command)))
    assert (
        "uv run" in reason
        or "uv add" in reason
        or "uvx" in reason
        or "uv tool" in reason
    )


ALLOWED = [
    "uv run --no-project scripts/state-report.py --json",
    "uv tool run pytest -q",
    "uvx ruff check .",
    "echo python",
    'echo "pip install requests"',
    "git status --short",
    '"C:\\My Tools\\deploy.exe" --go',
    "scripts/state-report.py --json",
    "# python -m pytest",
    "run python3_tests.py",
]


@pytest.mark.parametrize("command", ALLOWED)
def test_allowed_forms_exit_0_silently(command):
    r = guard(hook(command=command))
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr.strip() == ""


def test_chained_second_command_bad_denies():
    # The one real-uv launch proving the uv-guard entry point boots under uv.
    reason = deny_of(
        guard(hook(command="uv run pytest -q && python -m pytest"), uv=True)
    )
    assert "python -m pytest" in reason


def test_chained_first_command_bad_denies():
    reason = deny_of(guard(hook(command="pip install x; uv run pytest -q")))
    assert "pip install x" in reason


def test_powershell_wrapper_unwrapped():
    reason = deny_of(
        guard(hook(command='powershell -Command "python -m pytest tests/"'))
    )
    assert "python -m pytest" in reason


def test_powershell_flags_wrapper_unwrapped():
    reason = deny_of(
        guard(hook(command='powershell -NoProfile -Command "& pip install requests"'))
    )
    assert "pip install requests" in reason


def test_bash_wrapper_second_bad_denies():
    reason = deny_of(
        guard(hook(command='bash -c "cd repo && python setup.py install"'))
    )
    assert "python setup.py install" in reason


def test_cmd_wrapper_unwrapped():
    reason = deny_of(guard(hook(command='cmd /c "pip install requests"')))
    assert "pip install requests" in reason


def test_windows_spaced_python_path_denies():
    reason = deny_of(
        guard(hook(command='"C:\\Program Files\\Python312\\python.exe" script.py'))
    )
    assert "uv run" in reason


def test_crlf_stdin_still_denies():
    payload = json.dumps(hook(command="uv run a\r\npip install requests")) + "\r\n"
    reason = deny_of(guard(hook(), raw=payload))
    assert "pip install requests" in reason


def test_py_launcher_major_flag_dropped_from_suggestion():
    reason = deny_of(guard(hook(command="py -3 tool.py")))
    assert (
        reason
        == "blocked 'py -3 tool.py' - use 'uv run --no-project python tool.py' instead"
    )


def test_py_launcher_minor_flag_becomes_python_option():
    reason = deny_of(guard(hook(command="py -3.12 tool.py")))
    assert (
        reason
        == "blocked 'py -3.12 tool.py' - use 'uv run --no-project python --python 3.12 tool.py' instead"
    )


def test_script_shape_input_denies():
    reason = deny_of(guard(hook(script="pip install requests")))
    assert "pip install requests" in reason


def test_empty_stdin_allows_with_note():
    r = guard(hook(), raw="")
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr.strip() != ""


def test_malformed_stdin_allows_with_note():
    r = guard(hook(), raw="{not json")
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr.strip() != ""


def test_json_array_stdin_allows_with_note():
    r = guard(hook(), raw="[1, 2]")
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr.strip() != ""


def test_missing_command_allows_with_note():
    r = guard({"tool_name": "Read", "tool_input": {"file_path": "x"}})
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr.strip() != ""
