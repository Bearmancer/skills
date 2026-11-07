import assert from "node:assert/strict";
import { test } from "node:test";
import {
  addCapability,
  assimilateLedger,
  purgeSuperseded,
  repoErrors,
  addRow,
  changeStatus,
  cpmSchedule,
  dagDefinition,
  designFrontier,
  emptyLedger,
  evidenceErrors,
  frontier,
  GATES,
  ISSUE_TYPES,
  planDir,
  planSkeleton,
  approvalQuoteError,
  autonomyMode,
  Q0_CATEGORIES,
  q0Errors,
  renderIssues,
  scopeSize,
  SKIPPABLE,
  sha256,
  taskWarnings,
  todoPhases,
  validateLedger,
} from "./planning.mjs";

const base = () => emptyLedger({ slug: "demo", branch: "plan/demo", size: "S" });
// Size L adds user-stories and a task-graph approval; this helper meets both so a test can target one other rule.
const largeOk = (l) => {
  l.size = "L";
  addRow(l, { type: "decision", label: "user-stories", answer: "As a user, I can run the demo" });
  l.approvals.push({ gate: "G4", token: "approve-task-graph", by: "user", quote: "ok", at: "2026-01-01T00:00:00Z" });
  return l;
};

test("defaults: test-first on (flipped; --no-test-first turns it off), interview on, branch is plan/<slug>", () => {
  const l = base();
  assert.equal(l.flags.test_first, true);
  assert.equal(l.flags.no_interview, false);
  addRow(l, { type: "decision", label: "destination", answer: "ship the demo" });
  assert.deepEqual(GATES.G0(l), []);
  const unclear = base();
  assert.match(GATES.G0(unclear).join("\n"), /destination/);
  const off = emptyLedger({ slug: "demo", branch: "plan/demo", test_first: false , size: "S" });
  assert.equal(off.flags.test_first, false);
});

test("G_AX: P1 axes gate needs an axis, unique ids, and known fact axes", () => {
  const l = base();
  l.phase = "P1";
  assert.match(GATES.G_AX(l).join("\n"), /axes\[\] is empty/);
  l.axes.push({ id: "A1", label: "flow" });
  assert.deepEqual(GATES.G_AX(l), []);
  addRow(l, { type: "fact", kind: "quote", label: "doc", locator: "x:1", axis: "A9" });
  assert.match(GATES.G_AX(l).join("\n"), /unknown axis A9/);
  l.axes.push({ id: "A1", label: "duplicate" });
  assert.match(GATES.G_AX(l).join("\n"), /duplicate axis id A1/);
});

test("G1 fails until axis covered and 2 empty waves", () => {
  const l = base();
  l.axes.push({ id: "A1", label: "flow" });
  assert.ok(GATES.G1(l).length > 0);
  addRow(l, { type: "fact", kind: "quote", label: "doc", locator: "x:1", axis: "A1" });
  l.waves.push({ n: 1, new_facts: 0 }, { n: 2, new_facts: 0 });
  assert.deepEqual(GATES.G1(l), []);
});

test("ledger is append-only: supersede needs replacement + reason, terminal after", () => {
  const l = base();
  const f = addRow(l, { type: "fact", kind: "quote", label: "a", locator: "x:1" });
  const g = addRow(l, { type: "fact", kind: "quote", label: "b", locator: "x:2" });
  assert.throws(() => changeStatus(l, f.id, "superseded", { reason: "r" }), /replacement/);
  changeStatus(l, f.id, "superseded", { replacement: g.id, reason: "newer source" });
  assert.throws(() => changeStatus(l, f.id, "retracted", { reason: "r" }), /illegal transition/);
  assert.equal(l.events.length, 1, "one status change records one event");
  assert.deepEqual(validateLedger(l), []);
});

test("duplicate labels and cycles are validator errors, not vibes", () => {
  const l = base();
  addRow(l, { type: "fact", kind: "derived", label: "dup", locator: "x:1", operands: ["F2"] });
  addRow(l, { type: "fact", kind: "derived", label: "dup", locator: "x:2", operands: ["F1"] });
  const errs = validateLedger(l).join("\n");
  assert.match(errs, /label 'dup' reused/);
  assert.match(errs, /cycle/);
});

test("G4: structured test-first contract required by default; forbidden with --no-test-first", () => {
  const off = emptyLedger({ slug: "demo", branch: "plan/demo", test_first: false , size: "S" });
  addRow(off, goodTask());
  assert.match(GATES.G4(off, planSkeleton(off)).join("\n"), /--no-test-first was passed/);
  const on = base(); // default ledger: test-first on
  addRow(on, { type: "task", label: "t", files: ["a.js"], interfaces: "x", acceptance: "y", verify: "node --test" });
  assert.match(GATES.G4(on, planSkeleton(on)).join("\n"), /no test_seam/);
  const badSeam = base();
  addRow(badSeam, goodTask({ test_seam: "api" }));
  assert.match(GATES.G4(badSeam, planSkeleton(badSeam)).join("\n"), /test_seam must read/);
  const same = base();
  addRow(same, goodTask({ green: "red: failing test fails for the expected reason" }));
  assert.match(GATES.G4(same, planSkeleton(same)).join("\n"), /identical/);
  const cleanOff = emptyLedger({ slug: "demo", branch: "plan/demo", test_first: false , size: "S" });
  addRow(cleanOff, goodTask({ test_seam: null, test_file: null, red: null, green: null }));
  assert.deepEqual(GATES.G4(cleanOff, planSkeleton(cleanOff)), []);
  const cleanOn = base();
  addRow(cleanOn, goodTask());
  assert.deepEqual(GATES.G4(cleanOn, planSkeleton(cleanOn)), []);
});

test("G2 requires explicit confirmed intent, silence is not yes", () => {
  const l = base();
  Object.assign(l.intent, { outcome: "o", user: "u", why_now: "w", success: "s", constraint: "c", out_of_scope: "x" });
  assert.match(GATES.G2(l).join("\n"), /not confirmed/);
  l.intent.confirmed = true;
  assert.deepEqual(GATES.G2(l), []);
});

test("G2/G3 --no-interview: assumed intent needs backing, no fake yes", () => {
  const l = emptyLedger({ slug: "demo", branch: "plan/demo", noInterview: true , size: "S" });
  Object.assign(l.intent, { outcome: "o", user: "u", why_now: "w", success: "s", constraint: "c", out_of_scope: "x" });
  assert.match(GATES.G2(l).join("\n"), /intent\.assumed must be true/);
  l.intent.assumed = true;
  assert.match(GATES.G2(l).join("\n"), /assumed fact/);
  addRow(l, { type: "fact", kind: "assumed", label: "assump", locator: "request:1" });
  addRow(l, { type: "decision", label: "design-x", answer: "chosen" });
  assert.deepEqual(GATES.G2(l), []);
  l.intent.confirmed = true;
  assert.match(GATES.G2(l).join("\n"), /confirmed must stay false/);
  l.intent.confirmed = false;
  withReview(l);
  assert.deepEqual(GATES.G3(l), []);
});

test("capability map: stable ids, deps exist, acyclic, gated when >1", () => {
  const l = base();
  l.capabilities.push(
    { id: "identity", responsibility: "accounts", depends_on: [] },
    { id: "billing", responsibility: "invoices", depends_on: ["identity"] },
  );
  assert.deepEqual(validateLedger(l), []);
  assert.match(GATES.G3(l).join("\n"), /approve-capability-map/);
  l.approvals.push({ gate: "G3", token: "approve-capability-map", by: "user", quote: "approved", at: "2026-01-01T00:00:00Z" });
  l.approvals.push({ gate: "G3", token: "approve-design", by: "user", quote: "approved", at: "2026-01-01T00:00:00Z" });
  withReview(l);
  assert.deepEqual(GATES.G3(l), []);
  const bad = base();
  bad.capabilities.push(
    { id: "a", responsibility: "x", depends_on: ["b"] },
    { id: "b", responsibility: "y", depends_on: ["a"] },
  );
  assert.match(validateLedger(bad).join("\n"), /capability cycle/);
});

test("perf: long derived chain validates (single DFS, not quadratic)", () => {
  const l = base();
  addRow(l, { type: "fact", kind: "quote", label: "f0", locator: "x:0" });
  for (let i = 1; i < 2000; i++) {
    addRow(l, { type: "fact", kind: "derived", label: `f${i}`, locator: `x:${i}`, operands: [`F${i}`] });
  }
  const t0 = performance.now();
  assert.deepEqual(validateLedger(l), []);
  assert.ok(performance.now() - t0 < 50, "validateLedger on 2000-row chain must stay under the 50ms bench budget");
});

