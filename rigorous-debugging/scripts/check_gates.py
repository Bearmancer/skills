#!/usr/bin/env python3
"""Mechanical gate audit for a rigorous-debugging LEDGER.md.

Checks stage gates (fields filled; yes-keys yes; research rows consulted()/
N/A(); waivers carry reason + locator; stages 0/1 never waived; any waiver
implies the post-fix sweep; stage 5 closes with a critical unknown and a
discriminating probe), counts failed [attempt] journal lines against
the 3-fix circuit breaker, and greps --scan trees for leftover debug
instrumentation. Shape is mechanical; the truth of pasted evidence stays
human-reviewed.

Usage: uv run --no-project check_gates.py <LEDGER.md> [--scan PATH ...] [--tag RE]
Exit codes: 0 chain closed · 1 open gates · 2 ledger unreadable / no usage.
Python >= 3.10. Speed-first conventions: no argparse (startup-dominated
tool), scandir stack walk, bytes-mode regex on raw data, positional capture
groups, precomputed spec order. pathlib stays at the file boundary because
the workspace python-pathlib-guard policy requires it; binary handles make
the encoding-corruption concern moot.
"""

import os
import re
import sys
from pathlib import Path

STAGE_FIELDS: dict[int, list[tuple[str, str]]] = {
    0: [("changes_halted", "yes"), ("redacted", "yes"), ("evidence", "text")],
    1: [
        ("command", "text"),
        ("run_once", "text"),
        ("red_capable", "yes"),
        ("deterministic", "yes"),
        ("fast", "text"),
        ("agent_runnable", "yes"),
    ],
    2: [
        ("exact_symptom", "yes"),
        ("minimal_scenario", "text"),
        ("load_bearing", "yes"),
    ],
    3: [("failing_layer", "text"), ("boundary_evidence", "text")],
    4: [
        ("project_docs", "research"),
        ("recent_changes", "research"),
        ("working_examples", "research"),
        ("reference_read_completely", "research"),
        ("official_docs", "research"),
        ("upstream_issues", "research"),
        ("environment_deltas", "research"),
    ],
    5: [
        ("ranked", "text"),
        ("critical_unknown", "text"),
        ("discriminating_probe", "text"),
        ("chosen", "text"),
    ],
    6: [("probes", "text"), ("one_variable", "yes")],
    7: [
        ("seam", "text"),
        ("test_red", "text"),
        ("test_green", "text"),
        ("single_change", "yes"),
    ],
    8: [
        ("original_loop", "text"),
        ("full_suite", "text"),
        ("build", "text"),
        ("e2e_spot", "text"),
        ("mitigations", "text"),
    ],
    9: [
        ("debug_tags_gone", "yes"),
        ("prototypes_cleaned", "yes"),
        ("commit", "text"),
        ("post_fix_sweep", "text"),
        ("breaker", "text"),
    ],
}
SPECS = tuple(sorted(STAGE_FIELDS.items()))  # fixed iteration order, computed once
NO_WAIVER_STAGES = frozenset({0, 1})
MISSING_SEAM_OK = frozenset(
    {(7, "test_red"), (7, "test_green"), (7, "negative_control")}
)
SCAN_EXTS = frozenset(
    {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".md",
        ".ps1",
        ".sh",
        ".rb",
        ".go",
        ".java",
        ".html",
        ".txt",
    }
)
PRUNE_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "target",
    }
)
MAX_SCAN_BYTES = 1_500_000

