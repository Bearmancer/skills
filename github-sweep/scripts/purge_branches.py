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
    raw = run_cmd(
        [
            "gh",
            "repo",
            "list",
            "--fork",
            "--json",
            "nameWithOwner,name,parent,defaultBranchRef",
            "--limit",
            "100",
        ]
    )
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def get_all_prs():
    # headRepository is required: a bare headRefName can collide across forks.
    query = (
        "query { viewer { pullRequests(first: 100, orderBy: "
        "{field: CREATED_AT, direction: DESC}) { nodes { headRefName state "
        "headRepository { nameWithOwner } repository { nameWithOwner } } } } }"
    )
    raw = run_cmd(["gh", "api", "graphql", "-f", f"query={query}"])
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return (
            data.get("data", {})
            .get("viewer", {})
            .get("pullRequests", {})
            .get("nodes", [])
        )
    except Exception:
        return []


def main():
    parser = argparse.ArgumentParser(
        description="Purge merged/closed/stale branches across all user forks without prompts."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report candidates without deleting"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print detailed evaluation per branch"
    )
    args = parser.parse_args()

    current_user = get_current_user()
    forks = get_forks()
    prs = get_all_prs()

    # Index PRs by (head repository, head ref). A bare ref is not enough:
    # the same branch name can exist in many forks with different PR states.
    pr_states = {}
    unknown_head_refs = set()

    for p in prs:
        ref = p.get("headRefName")
        state = str(p.get("state") or "").upper()
        if not ref or not state:
            continue
        head = p.get("headRepository") or {}
        head_repo = head.get("nameWithOwner") if isinstance(head, dict) else None
        if head_repo:
            pr_states.setdefault((head_repo, ref), set()).add(state)
        else:
            # The fork may be deleted or inaccessible. Never use this PR as
            # proof that an arbitrary fork branch is safe to delete.
            unknown_head_refs.add(ref)

    purged = []
    preserved = []

    print(f"Auditing {len(forks)} forks for @{current_user}...")

    for f in forks:
        fork_full = f["nameWithOwner"]
        upstream_full = f.get("parent", {}).get("nameWithOwner")
        upstream_default = (
            f.get("parent", {}).get("defaultBranchRef", {}).get("name", "main")
        )
        fork_default = f.get("defaultBranchRef", {}).get("name", "main")

        # Get remote branches on fork
        raw_branches = run_cmd(
            ["gh", "api", f"repos/{fork_full}/branches", "--jq", ".[].name"]
        )
        if not raw_branches:
            continue
        branch_names = raw_branches.splitlines()

        for b in branch_names:
            # Invariable safety checks
            if b in [fork_default, upstream_default, "main", "master", "dev"]:
                preserved.append(
                    {"fork": fork_full, "branch": b, "reason": "Default base branch"}
                )
                continue

            states = pr_states.get((fork_full, b), set())
            if "OPEN" in states:
                preserved.append(
                    {
                        "fork": fork_full,
                        "branch": b,
                        "reason": "Active OPEN pull request",
                    }
                )
                continue

            if not states and b in unknown_head_refs:
                preserved.append(
                    {
                        "fork": fork_full,
                        "branch": b,
                        "reason": "PR head repository unknown; fail closed",
                    }
                )
                continue

            if not upstream_full:
                preserved.append(
                    {
                        "fork": fork_full,
                        "branch": b,
                        "reason": "No upstream parent; cannot compare",
                    }
                )
                continue

            # Always compare against upstream before deleting. A merged or
            # closed PR does not prove that the branch has no extra commits.
            head_owner = fork_full.split("/")[0]
            cmp_raw = run_cmd(
                [
                    "gh",
                    "api",
                    f"repos/{upstream_full}/compare/{upstream_default}...{head_owner}:{b}",
                    "--jq",
                    "{status: .status, ahead_by: .ahead_by}",
                ]
            )
            if not cmp_raw:
                preserved.append(
                    {
                        "fork": fork_full,
                        "branch": b,
                        "reason": "Comparison check inconclusive",
                    }
                )
                continue

            try:
                cmp_data = json.loads(cmp_raw)
                ahead = cmp_data.get("ahead_by")
                status = cmp_data.get("status")
            except Exception:
                preserved.append(
                    {
                        "fork": fork_full,
                        "branch": b,
                        "reason": "Comparison check inconclusive",
                    }
                )
                continue

            if ahead is None:
                preserved.append(
                    {
                        "fork": fork_full,
                        "branch": b,
                        "reason": "Comparison check inconclusive (no ahead_by)",
                    }
                )
                continue

            if ahead > 0:
                preserved.append(
                    {
                        "fork": fork_full,
                        "branch": b,
                        "reason": f"Unmerged work (ahead by {ahead})",
                    }
                )
                continue

            if states and not ({"MERGED", "CLOSED"} & states):
                preserved.append(
                    {
                        "fork": fork_full,
                        "branch": b,
                        "reason": f"PR state {sorted(states)} is not purgeable",
                    }
                )
                continue

            delete_reason = None
            if "MERGED" in states:
                delete_reason = "PR was MERGED upstream"
            elif "CLOSED" in states:
                delete_reason = "PR was CLOSED"
            else:
                delete_reason = f"0 unmerged commits vs upstream ({status})"

            if delete_reason:
                if not args.dry_run:
                    del_res = subprocess.run(
                        [
                            "gh",
                            "api",
                            "-X",
                            "DELETE",
                            f"repos/{fork_full}/git/refs/heads/{b}",
                        ],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                    )
                    if del_res.returncode == 0:
                        purged.append(
                            {"fork": fork_full, "branch": b, "reason": delete_reason}
                        )
                        print(f"  [PURGED] {fork_full}:{b} ({delete_reason})")
                    else:
                        print(
                            f"  [FAILED] Could not delete {fork_full}:{b}: {del_res.stderr.strip()}"
                        )
                else:
                    purged.append(
                        {
                            "fork": fork_full,
                            "branch": b,
                            "reason": f"[DRY-RUN] {delete_reason}",
                        }
                    )
                    print(f"  [CANDIDATE] {fork_full}:{b} ({delete_reason})")

    print("\n=== PURGE REPORT ===")
    print(f"Branches purged: {len(purged)}")
    print(f"Branches preserved: {len(preserved)}")
    if args.verbose:
        for p in preserved:
            print(f"  - Preserved: {p['fork']}:{p['branch']} ({p['reason']})")


if __name__ == "__main__":
    main()
