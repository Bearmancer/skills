# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Benchmark a pytest suite: process costs, collection, serial/xdist walls, JUnit rankings, subprocess counts, bottlenecks.

Stdlib only; pytest and pytest-xdist arrive via `uv run --with` at run time.
Usage: uv run scripts/bench.py [suite] [--slow N] [--workers auto] [--no-serial] [--no-xdist]
"""

import argparse
import collections
import os
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

BENCH = Path(__file__).resolve()
CALL_TIMEOUT = 120
SPY_TIMEOUT = 600
COLLECTED_RE = re.compile(r"(\d+)\s+tests?\s+collected")


def sh(cmd, cwd=None, timeout=CALL_TIMEOUT):
    t = time.perf_counter()
    r = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return time.perf_counter() - t, r


def uv_base(withs):
    # pytest-xdist is always in the env: the xdist wall run needs -n, and a
    # missing plugin turns into pytest exit 4 (usage error) instead of a timing.
    base = ["uv", "run", "--no-project", "--with", "pytest", "--with", "pytest-xdist"]
    for w in withs:
        if w not in ("pytest", "pytest-xdist"):
            base += ["--with", w]
    return base + [
        "python",
        "-W",
        "error",
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
    ]


def process_costs():
    tmp = Path(tempfile.mkdtemp(prefix="bench-proc-"))
    probes = {
        "uv run python -c pass": ["uv", "run", "--no-project", "python", "-c", "pass"],
        "uv run --with pytest": [
            "uv",
            "run",
            "--no-project",
            "--with",
            "pytest",
            "python",
            "-c",
            "pass",
        ],
        "git --version": ["git", "--version"],
        "git init empty repo": ["git", "init", "-q", str(tmp / "r")],
    }
    out = {}
    for name, cmd in probes.items():
        try:
            out[name] = min(sh(cmd)[0] for _ in range(3))
        except Exception as e:
            out[name] = f"probe failed: {e}"
    try:
        for p in sorted(tmp.rglob("*")):
            if p.is_file():
                p.unlink()
        tmp.rmdir()
    except OSError:
        pass
    return out


def parse_collect_output(out):
    """(count, {(file stem, test name): node id}) from --collect-only -q output.

    The count comes from the summary line, so it stays right when -qq hides
    the node ids (a second -q collapses the listing into per-file counts).
    """
    ids = [l.strip() for l in out.splitlines() if "::" in l]
    table = {}
    for nid in ids:
        head, _, name = nid.rpartition("::")
        table[(Path(head).stem, name)] = nid
    found = COLLECTED_RE.findall(out)
    return (int(found[-1]) if found else None, table)


def file_key_for(tc):
    f = (tc.get("file") or "").replace("\\", "/")
    if f:
        return Path(f).name or "?"
    parts = [p for p in tc.get("classname", "").split(".") if p]
    if not parts:
        return "?"
    if len(parts) >= 2 and not parts[-1].startswith("test") and parts[-1][:1].isupper():
        parts = parts[:-1]  # drop trailing TestClass, keep the module
    return parts[-1] + ".py"


def parse_junit(xml):
    per_file = collections.defaultdict(lambda: [0, 0.0])
    tests = []
    root = ET.parse(xml).getroot()
    for tc in root.iter("testcase"):
        name = tc.get("name", "?")
        key = file_key_for(tc)
        fileattr = (tc.get("file") or "").replace("\\", "/")
        try:
            d = float(tc.get("time", 0))
        except ValueError:
            d = 0.0
        per_file[key][0] += 1
        per_file[key][1] += d
        tests.append((d, key, name, fileattr))
    total = sum(v[1] for v in per_file.values())
    return per_file, tests, total


def resolve_nodeid(table, fileattr, key, name, suite):
    """Rebuild a runnable node id for a JUnit row.

    Prefers the JUnit file attribute, then the exact collect-only table, then
    a classname-derived path that exists under the suite (JUnit classnames
    often lack the tests/ folder prefix).
    """
    suite = Path(suite)
    if fileattr:
        cand = fileattr.lstrip("./")
        if (suite / cand).is_file():
            return f"{cand}::{name}"
    stem = Path(key).stem
    hit = table.get((stem, name))
    if hit is None:
        for (s, n), nid in table.items():
            if s == stem and n.split("[")[0] == name.split("[")[0]:
                hit = nid
                break
    if hit is not None:
        return hit
    for cand in (f"tests/{stem}.py", f"{stem}.py"):
        if (suite / cand).is_file():
            return f"{cand}::{name}"
    return None


def _short(cmd):
    if isinstance(cmd, (list, tuple)):
        return " ".join(map(str, cmd[:3]))
    return str(cmd)[:60]


def _is_git(cmd):
    if not isinstance(cmd, (list, tuple)) or not cmd:
        return False
    b = os.path.basename(str(cmd[0])).lower()
    return b in ("git", "git.exe", "git.bat", "git.cmd") or b.startswith("git.")


def spy_one(testid):
    import subprocess as sp

    calls = []
    real_popen = sp.Popen

    # Patch Popen only: subprocess.run is implemented on top of Popen, so it
    # is timed exactly once via communicate. (Patching run too would count
    # every call twice and report more subprocess time than wall time.)
    class PopenSpy(real_popen):
        def communicate(self, *a, **k):
            t = time.perf_counter()
            try:
                return super().communicate(*a, **k)
            finally:
                calls.append(
                    (time.perf_counter() - t, _short(self.args), _is_git(self.args))
                )

    sp.Popen = PopenSpy
    import pytest

    wall = time.perf_counter()
    before_mods, before_path = dict(sys.modules), list(sys.path)
    try:
        rc = pytest.main(["-q", "-p", "no:cacheprovider", "--no-header", testid])
    finally:
        wall = time.perf_counter() - wall
        # An in-process pytest run imports the target suite's conftest and test
        # modules into THIS process (conftest lands as top-level "conftest",
        # overwriting our own). Evict what it added and restore what it replaced
        # so later imports still resolve to our suite.
        for m in set(sys.modules) - set(before_mods):
            sys.modules.pop(m, None)
        for m, mod in before_mods.items():
            if sys.modules.get(m) is not mod:
                sys.modules[m] = mod
        sys.path[:] = before_path
    sub = sum(d for d, _, _ in calls)
    git_calls = sum(1 for _, _, g in calls if g)
    git_time = sum(d for d, _, g in calls if g)
    print(
        f"SPY {testid} rc={rc} wall={wall:.2f} calls={len(calls)} "
        f"sub={sub:.2f} git_calls={git_calls} git_time={git_time:.2f}"
    )
    agg = collections.defaultdict(lambda: [0, 0.0])
    for d, s, _ in calls:
        agg[s][0] += 1
        agg[s][1] += d
    for s, (n, t) in sorted(agg.items(), key=lambda kv: -kv[1][1])[:8]:
        print(f"SPYTOP {t:6.2f}s {n:4d}x  {s}")
    return 0


def classify(wall, sub, git_calls, uv_spawns):
    share = sub / wall if wall > 0 else 0.0
    if share >= 0.5 and git_calls >= 10:
        return (
            f"git-heavy: {git_calls} git calls, {sub:.1f}s of {wall:.1f}s in subprocess "
            "- cut calls / share repos"
        )
    if share >= 0.5 and uv_spawns >= 1:
        return (
            f"uv-launch overhead: {uv_spawns} uv spawns, {sub:.1f}s of {wall:.1f}s in subprocess "
            "- use the resolved interpreter"
        )
    if share >= 0.5:
        return (
            f"subprocess-heavy: {sub:.1f}s of {wall:.1f}s in subprocess - fewer spawns"
        )
    return (
        f"in-process work: {wall - sub:.1f}s of {wall:.1f}s outside subprocess "
        "- share seeded setup / fewer audits"
    )


def format_run_result(label, elapsed, rc, summary_tail, err_text):
    """Report one suite run: a timing on success, FAILED plus the stderr tail
    otherwise. A failed run (pytest exit 4 is a usage error, e.g. a missing
    plugin) is never presented as a timing."""
    if rc != 0:
        print(f"== {label}: FAILED exit {rc} (not a timing) ==")
        for line in (err_text or "").strip().splitlines()[-5:]:
            if line.strip():
                print(f"   {line.strip()}")
        return False
    print(f"== {label}: {elapsed:.1f}s, exit 0; {summary_tail} ==")
    return True


def full(suite, withs, slow_n, workers, want_serial, want_xdist):
    base = uv_base(withs)
    print(f"== suite: {suite} ==")
    print("== process costs (seconds, best of 3) ==")
    for name, val in process_costs().items():
        print(f"{val:7.3f}  {name}" if isinstance(val, float) else f"  {name}: {val}")
    # Base already carries one -q: appending another would collapse the listing
    # into per-file counts (-qq) with no node ids to map.
    t, r = sh(base + ["--collect-only"], cwd=suite)
    count, table = parse_collect_output(r.stdout)
    print(
        f"\n== collection: {t:.2f}s (incl. uv env resolve), "
        f"{count if count is not None else '?'} tests collected, exit {r.returncode} =="
    )
    xml = {
        "serial": Path(tempfile.mkdtemp(prefix="bench-")) / "serial.xml",
        "xdist": Path(tempfile.mkdtemp(prefix="bench-")) / "xdist.xml",
    }
    have = {}
    if want_serial:
        t, r = sh(base + [f"--junitxml={xml['serial']}"], cwd=suite, timeout=1800)
        tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
        if format_run_result("serial run", t, r.returncode, tail, r.stderr):
            have["serial"] = (t, xml["serial"])
    if want_xdist:
        t, r = sh(
            base + ["-n", workers, f"--junitxml={xml['xdist']}"],
            cwd=suite,
            timeout=1800,
        )
        tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
        if format_run_result(f"xdist -n {workers}", t, r.returncode, tail, r.stderr):
            have[f"xdist -n {workers}"] = (t, xml["xdist"])
    if not have:
        print("no suite run produced output; nothing to rank")
        return 1
    if "serial" in have:
        print(
            f"serial {have['serial'][0]:.1f}s"
            + "".join(f", {k} {v[0]:.1f}s" for k, v in have.items() if k != "serial")
        )
    src = have["serial"][1] if "serial" in have else next(iter(have.values()))[1]
    per_file, tests, total = parse_junit(str(src))
    ranked_files = sorted(per_file.items(), key=lambda kv: -kv[1][1])
    ranked_tests = sorted(tests, reverse=True)
    print(
        f"\nsum of test times {total:.1f}s (wall minus this = collection, env, teardown)"
    )
    print("\n== per file: seconds, tests, s/test, share ==")
    for f, (n, s) in ranked_files:
        print(
            f"{s:7.1f}  {n:4d}  {s / n:6.2f}  {100 * s / total:5.1f}%  {f}"
            if total
            else f"  {f}"
        )
    print("\n== slowest tests (JUnit time) ==")
    for d, f, n, _fa in ranked_tests[:12]:
        print(f"{d:7.2f}  {f}::{n}")
    spy_data = []
    if slow_n > 0:
        print(f"\n== subprocess counts for {slow_n} slowest tests ==")
        for d, f, n, fa in ranked_tests[:slow_n]:
            nid = resolve_nodeid(table, fa, f, n, suite)
            if nid is None:
                print(f"  no nodeid for {f}::{n}, skipped")
                continue
            try:
                _, r = sh(
                    [
                        "uv",
                        "run",
                        "--no-project",
                        "--with",
                        "pytest",
                        str(BENCH),
                        "--spy",
                        nid,
                    ],
                    cwd=suite,
                    timeout=SPY_TIMEOUT,
                )
            except Exception as e:
                print(f"  spy failed for {nid}: {e}")
                continue
            line = next((l for l in r.stdout.splitlines() if l.startswith("SPY ")), "")
            tops = [l for l in r.stdout.splitlines() if l.startswith("SPYTOP ")]
            print(f"  {line or 'no SPY output for ' + nid}")
            for tl in tops[:4]:
                print(f"    {tl}")
            parts = (
                dict(kv.split("=", 1) for kv in line.split()[2:] if "=" in kv)
                if line
                else {}
            )
            try:
                wall = float(parts.get("wall", d))
                sub = float(parts.get("sub", 0.0))
                gcalls = int(parts.get("git_calls", 0))
            except ValueError:
                wall, sub, gcalls = d, 0.0, 0
            uv_spawns = sum(
                int(tl.split()[2].rstrip("x"))
                for tl in tops
                if " uv " in tl or " uv run" in tl
            )
            spy_data.append((d, f, n, wall, sub, gcalls, uv_spawns))
    if spy_data:
        print("\n== bottlenecks, ranked (dominant cause) ==")
        for i, (d, f, n, wall, sub, gcalls, uv_spawns) in enumerate(
            sorted(spy_data, key=lambda r: -r[0]), 1
        ):
            print(f"{i}. {d:6.2f}s {f}::{n}: {classify(wall, sub, gcalls, uv_spawns)}")
    for p in xml.values():
        try:
            p.unlink()
            p.parent.rmdir()
        except OSError:
            pass
    return 0


def add_options(ap):
    ap.add_argument(
        "suite",
        nargs="?",
        default=".",
        help="suite directory to benchmark (default: the current directory)",
    )
    ap.add_argument(
        "--slow",
        type=int,
        default=5,
        help="how many of the slowest tests get subprocess/git call counts (default: 5)",
    )
    ap.add_argument(
        "--workers",
        default="auto",
        help="xdist worker count for the parallel wall run, e.g. 8 (default: auto)",
    )
    ap.add_argument(
        "--with",
        dest="withs",
        action="append",
        default=[],
        help="extra uv --with package for the benchmarked env (repeatable)",
    )
    ap.add_argument(
        "--no-serial",
        action="store_true",
        help="skip the serial wall run (rankings then come from the xdist run)",
    )
    ap.add_argument("--no-xdist", action="store_true", help="skip the xdist wall run")
    ap.add_argument(
        "--spy",
        default=None,
        help="INTERNAL: run one test in-process with subprocess spies; "
        "used by bench itself for the --slow counts, not for direct use",
    )
    return ap


def main(argv=None):
    a = add_options(
        argparse.ArgumentParser(description="Benchmark a pytest suite.")
    ).parse_args(argv)
    if a.spy:
        return spy_one(a.spy)
    return full(
        Path(a.suite).resolve(),
        a.withs,
        a.slow,
        a.workers,
        not a.no_serial,
        not a.no_xdist,
    )


if __name__ == "__main__":
    sys.exit(main())
