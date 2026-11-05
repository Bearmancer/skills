#!/usr/bin/env python3
"""
rebase.py: Isolated CodeGraph-backed rebase runner for GitHub pull requests.
Clones target repo, initializes CodeGraph, rebases the PR branch onto upstream base,
and reports conflicts or pushes with lease protection.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

def run_cmd(cmd, cwd=None, env=None, timeout=None):
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", env=env, timeout=timeout)
        return res
    except Exception as e:
        print(f"Error running {cmd}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Rebase a PR branch in an isolated CodeGraph environment.")
    parser.add_argument("repo", help="Target upstream repository (e.g. code-yeongyu/oh-my-openagent)")
    parser.add_argument("pr", type=int, help="PR number")
    parser.add_argument("--push", action="store_true", help="Push to fork with --force-with-lease if rebase succeeds")
    parser.add_argument("--keep-workspace", action="store_true", help="Do not delete temporary workspace")
    args = parser.parse_args()

    # 1. Fetch PR details
    res = run_cmd(["gh", "pr", "view", str(args.pr), "--repo", args.repo, "--json", "headRefName,baseRefName,headRepositoryOwner,headRepository"])
    if not res or res.returncode != 0:
        print(f"Could not fetch PR #{args.pr} from {args.repo}")
        sys.exit(1)

    pr_info = json.loads(res.stdout)
    head_branch = pr_info["headRefName"]
    base_branch = pr_info["baseRefName"]
    fork_owner = pr_info["headRepositoryOwner"]["login"]
    fork_repo = pr_info["headRepository"]["nameWithOwner"]

    print(f"Rebasing {args.repo}#{args.pr}: {fork_repo}:{head_branch} -> upstream/{base_branch}")

    # 2. Setup isolated scratch directory
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"gh-rebase-{args.pr}-"))
    repo_dir = tmp_dir / "repo"
    rebase_res = None
    conflict_retained = False
    print(f"Workspace: {tmp_dir}")

    try:
        # 3. Clone upstream repo (blobless)
        print("Cloning upstream default branch...")
        run_cmd(["gh", "repo", "clone", args.repo, str(repo_dir), "--", "--filter=blob:none", "--branch", base_branch])

        # 4. Initialize CodeGraph
        print("Initializing CodeGraph index on base...")
        codegraph_bin = shutil.which("codegraph") or "codegraph"
        run_cmd([codegraph_bin, "init", "-y"], cwd=repo_dir,
                env={**os.environ, "CODEGRAPH_PARSE_WORKERS": "2"}, timeout=900)  # CODEGRAPH-TEARDOWN v1

        # 5. Add user fork remote & fetch branch
        print(f"Fetching fork branch {head_branch}...")
        run_cmd(["git", "remote", "add", "fork", f"https://github.com/{fork_repo}.git"], cwd=repo_dir)
        run_cmd(["git", "fetch", "fork", head_branch], cwd=repo_dir)
        run_cmd(["git", "checkout", "-b", head_branch, "FETCH_HEAD"], cwd=repo_dir)

        # 6. Rebase onto origin/base
        print(f"Rebasing onto origin/{base_branch}...")
        rebase_res = run_cmd(["git", "rebase", f"origin/{base_branch}"], cwd=repo_dir)

        if rebase_res.returncode == 0:
            new_sha = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_dir).stdout.strip()
            print(f"\n[SUCCESS] Rebase completed cleanly! New HEAD: {new_sha}")

            if args.push:
                print("Pushing with --force-with-lease...")
                push_res = run_cmd(["git", "push", "--force-with-lease", "fork", head_branch], cwd=repo_dir)
                if push_res.returncode == 0:
                    print(f"[PUSHED] Successfully updated fork {fork_repo}:{head_branch}")
                else:
                    print(f"[PUSH FAILED] {push_res.stderr}")
        else:
            status_res = run_cmd(["git", "status"], cwd=repo_dir)
            print("\n[CONFLICT] Rebase encountered merge conflicts:")
            print(status_res.stdout)
            print("\nRun CodeGraph symbol exploration in workspace to resolve conflicts.")
            if not args.keep_workspace:
                conflict_retained = True
                print(f"Workspace retained at: {tmp_dir}")
                return

    finally:
        if not args.keep_workspace and not conflict_retained:
            shutil.rmtree(tmp_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
