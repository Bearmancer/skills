#!/usr/bin/env python3
"""
purge_branches.py: Autonomous maximal branch purge for user forks.
Deletes remote fork branches whose PRs are merged or closed, or which have 0 unique commits vs upstream.
Never deletes branches of open PRs, default branches, branches with unmerged work,
or branches checked out in a local worktree (bounded scan of cwd and ~/Dev).

Fail-closed: an incomplete PR census, unknown upstream, inconclusive compare or
failed worktree scan (outside --dry-run) aborts or preserves; never guesses.

Compares run as batched GraphQL alias queries (50 branches per query) with a
per-branch REST fallback, so thousand-branch mirrors cost dozens of calls, not
thousands.
"""

import argparse
import json
from pathlib import Path
import re
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
            "1000",
        ]
    )
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def get_all_prs():
    """Paginated viewer PR census. Returns None when incomplete (fail closed)."""
    query = (
        "query($cursor: String) { viewer { pullRequests(first: 100, after: $cursor, "
        "orderBy: {field: CREATED_AT, direction: DESC}) { pageInfo { hasNextPage endCursor } "
        "nodes { headRefName state headRepository { nameWithOwner } "
        "repository { nameWithOwner } } } } }"
    )
    nodes = []
    cursor = None
    for _ in range(50):  # hard cap: 5000 PRs; beyond that, refuse to guess
        cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
        if cursor:
            cmd += ["-f", f"cursor={cursor}"]
        raw = run_cmd(cmd)
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except Exception:
            return None
        pr = data.get("data", {}).get("viewer", {}).get("pullRequests", {})
        nodes.extend(pr.get("nodes", []))
        page_info = pr.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            return nodes
        cursor = page_info.get("endCursor")
        if not cursor:
            return None
    return None


