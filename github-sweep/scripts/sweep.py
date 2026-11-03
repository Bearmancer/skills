#!/usr/bin/env python3
"""
sweep.py: Bundled execution engine for the github-sweep skill.
Autonomous account-wide discovery, third-party triage, and branch status checks.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
from collections import defaultdict

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

def is_personal_repo(name_with_owner, current_user, forks_set):
    owner = name_with_owner.split("/")[0]
    if owner.lower() == current_user.lower():
        return name_with_owner.lower() not in forks_set
    return False

def sweep_prs(current_user, forks_set, fetch_details=True):
    raw = run_cmd(["gh", "search", "prs", "--author", "@me", "--limit", "100", "--json", "repository,number,title,state,url,createdAt,updatedAt,closedAt"])
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except Exception:
        return []

    third_party = []
    for item in items:
        repo = item["repository"]["nameWithOwner"]
        if is_personal_repo(repo, current_user, forks_set):
            continue
        third_party.append(item)

    if not fetch_details:
        return third_party

    for item in third_party:
        if item.get("state", "").lower() != "open":
            continue
        repo = item["repository"]["nameWithOwner"]
        num = item["number"]
        detail_raw = run_cmd(["gh", "pr", "view", str(num), "--repo", repo, "--json", "mergeable,reviewDecision,statusCheckRollup,headRefName"])
        if detail_raw:
            try:
                d = json.loads(detail_raw)
                item["mergeable"] = d.get("mergeable")
                item["reviewDecision"] = d.get("reviewDecision")
                item["headRefName"] = d.get("headRefName")
                
                rollup = d.get("statusCheckRollup") or []
                failures = [c.get("name") or c.get("context") for c in rollup if c.get("conclusion") in ["FAILURE", "TIMED_OUT", "ACTION_REQUIRED"]]
                in_prog = [c for c in rollup if c.get("status") in ["IN_PROGRESS", "QUEUED"]]
                item["ci_total"] = len(rollup)
                item["ci_failures"] = len(failures)
                item["ci_in_progress"] = len(in_prog)
                item["failure_names"] = failures
            except Exception:
                pass
    return third_party

def sweep_issues(current_user, forks_set):
    raw = run_cmd(["gh", "search", "issues", "--author", "@me", "--limit", "200", "--json", "repository,number,title,state,url,createdAt,updatedAt,closedAt"])
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except Exception:
        return []

    third_party = []
    for item in items:
        repo = item["repository"]["nameWithOwner"]
        if is_personal_repo(repo, current_user, forks_set):
            continue
        third_party.append(item)
    return third_party

def sweep_forks(current_user):
    raw = run_cmd(["gh", "repo", "list", "--fork", "--json", "nameWithOwner,name,parent,defaultBranchRef", "--limit", "100"])
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []

def main():
    parser = argparse.ArgumentParser(description="Account-wide GitHub sweep for third-party PRs, issues, and fork branches.")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--open-only", action="store_true", help="Only include open items")
    parser.add_argument("--prs-only", action="store_true", help="Sweep PRs only")
    parser.add_argument("--issues-only", action="store_true", help="Sweep issues only")
    parser.add_argument("--forks-only", action="store_true", help="Sweep forks only")
    parser.add_argument("--out", type=str, help="Save report to specified file path")
    args = parser.parse_args()

    current_user = get_current_user()
    forks = sweep_forks(current_user)
    forks_set = {f["nameWithOwner"].lower() for f in forks}

    report = {"user": current_user, "forks": forks}

    if not args.issues_only and not args.forks_only:
        report["prs"] = sweep_prs(current_user, forks_set)
    if not args.prs_only and not args.forks_only:
        report["issues"] = sweep_issues(current_user, forks_set)

    summary = {}
    if "prs" in report:
        all_prs = report["prs"]
        open_prs = [p for p in all_prs if p.get("state", "").lower() == "open"]
        merged_prs = [p for p in all_prs if p.get("state", "").lower() == "merged"]
        closed_prs = [p for p in all_prs if p.get("state", "").lower() == "closed"]
        summary["prs"] = {
            "total": len(all_prs),
            "open": len(open_prs),
            "merged": len(merged_prs),
            "closed": len(closed_prs)
        }
    if "issues" in report:
        all_issues = report["issues"]
        open_issues = [i for i in all_issues if i.get("state", "").lower() == "open"]
        closed_issues = [i for i in all_issues if i.get("state", "").lower() == "closed"]
        summary["issues"] = {
            "total": len(all_issues),
            "open": len(open_issues),
            "closed": len(closed_issues)
        }
    summary["forks"] = len(forks)
    report["summary"] = summary

    if args.json:
        output_str = json.dumps(report, indent=2)
        if args.out:
            Path(args.out).write_text(output_str, encoding="utf-8")
        else:
            print(output_str)
        return

    lines = []
    lines.append(f"# Third-Party GitHub Sweep Report (@{current_user})\n")
    if "prs" in summary:
        p = summary["prs"]
        lines.append(f"**Pull Requests:** {p['total']} total ({p['open']} Open, {p['merged']} Merged, {p['closed']} Closed)")
    if "issues" in summary:
        i = summary["issues"]
        lines.append(f"**Issues:** {i['total']} total ({i['open']} Open, {i['closed']} Closed)")
    lines.append(f"**Tracked Forks:** {summary['forks']}")
    lines.append("")

    if "prs" in report:
        open_prs = [p for p in report["prs"] if p.get("state", "").lower() == "open"]
        lines.append("## Open Pull Requests")
        if not open_prs:
            lines.append("No open third-party pull requests.\n")
        else:
            for pr in open_prs:
                repo = pr["repository"]["nameWithOwner"]
                num = pr["number"]
                title = pr["title"]
                mergeable = pr.get("mergeable", "UNKNOWN")
                rev = pr.get("reviewDecision") or "NONE"
                ci_tot = pr.get("ci_total", 0)
                ci_fail = pr.get("ci_failures", 0)
                ci_run = pr.get("ci_in_progress", 0)
                
                ci_str = f"CI: {ci_tot - ci_fail - ci_run}/{ci_tot} passed"
                if ci_fail > 0:
                    ci_str += f" ({ci_fail} failed: {', '.join(pr.get('failure_names', []))})"
                if ci_run > 0:
                    ci_str += f" ({ci_run} queued/running)"
                
                lines.append(f"- **[{repo}#{num}]** {title}")
                lines.append(f"  - Mergeable: `{mergeable}` | Review: `{rev}` | {ci_str}")
                lines.append(f"  - URL: {pr['url']}")
            lines.append("")

    if "issues" in report and not args.open_only:
        open_issues = [i for i in report["issues"] if i.get("state", "").lower() == "open"]
        lines.append("## Open Issues by Repository")
        by_repo = defaultdict(list)
        for iss in open_issues:
            by_repo[iss["repository"]["nameWithOwner"]].append(iss)
        
        for r, r_issues in sorted(by_repo.items()):
            lines.append(f"### {r} ({len(r_issues)} open)")
            for iss in r_issues:
                lines.append(f"- **#{iss['number']}**: {iss['title']} ([Link]({iss['url']}))")
            lines.append("")

    out_text = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(out_text, encoding="utf-8")
        print(f"Report written to {args.out}")
    else:
        print(out_text)

if __name__ == "__main__":
    main()
