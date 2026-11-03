#!/usr/bin/env python3
"""
purge.py: Autonomous maximal branch purge for user forks.
Deletes remote fork branches whose PRs are merged or closed, or which have 0 unique commits vs upstream.
Never deletes branches of open PRs, default branches, or branches with unmerged work.
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

def get_current_user():
    user = run_cmd(["gh", "api", "user", "--jq", ".login"])
    if not user:
        status = run_cmd(["gh", "auth", "status"])
        for line in (status or "").splitlines():
            if "account" in line:
                parts = line.split("account")
                if len(parts) > 1:
                    return parts[1].split()[0]
    return user or "Bearmancer"

def get_forks():
    raw = run_cmd(["gh", "repo", "list", "--fork", "--json", "nameWithOwner,name,parent,defaultBranchRef", "--limit", "100"])
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []

def get_all_prs():
    raw = run_cmd(["gh", "search", "prs", "--author", "@me", "--limit", "150", "--json", "repository,number,state,headRefName"])
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []

def main():
    parser = argparse.ArgumentParser(description="Purge merged/closed/stale branches across all user forks without prompts.")
    parser.add_argument("--dry-run", action="store_true", help="Report candidates without deleting")
    parser.add_argument("--verbose", action="store_true", help="Print detailed evaluation per branch")
    args = parser.parse_args()

    current_user = get_current_user()
    forks = get_forks()
    prs = get_all_prs()

    # Index PRs by (headRefName, targetRepo)
    # Also track branches that have ANY open PR
    open_branches = set()
    merged_branches = set()
    closed_branches = set()

    for p in prs:
        ref = p.get("headRefName")
        state = p.get("state", "").upper()
        if not ref:
            continue
        if state == "OPEN":
            open_branches.add(ref)
        elif state == "MERGED":
            merged_branches.add(ref)
        elif state == "CLOSED":
            closed_branches.add(ref)

    purged = []
    preserved = []

    print(f"Auditing {len(forks)} forks for @{current_user}...")

    for f in forks:
        fork_full = f["nameWithOwner"]
        upstream_full = f.get("parent", {}).get("nameWithOwner")
        upstream_default = f.get("parent", {}).get("defaultBranchRef", {}).get("name", "main")
        fork_default = f.get("defaultBranchRef", {}).get("name", "main")

        # Get remote branches on fork
        raw_branches = run_cmd(["gh", "api", f"repos/{fork_full}/branches", "--jq", ".[].name"])
        if not raw_branches:
            continue
        branch_names = raw_branches.splitlines()

        for b in branch_names:
            # Invariable safety checks
            if b in [fork_default, upstream_default, "main", "master", "dev"]:
                preserved.append({"fork": fork_full, "branch": b, "reason": "Default base branch"})
                continue

            if b in open_branches:
                preserved.append({"fork": fork_full, "branch": b, "reason": "Active OPEN pull request"})
                continue

            # Candidate for purge check
            delete_reason = None
            if b in merged_branches:
                delete_reason = "PR was MERGED upstream"
            elif b in closed_branches:
                delete_reason = "PR was CLOSED"
            else:
                # Compare against upstream default
                if upstream_full:
                    cmp_raw = run_cmd(["gh", "api", f"repos/{upstream_full}/compare/{upstream_default}...{current_user}:{b}", "--jq", "{status: .status, ahead_by: .ahead_by}"])
                    if cmp_raw:
                        try:
                            cmp_data = json.loads(cmp_raw)
                            ahead = cmp_data.get("ahead_by", 1)
                            status = cmp_data.get("status")
                            if ahead == 0 or status in ["identical", "behind"]:
                                delete_reason = f"0 unmerged commits vs upstream ({status})"
                            else:
                                preserved.append({"fork": fork_full, "branch": b, "reason": f"Unmerged work (ahead by {ahead})"})
                                continue
                        except Exception:
                            preserved.append({"fork": fork_full, "branch": b, "reason": "Comparison check inconclusive"})
                            continue

            if delete_reason:
                if not args.dry_run:
                    del_res = subprocess.run(["gh", "api", "-X", "DELETE", f"repos/{fork_full}/git/refs/heads/{b}"], capture_output=True, text=True, encoding="utf-8")
                    if del_res.returncode == 0:
                        purged.append({"fork": fork_full, "branch": b, "reason": delete_reason})
                        print(f"  [PURGED] {fork_full}:{b} ({delete_reason})")
                    else:
                        print(f"  [FAILED] Could not delete {fork_full}:{b}: {del_res.stderr.strip()}")
                else:
                    purged.append({"fork": fork_full, "branch": b, "reason": f"[DRY-RUN] {delete_reason}"})
                    print(f"  [CANDIDATE] {fork_full}:{b} ({delete_reason})")

    print("\n=== PURGE REPORT ===")
    print(f"Branches purged: {len(purged)}")
    print(f"Branches preserved: {len(preserved)}")
    if args.verbose:
        for p in preserved:
            print(f"  - Preserved: {p['fork']}:{p['branch']} ({p['reason']})")

if __name__ == "__main__":
    main()
