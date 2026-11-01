# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Audit how tests are written: per-test setup, unmocked probes, wait-based
simulation, duplicated helpers, slow tests without bench evidence, weak
asserts, count drift, shared mutable state.

Usage: uv run scripts/test-audit.py [repo] [--junitxml FILE] [--collected N] [--slow-over SECS]
Findings use the record shape {check, path, claim, evidence, severity, fixed}.
A `# test-audit: accept <reason>` comment on a flagged line (or its def line)
suppresses the finding. Exit 1 when findings exist, else 0.
"""

import argparse
import ast
import difflib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SLOW_OVER = 5.0
SIMILARITY = 0.85
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".pytest_cache"}
ACCEPT = "test-audit: accept"

BUILDERS = {
    "make_repo",
    "make_demo",
    "git",
    "subprocess.run",
    "subprocess.Popen",
    "pytest.main",
}
AUDITS = {"run_state_report", "run_record", "run_stop_guard", "state_report", "audit"}
PROBES = [
    re.compile(p)
    for p in (
        r"\bgh(\.EXE)?\b.*\b(api|auth|issue|pr)\b",
        r"dotnet\s+--version",
        r"\bcargo\s+--version",
        r"\bgo\s+version\b",
        r"\bnpm\s+--version\b",
        r"\bnode\s+--version\b",
        r"\burllib\b",
        r"\brequests\.",
        r"\bsocket\.",
    )
]
MOCK_HINTS = ("no_gh", "no_mock", "fake", "mock", "stub", "monkeypatch", "which(")
WAIT_RES = [
    re.compile(r"slee" + r"p\s*\("),
    re.compile(r"ping\s+-n\b"),
    re.compile(r"timeout\s*=\s*0(?![\d.])"),
]
WEAK_RES = [
    re.compile(r"\bor\s+True\b"),
    re.compile(r"assert\s+True\b"),
    re.compile(r"raises\(\s*Exception\s*\)"),
    re.compile(r"except\s+Exception\s*:"),
]
HARD_TEMP_RES = [
    re.compile(r"/tmp/"),
    re.compile(r"[Cc]:\\Temp"),
    re.compile(r"[Cc]:/Temp"),
]


def test_files(root):
    out = []
    for p in sorted(Path(root).rglob("*.py")):
        if any(d in SKIP_DIRS for d in p.parts):
            continue
        if p.name.startswith("test_") or p.name.endswith("_test.py"):
            out.append(p)
    return out


def accepted(lines, lineno, fn_start):
    for n in (lineno, fn_start):
        if n is not None and 1 <= n <= len(lines) and ACCEPT in lines[n - 1]:
            return True
    return False


def fn_ranges(tree):
    """[(name, start, end, node)] for every test function (methods included)."""
    out = []

    def visit(body):
        for node in body:
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and node.name.startswith("test"):
                out.append(
                    (node.name, node.lineno, node.end_lineno or node.lineno, node)
                )
            elif isinstance(node, ast.ClassDef):
                visit(node.body)

    visit(tree.body)
    return out


def owner_of(ranges, lineno):
    for name, s, e, _node in ranges:
        if s <= lineno <= e:
            return name, s
    return None, None


def dotted(fn):
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        v = dotted(fn.value)
        return f"{v}.{fn.attr}" if v else fn.attr
    return ""


def calls_in(node):
    return {dotted(n.func) for n in ast.walk(node) if isinstance(n, ast.Call)}


def call_lines(node):
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            d = dotted(n.func)
            if d:
                out.append((n.lineno, d))
    return out


def finding(check, path, claim, evidence, severity):
    return {
        "check": check,
        "path": path,
        "claim": claim,
        "evidence": evidence,
        "severity": severity,
        "fixed": False,
    }


def check_t1(path, rel, src):
    out = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    lines = src.splitlines()
    for name, start, _end, node in fn_ranges(tree):
        calls = calls_in(node)
        if "pytest.main" in calls and not accepted(lines, start, start):
            out.append(
                finding(
                    "T1",
                    rel,
                    f"{name} runs pytest.main in-process: fixture suites only",
                    f"{rel}:{start}",
                    "low",
                )
            )
        hit = sorted((BUILDERS & calls) - {"pytest.main"})
        if hit and (AUDITS & calls) and not accepted(lines, start, start):
            first = min(l for l, d in call_lines(node) if d in BUILDERS)
            out.append(
                finding(
                    "T1",
                    rel,
                    f"{name} builds a repo/process per test and audits it "
                    f"({hit[0]}): share a once-per-process template",
                    f"{rel}:{first}",
                    "medium",
                )
            )
    return out


def check_t2(path, rel, src):
    out = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    lines = src.splitlines()
    ranges = fn_ranges(tree)
    bodies = {}
    for name, s, e, _n in ranges:
        bodies[name] = "\n".join(lines[s - 1 : e]).lower()
    for i, line in enumerate(lines, 1):
        low = line.lower()
        if ACCEPT in line:
            continue
        if re.match(r"\s*[A-Z][A-Z0-9_]*\s*=", line):
            continue  # message constants are fixture data, not probes
        if any(rx.search(line) for rx in PROBES):
            name, start = owner_of(ranges, i)
            body = bodies.get(name, low)
            if any(h in body for h in MOCK_HINTS):
                continue
            out.append(
                finding(
                    "T2",
                    rel,
                    "unmocked external-tool probe in a unit test "
                    "(gh/dotnet/network waits cost seconds and need the network)",
                    f"{rel}:{i}",
                    "high",
                )
            )
    return out


def check_t3_file(path, rel, src, in_tests):
    out = []
    lines = src.splitlines()
    try:
        ranges = fn_ranges(ast.parse(src)) if in_tests else []
    except SyntaxError:
        ranges = []
    for i, line in enumerate(lines, 1):
        if ACCEPT in line:
            continue
        if any(rx.search(line) for rx in WAIT_RES):
            _name, start = owner_of(ranges, i)
            if accepted(lines, i, start):
                continue
            out.append(
                finding(
                    "T3",
                    rel,
                    "wait-based simulation (delay/timeout-zero/ping): "
                    "prove a real bound instead, or record why it must hang",
                    f"{rel}:{i}",
                    "medium",
                )
            )
    return out


def helpers_of(src):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {}
    out = {}
    for node in tree.body:
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ) and not node.name.startswith("test"):
            seg = "\n".join(
                l
                for l in ast.get_source_segment(src, node).splitlines()
                if l.strip() and not l.strip().startswith("#")
            )
            out[node.name] = seg
    return out


def check_t4(files):
    out = []
    seen = {}
    for path, rel, helpers in files:
        for name in helpers:
            if name in seen:
                other = seen[name]
                if other != rel and not any(
                    f["evidence"] == f"{rel}:1" and name in f["claim"] for f in out
                ):
                    out.append(
                        finding(
                            "T4",
                            rel,
                            f"helper {name} also defined in {other}: "
                            "keep one copy (conftest or a shared module)",
                            f"{rel}:1",
                            "low",
                        )
                    )
            else:
                seen[name] = rel
    items = [
        (rel, name, body)
        for _p, rel, helpers in files
        for name, body in helpers.items()
    ]
    for i, (rel_a, _na, body_a) in enumerate(items):
        for rel_b, nb, body_b in items[i + 1 :]:
            if rel_a == rel_b or len(body_a) < 200 or len(body_b) < 200:
                continue
            ratio = difflib.SequenceMatcher(None, body_a, body_b).ratio()
            if ratio >= SIMILARITY:
                out.append(
                    finding(
                        "T4",
                        rel_b,
                        f"helper {nb} is {ratio:.0%} identical to "
                        f"{rel_a}: merge the duplicates",
                        f"{rel_b}:1",
                        "low",
                    )
                )
    return out


def junit_slow_rows(xml, slow_over):
    rows = []
    root = ET.parse(xml).getroot()
    for tc in root.iter("testcase"):
        try:
            d = float(tc.get("time", 0))
        except ValueError:
            continue
        if d >= slow_over:
            rows.append(
                (
                    d,
                    (tc.get("file") or "").replace("\\", "/"),
                    tc.get("classname", ""),
                    tc.get("name", "?"),
                )
            )
    return rows


def locate_source(root, fileattr, classname):
    if fileattr and (Path(root) / fileattr.lstrip("./")).is_file():
        return Path(root) / fileattr.lstrip("./")
    parts = [p for p in classname.split(".") if p]
    if parts and not parts[-1].startswith("test") and parts[-1][:1].isupper():
        parts = parts[:-1]
    if parts:
        for cand in (
            Path(root) / "tests" / (parts[-1] + ".py"),
            Path(root) / (parts[-1] + ".py"),
        ):
            if cand.is_file():
                return cand
    return None


def check_t5(root, junitxml, slow_over):
    if not junitxml:
        return [], "skipped (need --junitxml)"
    out = []
    for d, fileattr, classname, name in junit_slow_rows(junitxml, slow_over):
        src = locate_source(root, fileattr, classname)
        if src is None:
            out.append(
                finding(
                    "T5",
                    "?",
                    f"slow test {name} ({d:.1f}s) has no mappable source",
                    "?:1",
                    "low",
                )
            )
            continue
        rel = src.relative_to(root).as_posix()
        text = src.read_text(encoding="utf-8", errors="ignore")
        base = name.split("[")[0]
        m = re.search(rf"^def {re.escape(base)}\b", text, re.M)
        body = text[m.start() :] if m else text
        if "bench:" not in body.split("\ndef ", 1)[0]:
            line = text[: m.start()].count("\n") + 1 if m else 1
            out.append(
                finding(
                    "T5",
                    rel,
                    f"slow test {name} ({d:.1f}s) carries no `# bench:` "
                    "evidence from scripts/bench.py",
                    f"{rel}:{line}",
                    "low",
                )
            )
    return out, ""


def check_t6(path, rel, src):
    out = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    lines = src.splitlines()
    for name, start, end, node in fn_ranges(tree):
        if accepted(lines, start, start):
            continue
        body = lines[start - 1 : end]
        for off, line in enumerate(body, start):
            if ACCEPT in line:
                continue
            hit = next((rx for rx in WEAK_RES if rx.search(line)), None)
            if hit:
                out.append(
                    finding(
                        "T6",
                        rel,
                        f"{name} has a weak assert ({hit.pattern}): it cannot fail",
                        f"{rel}:{off}",
                        "medium",
                    )
                )
        has_assert = any(isinstance(n, ast.Assert) for n in ast.walk(node))
        has_raises = any(
            isinstance(n, ast.With)
            and any(
                isinstance(i.context_expr, ast.Call)
                and dotted(i.context_expr.func).endswith("raises")
                for i in n.items
            )
            for n in ast.walk(node)
        )
        if not has_assert and not has_raises:
            out.append(
                finding(
                    "T6",
                    rel,
                    f"{name} has no assert: it cannot fail",
                    f"{rel}:{start}",
                    "high",
                )
            )
    return out


def len_of(arg, assigns):
    if isinstance(arg, (ast.List, ast.Tuple)):
        return len(arg.elts)
    if isinstance(arg, ast.Name):
        return assigns.get(arg.id)  # @parametrize over a module-level list
    return None


def predict_file(src):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None

    def cases(dec):
        if not isinstance(dec, ast.Call):
            return 1
        if getattr(dec.func, "attr", "") != "parametrize":
            return 1
        if len(dec.args) < 2:
            return None
        return len_of(dec.args[1], assigns)

    assigns = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, (ast.List, ast.Tuple))
        ):
            assigns[node.targets[0].id] = len(node.value.elts)

    def fns(body):
        for node in body:
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and node.name.startswith("test"):
                yield node
            elif isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(
                        sub, (ast.FunctionDef, ast.AsyncFunctionDef)
                    ) and sub.name.startswith("test"):
                        yield sub

    total = 0
    for fn in fns(tree.body):
        mult = 1
        for dec in fn.decorator_list:
            c = cases(dec)
            if c is None:
                return None
            mult *= c
        total += mult
    return total


def check_t7(root, files, collected):
    if collected is None:
        return [], "skipped (need --collected)"
    predicted, wild = 0, []
    for _path, rel, src in files:
        n = predict_file(src)
        if n is None:
            wild.append(rel)
        else:
            predicted += n
    if wild or predicted != collected:
        detail = f"predicted {predicted} from test functions" + (
            f", unpredicted in {','.join(wild)}" if wild else ""
        )
        return [
            finding(
                "T7",
                "tests",
                f"test count drift: collected {collected} but {detail}",
                "tests:1",
                "medium",
            )
        ], ""
    return [], ""


def check_t8(path, rel, src):
    out = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            out.append(
                finding(
                    "T8",
                    rel,
                    f"shared mutable state via `global {','.join(node.names)}`: "
                    "xdist runs tests in shared worker processes",
                    f"{rel}:{node.lineno}",
                    "medium",
                )
            )
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            if dotted(node.value) == "os.environ" and not accepted(
                lines, node.lineno, node.lineno
            ):
                out.append(
                    finding(
                        "T8",
                        rel,
                        "direct os.environ write: use monkeypatch.setenv "
                        "so workers cannot leak state",
                        f"{rel}:{node.lineno}",
                        "medium",
                    )
                )
    for i, line in enumerate(lines, 1):
        if ACCEPT in line:
            continue
        if any(rx.search(line) for rx in HARD_TEMP_RES):
            out.append(
                finding(
                    "T8",
                    rel,
                    "hardcoded temp path: use tmp_path",
                    f"{rel}:{i}",
                    "medium",
                )
            )
    return out


CHECKS = (
    (
        "T1",
        "per-test setup",
        "per-test repo/process setup instead of once-per-process templates",
    ),
    (
        "T2",
        "unmocked probes",
        "unmocked external-tool probes (gh, dotnet, network) inside unit tests",
    ),
    ("T3", "wait simulation", "timeout- or delay-based simulations"),
    ("T4", "duplicated helpers", "duplicated helpers and fixtures across test files"),
    ("T5", "slow tests", "slow tests without benchmark evidence"),
    ("T6", "weak asserts", "weak or unfailable asserts"),
    ("T7", "count drift", "test counts that disagree between runs"),
    ("T8", "shared state", "tests that share mutable state or are not xdist-safe"),
)


def audit_repo(root, junitxml=None, collected=None, slow_over=SLOW_OVER):
    root = Path(root)
    findings, notes = [], {}
    tfiles = test_files(root)
    srcs = [
        (
            p,
            p.relative_to(root).as_posix(),
            p.read_text(encoding="utf-8", errors="ignore"),
        )
        for p in tfiles
    ]
    by_rel = {rel: (p, src) for p, rel, src in srcs}
    for _p, rel, src in srcs:
        findings += check_t1(_p, rel, src)
        findings += check_t2(_p, rel, src)
        findings += check_t3_file(_p, rel, src, True)
        findings += check_t6(_p, rel, src)
        findings += check_t8(_p, rel, src)
    scripts = (
        sorted((root / "scripts").glob("*.py")) if (root / "scripts").is_dir() else []
    )
    for p in scripts:
        rel = p.relative_to(root).as_posix()
        findings += check_t3_file(
            p, rel, p.read_text(encoding="utf-8", errors="ignore"), False
        )
    findings += check_t4([(p, rel, helpers_of(src)) for p, rel, src in srcs])
    slow, note = check_t5(root, junitxml, slow_over)
    findings += slow
    notes["T5"] = note
    drift, note = check_t7(root, [(p, rel, src) for p, rel, src in srcs], collected)
    findings += drift
    notes["T7"] = note
    by_check = {}
    for f in findings:
        by_check.setdefault(f["check"], []).append(f)
    return findings, by_check, notes


def main(argv=None):
    ap = argparse.ArgumentParser(description="Audit how tests are written.")
    ap.add_argument("repo", nargs="?", default=".", help="repo whose tests get audited")
    ap.add_argument(
        "--junitxml",
        default=None,
        help="JUnit XML of a recent run (enables the slow-test check)",
    )
    ap.add_argument(
        "--collected",
        type=int,
        default=None,
        help="collected test count (enables the count-drift check)",
    )
    ap.add_argument(
        "--slow-over",
        type=float,
        default=SLOW_OVER,
        help="seconds above which a test counts as slow",
    )
    ap.add_argument("--json", action="store_true", help="print the findings as JSON")
    a = ap.parse_args(argv)
    findings, by_check, notes = audit_repo(a.repo, a.junitxml, a.collected, a.slow_over)
    if a.json:
        print(json.dumps(findings, indent=1))
        return 1 if findings else 0
    from datetime import datetime

    print(f"test-audit {datetime.now():%Y-%m-%d %H:%M} repo: {a.repo}")
    for tag, _name, desc in CHECKS:
        extra = f" [{notes[tag]}]" if notes.get(tag) else ""
        items = by_check.get(tag, [])
        print(f"{tag} {desc}: {len(items)} finding(s){extra}")
        for f in items[:10]:
            print(f"     - {f['path']}: {f['claim']} [{f['evidence']}]")
    print(f"{len(findings)} findings total")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
