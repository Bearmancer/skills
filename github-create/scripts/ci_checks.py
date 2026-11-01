"""CI-check reads for preflight: a check failed only when its bucket is fail or cancel, never by raw state."""

import json
import re


def gh_json(run, *argv):
    try:
        return json.loads(run(["gh", *argv]) or "null")
    except ValueError:
        return None


FAILED_JOBS = ("failure", "timed_out")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
TS = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z\s*")


def failed_checks(slug, pr, run):
    """Failed checks of a PR, or None when the probe itself failed (fail closed)."""
    checks = gh_json(
        run,
        "pr",
        "checks",
        str(pr),
        "--repo",
        slug,
        "--json",
        "name,workflow,state,bucket,link",
    )
    if checks is None:
        return None
    return [c for c in checks if str(c.get("bucket")).lower() in ("fail", "cancel")]


def log_tail(run, slug, run_id, job_id=None):
    """Last lines of a run's (or one job's) failed log, joined; None when gh cannot answer."""
    out = run(
        [
            "gh",
            "run",
            "view",
            str(run_id),
            "--repo",
            slug,
            "--log-failed",
            *(["--job", str(job_id)] if job_id else []),
        ]
    )
    if out is None:
        return None
    lines = [
        TS.sub("", ANSI.sub("", x.split("\t", 2)[-1]).strip()) for x in out.splitlines()
    ]
    lines = [x for x in lines if x]
    marks = [i for i, x in enumerate(lines) if "##[error]" in x]
    if (
        marks
    ):  # the job log ends in cleanup noise, so start at the first error annotation
        return " / ".join(lines[max(0, marks[0] - 6) : marks[0] + 6])[:900]
    return " / ".join(lines[-12:])[-900:]
