import argparse
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "preflight", Path(__file__).parents[1] / "scripts" / "preflight.py"
)
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)

DISCLOSURE = "Drafted with AI assistance."


def exit_code(fn, *args):
    with pytest.raises(SystemExit) as raised:
        fn(*args)
    return raised.value.code


def comment_args(tmp_path, text):
    path = tmp_path / "comment.md"
    path.write_text(text)
    return argparse.Namespace(body=str(path), banner=None)


def disclosure_problems(body):
    problems = []
    args = argparse.Namespace(ai_policy="disclose", disclosure=DISCLOSURE)
    pf.check_policy(None, args, body, problems)
    return problems


def test_comment_with_banner_last_passes(tmp_path):
    text = f"Finding.\n\n> {pf.DEFAULT_COMMENT_BANNER}\n"
    assert exit_code(pf.check_comment, comment_args(tmp_path, text)) == 0


def test_comment_with_banner_first_is_refused(tmp_path):
    text = f"> {pf.DEFAULT_COMMENT_BANNER}\n\nFinding.\n"
    assert exit_code(pf.check_comment, comment_args(tmp_path, text)) != 0


def test_body_with_disclosure_last_passes():
    assert disclosure_problems(f"## What\n\nFix.\n\n{DISCLOSURE}\n") == []


def test_body_with_disclosure_first_is_flagged():
    assert disclosure_problems(f"{DISCLOSURE}\n\n## What\n\nFix.\n") != []