test("sha256 matches a known vector", () => {
  assert.equal(sha256(""), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  assert.equal(sha256("plan").length, 64);
});

test("CLI: init flags are sticky, answer is guarded, out-of-scope maps", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, rmSync, readFileSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const cli = new URL("./planning.mjs", import.meta.url).pathname.replace(/^\//, "");
  const dir = mkdtempSync(join(tmpdir(), "planning-cli-"));
  const run = (...a) => spawnSync("node", [cli, ...a], { cwd: dir, encoding: "utf8" });
  try {
    assert.equal(run("init", "--slug", "demo", "--no-branch").status, 0);
    assert.equal(
      run("init", "--slug", "demo", "--no-branch", "--test-first").status,
      0,
      "re-init with --test-first matches the default (on)",
    );
    assert.notEqual(
      run("init", "--slug", "demo", "--no-branch", "--no-test-first").status,
      0,
      "re-init with --no-test-first flips the stored flag and must fail",
    );
    assert.equal(run("question", "--slug", "demo", "--label", "q1", "--question", "which?").status, 0);
    assert.equal(run("answer", "--slug", "demo", "--id", "Q1", "--answer", "this").status, 0);
    assert.notEqual(
      run("answer", "--slug", "demo", "--id", "Q1", "--answer", "again").status,
      0,
      "answered question cannot be re-answered",
    );
    assert.equal(run("intent", "--slug", "demo", "--out-of-scope", "nothing-else").status, 0);
    const ledger = JSON.parse(readFileSync(join(dir, ".rigor", "plans", "feature", "demo", "ledger.json"), "utf8"));
    assert.equal(ledger.intent.out_of_scope, "nothing-else");
    assert.notEqual(run("intent", "--slug", "demo", "--confirm").status, 0, "confirm without --by user must fail");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

// ---- rigorous-planning additions: .rigor/plans layout, issues, task kinds, new sections ----
const goodTask = (over = {}) => ({
  type: "task",
  label: "t",
  files: ["a.js"],
  interfaces: "x",
  acceptance: "y",
  verify: "node --test",
  test_seam: "api | catches: behaviour | misses: internals | class: in-process",
  test_file: "a.test.js",
  red: "red: failing test fails for the expected reason",
  green: "green: minimal pass",
  ...over,
});

test("planDir: .rigor/plans/<issue-type>/<slug>; issue types are a closed set", () => {
  assert.deepEqual(planDir("bug", "demo").split(/[\\/]/), [".rigor", "plans", "bug", "demo"]);
  for (const t of ["feature", "bug", "refactor", "audit", "evidence", "chore", "docs"]) {
    assert.ok(ISSUE_TYPES.includes(t), t);
  }
  const l = emptyLedger({ slug: "demo", branch: "plan/demo" , size: "S" });
  assert.equal(l.issue_type, "feature");
  assert.equal(l.schemaVersion, 2);
  l.issue_type = "nonsense";
  assert.match(validateLedger(l).join("\n"), /issue_type/);
});

test("issues: refs are owner/repo#n; a task may only link a declared issue", () => {
  const l = base();
  l.issues = [{ ref: "Bearmancer/Toolbox#289" }];
  assert.deepEqual(validateLedger(l), []);
  l.issues.push({ ref: "not-a-ref" });
  assert.match(validateLedger(l).join("\n"), /issue ref/);
  l.issues.pop();
  addRow(l, goodTask({ issue: "Bearmancer/Toolbox#999" }));
  assert.match(validateLedger(l).join("\n"), /not declared/);
  const ok = base();
  ok.issues = [{ ref: "Bearmancer/Toolbox#289" }];
  addRow(ok, goodTask({ issue: "Bearmancer/Toolbox#289" }));
  assert.deepEqual(validateLedger(ok), []);
  assert.match(planSkeleton(ok), /^## Issues$/m);
  assert.match(planSkeleton(ok), /Bearmancer\/Toolbox#289/);
});

test("G4 requires '## Issues' heading when issues exist, plus the new review and handoff sections", () => {
  const l = base();
  l.issues = [{ ref: "Bearmancer/Toolbox#289" }];
  addRow(l, goodTask());
  const full = planSkeleton(l);
  assert.deepEqual(GATES.G4(l, full), []);
  assert.match(GATES.G4(l, full.replace("## Issues", "## Nope")).join("\n"), /Issues/);
  assert.match(
    GATES.G4(l, full.replace("## Verification and review plan", "## X")).join("\n"),
    /Verification and review plan/,
  );
  assert.match(GATES.G4(l, full.replace("## Handoff", "## X")).join("\n"), /Handoff/);
});

test("task kinds: fix needs a repro step (Prove-It), refactor must state preserved behaviour", () => {
  const fix = base();
  addRow(fix, goodTask({ kind: "fix", red: "red: failing test" }));
  assert.match(GATES.G4(fix, planSkeleton(fix)).join("\n"), /repro/);
  const fixOk = base();
  addRow(fixOk, goodTask({ kind: "fix", red: "red: repro test fails; green: fix passes" }));
  assert.deepEqual(GATES.G4(fixOk, planSkeleton(fixOk)), []);
  const ref = base();
  addRow(ref, goodTask({ kind: "refactor" }));
  assert.match(GATES.G4(ref, planSkeleton(ref)).join("\n"), /behaviou?r/);
  const refOk = base();
  addRow(refOk, goodTask({ kind: "refactor", acceptance: "behaviour unchanged, characterization tests green" }));
  assert.deepEqual(GATES.G4(refOk, planSkeleton(refOk)), []);
  const bad = base();
  addRow(bad, goodTask({ kind: "wizardry" }));
  assert.match(validateLedger(bad).join("\n"), /kind/);
});

test("fake completion in a task is a G4 error (skip/only/TODO/not implemented)", () => {
  for (const bad of ["test.skip the flaky case", "it.only(x)", "TODO wire later", "branch not implemented yet"]) {
    const l = base();
    addRow(l, goodTask({ acceptance: bad }));
    assert.match(GATES.G4(l, planSkeleton(l)).join("\n"), /fake completion/, bad);
  }
});

test("taskWarnings: >5 files or >3 acceptance bullets is advisory, never an error", () => {
  const l = base();
  addRow(l, { type: "decision", label: "quality-bar", answer: "tests green" });
  addRow(l, goodTask({ files: ["1", "2", "3", "4", "5", "6"], acceptance: "a;b;c;d" }));
  const w = taskWarnings(l);
  assert.equal(w.length, 2);
  assert.deepEqual(GATES.G4(l, planSkeleton(l)), []);
});

test("frontier: tasks whose deps are all done and that are not done themselves", () => {
  const l = base();
  addRow(l, goodTask({ label: "a" }));
  addRow(l, goodTask({ label: "b", deps: ["T1"] }));
  addRow(l, goodTask({ label: "c", deps: ["T1"] }));
  addRow(l, goodTask({ label: "d", deps: ["T2", "T3"] }));
  assert.deepEqual(frontier(l, []), ["T1"]);
  assert.deepEqual(frontier(l, ["T1"]), ["T2", "T3"]);
  assert.deepEqual(frontier(l, ["T1", "T2", "T3"]), ["T4"]);
});

test("renderIssues: one ticket file per task with blocked-by, acceptance, verify, labels", () => {
  const l = base();
  l.issues = [{ ref: "Bearmancer/Toolbox#289" }];
  addRow(l, goodTask({ label: "first", issue: "Bearmancer/Toolbox#289" }));
  addRow(l, goodTask({ label: "second", deps: ["T1"] }));
  const out = renderIssues(l);
  assert.deepEqual(out.map((o) => o.file), ["01-first.md", "02-second.md"]);
  assert.match(out[0].body, /Bearmancer\/Toolbox#289/);
  assert.match(out[1].body, /Blocked by: .*01-first/);
  assert.match(out[1].body, /Acceptance/);
  assert.match(out[1].body, /Verify/);
  assert.match(out[1].body, /needs-triage/);
});

test("CLI: .rigor/plans layout, --type, issues, render-issues, frontier, ambiguous slug", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, rmSync, readFileSync, writeFileSync, existsSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const cli = new URL("./planning.mjs", import.meta.url).pathname.replace(/^\//, "");
  const dir = mkdtempSync(join(tmpdir(), "planning-cli2-"));
  const run = (...a) => spawnSync("node", [cli, ...a], { cwd: dir, encoding: "utf8" });
  const taskArgs = (label, extra = []) => [
    "task", "--slug", "demo", "--label", label, "--files", "a.js", "--interfaces", "i", "--acceptance", "a",
    "--verify", "node --test", "--test-seam", "api | catches: behaviour | misses: internals | class: in-process",
    "--test-file", "a.test.js", "--red", "red: repro test fails", "--green", "green: minimal pass", ...extra,
  ];
  const setPhase = (phase) => {
    const p = join(dir, ".rigor", "plans", "bug", "demo", "ledger.json");
    const x = JSON.parse(readFileSync(p, "utf8"));
    x.phase = phase;
    writeFileSync(p, JSON.stringify(x, null, 2) + "\n");
  };
  try {
    assert.equal(
      run("init", "--slug", "demo", "--type", "bug", "--no-branch", "--issue", "Bearmancer/Toolbox#289").status,
      0,
    );
    assert.ok(existsSync(join(dir, ".rigor", "plans", "bug", "demo", "ledger.json")));
    assert.ok(existsSync(join(dir, ".rigor", "plans", "bug", "demo", "plan.md")));
    assert.ok(!existsSync(join(dir, ".planning")), "legacy .planning dir must never be created");
    setPhase("P4");
    assert.notEqual(run("init", "--slug", "x", "--type", "nonsense", "--no-branch").status, 0);
    assert.equal(run("issue", "--slug", "demo", "--ref", "Bearmancer/Toolbox#286").status, 0);
    assert.notEqual(run("issue", "--slug", "demo", "--ref", "junk").status, 0);
    assert.equal(run(...taskArgs("first", ["--issue", "Bearmancer/Toolbox#289"])).status, 0);
    assert.equal(run(...taskArgs("second", ["--deps", "T1", "--closes", "ideal-1"])).status, 0);
    const led = JSON.parse(readFileSync(join(dir, ".rigor", "plans", "bug", "demo", "ledger.json"), "utf8"));
    assert.deepEqual(led.rows.find((r) => r.id === "T2").closes, ["ideal-1"]);
    assert.equal(run("frontier", "--slug", "demo").stdout.trim(), "T1");
    assert.equal(run("frontier", "--slug", "demo", "--done", "T1").stdout.trim(), "T2");
    assert.equal(run("render-issues", "--slug", "demo").status, 0);
    const t = readFileSync(join(dir, ".rigor", "plans", "bug", "demo", "issues", "02-second.md"), "utf8");
    assert.match(t, /Blocked by: .*01-first/);
    assert.equal(
      run("init", "--slug", "demo", "--type", "feature", "--no-branch").status,
      0,
      "same slug under another type is allowed",
    );
    const amb = run("validate", "--slug", "demo");
    assert.notEqual(amb.status, 0, "slug in two types needs --type");
    assert.match(amb.stderr, /--type/);
    assert.equal(run("validate", "--slug", "demo", "--type", "bug").status, 0);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

// ---- maximal-rigor additions: feature flags, size classes, doubt, constraints, ADR, type coupling, size budget ----
const mkTasks = (l, n, over = {}) => {
  for (let i = 1; i <= n; i++) addRow(l, goodTask({ label: `t${i}`, files: [`f${i}.js`], ...over }));
  return l;
};
const withBar = (l) => {
  addRow(l, { type: "decision", label: "quality-bar", answer: "tests green, no skips, lint clean" });
  return l;
};

test("features: closed skip set, every feature on by default", () => {
  const l = emptyLedger({ slug: "demo", branch: "plan/demo" , size: "S" });
  assert.deepEqual(l.flags.skip, []);
  assert.deepEqual(SKIPPABLE.slice().sort(), ["adr", "constraints", "doubt", "handoff", "plan-review", "review-section", "task-approval"]);
  const off = emptyLedger({ slug: "demo", branch: "plan/demo", skip: ["doubt"] , size: "S" });
  assert.deepEqual(validateLedger(off), []);
  off.flags.skip = ["nonsense"];
  assert.match(validateLedger(off).join("\n"), /skip/);
});

test("scopeSize: S <=2 tasks <=3 files one capability no irreversible decision; L >8 tasks or >2 capabilities", () => {
  const s = mkTasks(base(), 2);
  assert.equal(scopeSize(s), "S");
  assert.equal(scopeSize(mkTasks(base(), 3)), "L");
  assert.equal(scopeSize(mkTasks(base(), 9)), "L");
  const irr = mkTasks(base(), 1);
  addRow(irr, { type: "decision", label: "drop-table", answer: "x", irreversible: true });
  assert.equal(scopeSize(irr), "L");
  const wide = base();
  addRow(wide, goodTask({ files: ["a", "b", "c", "d"] }));
  assert.equal(scopeSize(wide), "L");
});

test("G5 audits an understated size claim", () => {
  const mk = (size) => {
    const l = emptyLedger({ slug: "demo", branch: "plan/demo", size });
    l.axes.push({ id: "A1", label: "flow" });
    addRow(l, { type: "fact", kind: "quote", label: "doc", locator: "x:1", axis: "A1" });
    l.waves.push({ n: 1, new_facts: 1 }, { n: 2, new_facts: 0 });
    return l;
  };
  const under = mkTasks(mk("S"), 4);
  assert.match(GATES.G5(under, planSkeleton(under)).join("\n"), /size.*understated|understated.*size/i);
});

test("doubt: irreversible decision needs persisted findings, max 3 cycles then escalation", () => {
  const l = base();
  addRow(l, { type: "decision", label: "drop-table", answer: "x", irreversible: true });
  assert.match(GATES.G3(withApprovals(l)).join("\n"), /no doubt record/);
  l.doubts = [{ decision: "D1", cycle: 1, claim: "c", clean: false, scope: ["artifact"] }];
  assert.match(GATES.G3(withReview(withApprovals(l))).join("\n"), /no finding rows/);
  l.doubts[0].clean = true;
  l.doubts[0].scope = [];
  assert.match(GATES.G3(withReview(withApprovals(l))).join("\n"), /no scope locators/);
  l.doubts[0].clean = false;
  l.doubts[0].scope = ["artifact"];
  addRow(l, { type: "finding", label: "doubt-noise", review: "doubt:D1:1", class: "noise", note: "none" });
  assert.deepEqual(GATES.G3(withDeliberate(withReview(withApprovals(l)))), []);
  l.doubts.push({ decision: "D1", cycle: 4, claim: "c", clean: true, scope: ["artifact"] });
  assert.match(GATES.G3(withDeliberate(withReview(withApprovals(l)))).join("\n"), /cycle/);
  const skipped = emptyLedger({ slug: "demo", branch: "plan/demo", skip: ["doubt"] , size: "S" });
  addRow(skipped, { type: "decision", label: "drop-table", answer: "x", irreversible: true });
  assert.deepEqual(GATES.G3(withDeliberate(withReview(withApprovals(skipped)))), []);
});

test("deliberate: L, irreversible, or --deliberate requires the deliberation record rows", () => {
  const l = emptyLedger({ slug: "demo", branch: "plan/demo", size: "L" });
  withApprovals(l);
  withReview(l);
  assert.match(GATES.G3(l).join("\n"), /principles/);
  withDeliberate(l);
  assert.deepEqual(GATES.G3(l), []);

  const bad = emptyLedger({ slug: "demo", branch: "plan/demo", size: "L" });
  withApprovals(bad);
  withReview(bad);
  addRow(bad, { type: "decision", label: "principles", answer: "a; b" });
  addRow(bad, { type: "decision", label: "drivers", answer: "a; b; c" });
  addRow(bad, { type: "decision", label: "option-a", answer: "a" });
  addRow(bad, { type: "decision", label: "option-b", answer: "b" });
  addRow(bad, { type: "decision", label: "pre-mortem", answer: "a; b; c" });
  addRow(bad, { type: "decision", label: "expanded-test-plan", answer: "unit integration e2e observability" });
  assert.match(GATES.G3(bad).join("\n"), /principles/);

  const forced = emptyLedger({ slug: "demo", branch: "plan/demo", size: "S", deliberate: true });
  withApprovals(forced);
  withReview(forced);
  assert.match(GATES.G3(forced).join("\n"), /principles/);

  const plain = emptyLedger({ slug: "demo", branch: "plan/demo", size: "S" });
  withApprovals(plain);
  withReview(plain);
  assert.deepEqual(GATES.G3(plain), []);
});

function withDeliberate(l) {
  addRow(l, { type: "decision", label: "principles", answer: "fast; reversible; observable" });
  addRow(l, { type: "decision", label: "drivers", answer: "risk; cost; speed" });
  addRow(l, { type: "decision", label: "option-a", answer: "do the small change" });
  addRow(l, { type: "decision", label: "option-b", answer: "do the larger change" });
  addRow(l, { type: "decision", label: "pre-mortem", answer: "data loss; auth bypass; rollout stall" });
  addRow(l, { type: "decision", label: "expanded-test-plan", answer: "unit, integration, e2e, observability" });
  return l;
}

function withReview(l) {
  l.plan_reviews = [{ cycle: 1, clean: false, scope: ["spec"] }];
  addRow(l, { type: "finding", label: "review-noise", review: "plan-review:1", class: "noise", note: "none" });
  return l;
}

function withApprovals(l) {
  l.approvals = [{ gate: "G3", token: "approve-design", by: "user", quote: "approved", at: "2026-01-01T00:00:00Z" }];
  return l;
}

test("constraints: M/L plans need a quality-bar decision; S and --no-constraints are exempt", () => {
  const m = largeOk(mkTasks(base(), 3));
  assert.match(GATES.G4(m, planSkeleton(m)).join("\n"), /quality-bar/);
  const ok = withBar(largeOk(mkTasks(base(), 3)));
  assert.deepEqual(GATES.G4(ok, planSkeleton(ok)), []);
  const exempt = largeOk(mkTasks(emptyLedger({ slug: "demo", branch: "plan/demo", skip: ["constraints"], size: "S" }), 3));
  assert.deepEqual(GATES.G4(exempt, planSkeleton(exempt)), []);
  const s = mkTasks(base(), 1);
  assert.deepEqual(GATES.G4(s, planSkeleton(s)), []);
});

test("ADR decisions need a detected adr-convention fact (unless --no-adr)", () => {
  const l = withBar(mkTasks(base(), 3));
  addRow(l, { type: "decision", label: "pick-db", answer: "pg", adr: true, adr_file: "docs/adr/0007-pick-db.md" });
  assert.match(GATES.G4(l, planSkeleton(l)).join("\n"), /adr-convention/);
  addRow(l, { type: "fact", kind: "quote", label: "adr-convention", locator: "docs/adr/0001-x.md:1" });
  assert.deepEqual(GATES.G4(l, planSkeleton(l)).filter((e) => !/Evidence|cites/.test(e)), []);
});

test("issue type couples to task kinds: bug needs a fix task, refactor needs a refactor task", () => {
  const bug = emptyLedger({ slug: "demo", issueType: "bug", branch: "plan/demo" });
  addRow(bug, goodTask());
  assert.match(GATES.G4(bug, planSkeleton(bug)).join("\n"), /bug.*fix/);
  const ref = emptyLedger({ slug: "demo", issueType: "refactor", branch: "plan/demo" });
  addRow(ref, goodTask());
  assert.match(GATES.G4(ref, planSkeleton(ref)).join("\n"), /refactor.*refactor/);
});

test("size budget: est_lines >1000 must split, >500 must be scripted, lockfile edits are chore + changelog", () => {
  const big = base();
  addRow(big, goodTask({ est_lines: 1200 }));
  assert.match(GATES.G4(big, planSkeleton(big)).join("\n"), /split/);
  const mid = base();
  addRow(mid, goodTask({ est_lines: 600, steps: "red: test; green: pass" }));
  assert.match(GATES.G4(mid, planSkeleton(mid)).join("\n"), /codemod|scripted/);
  const midOk = base();
  addRow(midOk, goodTask({ est_lines: 600, steps: "red: test; green: pass via codemod transform" }));
  assert.deepEqual(GATES.G4(midOk, planSkeleton(midOk)), []);
  const lock = base();
  addRow(lock, goodTask({ files: ["package.json", "package-lock.json"] }));
  assert.match(GATES.G4(lock, planSkeleton(lock)).join("\n"), /lockfile/);
  const lockOk = base();
  addRow(lockOk, goodTask({ kind: "chore", files: ["package.json", "package-lock.json"], acceptance: "changelog read, lockfile diff reviewed" }));
  assert.deepEqual(GATES.G4(lockOk, planSkeleton(lockOk)), []);
  const warn = base();
  addRow(warn, goodTask({ est_lines: 400 }));
  assert.equal(taskWarnings(warn).length, 1);
});

test("CLI: --no-<feature> flags, size, doubt, irreversible decisions", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, rmSync, readFileSync, writeFileSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const cli = new URL("./planning.mjs", import.meta.url).pathname.replace(/^\//, "");
  const dir = mkdtempSync(join(tmpdir(), "planning-cli3-"));
  const run = (...a) => spawnSync("node", [cli, ...a], { cwd: dir, encoding: "utf8" });
  try {
    assert.equal(run("init", "--slug", "demo", "--no-branch", "--no-doubt", "--no-handoff", "--size", "S").status, 0);
    const p = join(dir, ".rigor", "plans", "feature", "demo");
    const l = JSON.parse(readFileSync(join(p, "ledger.json"), "utf8"));
    assert.deepEqual(l.flags.skip.sort(), ["doubt", "handoff"]);
    assert.equal(l.size, "S");
    assert.ok(!/^## Handoff$/m.test(readFileSync(join(p, "plan.md"), "utf8")), "skipped handoff is not rendered");
    const raw = JSON.parse(readFileSync(join(p, "ledger.json"), "utf8"));
    raw.phase = "P3";
    writeFileSync(join(p, "ledger.json"), JSON.stringify(raw, null, 2) + "\n");
    assert.equal(run("decision", "--slug", "demo", "--label", "drop-table", "--decision", "x", "--irreversible").status, 0);
    assert.equal(run("size", "--slug", "demo", "--class", "L").status, 0);
    assert.notEqual(run("size", "--slug", "demo", "--class", "M").status, 0, "M is no longer a size");
    assert.notEqual(run("size", "--slug", "demo", "--class", "XL").status, 0);
    const f = run("doubt", "--slug", "demo", "--id", "D1", "--claim", "c", "--cycle", "1");
    assert.equal(f.status, 0, f.stderr);
    assert.equal(run("finding", "--slug", "demo", "--review", "doubt:D1:1", "--class", "noise", "--note", "none").status, 0);
    const l2 = JSON.parse(readFileSync(join(p, "ledger.json"), "utf8"));
    assert.equal(l2.doubts[0].clean, false);
    assert.equal(l2.rows.filter((x) => x.type === "finding").length, 1);
    assert.equal(run("init", "--slug", "delib", "--no-branch", "--deliberate").status, 0);
    const dl = JSON.parse(readFileSync(join(dir, ".rigor", "plans", "feature", "delib", "ledger.json"), "utf8"));
    assert.equal(dl.flags.deliberate, true);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

// ---- performance/ceremony additions: --lean umbrella, batch carries every row type, skill structure guard ----
test("CLI: --lean switches off every skippable feature at once and is sticky", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, rmSync, readFileSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const cli = new URL("./planning.mjs", import.meta.url).pathname.replace(/^\//, "");
  const dir = mkdtempSync(join(tmpdir(), "planning-cli4-"));
  const run = (...a) => spawnSync("node", [cli, ...a], { cwd: dir, encoding: "utf8" });
  try {
    assert.equal(run("init", "--slug", "demo", "--no-branch", "--lean").status, 0);
    const l = JSON.parse(readFileSync(join(dir, ".rigor", "plans", "feature", "demo", "ledger.json"), "utf8"));
    assert.deepEqual(l.flags.skip.slice().sort(), SKIPPABLE.slice().sort());
    assert.equal(l.flags.test_first, true, "--lean never touches test_first/interview/branch");
    assert.equal(l.flags.no_interview, false);
    assert.equal(run("init", "--slug", "demo", "--no-branch").status !== 0, true, "dropping --lean on re-init flips the stored flags");
    assert.equal(run("init", "--slug", "demo", "--no-branch", "--lean").status, 0);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("CLI: one batch call records issue, size, intent, decision, doubt and tasks (one spawn, not six)", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, rmSync, readFileSync, writeFileSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const cli = new URL("./planning.mjs", import.meta.url).pathname.replace(/^\//, "");
  const dir = mkdtempSync(join(tmpdir(), "planning-cli5-"));
  const run = (...a) => spawnSync("node", [cli, ...a], { cwd: dir, encoding: "utf8" });
  try {
    assert.equal(run("init", "--slug", "demo", "--no-branch").status, 0);
    const p = join(dir, ".rigor", "plans", "feature", "demo", "ledger.json");
    const init = JSON.parse(readFileSync(p, "utf8"));
    init.phase = "P4";
    writeFileSync(p, JSON.stringify(init, null, 2) + "\n");
    const rows = [
      { type: "issue", ref: "Bearmancer/Toolbox#289", title: "undo" },
      { type: "size", class: "S" },
      { type: "intent", outcome: "o", user: "u", why_now: "w", success: "s", constraint: "c", out_of_scope: "x" },
      { type: "decision", label: "drop-table", decision: "x", irreversible: true },
      { type: "doubt", id: "D1", claim: "c", cycle: 1 },
      { type: "finding", review: "doubt:D1:1", class: "noise", note: "none" },
      { type: "task", label: "t1", files: ["a.js"], interfaces: "i", acceptance: "a", verify: "node --test",
        test_seam: "api | catches: behaviour | misses: internals | class: in-process", test_file: "a.test.js",
        red: "red: repro test fails", green: "green: minimal pass", issue: "Bearmancer/Toolbox#289" },
    ];
    writeFileSync(join(dir, "rows.json"), JSON.stringify(rows));
    const r = run("batch", "--slug", "demo", "--file", "rows.json");
    assert.equal(r.status, 0, r.stderr);
    const l = JSON.parse(readFileSync(p, "utf8"));
    assert.equal(l.issues[0].ref, "Bearmancer/Toolbox#289");
    assert.equal(l.size, "S");
    assert.equal(l.intent.outcome, "o");
    assert.equal(l.doubts[0].clean, false);
    assert.equal(l.rows.filter((x) => x.type === "finding").length, 1);
    assert.equal(l.rows.find((x) => x.id === "T1").issue, "Bearmancer/Toolbox#289");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("skill structure guard: pointers resolve and the description and size budgets hold", async () => {
  const { readFileSync, existsSync, readdirSync, statSync } = await import("node:fs");
  const { join } = await import("node:path");
  const root = new URL("..", import.meta.url).pathname.replace(/^\//, "");
  const skill = readFileSync(new URL("../SKILL.md", import.meta.url), "utf8");
  const fm = /^---\r?\n([\s\S]*?)\r?\n---/.exec(skill)[1];
  const desc = JSON.parse(/^description: (".*")$/m.exec(fm)[1]);
  assert.ok(desc.length <= 300, `description ${desc.length} chars; keep it brief`);
  assert.ok(Buffer.byteLength(skill) < 18000, "always-loaded contract budget: 18 KB");
  const pointers = [...skill.matchAll(/`((?:phases|methods)\/[^`]+\.md)`/g)].map((m) => m[1]);
  assert.ok(pointers.length >= 12, `expected phase/method pointers, found ${pointers.length}`);
  for (const p of new Set(pointers)) {
    assert.ok(existsSync(join(root, p)), `pointer target missing: ${p}`);
  }
  let content = Buffer.byteLength(skill);
  for (const dir of ["phases", "methods"]) {
    for (const f of readdirSync(join(root, dir))) {
      if (f.endsWith(".md")) content += statSync(join(root, dir, f)).size;
    }
  }
  assert.ok(content < 120000, `playbook total budget: 120 KB (got ${content})`);
});

// ---- review fixes: evidence bypass, traversal, dangling flags, status filter, G1 waves, word-bounded test-first, topo order ----
test("review: dangling and unknown flags are errors, --issue repeats accumulate, files are trimmed", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, rmSync, readFileSync, writeFileSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const { fileURLToPath } = await import("node:url");
  const cli = fileURLToPath(new URL("./planning.mjs", import.meta.url));
  const dir = mkdtempSync(join(tmpdir(), "planning-cli6-"));
  const run = (...a) => spawnSync("node", [cli, ...a], { cwd: dir, encoding: "utf8" });
  try {
    assert.equal(
      run("init", "--slug", "demo", "--no-branch", "--issue", "o/r#1", "--issue", "o/r#2").status,
      0,
    );
    const lp = join(dir, ".rigor", "plans", "feature", "demo", "ledger.json");
    const l = JSON.parse(readFileSync(lp, "utf8"));
    assert.deepEqual(l.issues.map((i) => i.ref), ["o/r#1", "o/r#2"]);
    l.phase = "P4";
    writeFileSync(lp, JSON.stringify(l, null, 2) + "\n");
    const bad = run("task", "--slug", "demo", "--label", "t", "--files", "a.js", "--interfaces", "i", "--acceptance", "a", "--verify", "--kind", "chore");
    assert.notEqual(bad.status, 0);
    assert.match(bad.stderr, /--verify requires a value/);
    const typo = run("init", "--slug", "other", "--no-branch", "--no-interviw");
    assert.notEqual(typo.status, 0);
    assert.match(typo.stderr, /unknown flag/);
    const trav = run("question", "--slug", "demo", "--label", "x/../../../../evil", "--question", "q");
    assert.notEqual(trav.status, 0);
    assert.match(trav.stderr, /label/);
    assert.equal(
      run("task", "--slug", "demo", "--label", "t1", "--files", "a.js, b.js", "--interfaces", "i", "--acceptance", "a",
        "--verify", "v", "--test-seam", "api | catches: behaviour | misses: internals | class: in-process",
        "--test-file", "a.test.js", "--red", "red: repro test fails", "--green", "green: minimal pass").status,
      0,
    );
    const l2 = JSON.parse(readFileSync(join(dir, ".rigor", "plans", "feature", "demo", "ledger.json"), "utf8"));
    assert.deepEqual(l2.rows.find((x) => x.id === "T1").files, ["a.js", "b.js"]);
    const sup = run("supersede", "--slug", "demo", "--id", "T1", "--reason", "r");
    assert.notEqual(sup.status, 0);
    assert.match(sup.stderr, /^ERROR /m, "errors are ERROR lines, never stack traces");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("review: superseded rows never render; quality-bar must be the exact label; capability order is topological", () => {
  const l = base();
  addRow(l, goodTask({ label: "keep" }));
  addRow(l, goodTask({ label: "old" }));
  changeStatus(l, "T2", "superseded", { replacement: "T1", reason: "dup" });
  assert.doesNotMatch(planSkeleton(l), /T2\./);
  const tool = mkTasks(base(), 3);
  addRow(tool, { type: "decision", label: "toolbar", answer: "x" });
  assert.match(GATES.G4(tool, planSkeleton(tool)).join("\n"), /quality-bar/);
  const caps = base();
  caps.capabilities.push(
    { id: "billing", responsibility: "b", depends_on: ["identity"] },
    { id: "identity", responsibility: "i", depends_on: [] },
  );
  assert.match(planSkeleton(caps), /Build order: identity -> billing/);
});

test("review: G1 rejects facts recorded after the last wave and zero-wave saturation; test-first requires a red step", () => {
  const l = base();
  l.axes.push({ id: "A1", label: "flow" });
  l.waves.push({ n: 1, new_facts: 0 }, { n: 2, new_facts: 0 }, { n: 3, new_facts: 0 });
  addRow(l, { type: "fact", kind: "quote", label: "late", locator: "x:1", axis: "A1", wave: 4 });
  assert.match(GATES.G1(l).join("\n"), /after the last wave/);
  const t = base();
  addRow(t, goodTask({ red: null }));
  assert.match(GATES.G4(t, planSkeleton(t)).join("\n"), /no red step/);
  const lock = base();
  addRow(lock, goodTask({ files: ["package.json", "package-lock.json:10-20"] }));
  assert.match(GATES.G4(lock, planSkeleton(lock)).join("\n"), /lockfile/);
});

test("review: evidence resolves bare filenames, ranges and URL facts without --external", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, rmSync, writeFileSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const { fileURLToPath } = await import("node:url");
  const cli = fileURLToPath(new URL("./planning.mjs", import.meta.url));
  const dir = mkdtempSync(join(tmpdir(), "planning-cli7-"));
  const run = (...a) => spawnSync("node", [cli, ...a], { cwd: dir, encoding: "utf8" });
  const g1 = () => {
    const r = run("gate", "--slug", "demo", "--id", "G1");
    return r.stderr + r.stdout;
  };
  try {
    assert.equal(run("init", "--slug", "demo", "--no-branch").status, 0);
    writeFileSync(join(dir, "README.md"), "one\ntwo\n");
    run("axis", "--slug", "demo", "--label", "a");
    run("fact", "--slug", "demo", "--label", "f1", "--locator", "README.md:99", "--axis", "A1");
    run("wave", "--slug", "demo");
    run("wave", "--slug", "demo");
    run("wave", "--slug", "demo");
    assert.match(g1(), /README\.md/, "bare filename past end of file must fail");
    run("supersede", "--slug", "demo", "--id", "F1", "--reason", "fix", "--replacement", "F2");
    run("fact", "--slug", "demo", "--label", "f2", "--locator", "src/nope.js:1-20", "--axis", "A1");
    assert.match(g1(), /nope\.js/, "range locator into a missing file must fail");
    const url = run("fact", "--slug", "demo", "--label", "f3", "--locator", "https://example.com/x", "--axis", "A1");
    assert.equal(url.status, 0);
    assert.match(g1(), /external/, "URL fact without --external must fail");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("review: publish refuses a hand-edited plan.md; self-reported doubt totals are rejected", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, rmSync, readFileSync, writeFileSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const { fileURLToPath } = await import("node:url");
  const cli = fileURLToPath(new URL("./planning.mjs", import.meta.url));
  const dir = mkdtempSync(join(tmpdir(), "planning-cli8-"));
  const run = (...a) => spawnSync("node", [cli, ...a], { cwd: dir, encoding: "utf8" });
  const lp = join(dir, ".rigor", "plans", "feature", "demo", "ledger.json");
  const setPhase = (phase) => {
    const x = JSON.parse(readFileSync(lp, "utf8"));
    x.phase = phase;
    writeFileSync(lp, JSON.stringify(x, null, 2) + "\n");
  };
  try {
    assert.equal(run("init", "--slug", "demo", "--no-branch").status, 0);
    setPhase("P5");
    const p = join(dir, ".rigor", "plans", "feature", "demo", "plan.md");
    writeFileSync(p, readFileSync(p, "utf8") + "\nhand edit\n");
    const r = run("publish", "--slug", "demo");
    assert.notEqual(r.status, 0);
    assert.match(r.stderr, /differs from the last render/);
    setPhase("P3");
    run("decision", "--slug", "demo", "--label", "drop", "--decision", "x", "--irreversible");
    const bad = run("doubt", "--slug", "demo", "--id", "D1", "--claim", "c", "--cycle", "1", "--findings", "noise:2", "--total", "3");
    assert.notEqual(bad.status, 0);
    assert.match(bad.stderr, /no longer accepts/);
    assert.equal(run("doubt", "--slug", "demo", "--id", "D1", "--claim", "c", "--cycle", "1").status, 0);
    assert.equal(run("finding", "--slug", "demo", "--review", "doubt:D1:1", "--class", "noise", "--note", "none").status, 0);
    const g = run("gate", "--slug", "demo", "--id", "G3");
    assert.match(g.stderr, /approve-design/);
    assert.doesNotMatch(g.stderr, /classified/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("review: project commands, boundaries and risks reach plan.md via labelled decisions; a risk needs a mitigation", () => {
  const l = base();
  addRow(l, { type: "decision", label: "commands", answer: "test: node --test" });
  addRow(l, { type: "decision", label: "boundaries", answer: "Never: edit vendor/" });
  addRow(l, { type: "decision", label: "risk-1", answer: "stale cache | H | version the key" });
  const p = planSkeleton(l);
  assert.match(p, /### Commands\n\ntest: node --test/);
  assert.match(p, /### Boundaries\n\nNever: edit vendor\//);
  assert.match(p, /## Risks\n\n- risk-1: stale cache \| H \| version the key/);
  addRow(l, goodTask());
  assert.deepEqual(GATES.G4(l, planSkeleton(l)), []);
  addRow(l, { type: "decision", label: "risk-2", answer: "no mitigation here" });
  assert.match(GATES.G4(l, planSkeleton(l)).join("\n"), /risk-2.*mitigation/);
});

// ---- owner decisions: default-on plan-review gate, size-S waivers, executor rules rendered into plan.md ----
test("plan-review: G3 needs persisted findings unless --no-plan-review; cycles cap at 3", () => {
  const l = withApprovals(base());
  assert.match(GATES.G3(l).join("\n"), /plan-review/);
  l.plan_reviews = [{ cycle: 1, clean: false, scope: ["spec"] }];
  assert.match(GATES.G3(l).join("\n"), /no finding rows/);
  addRow(l, { type: "finding", label: "review-1", review: "plan-review:1", class: "valid_actionable", locator: "a.js:1" });
  assert.deepEqual(GATES.G3(l), []);
  l.plan_reviews = [{ cycle: 4, clean: false, scope: ["spec"] }];
  addRow(l, { type: "finding", label: "review-4", review: "plan-review:4", class: "noise", note: "none" });
  assert.match(GATES.G3(l).join("\n"), /cycle/);
  const off = withApprovals(emptyLedger({ slug: "demo", branch: "plan/demo", skip: ["plan-review"] , size: "S" }));
  assert.deepEqual(GATES.G3(off), []);
});

test("review-section skip: the section is not rendered and G4 accepts its absence", () => {
  const hid = emptyLedger({ slug: "demo", branch: "plan/demo", skip: ["review-section"] , size: "S" });
  addRow(hid, goodTask());
  assert.doesNotMatch(planSkeleton(hid), /## Verification and review plan/);
  assert.deepEqual(GATES.G4(hid, planSkeleton(hid)), []);
});

test("size S: one closed evidence wave is enough (any count), M/L still need two empty waves", () => {
  const mk = (size, waves) => {
    const l = emptyLedger({ slug: "demo", branch: "plan/demo", size });
    l.axes.push({ id: "A1", label: "flow" });
    addRow(l, { type: "fact", kind: "quote", label: "doc", locator: "x:1", axis: "A1" });
    l.waves.push(...waves);
    return l;
  };
  assert.deepEqual(GATES.G1(mk("S", [{ n: 1, new_facts: 3 }])), []);
  assert.match(GATES.G1(mk("S", [])).join("\n"), /saturation/);
  assert.match(GATES.G1(mk("M", [{ n: 1, new_facts: 3 }])).join("\n"), /saturation/);
});

test("CLI: size S implies no branch in a git repo; plan-review command records a review; --no-plan-review sticks", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, rmSync, readFileSync, writeFileSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const { fileURLToPath } = await import("node:url");
  const cli = fileURLToPath(new URL("./planning.mjs", import.meta.url));
  const dir = mkdtempSync(join(tmpdir(), "planning-cli9-"));
  const run = (...a) => spawnSync("node", [cli, ...a], { cwd: dir, encoding: "utf8" });
  try {
    spawnSync("git", ["init", "-q"], { cwd: dir });
    assert.equal(run("init", "--slug", "demo", "--size", "S", "--no-sweep").status, 0);
    const p = join(dir, ".rigor", "plans", "feature", "demo");
    const l = JSON.parse(readFileSync(join(p, "ledger.json"), "utf8"));
    assert.equal(l.branch, null);
    assert.equal(l.branch_reason, "size-s");
    const br = spawnSync("git", ["branch", "--list", "plan/demo"], { cwd: dir, encoding: "utf8" }).stdout.trim();
    assert.equal(br, "", "no plan branch is created at size S");
    assert.equal(run("decision", "--slug", "demo", "--label", "destination", "--decision", "ship the demo").status, 0);
    assert.equal(run("gate", "--slug", "demo", "--id", "G0").status, 0);
    const raw = JSON.parse(readFileSync(join(p, "ledger.json"), "utf8"));
    raw.phase = "P3";
    writeFileSync(join(p, "ledger.json"), JSON.stringify(raw, null, 2) + "\n");
    const r = run("plan-review", "--slug", "demo", "--cycle", "1", "--clean", "--scope", "plan.md");
    assert.equal(r.status, 0, r.stderr);
    const l2 = JSON.parse(readFileSync(join(p, "ledger.json"), "utf8"));
    assert.equal(l2.plan_reviews[0].clean, true);
    assert.equal(run("init", "--slug", "x2", "--no-branch", "--no-plan-review").status, 0);
    const l3 = JSON.parse(readFileSync(join(dir, ".rigor", "plans", "feature", "x2", "ledger.json"), "utf8"));
    assert.ok(l3.flags.skip.includes("plan-review"));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

// ---- hard-gate additions: map branch, phase machine, rounds, test runs, glossary, user stories, deps ----
test("map: unknowns branch, map, G_MAP, handoff", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, rmSync, readFileSync, existsSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const cli = new URL("./planning.mjs", import.meta.url).pathname.replace(/^\//, "");
  const dir = mkdtempSync(join(tmpdir(), "planning-wf-"));
  const run = (...a) => spawnSync("node", [cli, ...a], { cwd: dir, encoding: "utf8" });
  try {
    assert.equal(run("init", "--slug", "mapdemo", "--map").status, 0);
    const mapPath = join(dir, ".rigor", "maps", "mapdemo", "map.md");
    assert.ok(existsSync(mapPath), "map creates a map, not a plan");
    const l = JSON.parse(readFileSync(join(dir, ".rigor", "maps", "mapdemo", "ledger.json"), "utf8"));
    assert.equal(l.phase, "W0");
    assert.equal(l.map.map, true);
    assert.notEqual(
      run("task", "--slug", "mapdemo", "--label", "t", "--files", "a.js", "--interfaces", "i", "--acceptance", "a", "--verify", "v").status,
      0,
      "no task rows in the unknowns branch",
    );
    assert.equal(run("decision", "--slug", "mapdemo", "--label", "destination", "--decision", "A tested auth spec").status, 0);
    assert.equal(run("question", "--slug", "mapdemo", "--label", "which-idp", "--question", "Which IdP?", "--map", "--kind", "evidence").status, 0);
    assert.equal(run("answer", "--slug", "mapdemo", "--id", "Q1", "--answer", "OIDC").status, 0);
    assert.notEqual(run("gate", "--slug", "mapdemo", "--id", "G_MAP").status, 0, "unknowns are still recorded");
    assert.equal(run("unknowns", "--slug", "mapdemo", "--clear").status, 0);
    const unsigned = run("gate", "--slug", "mapdemo", "--id", "G_MAP");
    assert.notEqual(unsigned.status, 0, "the captain must sign the destination");
    assert.match(unsigned.stderr, /map-destination/);
    assert.equal(
      run("approve", "--slug", "mapdemo", "--gate", "G_MAP", "--token", "map-destination", "--by", "user", "--quote", "A tested auth spec").status,
      0,
      "approve is allowed at W0 for G_MAP",
    );
    assert.equal(run("gate", "--slug", "mapdemo", "--id", "G_MAP").status, 0);
    assert.equal(run("map-handoff", "--slug", "mapdemo", "--type", "feature").status, 0);
    assert.ok(existsSync(join(dir, ".rigor", "plans", "feature", "mapdemo", "ledger.json")), "handoff seeds a planning ledger at P0");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("next: prints the next gate and keeps going until publish", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const cli = new URL("./planning.mjs", import.meta.url).pathname.replace(/^\//, "");
  const dir = mkdtempSync(join(tmpdir(), "planning-next-"));
  const run = (...a) => spawnSync("node", [cli, ...a], { cwd: dir, encoding: "utf8" });
  try {
    assert.equal(run("init", "--slug", "demo", "--no-branch", "--size", "S", "--no-sweep").status, 0);
    let n = run("next", "--slug", "demo");
    assert.equal(n.status, 0);
    assert.match(n.stdout, /gate --id G0/);
    assert.match(n.stdout, /Do not stop until DONE published/);
    assert.equal(run("decision", "--slug", "demo", "--label", "destination", "--decision", "ship").status, 0);
    assert.equal(run("gate", "--slug", "demo", "--id", "G0").status, 0);
    n = run("next", "--slug", "demo");
    assert.match(n.stdout, /gate --id G_AX/);
    assert.equal(run("axis", "--slug", "demo", "--label", "flow").status, 0);
    n = run("next", "--slug", "demo");
    assert.match(n.stdout, /gate --id G1/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("phase machine: G0 advances to P1 and tasks cannot be minted before G3", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, rmSync, readFileSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const cli = new URL("./planning.mjs", import.meta.url).pathname.replace(/^\//, "");
  const dir = mkdtempSync(join(tmpdir(), "planning-phase-"));
  const run = (...a) => spawnSync("node", [cli, ...a], { cwd: dir, encoding: "utf8" });
  try {
    assert.equal(run("init", "--slug", "demo", "--no-branch", "--size", "S", "--no-sweep").status, 0);
    assert.equal(run("decision", "--slug", "demo", "--label", "destination", "--decision", "ship the demo").status, 0);
    assert.equal(run("gate", "--slug", "demo", "--id", "G0").status, 0);
    const l = JSON.parse(readFileSync(join(dir, ".rigor", "plans", "feature", "demo", "ledger.json"), "utf8"));
    assert.equal(l.phase, "P1");
    const t = run("task", "--slug", "demo", "--label", "t", "--files", "a.js", "--interfaces", "i", "--acceptance", "a", "--verify", "v");
    assert.notEqual(t.status, 0);
    assert.match(t.stderr, /before G3/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("rounds: a dependent question waits; a new round cannot open over an unresolved round", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const cli = new URL("./planning.mjs", import.meta.url).pathname.replace(/^\//, "");
  const dir = mkdtempSync(join(tmpdir(), "planning-rounds-"));
  const run = (...a) => spawnSync("node", [cli, ...a], { cwd: dir, encoding: "utf8" });
  try {
    assert.equal(run("init", "--slug", "demo", "--no-branch").status, 0);
    assert.equal(run("question", "--slug", "demo", "--label", "q1", "--question", "First?").status, 0);
    assert.equal(run("question", "--slug", "demo", "--label", "q2", "--question", "Second?", "--blocked-by", "Q1").status, 0);
    assert.equal(run("round", "--slug", "demo", "--asks", "Q1").status, 0);
    assert.notEqual(run("round", "--slug", "demo", "--asks", "Q2").status, 0, "round 1 is still open");
    assert.equal(run("answer", "--slug", "demo", "--id", "Q1", "--answer", "yes").status, 0);
    assert.equal(run("round", "--slug", "demo", "--asks", "Q2").status, 0);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("test_run rows validate against their task", () => {
  const l = base();
  addRow(l, goodTask());
  addRow(l, { type: "test_run", label: "red", task: "T1", phase: "red", cmd: "node --test", exit: 1, artifact: "sources/T1-red.log" });
  addRow(l, { type: "test_run", label: "green", task: "T1", phase: "green", cmd: "node --test", exit: 0, artifact: "sources/T1-green.log" });
  assert.deepEqual(validateLedger(l), []);
  const bad = base();
  addRow(bad, goodTask());
  addRow(bad, { type: "test_run", label: "bad", task: "T9", phase: "red", cmd: "node --test", exit: 1, artifact: "x" });
  assert.match(validateLedger(bad).join("\n"), /not a task/);
});

test("domain term: a closed term needs a glossary fact; user stories are required at size L; deps render", () => {
  const l = base();
  addRow(l, { type: "question", label: "order-definition", quote: "What is an order?", status: "answered", answer: "a purchase", domain_term: "order" });
  addRow(l, goodTask());
  addRow(l, { type: "decision", label: "quality-bar", answer: "tests green" });
  const p = planSkeleton(l);
  assert.match(GATES.G4(l, p).join("\n"), /term-order/);
  addRow(l, { type: "fact", kind: "quote", label: "term-order", locator: "GLOSSARY.md:3", quote: "**Order**: a purchase. _Avoid_: transaction" });
  assert.doesNotMatch(GATES.G4(l, planSkeleton(l)).join("\n"), /term-order/);

  const big = emptyLedger({ slug: "demo", branch: "plan/demo", size: "L" });
  addRow(big, goodTask());
  addRow(big, { type: "decision", label: "quality-bar", answer: "tests green" });
  assert.match(GATES.G4(big, planSkeleton(big)).join("\n"), /user-stories/);
  addRow(big, { type: "decision", label: "user-stories", answer: "As a user, I can log in" });
  assert.doesNotMatch(GATES.G4(big, planSkeleton(big)).join("\n"), /user-stories/);

  const deps = base();
  addRow(deps, goodTask({ label: "a" }));
  addRow(deps, goodTask({ label: "b", deps: ["T1"] }));
  const dp = planSkeleton(deps);
  assert.match(dp, /deps: T1/);
  assert.match(GATES.G4(deps, dp.replace("deps: T1", "deps: none")).join("\n"), /blocking edges/);
});

test("frontier rejects an unknown done id", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const cli = new URL("./planning.mjs", import.meta.url).pathname.replace(/^\//, "");
  const dir = mkdtempSync(join(tmpdir(), "planning-frontier-"));
  const run = (...a) => spawnSync("node", [cli, ...a], { cwd: dir, encoding: "utf8" });
  try {
    assert.equal(run("init", "--slug", "demo", "--no-branch").status, 0);
    const r = run("frontier", "--slug", "demo", "--done", "T9");
    assert.notEqual(r.status, 0);
    assert.match(r.stderr, /not a task/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("refactor survey: G1 needs survey-* facts and a top-recommendation", () => {
  const l = emptyLedger({ slug: "demo", branch: "plan/demo", issueType: "refactor", size: "S" });
  l.axes.push({ id: "A1", label: "surface" });
  addRow(l, { type: "fact", kind: "quote", label: "base", locator: "a.js:1", axis: "A1" });
  l.waves.push({ n: 1, new_facts: 1 });
  assert.match(GATES.G1(l).join("\n"), /survey-/);
  const survey = addRow(l, { type: "fact", kind: "quote", label: "survey-api", locator: "a.js:2", axis: "A1" });
  assert.match(GATES.G1(l).join("\n"), /top-recommendation/);
  addRow(l, { type: "decision", label: "top-recommendation", answer: `deepen ${survey.id}` });
  assert.deepEqual(GATES.G1(l), []);
});

test("G5: a claim that tests ran needs a test_run row", () => {
  const l = base();
  addRow(l, goodTask());
  assert.match(GATES.G5(l, "we ran the tests").join("\n"), /test_run/);
  addRow(l, {
    type: "test_run",
    label: "run-green",
    task: "T1",
    phase: "green",
    cmd: "node --test",
    exit: 0,
    artifact: "sources/T1-green.log",
  });
  assert.doesNotMatch(GATES.G5(l, "we ran the tests").join("\n"), /test_run/);
  assert.doesNotMatch(GATES.G5(l, "no claim here").join("\n"), /test_run/);
});

test("Handoff plan: TL;DR, waves, dependency matrix and ideal/gap closure", () => {
  const l = withBar(base());
  addRow(l, { type: "decision", label: "ideal-1", answer: "one command syncs every tracked file" });
  addRow(l, { type: "decision", label: "gap-1", answer: "IDEAL-1: today the paths differ per harness" });
  const t1 = goodTask({ label: "one", closes: ["gap-1"] });
  const t2 = goodTask({ label: "two", deps: ["T1"], closes: ["gap-1"] });
  addRow(l, t1);
  addRow(l, t2);
  const p = planSkeleton(l);
  assert.match(p, /## TL;DR \(For humans\)/);
  assert.match(p, /### Parallel waves/);
  assert.match(p, /- Wave 1: T1/);
  assert.match(p, /- Wave 2: T2/);
  assert.match(p, /\| T1 \| — \| T2 \|/);
  assert.match(p, /\| IDEAL-1 \|/);
  assert.match(p, /closes: gap-1/);
  assert.deepEqual(GATES.G4(l, p), []);
  assert.match(GATES.G4(l, p.replace("| T2 | T1 |", "| T2 | — |")).join("\n"), /does not match deps/);
  const missing = withBar(base());
  addRow(missing, { type: "decision", label: "ideal-1", answer: "x" });
  addRow(missing, { type: "decision", label: "gap-1", answer: "IDEAL-1: y" });
  addRow(missing, goodTask());
  assert.match(GATES.G4(missing, planSkeleton(missing)).join("\n"), /must name the IDEAL or GAP/);
  const direct = withBar(base());
  addRow(direct, { type: "decision", label: "ideal-1", answer: "one path" });
  addRow(direct, goodTask({ closes: ["ideal-1"] }));
  assert.deepEqual(GATES.G4(direct, planSkeleton(direct)), []);
});

// ---- review-cycle additions ----

test("review2: designFrontier returns ready questions", () => {
  const l = emptyLedger({ slug: "demo", branch: "plan/demo" , size: "S" });
  const q1 = addRow(l, { type: "question", label: "q1", quote: "?" });
  const q2 = addRow(l, { type: "question", label: "q2", quote: "?", blocked_by: [q1.id] });
  assert.deepEqual(designFrontier(l).map((q) => q.id), [q1.id]);
  changeStatus(l, q1.id, "answered", { reason: "done" });
  assert.deepEqual(designFrontier(l).map((q) => q.id), [q2.id]);
});

test("review2: addCapability validates and normalizes", () => {
  const l = emptyLedger({ slug: "demo", branch: "plan/demo" , size: "S" });
  const c = addCapability(l, { id: "core", responsibility: "x", deps: "a,b" });
  assert.deepEqual(c.depends_on, ["a", "b"]);
  assert.throws(() => addCapability(l, { id: "Bad", responsibility: "x", deps: [] }), /must match/);
  assert.throws(() => addCapability(l, { id: "core", responsibility: "x", deps: [] }), /already exists/);
});

test("review2: task-graph approval required for multi or size L", () => {
  const l = emptyLedger({ slug: "demo", branch: "plan/demo", size: "L" });
  addRow(l, goodTask());
  assert.match(GATES.G4(l, planSkeleton(l)).join("\n"), /approve-task-graph/);
  l.approvals.push({ gate: "G4", token: "approve-task-graph", by: "user", quote: "approved", at: "2026-01-01T00:00:00Z" });
  assert.doesNotMatch(GATES.G4(l, planSkeleton(l)).join("\n"), /approve-task-graph/);
});

test("review2: --test-runs flag requires test_run rows", () => {
  const l = emptyLedger({ slug: "demo", branch: "plan/demo", testRuns: true , size: "S" });
  addRow(l, goodTask());
  assert.match(GATES.G4(l, planSkeleton(l)).join("\n"), /test_run row with phase "red"/);
  addRow(l, { type: "test_run", label: "r", task: "T1", phase: "red", cmd: "node --test", exit: 1, artifact: "sources/T1-red.log" });
  addRow(l, { type: "test_run", label: "g", task: "T1", phase: "green", cmd: "node --test", exit: 0, artifact: "sources/T1-green.log" });
  assert.doesNotMatch(GATES.G4(l, planSkeleton(l)).join("\n"), /test_run row/);
});

test("Q0 sweep: G0 stays closed until every category is asked or scoped out and no q0 question is open", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, rmSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const cli = new URL("./planning.mjs", import.meta.url).pathname.replace(/^\//, "");
  const dir = mkdtempSync(join(tmpdir(), "planning-q0-"));
  const run = (...a) => spawnSync("node", [cli, ...a], { cwd: dir, encoding: "utf8" });
  try {
    assert.equal(run("init", "--slug", "demo", "--no-branch").status, 0);
    assert.equal(run("decision", "--slug", "demo", "--label", "destination", "--decision", "ship the demo").status, 0);
    const closed = run("gate", "--slug", "demo", "--id", "G0");
    assert.notEqual(closed.status, 0);
    assert.match(closed.stderr, /sweep: category 'outcome'/);
    assert.match(run("next", "--slug", "demo").stdout, /Q0 sweep open/);
    for (const c of Q0_CATEGORIES.filter((x) => x !== "outcome")) {
      assert.equal(run("decision", "--slug", "demo", "--label", "q0-" + c, "--decision", "scoped out: not applicable here").status, 0);
    }
    assert.equal(run("question", "--slug", "demo", "--label", "q0-outcome", "--question", "What ships?").status, 0);
    const open = run("gate", "--slug", "demo", "--id", "G0");
    assert.notEqual(open.status, 0);
    assert.match(open.stderr, /Q1 \(q0-outcome\) is still open/);
    assert.equal(run("answer", "--slug", "demo", "--id", "Q1", "--answer", "the demo").status, 0);
    const noDoubt = run("gate", "--slug", "demo", "--id", "G0");
    assert.notEqual(noDoubt.status, 0);
    assert.match(noDoubt.stderr, /the doubt loop has not run/);
    assert.match(run("next", "--slug", "demo").stdout, /--label q0-doubt-1/);
    assert.equal(run("question", "--slug", "demo", "--label", "q0-doubt-1", "--question", "Any doubt left?").status, 0);
    assert.equal(run("answer", "--slug", "demo", "--id", "Q2", "--answer", "Yes: what about rollback?").status, 0);
    assert.match(run("gate", "--slug", "demo", "--id", "G0").stderr, /the doubt loop is open: q0-doubt-1/);
    assert.equal(run("question", "--slug", "demo", "--label", "q0-doubt-2", "--question", "Any doubt left?").status, 0);
    assert.equal(run("answer", "--slug", "demo", "--id", "Q3", "--answer", "No remaining doubt").status, 0);
    const noAuto = run("gate", "--slug", "demo", "--id", "G0");
    assert.notEqual(noAuto.status, 0);
    assert.match(noAuto.stderr, /no active 'autonomy' decision/);
    assert.equal(run("decision", "--slug", "demo", "--label", "autonomy", "--decision", "checkpoints: stop at design and task graph").status, 0);
    assert.equal(run("gate", "--slug", "demo", "--id", "G0").status, 0);
    assert.match(run("next", "--slug", "demo").stdout, /gate --id G_AX/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("Q0 sweep is off for ledgers without the flag, and a retracted scope-out stops counting", () => {
  const l = base();
  assert.equal(q0Errors({ ...l, rows: [] }).length, Q0_CATEGORIES.length + 2, "ten categories, the doubt loop and the autonomy decision");
  addRow(l, { type: "decision", label: "destination", answer: "d" });
  assert.deepEqual(GATES.G0(l), []);
});

const cpmTask = (label, effort, deps = [], files = [label + ".js"], extra = {}) => ({
  type: "task", label, files, interfaces: "i", acceptance: "a", verify: "node --test", effort, deps, ...extra,
});

test("CPM: critical path, slack and project length come from deps and effort", () => {
  const l = base();
  addRow(l, cpmTask("a", 2));
  addRow(l, cpmTask("b", 3, ["T1"]));
  addRow(l, cpmTask("c", 1, ["T1"]));
  addRow(l, cpmTask("d", 2, ["T2", "T3"]));
  const tasks = l.rows.filter((r) => r.type === "task");
  const { rows, length, path } = cpmSchedule(tasks);
  assert.equal(length, 7);
  assert.deepEqual(path, ["T1", "T2", "T4"]);
  const c = rows.find((r) => r.id === "T3");
  assert.deepEqual([c.es, c.ef, c.ls, c.lf, c.slack, c.critical], [2, 3, 4, 5, 2, false]);
  const plan = planSkeleton(l);
  assert.match(plan, /### Critical path \(CPM\)/);
  assert.match(plan, /Critical path: T1 -> T2 -> T4/);
  assert.match(plan, /- T3: ES 2, EF 3, LS 4, LF 5, slack 2\n/);
  const bad = base();
  addRow(bad, cpmTask("a", 0, [], ["a.js"], { category: "nonsense" }));
  const errs = validateLedger(bad).join("\n");
  assert.match(errs, /effort must be a positive number/);
  assert.match(errs, /category must be one of/);
});

test("dag: deps carry over, same-file tasks are serialized, category and --done are honored", () => {
  const l = base();
  addRow(l, cpmTask("a", 1, [], ["x.js"]));
  addRow(l, cpmTask("b", 1, [], ["x.js", "y.js"]));
  addRow(l, cpmTask("c", 1, ["T1"], ["z.js"], { category: "deep-low" }));
  const { definition, serialized } = dagDefinition(l);
  const node = (id) => definition.nodes.find((n) => n.id === id);
  assert.deepEqual(node("T1").dependsOn, []);
  assert.deepEqual(node("T2").dependsOn, ["T1"]);
  assert.deepEqual(node("T3").dependsOn, ["T1"]);
  assert.deepEqual(serialized, [{ after: "T1", before: "T2", files: ["x.js"] }]);
  assert.equal(node("T3").category, "deep-low");
  assert.equal(node("T1").category, "unspecified-high");
  assert.match(node("T2").prompt, /^TASK: .*\nDELIVERABLE: .*\nSCOPE: edit only x\.js, y\.js/);
  const rest = dagDefinition(l, ["T1"]).definition;
  assert.deepEqual(rest.nodes.map((n) => n.id), ["T2", "T3"]);
  assert.deepEqual(rest.nodes.find((n) => n.id === "T3").dependsOn, []);
  assert.notEqual(rest.key, definition.key);
});

test("autonomy: run-through needs an answered q0-authorization; its answer must ride every approve quote", () => {
  const l = base();
  addRow(l, { type: "decision", label: "autonomy", answer: "run-through: plan to publish without asking again" });
  assert.equal(autonomyMode(l), "run-through");
  assert.match(q0Errors(l).join("\n"), /run-through needs an answered q0-authorization/);
  const q = addRow(l, { type: "question", label: "q0-authorization", quote: "Run through?" });
  changeStatus(l, q.id, "answered", { reason: "user answer recorded" });
  l.rows.find((r) => r.id === q.id).answer = "Run through, I pre-approve design and task graph";
  assert.ok(!q0Errors(l).join("\n").includes("run-through needs"));
  assert.match(approvalQuoteError(l, "go ahead"), /q0-authorization answer verbatim/);
  assert.equal(approvalQuoteError(l, "Run through, I pre-approve design and task graph (standing)"), null);
  const cp = base();
  addRow(cp, { type: "decision", label: "autonomy", answer: "checkpoints" });
  assert.equal(approvalQuoteError(cp, "anything the user said"), null, "checkpoints keeps free-form approvals");
});

test("G4 CPM, owner-confirm and todo-mirror gates are deterministic", () => {
  const mk = () => {
    const l = base();
    l.flags.cpm = true;
    addRow(l, goodTask({ effort: 2, category: "quick" }));
    addRow(l, goodTask({ label: "second", effort: 1, category: "quick", deps: ["T1"], files: ["b.js"] }));
    return l;
  };
  const ok = mk();
  assert.deepEqual(GATES.G4(ok, planSkeleton(ok)), []);
  const noEffort = mk();
  noEffort.rows[1].effort = null;
  assert.match(GATES.G4(noEffort, planSkeleton(noEffort)).join("\n"), /T2 has no --effort/);
  const stale = mk();
  assert.match(GATES.G4(stale, planSkeleton(stale).replace("Critical path: T1 -> T2", "Critical path: T2")).join("\n"), /critical path does not match/);
  assert.match(GATES.G4(stale, planSkeleton(stale).replace('- Todo phase "Wave 1":', "- gone:")).join("\n"), /Todo mirror is missing phase "Wave 1"/);
  const phases = todoPhases(ok);
  assert.deepEqual(phases.map((p) => p.phase), ["Wave 1", "Wave 2", "Final verification wave"]);
  assert.equal(phases[0].items[0], "T1: " + ok.rows[0].label);
  const irr = mk();
  addRow(irr, { type: "decision", label: "autonomy", answer: "checkpoints" });
  addRow(irr, { type: "decision", label: "drop-table", answer: "x", irreversible: true });
  assert.ok(!GATES.G4(irr, planSkeleton(irr)).join("\n").includes("owner-confirm"), "only run-through requires owner-confirm roots");
});

test("next: the plan review is the next required action at P3 and is never a question", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, rmSync, readFileSync, writeFileSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const cli = new URL("./planning.mjs", import.meta.url).pathname.replace(/^\//, "");
  const dir = mkdtempSync(join(tmpdir(), "planning-review-next-"));
  const run = (...a) => spawnSync("node", [cli, ...a], { cwd: dir, encoding: "utf8" });
  const setPhase = (slug, phase) => {
    const p = join(dir, ".rigor", "plans", "feature", slug, "ledger.json");
    const l = JSON.parse(readFileSync(p, "utf8"));
    l.phase = phase;
    writeFileSync(p, JSON.stringify(l, null, 2) + "\n");
  };
  try {
    assert.equal(run("init", "--slug", "demo", "--no-branch", "--no-sweep").status, 0);
    setPhase("demo", "P3");
    const n = run("next", "--slug", "demo");
    assert.match(n.stdout, /plan-review --cycle 1/);
    assert.match(n.stdout, /never ask whether to run it/);
    assert.equal(run("plan-review", "--slug", "demo", "--cycle", "1", "--clean", "--scope", "plan.md").status, 0);
    assert.match(run("next", "--slug", "demo").stdout, /gate --id G3/);
    assert.equal(run("init", "--slug", "declined", "--no-branch", "--no-sweep", "--no-plan-review").status, 0);
    setPhase("declined", "P3");
    assert.match(run("next", "--slug", "declined").stdout, /gate --id G3/, "--no-plan-review is the only opt-out");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("multi-repo: every task names a registered repo, the plan lists repos, and two repos make the plan L", () => {
  const l = base();
  l.repos.push({ id: "api", path: "svc/api", role: "backend" }, { id: "web", path: "svc/web", role: null });
  addRow(l, goodTask({ label: "a", files: ["a.js"], repo: "api" }));
  addRow(l, goodTask({ label: "b", files: ["b.js"], repo: "web" }));
  const plan = planSkeleton(l);
  assert.deepEqual(repoErrors(l, plan), []);
  assert.equal(scopeSize(l), "L");
  assert.match(GATES.G4(l, plan).join("\n"), /approve-task-graph/, "two repos need the task-graph approval");
  assert.match(plan, /\| api \| svc\/api \| backend \|/);
  assert.match(plan, /- \[ \] T1\..*; repo: api/);
  assert.match(repoErrors(l, plan.replace("## Repos", "## X")).join("\n"), /no '## Repos' heading/);
  const bare = base();
  bare.repos.push({ id: "api", path: "svc/api" });
  addRow(bare, goodTask());
  assert.match(repoErrors(bare, planSkeleton(bare)).join("\n"), /T1 has no --repo/);
  const ghost = base();
  addRow(ghost, goodTask({ repo: "nope" }));
  assert.match(validateLedger(ghost).join("\n"), /repo nope is not registered/);
  const dup = base();
  dup.repos.push({ id: "api", path: "a" }, { id: "api", path: "b" });
  assert.match(validateLedger(dup).join("\n"), /duplicate repo id api/);
});

test("dag: the same file in two repos is not a conflict; the same repo and file is serialized", () => {
  const l = base();
  l.repos.push({ id: "api", path: "svc/api" }, { id: "web", path: "svc/web" });
  addRow(l, goodTask({ label: "a", files: ["x.js"], repo: "api" }));
  addRow(l, goodTask({ label: "b", files: ["x.js"], repo: "web" }));
  addRow(l, goodTask({ label: "c", files: ["x.js"], repo: "api" }));
  const { definition, serialized } = dagDefinition(l);
  const dep = (id) => definition.nodes.find((n) => n.id === id).dependsOn;
  assert.deepEqual(dep("T2"), []);
  assert.deepEqual(dep("T3"), ["T1"]);
  assert.deepEqual(serialized, [{ after: "T1", before: "T3", files: ["api:x.js"] }]);
  assert.match(definition.nodes[0].prompt, /SCOPE: in repo api \(svc\/api\), edit only x\.js/);
});

test("evidence: a fact's file locator resolves against its repo path", async () => {
  const { mkdtempSync, rmSync, mkdirSync, writeFileSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const root = mkdtempSync(join(tmpdir(), "planning-repoev-"));
  try {
    mkdirSync(join(root, "repoA"));
    writeFileSync(join(root, "repoA", "src.js"), "1\n2\n3\n");
    const l = base();
    l.repos.push({ id: "a", path: "repoA" });
    addRow(l, { type: "fact", kind: "quote", label: "in-repo", locator: "src.js:2", repo: "a" });
    assert.deepEqual(evidenceErrors(l, root, root), []);
    addRow(l, { type: "fact", kind: "quote", label: "past-end", locator: "src.js:99", repo: "a" });
    assert.match(evidenceErrors(l, root, root).join("\n"), /past end of file/);
    const lost = base();
    addRow(lost, { type: "fact", kind: "quote", label: "no-repo", locator: "src.js:2" });
    assert.match(evidenceErrors(lost, root, root).join("\n"), /locator file not found/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("assimilate: decisions, code facts and tasks come over with prefixed labels; external facts are skipped and counted", () => {
  const src = emptyLedger({ slug: "billing", size: "S" });
  addRow(src, { type: "decision", label: "destination", answer: "ship billing" });
  addRow(src, { type: "fact", kind: "quote", label: "f1", locator: "a.js:1" });
  addRow(src, { type: "fact", kind: "quote", label: "ext", locator: "https://x.test/doc", external: true, snapshot_sha256: "a".repeat(64), source_id: "S1" });
  addRow(src, goodTask({ label: "t1", files: ["a.js"] }));
  addRow(src, goodTask({ label: "t2", files: ["b.js"], deps: ["T1"] }));
  const l = base();
  l.phase = "P4";
  l.repos.push({ id: "bill", path: "." });
  const n = assimilateLedger(l, src, { repoId: "bill", dir: "/x/.rigor/plans/feature/billing", sha: "s" });
  assert.deepEqual(n, { decisions: 1, facts: 1, tasks: 2, tasks_skipped: 0, external_skipped: 1 });
  const byLabel = (x) => l.rows.find((r) => r.label === x);
  assert.ok(byLabel("billing-destination") && byLabel("billing-f1"));
  assert.deepEqual(byLabel("billing-t2").deps, [byLabel("billing-t1").id]);
  assert.equal(byLabel("billing-t2").repo, "bill");
  assert.deepEqual(validateLedger(l), []);
  assert.equal(l.sources[0].external_skipped, 1);
  assimilateLedger(l, src, { repoId: "bill", dir: "/x/.rigor/plans/feature/billing2", sha: "s" });
  assert.ok(byLabel("billing-t1-2"), "a second assimilation gets unique labels, never a collision");
  const early = base();
  const m = assimilateLedger(early, src, { dir: "/x/.rigor/plans/feature/billing", sha: "s" });
  assert.equal(m.tasks, 0);
  assert.equal(m.tasks_skipped, 2);
});

test("purge: assimilated plans and registered chats are deleted; unsafe, changed, current and non-file paths are skipped and recorded", async () => {
  const { mkdtempSync, rmSync, mkdirSync, writeFileSync, existsSync, readFileSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join, basename } = await import("node:path");
  const root = mkdtempSync(join(tmpdir(), "planning-purge-"));
  try {
    const plans = join(root, ".rigor", "plans", "feature");
    const mk = (slug, text) => {
      const d = join(plans, slug);
      mkdirSync(d, { recursive: true });
      writeFileSync(join(d, "ledger.json"), text);
      writeFileSync(join(d, "plan.md"), "x");
      return d;
    };
    const a = mk("a", "one"), b = mk("b", "two"), cur = mk("cur", "cur");
    const outside = join(root, "zzz", "x");
    mkdirSync(outside, { recursive: true });
    writeFileSync(join(outside, "ledger.json"), "o");
    const chat = join(root, "chat.jsonl");
    writeFileSync(chat, "hi");
    const dirChat = join(root, "adir");
    mkdirSync(dirChat);
    const sha = (d) => sha256(readFileSync(join(d, "ledger.json"), "utf8"));
    const l = base();
    l.sources = [a, cur, outside].map((d) => ({ slug: basename(d), dir: d, sha256: sha(d), purged: false, external_skipped: 0 }));
    l.sources.push({ slug: "b", dir: b, sha256: "stale", purged: false, external_skipped: 0 });
    l.sources.push({ slug: "gone", dir: join(plans, "gone"), sha256: "s", purged: false, external_skipped: 0 });
    l.chats = [{ path: chat, purged: false }, { path: dirChat, purged: false }];
    const out = purgeSuperseded(l, cur);
    const status = Object.fromEntries(out.map((x) => [basename(x.path) + ":" + x.kind, x.status]));
    assert.deepEqual(status, {
      "a:plan": "purged",
      "cur:plan": "skipped-current-plan",
      "x:plan": "skipped-not-a-plan-dir",
      "b:plan": "skipped-changed-since-assimilation",
      "gone:plan": "already-gone",
      "chat.jsonl:chat": "purged",
      "adir:chat": "skipped-not-a-file",
    });
    assert.ok(!existsSync(a) && !existsSync(chat), "purged paths are gone");
    assert.ok(existsSync(b) && existsSync(cur) && existsSync(outside) && existsSync(dirChat), "skipped paths are untouched");
    assert.equal(l.purges.length, 7);
    assert.deepEqual(purgeSuperseded(l, cur), [], "a second run does nothing and records nothing new");
    assert.equal(l.purges.length, 7);
    const ext = base();
    ext.sources = [{ slug: "e", dir: b, sha256: sha(b), purged: false, external_skipped: 2 }];
    assert.equal(purgeSuperseded(ext, cur)[0].status, "skipped-external-evidence-not-carried");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("CLI: repo, assimilate, chat and purge; purge waits for publish and runs automatically on it", async () => {
  const { spawnSync } = await import("node:child_process");
  const { mkdtempSync, rmSync, readFileSync, writeFileSync, existsSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const cli = new URL("./planning.mjs", import.meta.url).pathname.replace(/^\//, "");
  const dir = mkdtempSync(join(tmpdir(), "planning-multirepo-"));
  const run = (...a) => spawnSync("node", [cli, ...a], { cwd: dir, encoding: "utf8" });
  const lp = join(dir, ".rigor", "plans", "feature", "main", "ledger.json");
  try {
    assert.equal(run("init", "--slug", "src", "--no-branch", "--no-sweep").status, 0);
    assert.equal(run("decision", "--slug", "src", "--label", "destination", "--decision", "billing").status, 0);
    assert.equal(run("init", "--slug", "main", "--no-branch", "--no-sweep").status, 0);
    assert.notEqual(run("repo", "--slug", "main", "--id", "r1", "--path", "does-not-exist").status, 0);
    assert.equal(run("repo", "--slug", "main", "--id", "r1", "--path", ".").status, 0);
    assert.notEqual(run("repo", "--slug", "main", "--id", "r1", "--path", ".").status, 0, "repo ids are stable");
    assert.match(run("fact", "--slug", "main", "--label", "f", "--locator", "a.js:1", "--repo", "nope").stderr, /not registered/);
    const asm = run("assimilate", "--slug", "main", "--from", join(".rigor", "plans", "feature", "src"), "--repo", "r1");
    assert.equal(asm.status, 0, asm.stderr);
    assert.match(asm.stdout, /assimilated src: .*"decisions":1/);
    assert.match(run("assimilate", "--slug", "main", "--from", join(".rigor", "plans", "feature", "src")).stderr, /already assimilated/);
    writeFileSync(join(dir, "chat.txt"), "plan chat");
    assert.equal(run("chat", "--slug", "main", "--path", "chat.txt").status, 0);
    assert.match(run("purge", "--slug", "main").stderr, /not published/);
    assert.ok(existsSync(join(dir, ".rigor", "plans", "feature", "src")) && existsSync(join(dir, "chat.txt")));
    const raw = JSON.parse(readFileSync(lp, "utf8"));
    raw.plan_sha256 = "a".repeat(64);
    writeFileSync(lp, JSON.stringify(raw, null, 2) + "\n");
    const pg = run("purge", "--slug", "main");
    assert.equal(pg.status, 0, pg.stderr);
    assert.match(pg.stdout, /purge plan purged:/);
    assert.match(pg.stdout, /purge chat purged:/);
    assert.ok(!existsSync(join(dir, ".rigor", "plans", "feature", "src")) && !existsSync(join(dir, "chat.txt")));
    assert.equal(JSON.parse(readFileSync(lp, "utf8")).purges.length, 2);
    assert.match(run("purge", "--slug", "main").stdout, /nothing to do/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("doubt loop: rounds are numbered 1..n without gaps, and only an explicit 'No remaining doubt' closes it", () => {
  const l = base();
  const ask = (n, answer) => {
    const q = addRow(l, { type: "question", label: "q0-doubt-" + n, quote: "Any doubt left?" });
    if (answer !== undefined) {
      changeStatus(l, q.id, "answered", { reason: "user answer recorded" });
      l.rows.find((r) => r.id === q.id).answer = answer;
    }
  };
  const doubt = (x = l) => q0Errors(x).filter((e) => /doubt/.test(e)).join("\n");
  assert.match(doubt(), /the doubt loop has not run/);
  ask(1, "Yes: what about rollback?");
  assert.match(doubt(), /the doubt loop is open: q0-doubt-1/);
  ask(2, "no remaining doubt, go");
  assert.equal(doubt(), "", "an explicit clearance in any case closes the loop");
  ask(3, "Actually, one more thing");
  assert.match(doubt(), /the doubt loop is open: q0-doubt-3/, "a later doubt reopens a cleared loop");
  const gap = base();
  for (const n of [1, 3]) {
    const q = addRow(gap, { type: "question", label: "q0-doubt-" + n, quote: "?" });
    changeStatus(gap, q.id, "answered", { reason: "user answer recorded" });
    gap.rows.find((r) => r.id === q.id).answer = "No remaining doubt";
  }
  assert.match(doubt(gap), /q0-doubt-2 is missing/);
  const silent = base();
  addRow(silent, { type: "question", label: "q0-doubt-1", quote: "?" });
  assert.match(q0Errors(silent).join("\n"), /Q1 \(q0-doubt-1\) is still open/, "an unanswered round is open, never a clearance");
});
