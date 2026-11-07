#!/usr/bin/env python3
"""Safety repros for purge_branches.py.

The bug: merged/closed PRs are indexed by bare headRefName across every fork,
so a branch name that was merged in one repository can delete an unrelated
fork branch with unmerged work. These tests pin the fail-closed contract:
a branch is deleted only when the PR head is the same fork, or the branch has
zero commits ahead of upstream, and the ahead_by check always runs.
"""
import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

PURGE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "purge_branches.py"
SPEC = importlib.util.spec_from_file_location("purge_under_test", PURGE_PATH)
purge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(purge)


FORK = {
    "nameWithOwner": "user/forkB",
    "parent": {
        "nameWithOwner": "upstream/repoB",
        "defaultBranchRef": {"name": "main"},
    },
    "defaultBranchRef": {"name": "main"},
}


def run_main(prs, branches="shared-name", ahead_by=0, status="identical", dry_run=True, verbose=True):
    """Run purge.main with fake gh calls; return stdout and compare-call count."""
    compare_calls = []

    def fake_run_cmd(cmd):
        if any("branches" in str(part) for part in cmd):
            return branches
        if any("/compare/" in str(part) for part in cmd):
            compare_calls.append(cmd)
            if ahead_by is None:
                return None
            return json.dumps({"status": status, "ahead_by": ahead_by})
        return None

    argv = ["purge_branches.py"]
    if dry_run:
        argv.append("--dry-run")
    if verbose:
        argv.append("--verbose")

    out = io.StringIO()
    with mock.patch.object(purge, "get_current_user", return_value="user"), \
         mock.patch.object(purge, "get_forks", return_value=[FORK]), \
         mock.patch.object(purge, "get_all_prs", return_value=prs), \
         mock.patch.object(purge, "run_cmd", side_effect=fake_run_cmd), \
         mock.patch.object(purge.subprocess, "run") as sub_run, \
         mock.patch.object(sys, "argv", argv), \
         contextlib.redirect_stdout(out):
        sub_run.return_value = mock.Mock(returncode=0, stderr="")
        purge.main()
    return out.getvalue(), compare_calls, sub_run


def pr(state="MERGED", head="user/forkB", ref="shared-name", base="upstream/repoB"):
    return {
        "headRefName": ref,
        "state": state,
        "headRepository": {"nameWithOwner": head} if head else None,
        "repository": {"nameWithOwner": base},
    }


class PurgeSafetyTests(unittest.TestCase):
    def test_cross_fork_merged_pr_does_not_touch_unmerged_branch(self):
        out, compares, sub_run = run_main([pr(head="other/forkA")], ahead_by=3, status="ahead")
        self.assertIn("Branches purged: 0", out)
        self.assertNotIn("[CANDIDATE]", out)
        self.assertIn("Unmerged work", out)
        self.assertEqual(len(compares), 1)
        sub_run.assert_not_called()

    def test_same_fork_merged_pr_with_zero_ahead_is_purged(self):
        out, compares, sub_run = run_main([pr(head="user/forkB")], ahead_by=0, status="identical")
        self.assertIn("Branches purged: 1", out)
        self.assertIn("[CANDIDATE] user/forkB:shared-name", out)
        self.assertEqual(len(compares), 1)
        sub_run.assert_not_called()

    def test_same_fork_merged_pr_with_ahead_commits_is_preserved(self):
        out, compares, sub_run = run_main([pr(head="user/forkB")], ahead_by=2, status="ahead")
        self.assertIn("Branches purged: 0", out)
        self.assertNotIn("[CANDIDATE]", out)
        self.assertIn("Unmerged work", out)
        self.assertEqual(len(compares), 1)
        sub_run.assert_not_called()

    def test_open_pr_is_preserved_without_a_compare_call(self):
        out, compares, sub_run = run_main([pr(state="OPEN", head="user/forkB")], ahead_by=0)
        self.assertIn("Branches purged: 0", out)
        self.assertIn("Active OPEN pull request", out)
        self.assertEqual(compares, [])
        sub_run.assert_not_called()

    def test_unknown_head_repository_fails_closed(self):
        out, compares, sub_run = run_main([pr(head=None)], ahead_by=0, status="identical")
        self.assertIn("Branches purged: 0", out)
        self.assertNotIn("[CANDIDATE]", out)
        self.assertIn("head repository unknown", out.lower())
        sub_run.assert_not_called()

    def test_inconclusive_compare_fails_closed(self):
        out, compares, sub_run = run_main([], ahead_by=None)
        self.assertIn("Branches purged: 0", out)
        self.assertIn("inconclusive", out.lower())
        self.assertEqual(len(compares), 1)
        sub_run.assert_not_called()

    def test_orphan_branch_with_zero_ahead_is_purged(self):
        out, compares, sub_run = run_main([], ahead_by=0, status="identical")
        self.assertIn("Branches purged: 1", out)
        self.assertIn("[CANDIDATE] user/forkB:shared-name", out)

    def test_default_branch_is_preserved(self):
        out, compares, sub_run = run_main([], branches="main", ahead_by=0)
        self.assertIn("Branches purged: 0", out)
        self.assertIn("Default base branch", out)
        self.assertEqual(compares, [])

    def test_real_run_deletes_only_after_zero_ahead(self):
        out, compares, sub_run = run_main([pr(head="user/forkB")], ahead_by=0, status="identical", dry_run=False)
        self.assertIn("Branches purged: 1", out)
        sub_run.assert_called_once()
        delete_cmd = sub_run.call_args.args[0]
        self.assertIn("DELETE", delete_cmd)
        self.assertIn("repos/user/forkB/git/refs/heads/shared-name", delete_cmd)


if __name__ == "__main__":
    unittest.main(verbosity=2)