def get_worktree_branches():
    """(fork_full, branch) pairs checked out in local worktrees.

    Bounded scan: cwd and ~/Dev, each plus immediate subdirectories. Linked
    worktrees are covered by `git worktree list` on their parent repo.
    Returns (pairs, scan_ok); scan_ok False means a git probe failed.
    """
    pairs = set()
    scan_ok = True
    seen = set()
    roots = [Path.cwd(), Path.home() / "Dev"]
    url_re = re.compile(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?\s")
    for root in roots:
        if not root.is_dir():
            continue
        candidates = [root] + [p for p in root.iterdir() if p.is_dir()]
        for c in candidates:
            if not (c / ".git").exists() or c in seen:
                continue
            seen.add(c)
            remotes = run_cmd(["git", "-C", str(c), "remote", "-v"])
            if not remotes:
                continue
            repos = set()
            for line in remotes.splitlines():
                m = url_re.search(line + " ")
                if m:
                    repos.add(m.group(1))
            if not repos:
                continue
            wt = run_cmd(["git", "-C", str(c), "worktree", "list", "--porcelain"])
            if wt is None:
                scan_ok = False
                continue
            for line in wt.splitlines():
                if line.startswith("branch refs/heads/"):
                    branch = line[len("branch refs/heads/"):]
                    for repo in repos:
                        pairs.add((repo, branch))
    return pairs, scan_ok


def graphql_compare_batch(upstream_full, upstream_default, head_owner, branches):
    """branch -> (status, ahead_by) or None when inconclusive.

    One GraphQL query per 50 branches: repository(upstream).ref(default)
    .compare(headRef: "forkOwner:branch"). Cross-repo headRef is supported.
    A failed query marks its whole chunk None so the caller falls back to
    per-branch REST compares (fail closed).
    """
    owner, name = upstream_full.split("/", 1)
    esc_default = upstream_default.replace("\\", "\\\\").replace('"', '\\"')
    out = {}
    for i in range(0, len(branches), 50):
        chunk = branches[i : i + 50]
        fields = []
        for j, b in enumerate(chunk):
            esc = b.replace("\\", "\\\\").replace('"', '\\"')
            fields.append(
                f'c{j}: ref(qualifiedName: "refs/heads/{esc_default}") '
                f'{{ compare(headRef: "{head_owner}:{esc}") {{ status aheadBy }} }}'
            )
        query = (
            f'query {{ repository(owner: "{owner}", name: "{name}") {{ '
            + " ".join(fields)
            + " } }"
        )
        raw = run_cmd(["gh", "api", "graphql", "-f", f"query={query}"])
        repo_node = None
        if raw:
            try:
                repo_node = json.loads(raw).get("data", {}).get("repository")
            except Exception:
                repo_node = None
        for j, b in enumerate(chunk):
            cmp_node = None
            if isinstance(repo_node, dict):
                alias = repo_node.get(f"c{j}")
                if isinstance(alias, dict):
                    cmp_node = alias.get("compare")
            if isinstance(cmp_node, dict) and cmp_node.get("aheadBy") is not None:
                status = str(cmp_node.get("status") or "").lower()
                out[b] = (status, cmp_node["aheadBy"])
            else:
                out[b] = None
    return out


def rest_compare(upstream_full, upstream_default, head_owner, branch):
    """(status, ahead_by) or None when inconclusive (fail closed)."""
    cmp_raw = run_cmd(
        [
            "gh",
            "api",
            f"repos/{upstream_full}/compare/{upstream_default}...{head_owner}:{branch}",
            "--jq",
            "{status: .status, ahead_by: .ahead_by}",
        ]
    )
    if not cmp_raw:
        return None
    try:
        cmp_data = json.loads(cmp_raw)
    except Exception:
        return None
    if cmp_data.get("ahead_by") is None:
        return None
    return (cmp_data.get("status"), cmp_data["ahead_by"])


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
    parser.add_argument(
        "--fork",
        action="append",
        help="Restrict the audit to these forks (owner/repo, repeatable)",
    )
    args = parser.parse_args()

    current_user = get_current_user()
    forks = get_forks()
    if args.fork:
        wanted = {f.lower() for f in args.fork}
        forks = [f for f in forks if f["nameWithOwner"].lower() in wanted]

    prs = get_all_prs()
    if prs is None:
        print("ERROR: PR census incomplete or failed; refusing to purge (fail closed).")
        sys.exit(2)

    worktree_pairs, worktree_scan_ok = get_worktree_branches()
    if not worktree_scan_ok and not args.dry_run:
        print("ERROR: local worktree scan failed; refusing to purge (fail closed).")
        sys.exit(2)

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
    upstream_defaults = {}

    print(f"Auditing {len(forks)} forks for @{current_user} ({len(prs)} PRs censused)...")

    for f in forks:
        fork_full = f["nameWithOwner"]
        # gh repo list returns parent as {id, name, owner{login}} only:
        # nameWithOwner and defaultBranchRef are NOT populated on parent.
        parent = f.get("parent") or {}
        parent_owner = (parent.get("owner") or {}).get("login")
        parent_name = parent.get("name")
        upstream_full = (
            f"{parent_owner}/{parent_name}" if parent_owner and parent_name else None
        )
        upstream_default = None
        if upstream_full:
            if upstream_full not in upstream_defaults:
                upstream_defaults[upstream_full] = run_cmd(
                    ["gh", "api", f"repos/{upstream_full}", "--jq", ".default_branch"]
                )
            upstream_default = upstream_defaults[upstream_full]
        fork_default = (f.get("defaultBranchRef") or {}).get("name", "main")

        # Get remote branches on fork (paginated: forks can carry thousands).
        raw_branches = run_cmd(
            ["gh", "api", f"repos/{fork_full}/branches", "--paginate", "--jq", ".[].name"]
        )
        if not raw_branches:
            continue
        branch_names = raw_branches.splitlines()
        head_owner = fork_full.split("/")[0]

        # First pass: invariable safety checks; collect branches needing compare.
        pending = []
        for b in branch_names:
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

            if (fork_full, b) in worktree_pairs:
                preserved.append(
                    {
                        "fork": fork_full,
                        "branch": b,
                        "reason": "Checked out in a local worktree",
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

            if not upstream_full or not upstream_default:
                preserved.append(
                    {
                        "fork": fork_full,
                        "branch": b,
                        "reason": "Upstream unknown; cannot compare",
                    }
                )
                continue

            pending.append((b, states))

        if not pending:
            continue

        # Batched compares, REST fallback for anything inconclusive.
        batch = graphql_compare_batch(
            upstream_full, upstream_default, head_owner, [b for b, _ in pending]
        )

        for b, states in pending:
            result = batch.get(b)
            if result is None:
                result = rest_compare(upstream_full, upstream_default, head_owner, b)
            if result is None:
                preserved.append(
                    {
                        "fork": fork_full,
                        "branch": b,
                        "reason": "Comparison check inconclusive",
                    }
                )
                continue
            status, ahead = result

            # Always compare against upstream before deleting. A merged or
            # closed PR does not prove that the branch has no extra commits
            # (squash merges leave the branch ahead of the default branch).
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

            if "MERGED" in states:
                delete_reason = "PR was MERGED upstream"
            elif "CLOSED" in states:
                delete_reason = "PR was CLOSED"
            else:
                delete_reason = f"0 unmerged commits vs upstream ({status})"

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
    if not worktree_scan_ok:
        print("WARNING: local worktree scan incomplete; candidates need a manual B4 check.")
    if args.verbose:
        for p in preserved:
            print(f"  - Preserved: {p['fork']}:{p['branch']} ({p['reason']})")


if __name__ == "__main__":
    main()
