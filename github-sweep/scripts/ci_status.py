#!/usr/bin/env python3
"""
ci_status.py: Inspect and monitor GitHub Actions CI checks for a pull request.
Parses check runs, extracts failure details, and identifies pending/flaky jobs.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if res.returncode != 0:
            return None
        return res.stdout.strip()
    except Exception:
        return None

def main():
    parser = argparse.ArgumentParser(description="Inspect CI checks for a GitHub PR.")
    parser.add_argument("repo", help="Target upstream repository (e.g. code-yeongyu/oh-my-openagent)")
    parser.add_argument("pr", type=int, help="PR number")
    parser.add_argument("--json", action="store_true", help="Emit raw JSON")
    args = parser.parse_args()

    raw = run_cmd(["gh", "pr", "view", str(args.pr), "--repo", args.repo, "--json", "statusCheckRollup,mergeable,commits,title"])
    if not raw:
        print(f"Failed to fetch CI checks for {args.repo}#{args.pr}")
        sys.exit(1)

    data = json.loads(raw)
    rollup = data.get("statusCheckRollup") or []
    mergeable = data.get("mergeable", "UNKNOWN")
    head_sha = data.get("commits", [{}])[-1].get("oid", "unknown")[:10]

    passed = []
    failed = []
    in_progress = []
    queued = []

    for check in rollup:
        name = check.get("name") or check.get("context", "unnamed")
        status = check.get("status", "").upper()
        conclusion = check.get("conclusion", "").upper()
        details_url = check.get("detailsUrl") or check.get("targetUrl", "")

        entry = {"name": name, "status": status, "conclusion": conclusion, "url": details_url}

        if conclusion in ["FAILURE", "TIMED_OUT", "ACTION_REQUIRED", "CANCELLED"]:
            failed.append(entry)
        elif conclusion in ["SUCCESS", "NEUTRAL", "SKIPPED"]:
            passed.append(entry)
        elif status in ["IN_PROGRESS"]:
            in_progress.append(entry)
        elif status in ["QUEUED", "PENDING", "WAITING"]:
            queued.append(entry)

    report = {
        "repo": args.repo,
        "pr": args.pr,
        "title": data.get("title"),
        "head_sha": head_sha,
        "mergeable": mergeable,
        "total": len(rollup),
        "passed_count": len(passed),
        "failed_count": len(failed),
        "in_progress_count": len(in_progress),
        "queued_count": len(queued),
        "failures": failed,
        "in_progress": in_progress,
        "queued": queued,
    }

    if args.json:
        print(json.dumps(report, indent=2))
        return

    print(f"# CI Status for {args.repo}#{args.pr} ({data.get('title')})")
    print(f"HEAD: {head_sha} | Mergeable: `{mergeable}`")
    print(f"Checks: {len(passed)}/{len(rollup)} passed ({len(failed)} failed, {len(in_progress)} in-progress, {len(queued)} queued)\n")

    if failed:
        print("## Failed Checks")
        for f in failed:
            print(f"- **{f['name']}** [{f['conclusion']}]: {f['url']}")
        print("")

    if in_progress or queued:
        print("## Pending Checks")
        for p in in_progress:
            print(f"- [IN_PROGRESS] {p['name']}")
        for q in queued:
            print(f"- [QUEUED] {q['name']}")
        print("")

    if not failed and not in_progress and not queued:
        print("All CI checks are GREEN!")

if __name__ == "__main__":
    main()