TOKEN_RE = re.compile(
    r"""
      ^-\s*\d{0,2}:?\d{2}\s*\[(?P<jtype>[a-z-]+)\].*
    | ^[#]{3}\s*Stage\s*(?P<stage>\d+)
    | ^-\s*(?P<key>[a-z0-9_]+):\s*(?P<val>.*)
""",
    re.M | re.X,
)
# positional access beats named lookup ~10-20%; groups never reorder
G_JTYPE, G_STAGE, G_KEY, G_VAL = 1, 2, 3, 4
ATTEMPT_FAIL_RE = re.compile(r"\b(REJECTED|FAILED)\b")
WAIVER_RE = re.compile(r"^WAIVED\((.*)\)$", re.I)
RESEARCH_OK_RE = re.compile(r"^(consulted|N/A)\(", re.I)
ALT_RE = re.compile(r"^\S+ \| ")
INDENT = ("    ", "\t")
SPLITEXT = os.path.splitext  # separator-aware; not a raw-string trap


def read_str(path: str) -> str:
    """Whole-file bytes read, decoded once; beats TextIOWrapper's
    incremental decode while keeping Path at the open boundary."""
    with Path(path).open("rb") as fh:
        return fh.read().decode("utf-8", "ignore")


def parse_ledger(text: str) -> tuple[dict[int, dict[str, str]], list[tuple[str, str]]]:
    """Return (stages, journal). Journal lines match anywhere (append-only
    events land after the last stage section)."""
    toks = list(TOKEN_RE.finditer(text))
    stages: dict[int, dict[str, str]] = {}
    journal: list[tuple[str, str]] = []
    stage: int | None = None
    last = len(toks) - 1
    for n, m in enumerate(toks):
        jtype = m[G_JTYPE]
        if jtype is not None:
            journal.append((jtype, m[0]))
        elif (sh := m[G_STAGE]) is not None:
            stage = int(sh)
            stages.setdefault(stage, {})
        elif (key := m[G_KEY]) is not None and stage is not None:
            value = (m[G_VAL] or "").strip()
            if value == "|":
                end = toks[n + 1].start() if n < last else len(text)
                block: list[str] = []
                for ln in text[m.end() : end].splitlines():
                    if ln.strip():
                        if not ln.startswith(INDENT):
                            break
                        block.append(ln.strip())
                value = " ".join(block) or "|"
            stages[stage][key] = value
    return stages, journal


def is_placeholder(value: str) -> bool:
    return (
        not value
        or value == "|"
        or value.startswith(("<", "yes|"))
        or bool(ALT_RE.match(value))
    )


def _gate_message(kind: str, value: str, seam_pass: bool) -> str | None:
    """Why one non-waiver field fails its gate; None means pass."""
    lower = value.lower()
    match kind:
        case "yes" if lower == "yes" or lower.startswith(("yes ", "yes(")):
            return None
        case "yes":
            return f"not yes or missing (got {value[:30]!r})"
        case "research" if RESEARCH_OK_RE.match(value) and "|" not in value:
            return None
        case "research":
            return f"needs consulted()/N/A() (got {value[:30]!r})"
        case "text" if seam_pass and lower.startswith("n/a"):
            return None
        case "text" if is_placeholder(value):
            return "unfilled placeholder"
        case _:
            return None


def check_value(
    key: str,
    kind: str,
    value: str,
    stage: int,
    findings: list[str],
    waived: set[str],
    seam_missing: bool,
) -> None:
    value = value or ""
    if wm := WAIVER_RE.match(value):
        if "," not in wm[1]:
            findings.append(f"STAGE{stage}.{key}: bare waiver (needs reason, locator)")
        if stage in NO_WAIVER_STAGES:
            findings.append(f"STAGE{stage}.{key}: non-waivable stage was waived")
        waived.add(f"{stage}.{key}")
        return
    seam_pass = (stage, key) in MISSING_SEAM_OK and seam_missing
    if msg := _gate_message(kind, value, seam_pass):
        findings.append(f"STAGE{stage}.{key}: {msg}")


def _scan_file(path: str, tag_re: re.Pattern[bytes], hits: list[str]) -> None:
    """bytes-mode regex over raw data; Path.open("rb") keeps the policy
    boundary and skips incremental text decoding."""
    try:
        if os.stat(path).st_size > MAX_SCAN_BYTES:
            return
        with Path(path).open("rb") as fh:
            data = fh.read()
    except OSError:
        return
    for m in tag_re.finditer(data):
        hits.append(f"{path}: {m[0].decode('ascii', 'ignore')}")


