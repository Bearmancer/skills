import argparse
import subprocess
import sys
from pathlib import Path


def read(path):
    return path.read_text(encoding="utf-8", errors="replace")


def git(repo, *argv):
    cmd = ["git", "-C", str(repo), *argv]
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def check_rebase(args):
    repo = Path(args.repo)
    base = args.base_ref
    allow = set(args.allow or [])
    try:
        out = git(repo, "diff", f"{base}", "--name-only")
    except subprocess.CalledProcessError as e:
        print(f"FAIL check-rebase: git diff failed: {e.stderr.strip()[:200]}")
        sys.exit(2)
    changed = [line.strip() for line in out.splitlines() if line.strip()]
    if allow:
        for name in changed:
            if name not in allow:
                print(f"FAIL check-rebase: {name} not in allowlist")
                sys.exit(2)
    try:
        clog = git(repo, "diff", f"{base}", "--", "CHANGELOG.md")
    except subprocess.CalledProcessError as e:
        print(
            f"FAIL check-rebase: git diff CHANGELOG.md failed: {e.stderr.strip()[:200]}"
        )
        sys.exit(2)
    deleted = sum(
        1
        for line in clog.splitlines()
        if line.startswith("-") and not line.startswith("---")
    )
    if deleted > args.allow_delete:
        print(
            f"FAIL check-rebase: CHANGELOG.md has {deleted} deleted line(s), allowed {args.allow_delete}"
        )
        sys.exit(2)
    print(f"PASS check-rebase: {len(changed)} file(s), {deleted} CHANGELOG deletion(s)")


def check_splice(args):
    path = Path(args.text_file)
    text = read(path)
    start = args.start
    end = args.end
    length = len(text)
    if not (0 <= start < end <= length):
        print(
            f"FAIL check-splice: need 0 <= start < end <= length, got start={start} end={end} length={length}"
        )
        sys.exit(3)
    size = end - start
    if size <= 0:
        print(f"FAIL check-splice: empty slice start={start} end={end}")
        sys.exit(3)
    print(
        f"PASS check-splice: slice length {size} (start={start} end={end} length={length})"
    )


def build_parser():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    rb = sub.add_parser("check-rebase")
    rb.add_argument("repo")
    rb.add_argument("base_ref")
    rb.add_argument(
        "--allow", action="append", default=[], help="allowed changed file (repeatable)"
    )
    rb.add_argument(
        "--allow-delete", type=int, default=0, help="allowed CHANGELOG.md deleted lines"
    )
    sp = sub.add_parser("check-splice")
    sp.add_argument("text_file")
    sp.add_argument("--start", type=int, required=True)
    sp.add_argument("--end", type=int, required=True)
    return parser


def main():
    args = build_parser().parse_args()
    if args.cmd == "check-rebase":
        check_rebase(args)
    else:
        check_splice(args)


main()
