#!/usr/bin/env node
// Hardcoded timing harness for the planning skill (performance-optimization loop:
// MEASURE -> IDENTIFY -> FIX -> VERIFY -> GUARD; fast-tests spawn cost model).
// Zero dependencies. Same method before/after: warmup, fixed reps, median decides.
// Neutral (within noise) = revert. Budgets below are the GUARD step: exit 1 on breach.
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { addRow, emptyLedger, GATES, planSkeleton, sha256, validateLedger } from "./planning.mjs";

const REPS = 20,
  WARMUP = 3;
const BUDGETS = {
  // median ms; measured baseline on this box is printed alongside
  "build chain-2000": 25,
  "validate chain-2000": 25,
  "validate wide-5000": 25,
  "G5 complete-500": 10,
  "render scan-2000": 10,
};

function median(xs) {
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}
function bench(name, fn) {
  for (let i = 0; i < WARMUP; i++) fn();
  const times = [];
  for (let i = 0; i < REPS; i++) {
    const t = performance.now();
    fn();
    times.push(performance.now() - t);
  }
  const med = median(times),
    min = Math.min(...times),
    spread = Math.max(...times) - min;
  const budget = BUDGETS[name];
  const verdict = med <= budget ? "keep" : "OVER BUDGET";
  console.log(
    `${name.padEnd(24)} median ${med.toFixed(1).padStart(7)} ms  min ${min.toFixed(1).padStart(7)} ms  spread ${
      spread.toFixed(1)
    } ms  budget ${budget} ms  ${verdict}`,
  );
  return med <= budget;
}

function chainLedger(n) {
  const l = emptyLedger({ slug: "bench", branch: "plan/bench" });
  addRow(l, { type: "fact", kind: "quote", label: "f0", locator: "x:0", axis: "A1" });
  for (let i = 1; i < n; i++) {
    addRow(l, { type: "fact", kind: "derived", label: `f${i}`, locator: `x:${i}`, operands: [`F${i}`] });
  }
  return l;
}
function wideLedger(n) {
  const l = emptyLedger({ slug: "bench", branch: "plan/bench" });
  for (let i = 0; i < n; i++) addRow(l, { type: "fact", kind: "quote", label: `w${i}`, locator: `x:${i}` });
  return l;
}
function completeLedger() {
  const l = chainLedger(500);
  l.axes.push({ id: "A1", label: "bench" });
  l.waves.push({ n: 1, new_facts: 0 }, { n: 2, new_facts: 0 });
  Object.assign(l.intent, {
    outcome: "o",
    user: "u",
    why_now: "w",
    success: "s",
    constraint: "c",
    out_of_scope: "x",
    confirmed: true,
  });
  l.approvals.push({ gate: "G3", token: "approve-design", at: "2026-01-01T00:00:00.000Z" });
  addRow(l, {
    type: "task",
    label: "t",
    files: ["a.js"],
    interfaces: "x",
    acceptance: "y",
    verify: "node --test",
    test_seam: "api",
    steps: "red: failing test; green: minimal pass",
  });
  // plan_sha256 must match for G5; set by the caller with the module's sha256.
  return { l, plan: planSkeleton(l) };
}

let ok = true;
{
  const { l, plan } = completeLedger();
  l.plan_sha256 = sha256(plan);
  // Build once, measure the named operation only (same method before/after).
  const chain = chainLedger(2000),
    wide = wideLedger(5000);
  ok = bench("build chain-2000", () => chainLedger(2000)) && ok;
  ok = bench("validate chain-2000", () => validateLedger(chain)) && ok;
  ok = bench("validate wide-5000", () => validateLedger(wide)) && ok;
  ok = bench("G5 complete-500", () => GATES.G5(l, plan)) && ok;
  ok = bench("render scan-2000", () => planSkeleton(chain)) && ok;
}

// Spawn cost (fast-tests cost model): one CLI call = one process spawn.
// On Windows a spawn is 0.1-0.25 s; this is why SKILL.md says batch writes per wave.
{
  const dir = mkdtempSync(join(tmpdir(), "planning-bench-"));
  const here = dirname(fileURLToPath(import.meta.url));
  const cli = join(here, "planning.mjs");
  try {
    spawnSync("node", [cli, "init", "--slug", "bench"], { cwd: dir, stdio: "ignore" });
    for (let i = 0; i < 2; i++) spawnSync("node", [cli, "validate", "--slug", "bench"], { cwd: dir, stdio: "ignore" }); // warmup
    const times = [];
    for (let i = 0; i < 10; i++) {
      const t = performance.now();
      spawnSync("node", [cli, "validate", "--slug", "bench"], { cwd: dir, stdio: "ignore" });
      times.push(performance.now() - t);
    }
    // Budget is relative to the raw node-startup floor on this box right now:
    // an empty `node -e 0` spawn can cost 60-300 ms depending on machine load,
    // and validate cannot beat the floor it is built on.
    const rawTimes = [];
    for (let i = 0; i < 5; i++) {
      const t = performance.now();
      spawnSync("node", ["-e", "0"], { stdio: "ignore" });
      rawTimes.push(performance.now() - t);
    }
    const rawMed = median(rawTimes);
    const budget = Math.max(250, Math.ceil(rawMed * 2));
    const med = median(times), spawnOk = med <= budget;
    if (!spawnOk) ok = false;
    console.log(
      `${"CLI spawn (validate)".padEnd(24)} median ${med.toFixed(1).padStart(7)} ms  raw-node floor ${
        rawMed.toFixed(1)
      } ms  budget ${budget} ms  ${spawnOk ? "keep" : "OVER BUDGET"}  (1 spawn per CLI call; use batch)`,
    );
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}
console.log(
  ok ? "PASS bench budgets" : "FAIL bench budgets (revert the change that caused it, or re-measure on an idle box)",
);
process.exit(ok ? 0 : 1);