def scan_tags(paths: list[str], tag_re: re.Pattern[bytes]) -> list[str]:
    """scandir stack walk: prunes dependency/VCS dirs, caps size read."""
    hits: list[str] = []
    stack: list[str] = []
    for raw in paths:
        if not Path(raw).is_file():
            stack.append(raw)
            while stack:
                try:
                    entries = os.scandir(stack.pop())
                except OSError:
                    continue
                with entries:
                    for e in entries:
                        try:
                            if e.is_dir(follow_symlinks=False):
                                if e.name.lower() not in PRUNE_DIRS:
                                    stack.append(e.path)
                            elif SPLITEXT(e.name)[1].lower() in SCAN_EXTS:
                                _scan_file(e.path, tag_re, hits)
                        except OSError:
                            pass
            continue
        if SPLITEXT(raw)[1].lower() in SCAN_EXTS:
            _scan_file(raw, tag_re, hits)
    return hits


def main(argv: list[str]) -> int:
    ledger, scan, tag = "", [], r"\[DEBUG-[^\]\s]{2,}\]"
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--scan":
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                scan.append(argv[i])
                i += 1
            continue
        if a == "--tag":
            i += 1
            if i < len(argv):
                tag = argv[i]
        elif a.startswith("--tag="):
            tag = a[6:]
        elif not a.startswith("-") and not ledger:
            ledger = a
        i += 1
    if not ledger:
        print("usage: check_gates.py <LEDGER.md> [--scan PATH ...] [--tag RE]")
        return 2

    if not Path(ledger).is_file():
        print(f"OPEN ledger: file not found: {ledger}")
        return 2
    stages, journal = parse_ledger(read_str(ledger))

    findings: list[str] = []
    waived: set[str] = set()
    cause_found = any(
        t == "cause-found" and not is_placeholder(rest) for t, rest in journal
    )
    failed = sum(
        1 for t, rest in journal if t == "attempt" and ATTEMPT_FAIL_RE.search(rest)
    )

    if failed >= 3 and not cause_found:
        findings.append(
            f"JOURNAL: {failed} failed attempts with no cause-found or re-entry trail"
        )

    for num, specs in SPECS:
        if (fields := stages.get(num)) is None:
            findings.append(f"STAGE{num}: section missing")
            continue
        seam_missing = str(fields.get("seam", "")).upper().startswith("MISSING-SEAM")
        for key, kind in specs:
            check_value(
                key, kind, fields.get(key, ""), num, findings, waived, seam_missing
            )

    if waived and not cause_found:
        findings.append("JOURNAL: waivers present but no [cause-found] line")
    if (
        failed >= 3
        and "discussion" not in str(stages.get(9, {}).get("breaker", "")).lower()
    ):
        findings.append(
            f"BREAKER: {failed} failed attempts require "
            "breaker: discussion(<with partner>)"
        )
    if waived:
        sweep = str(stages.get(9, {}).get("post_fix_sweep", "")).lower()
        if sweep.startswith("no-waivers"):
            findings.append(
                "STAGE9.post_fix_sweep: waivers exist, sweep claimed unnecessary"
            )
        if not sweep.startswith("done"):
            findings.append(
                "STAGE9.post_fix_sweep: required 'done(...)' when any waiver exists"
            )

    if scan:
        findings += [
            f"DEBUG-TAG leftover: {h}"
            for h in scan_tags(scan, re.compile(tag.encode("utf-8", "ignore")))
        ]

    if findings:
        print("\n".join(f"OPEN {f}" for f in findings))
        print(f"chain NOT closed: {len(findings)} open gates")
        return 1
    print(
        f"chain closed: all gates filled, {failed} failed attempt(s), "
        f"waiver={bool(waived)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
