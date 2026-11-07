#!/usr/bin/env node
// Deterministic ledger + gate validator for the `rigorous-planning` skill.
// Zero dependencies. Every gate is a regex, a count, a hash, or an exit code.
// No semantic judgement lives here: a gate either prints PASS or a string[] of errors and exits 1.
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, statSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

export const SLUG_RE = /^[a-z0-9][a-z0-9-]{0,79}$/;
// Plans live at .rigor/plans/<issue-type>/<slug>/{plan.md,ledger.json,sources/,issues/}.
export const ISSUE_TYPES = ["feature", "bug", "refactor", "audit", "evidence", "chore", "docs"];
export const TASK_KINDS = ["feature", "fix", "refactor", "docs", "chore"];
export const ISSUE_REF_RE = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+#\d+$/;
// Features that are ON by default; each can be switched off at init with --no-<feature>.
// (test_first, interview and branch keep their own top-level flags.)
export const SKIPPABLE = ["doubt", "plan-review", "review-section", "handoff", "adr", "constraints", "task-approval"];

// ---- Q0 sweep: every question category is asked or scoped out before intake closes. ----
export const Q0_CATEGORIES = [
	"outcome", "users", "scope", "constraints", "risk", "verification", "execution", "parallelism", "authorization", "done",
];
export const TASK_CATEGORIES = [
	"quick", "unspecified-low", "unspecified-high", "deep-low", "deep-high", "ultrabrain", "visual-engineering", "writing",
	"architect", "artistry",
];
export const AUTONOMY_MODES = ["run-through", "checkpoints"];
const normQuote = (x) => String(x ?? "").replace(/\s+/g, " ").trim().toLowerCase();
export function autonomyMode(l) {
	const d = (l.rows || []).find((r) => r.type === "decision" && r.status === "active" && r.label === "autonomy");
	const m = d && /^(run-through|checkpoints)\b/.exec(String(d.answer || "").trim());
	return m ? m[1] : null;
}
export function authorizationQuote(l) {
	const q = (l.rows || []).find(
		(r) => r.type === "question" && r.status === "answered" && /^q0-authorization(-|$)/.test(r.label || "") && String(r.answer || "").trim(),
	);
	return q ? String(q.answer).trim() : null;
}
// Under run-through the user's q0-authorization answer is the standing approval: every approve quote must carry it verbatim.
export function approvalQuoteError(l, quote) {
	if (autonomyMode(l) !== "run-through") return null;
	const auth = authorizationQuote(l);
	if (auth && normQuote(quote).includes(normQuote(auth))) return null;
	return "approve: autonomy is run-through, so --quote must contain the user's q0-authorization answer verbatim (the standing authorization); ask nothing new";
}
export function q0Errors(l) {
	const e = [];
	const live = (l.rows || []).filter(
		(r) => (r.type === "question" || r.type === "decision") && r.status !== "retracted" && /^q0-/.test(r.label || ""),
	);
	for (const c of Q0_CATEGORIES) {
		if (!live.some((r) => r.label === `q0-${c}` || r.label.startsWith(`q0-${c}-`))) {
			e.push(`sweep: category '${c}' has no q0-${c}* question and no q0-${c}* scope-out decision (ask it, or scope it out with a reason)`);
		}
	}
	for (const r of live) {
		if (r.type === "question" && r.status === "active") {
			e.push(`sweep: ${r.id} (${r.label}) is still open; the sweep ends only when every q0-* question is answered`);
		}
	}
	const rounds = live
		.filter((r) => r.type === "question" && /^q0-doubt-\d+$/.test(r.label))
		.map((r) => ({ n: +r.label.slice(9), r }))
		.sort((x, y) => x.n - y.n);
	if (!rounds.length) {
		e.push("sweep: the doubt loop has not run (ask q0-doubt-1: any doubt left about outcome, scope, constraints or risk, with 'No remaining doubt' as an option; ask q0-doubt-<n+1> while the last answer raises a doubt)");
	} else {
		for (let i = 0; i < rounds.length; i++) {
			if (rounds[i].n !== i + 1) {
				e.push("sweep: q0-doubt-" + (i + 1) + " is missing (doubt rounds are numbered 1..n without gaps)");
				break;
			}
		}
		const last = rounds[rounds.length - 1];
		if (last.r.status === "answered" && !/^\s*no remaining doubt\b/i.test(String(last.r.answer || ""))) {
			e.push("sweep: the doubt loop is open: q0-doubt-" + last.n + " was answered with a doubt; fold it in and ask q0-doubt-" + (last.n + 1));
		}
	}
	const mode = autonomyMode(l);
	if (!mode) {
		e.push("sweep: no active 'autonomy' decision (decision --label autonomy --decision run-through|checkpoints, taken from the q0-authorization answer)");
	} else if (mode === "run-through" && !authorizationQuote(l)) {
		e.push("sweep: autonomy run-through needs an answered q0-authorization question (a scope-out is not a standing authorization)");
	}
	return e;
}

// ---- Deterministic plan gates (G4): CPM fields, owner-confirm roots, harness todo mirror. ----
function activeTasks(l) {
	return (l.rows || []).filter((r) => r.type === "task" && r.status === "active");
}
function cpmErrors(l, planText) {
	if (!l.flags?.cpm) return [];
	const tasks = activeTasks(l);
	if (!tasks.length) return [];
	const e = [];
	for (const t of tasks) {
		if (!(Number.isFinite(+t.effort) && +t.effort > 0)) e.push(`plan: ${t.id} has no --effort (CPM needs a relative effort on every task; --no-cpm at init turns CPM off)`);
		if (!t.category) e.push(`plan: ${t.id} has no --category (the executor category the dag routes it by)`);
	}
	const { path } = cpmSchedule(tasks);
	if (!String(planText || "").includes(`Critical path: ${path.join(" -> ")}`)) {
		e.push("plan: the rendered critical path does not match the task graph (run render)");
	}
	return e;
}
function ownerConfirmErrors(l) {
	if (autonomyMode(l) !== "run-through") return [];
	const tasks = activeTasks(l);
	const e = [];
	for (const d of l.rows || []) {
		if (d.type !== "decision" || d.status !== "active" || !d.irreversible || /^q0-/.test(d.label || "")) continue;
		const t = tasks.find((x) => x.label === `owner-confirm-${d.label}`);
		if (!t) {
			e.push(`plan: irreversible decision ${d.id} (${d.label}) was not asked in Q0; under run-through it needs a root task 'owner-confirm-${d.label}' (the user's explicit yes at execution time)`);
		} else if ((t.deps || []).length) {
			e.push(`plan: ${t.id} (owner-confirm-${d.label}) must be a root task with no deps`);
		}
	}
	return e;
}
export const FINAL_WAVE = ["F1: plan compliance audit", "F2: code quality review", "F3: real manual QA", "F4: ideal-state fidelity"];
export function todoPhases(l, done = []) {
	const doneSet = new Set(done);
	const tasks = activeTasks(l).filter((t) => !doneSet.has(t.id));
	if (!tasks.length) return [];
	const byId = new Map(tasks.map((t) => [t.id, t]));
	const phases = taskWaves(tasks)
		.map((ids, n) => ({ phase: `Wave ${n + 1}`, items: ids.map((id) => `${id}: ${byId.get(id).label}`) }))
		.filter((p) => p.items.length);
	phases.push({ phase: "Final verification wave", items: [...FINAL_WAVE] });
	return phases;
}
function todoMirrorLines(l) {
	return [
		"### Todo mirror",
		"",
		`Mirror every wave and every task into the harness todo tool (senpi \`todo\`, TodoWrite, update_plan, whatever the harness provides) before work starts: one phase per wave, one item per task, items verbatim; mark an item in progress when it begins and done when it ends, never batched. \`node scripts/planning.mjs todos --slug ${l.slug}\` prints the JSON.`,
		"",
		...todoPhases(l).map((p) => `- Todo phase "${p.phase}": ${p.items.map((i) => `[${i}]`).join(" ")}`),
		"",
	];
}
function todoMirrorErrors(l, planText) {
	if (!activeTasks(l).length) return [];
	const lines = String(planText || "").split("\n");
	const e = [];
	for (const p of todoPhases(l)) {
		const line = lines.find((x) => x.startsWith(`- Todo phase "${p.phase}": `));
		if (!line) {
			e.push(`plan: Todo mirror is missing phase "${p.phase}" (run render)`);
			continue;
		}
		for (const it of p.items) if (!line.includes(`[${it}]`)) e.push(`plan: Todo mirror phase "${p.phase}" is missing item '${it}'`);
	}
	return e;
}

// ---- CPM: forward/backward pass over task deps. Effort is relative (task.effort, default 1). ----
const effortOf = (t) => (Number.isFinite(+t.effort) && +t.effort > 0 ? +t.effort : 1);
export function cpmSchedule(tasks) {
	const byId = new Map(tasks.map((t) => [t.id, t]));
	const succ = new Map(tasks.map((t) => [t.id, []]));
	for (const t of tasks) for (const d of t.deps || []) if (succ.has(d)) succ.get(d).push(t.id);
	const es = new Map(), ef = new Map();
	const fwd = (id, seen = new Set()) => {
		if (ef.has(id)) return ef.get(id);
		if (seen.has(id)) return 0; // a cycle is reported by validateLedger
		seen.add(id);
		let s = 0;
		for (const d of byId.get(id).deps || []) if (byId.has(d)) s = Math.max(s, fwd(d, seen));
		seen.delete(id);
		es.set(id, s);
		ef.set(id, s + effortOf(byId.get(id)));
		return ef.get(id);
	};
	for (const t of tasks) fwd(t.id);
	const length = Math.max(0, ...ef.values());
	const ls = new Map(), lf = new Map();
	const bwd = (id, seen = new Set()) => {
		if (ls.has(id)) return ls.get(id);
		if (seen.has(id)) return length;
		seen.add(id);
		let f = length;
		for (const s of succ.get(id)) f = Math.min(f, bwd(s, seen));
		seen.delete(id);
		lf.set(id, f);
		ls.set(id, f - effortOf(byId.get(id)));
		return ls.get(id);
	};
	for (const t of tasks) bwd(t.id);
	const rows = tasks.map((t) => {
		const slack = +(ls.get(t.id) - es.get(t.id)).toFixed(6);
		return { id: t.id, effort: effortOf(t), es: es.get(t.id), ef: ef.get(t.id), ls: ls.get(t.id), lf: lf.get(t.id), slack, critical: slack === 0 };
	});
	const path = rows
		.filter((r) => r.critical)
		.sort((a, b) => a.es - b.es || a.id.localeCompare(b.id, undefined, { numeric: true }))
		.map((r) => r.id);
	return { rows, length, path };
}
function cpmLines(tasks) {
	const { rows, length, path } = cpmSchedule(tasks);
	return [
		"### Critical path (CPM)",
		"",
		`Effort is in relative units (task \`effort\`, default 1); project length ${length}. Tasks with slack 0 set the schedule: start them first and never delay them; tasks with slack may start late or run in parallel.`,
		"",
		`Critical path: ${path.join(" -> ")}`,
		"",
		...rows.map((r) => `- ${r.id}: ES ${r.es}, EF ${r.ef}, LS ${r.ls}, LF ${r.lf}, slack ${r.slack}${r.critical ? " (critical)" : ""}`),
		"",
	];
}

// ---- mass-ulw bridge: the task graph as a workflow definition; same-file tasks are serialized, never raced. ----
function defaultCategory(t) {
	if (t.kind === "docs") return "writing";
	if ((t.est_lines ?? Infinity) <= 60 && (t.files || []).length <= 2) return "quick";
	return "unspecified-high";
}
export function dagDefinition(l, done = []) {
	const doneSet = new Set(done);
	const tasks = (l.rows || []).filter((r) => r.type === "task" && r.status === "active" && !doneSet.has(r.id));
	const ids = new Set(tasks.map((t) => t.id));
	const deps = new Map(tasks.map((t) => [t.id, (t.deps || []).filter((d) => ids.has(d))]));
	const reaches = (from, to, seen = new Set()) => {
		for (const d of deps.get(from) || []) {
			if (d === to) return true;
			if (!seen.has(d)) {
				seen.add(d);
				if (reaches(d, to, seen)) return true;
			}
		}
		return false;
	};
	const serialized = [];
	for (let j = 1; j < tasks.length; j++) {
		for (let i = 0; i < j; i++) {
			const a = tasks[i], b = tasks[j];
			const qual = (t) => (t.files || []).map((f) => (t.repo ? t.repo + ":" + f : f));
			const inB = new Set(qual(b));
			const shared = qual(a).filter((f) => inB.has(f));
			if (shared.length && !reaches(b.id, a.id) && !reaches(a.id, b.id)) {
				deps.get(b.id).push(a.id);
				serialized.push({ after: a.id, before: b.id, files: shared });
			}
		}
	}
	const nodes = tasks.map((t) => ({
		id: t.id,
		label: t.label,
		category: t.category || defaultCategory(t),
		dependsOn: deps.get(t.id),
		prompt: [
			`TASK: Implement ${t.id} "${t.label}" from plan ${l.slug}. This prompt is executable work, not a context handoff.`,
			`DELIVERABLE: ${t.interfaces || t.label}. Acceptance: ${t.acceptance}`,
			`SCOPE: ${t.repo ? `in repo ${t.repo} (${repoPath(l, t.repo)}), ` : ""}edit only ${(t.files || []).join(", ") || "the files this task names"}. Touch no other path; write "NOTICED BUT NOT TOUCHING: ..." in your report instead of fixing adjacent things.`,
			t.test_seam ? `TEST CONTRACT (red first): seam ${t.test_seam}; test file ${t.test_file}; red: ${t.red}; green: ${t.green}.` : null,
			`VERIFY: ${t.verify}. Report the command, its exit code and the evidence path.`,
			"STOP WHEN: acceptance holds and VERIFY passes. Do not commit unless the plan's commit strategy says so.",
		].filter(Boolean).join("\n"),
	}));
	const key = `${l.slug}-${sha256(JSON.stringify(nodes)).slice(0, 8)}`;
	return { definition: { key, name: `${l.slug} plan execution`, nodes }, serialized };
}
export const SIZES = ["S", "L"];
// Published plans can only be changed with a reason; these commands never amend.
const AMEND_EXEMPT = new Set(["gate", "publish", "render", "render-issues", "test-run"]);
export const DOUBT_CLASSES = ["valid_actionable", "valid_tradeoff", "contract_misread", "noise"];
const LOCKFILE_RE = /(^|[\\/])(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb?|Cargo\.lock|go\.sum|uv\.lock|poetry\.lock|Gemfile\.lock)$/;
const SCRIPTED_RE = /\b(codemod|scripted|ast-grep|jscodeshift|transform|sed)\b/i;
export const planDir = (issueType, slug) => join(".rigor", "plans", issueType, slug);
export const LABEL_RE = /^[a-z0-9_-]{1,32}$/;
export const SHA256_RE = /^[a-f0-9]{64}$/;
export const FACT_KINDS = ["measured", "quote", "derived", "assumed", "converted"];
export const ROW_PREFIX = { fact: "F", question: "Q", decision: "D", task: "T", axis: "A", finding: "N", round: "R", test_run: "X" };
const STATUSES = ["active", "answered", "superseded", "retracted"];
const TRANSITIONS = {
	active: ["answered", "superseded", "retracted"],
	answered: ["superseded", "retracted"],
	superseded: [],
	retracted: [],
};

export function sha256(text) {
	return createHash("sha256").update(text).digest("hex");
}

export function emptyLedger(
	{
		slug,
		issueType = "feature",
		branch = null,
		branchReason = "non-git",
		test_first = true,
		noInterview = false,
		noBranch = false,
		skip = [],
		size = "L",
		deliberate = false,
		testRuns = false,
		sweep = false,
		cpm = false,
		now = new Date().toISOString(),
	} = {},
) {
	return {
		schemaVersion: 2,
		slug,
		issue_type: issueType,
		issues: [],
		branch,
		branch_reason: branchReason,
		scope_multi: false,
		flags: {
			test_first: Boolean(test_first),
			no_interview: Boolean(noInterview),
			no_branch: Boolean(noBranch),
			deliberate: Boolean(deliberate),
			test_runs: Boolean(testRuns),
			sweep: Boolean(sweep),
			cpm: Boolean(cpm),
			skip: [...skip],
		},
		size,
		doubts: [],
		plan_reviews: [],
		phase: "P0",
		unknowns_open: false,
		unknown_items: [],
		map: null,
		created_at: now,
		intent: {
			outcome: null,
			user: null,
			why_now: null,
			success: null,
			constraint: null,
			out_of_scope: null,
			confirmed: false,
			assumed: false,
		},
		axes: [],
		waves: [],
		rows: [],
		events: [],
		changes: [],
		repos: [],
		sources: [],
		chats: [],
		purges: [],
		approvals: [],
		capabilities: [],
		plan_sha256: null,
		render_sha256: null,
	};
}

const ID_RE = {
	F: /^F(\d+)$/, Q: /^Q(\d+)$/, D: /^D(\d+)$/, T: /^T(\d+)$/, A: /^A(\d+)$/,
	N: /^N(\d+)$/, R: /^R(\d+)$/, X: /^X(\d+)$/,
};
const ROW_ID_RE = /^[FQDATNRX]\d+$/, SOURCE_RE = /^S\d+$/, FACT_REF_RE = /^[FQ]\d+$/;
export const FINDING_CLASSES = ["valid_actionable", "valid_tradeoff", "contract_misread", "noise"];
const SET_STATUSES = new Set(STATUSES), SET_FACT_KINDS = new Set(FACT_KINDS);
const INTENT_KEYS = ["outcome", "user", "why_now", "success", "constraint", "out_of_scope"];

export function nextId(rows, prefix) {
	const re = ID_RE[prefix];
	let max = 0;
	for (const r of rows) {
		const m = re.exec(r.id || "");
		if (m) {
			const n = +m[1];
			if (n > max) max = n;
		}
	}
	return `${prefix}${max + 1}`;
}

// One iterative DFS per graph (white/grey/black), O(V+E). Replaces the old
// per-node recursive `visit` that re-walked shared subgraphs: O(V^2) on chains.
function checkGraph(ids, depsOf, label, errors) {
	const known = new Set(ids);
	const color = new Map(); // 1 = on stack, 2 = done
	for (const root of ids) {
		if (color.get(root) === 2) continue;
		const stack = [[root, 0]];
		color.set(root, 1);
		const path = [root];
		while (stack.length) {
			const top = stack[stack.length - 1];
			const deps = depsOf(top[0]) || [];
			if (top[1] >= deps.length) {
				color.set(top[0], 2);
				stack.pop();
				path.pop();
				continue;
			}
			const dep = deps[top[1]++];
			if (dep === top[0]) {
				errors.push(`${top[0]}: self-reference`);
				continue;
			}
			if (!known.has(dep)) continue; // missing ref already reported by the caller
			const c = color.get(dep);
			if (c === 1) errors.push(`${label} cycle: ${[...path, dep].join("->")}`);
			else if (c !== 2) {
				color.set(dep, 1);
				stack.push([dep, 0]);
				path.push(dep);
			}
		}
	}
}

// Per-ledger id high-water marks. Without this, every addRow rescans all rows
// (nextId) and bulk construction is O(n^2). The cache self-invalidates when
// rows.length changes outside addRow, so hand-edited ledgers stay correct.
const idState = new WeakMap();
function nextIdFor(ledger, prefix) {
	let s = idState.get(ledger);
	if (!s || s.len !== ledger.rows.length) {
		s = { len: ledger.rows.length, max: { F: 0, Q: 0, D: 0, T: 0, A: 0, N: 0, R: 0, X: 0 } };
		for (const r of ledger.rows) {
			const m = /^[FQDATNRX](\d+)$/.exec(r.id || "");
			if (m) {
				const p = r.id[0], n = +m[1];
				if (n > s.max[p]) s.max[p] = n;
			}
		}
		idState.set(ledger, s);
	}
	s.max[prefix] += 1;
	s.len += 1;
	return `${prefix}${s.max[prefix]}`;
}

export function addRow(ledger, row, now = new Date().toISOString()) {
	const prefix = ROW_PREFIX[row.type];
	if (!prefix) throw new Error(`unknown row type: ${row.type}`);
	if (!LABEL_RE.test(row.label || "")) throw new Error(`label '${row.label}' must match ${LABEL_RE}`);
	const full = {
		status: "active",
		source_id: null,
		locator: null,
		snapshot_sha256: null,
		quote: null,
		axis: null,
		answer: null,
		observed_at: now,
		...row,
		id: nextIdFor(ledger, prefix),
	};
	ledger.rows.push(full);
	return full;
}

export function addCapability(ledger, { id, responsibility, deps } = {}) {
	if (!SLUG_RE.test(id || "")) throw new Error(`capability id must match ${SLUG_RE}`);
	if (!(ledger.capabilities ||= [])) ledger.capabilities = [];
	if (ledger.capabilities.some((c) => c.id === id)) {
		throw new Error(`capability '${id}' already exists (ids are stable, never reused)`);
	}
	const normalized = Array.isArray(deps)
		? deps
		: String(deps === undefined || deps === null ? "" : deps).split(",");
	const depList = normalized.map((x) => String(x).trim()).filter(Boolean);
	const cap = { id, responsibility, depends_on: depList };
	ledger.capabilities.push(cap);
	return cap;
}

export function changeStatus(ledger, id, to, { replacement = null, reason = null } = {}) {
	const row = ledger.rows.find((r) => r.id === id);
	if (!row) throw new Error(`no such row: ${id}`);
	if (to === "answered" && row.type !== "question") throw new Error("only questions can be answered");
	const allowed = TRANSITIONS[row.status] || [];
	if (!allowed.includes(to)) throw new Error(`illegal transition ${row.status} -> ${to} for ${id}`);
	if (to === "superseded" && !replacement) throw new Error("supersede requires --replacement");
	if (!reason) throw new Error("status change requires --reason");
	ledger.events.push({ fact_id: id, from: row.status, to, replacement, reason });
	row.status = to;
	return row;
}

export function validateLedger(ledger) {
	const errors = [];
	if (!ledger || typeof ledger !== "object") return ["ledger: not an object"];
	if (ledger.schemaVersion !== 2) errors.push("schemaVersion: must be 2");
	if (!SLUG_RE.test(ledger.slug || "")) errors.push(`slug: must match ${SLUG_RE}`);
	if (!ISSUE_TYPES.includes(ledger.issue_type)) {
		errors.push(`issue_type: must be one of ${ISSUE_TYPES.join("|")}`);
	}
	for (const k of ledger.flags?.skip || []) {
		if (!SKIPPABLE.includes(k)) errors.push(`flags.skip: '${k}' is not a skippable feature (${SKIPPABLE.join("|")})`);
	}
	if (!SIZES.includes(ledger.size)) errors.push(`size: must be one of ${SIZES.join("|")}`);
	const declared = new Set();
	for (const i of ledger.issues || []) {
		if (!ISSUE_REF_RE.test(i?.ref || "")) errors.push(`issues: issue ref '${i?.ref}' must be owner/repo#number`);
		else declared.add(i.ref);
	}
	if (typeof ledger.flags?.test_first !== "boolean") {
		errors.push("flags.test_first: must be boolean (default true; --no-test-first turns it off)");
	}
	if (typeof ledger.flags?.no_interview !== "boolean") {
		errors.push("flags.no_interview: must be boolean (default false)");
	}
	if (ledger.flags?.deliberate !== undefined && typeof ledger.flags.deliberate !== "boolean") {
		errors.push("flags.deliberate: must be boolean (default false; --deliberate forces the record)");
	}
	if (ledger.flags?.sweep !== undefined && typeof ledger.flags.sweep !== "boolean") {
		errors.push("flags.sweep: must be boolean (default true from init; --no-sweep turns the Q0 sweep off)");
	}
	if (ledger.flags?.cpm !== undefined && typeof ledger.flags.cpm !== "boolean") {
		errors.push("flags.cpm: must be boolean (default true from init; --no-cpm turns CPM requirements off)");
	}
	if (ledger.changes !== undefined && !Array.isArray(ledger.changes)) errors.push("changes: must be an array");
	const repoIds = new Set();
	for (const rp of ledger.repos || []) {
		if (!SLUG_RE.test(rp?.id || "") || !String(rp?.path || "").trim()) errors.push("repos: each repo needs a kebab id and a path");
		else if (repoIds.has(rp.id)) errors.push("repos: duplicate repo id " + rp.id);
		else repoIds.add(rp.id);
	}
	const rows = ledger.rows || [];
	const seenIds = new Set(), seenLabels = new Set();
	const byId = new Map();
	for (const r of rows) byId.set(r.id, r);
	for (const r of rows) {
		if (seenIds.has(r.id)) errors.push(`${r.id}: duplicate id`);
		seenIds.add(r.id);
		if (!ROW_ID_RE.test(r.id || "")) errors.push(`${r.id}: id must be F/Q/D/A/T + number`);
		if (!LABEL_RE.test(r.label || "")) errors.push(`${r.id}: label must match ${LABEL_RE}`);
		if (r.label) {
			if (seenLabels.has(r.label)) errors.push(`${r.id}: label '${r.label}' reused (labels are unique forever)`);
			seenLabels.add(r.label);
		}
		if (!SET_STATUSES.has(r.status)) {
			errors.push(`${r.id}: status '${r.status}' not in active|answered|superseded|retracted`);
		}
		if (r.repo && !repoIds.has(r.repo)) errors.push(r.id + ": repo " + r.repo + " is not registered (run the repo command first)");
		if (r.type === "fact") {
			if (!SET_FACT_KINDS.has(r.kind)) {
				errors.push(`${r.id}: kind must be one of measured|quote|derived|assumed|converted`);
			}
			if (!r.locator) errors.push(`${r.id}: fact requires locator (file:line or URL)`);
			if (r.source_id && !SOURCE_RE.test(r.source_id)) errors.push(`${r.id}: source_id must be S<n>`);
			if (r.external && !SHA256_RE.test(r.snapshot_sha256 || "")) {
				errors.push(`${r.id}: external fact requires snapshot_sha256 (64 hex)`);
			}
		}
		if (r.type === "task") {
			if (r.est_lines !== undefined && r.est_lines !== null && !(Number.isFinite(+r.est_lines) && +r.est_lines >= 0)) {
				errors.push(`${r.id}: est_lines must be a non-negative number`);
			}
			if (r.effort !== undefined && r.effort !== null && !(Number.isFinite(+r.effort) && +r.effort > 0)) {
				errors.push(`${r.id}: effort must be a positive number (relative CPM units)`);
			}
			if (r.category && !TASK_CATEGORIES.includes(r.category)) {
				errors.push(`${r.id}: category must be one of ${TASK_CATEGORIES.join("|")}`);
			}
			if (r.kind && !TASK_KINDS.includes(r.kind)) {
				errors.push(`${r.id}: kind must be one of ${TASK_KINDS.join("|")}`);
			}
			if (r.issue && !declared.has(r.issue)) {
				errors.push(`${r.id}: issue ${r.issue} is not declared in ledger.issues (add it with the issue command)`);
			}
		}
		if (r.type === "question" && r.status === "answered" && !r.answer) {
			errors.push(`${r.id}: answered question requires answer`);
		}
		if (r.type === "finding") {
			if (!FINDING_CLASSES.includes(r.class)) {
				errors.push(`${r.id}: finding class must be one of ${FINDING_CLASSES.join("|")}`);
			}
			if (!/^(plan-review:\d+|doubt:[A-Z]\d+:\d+)$/.test(String(r.review || ""))) {
				errors.push(`${r.id}: finding review must be plan-review:<cycle> or doubt:<decision>:<cycle>`);
			}
			if (!r.locator && r.class !== "noise") {
				errors.push(`${r.id}: a ${r.class} finding needs a locator (file:line or URL)`);
			}
			if (r.locator && r.locator.includes("://") && !SHA256_RE.test(r.snapshot_sha256 || "")) {
				errors.push(`${r.id}: external finding needs snapshot_sha256`);
			}
		}
		if (r.type === "round") {
			if (!Number.isInteger(+r.n) || +r.n < 1) errors.push(`${r.id}: round n must be an integer >= 1`);
			if (!Array.isArray(r.asks) || !r.asks.length) errors.push(`${r.id}: round asks must name at least one question`);
			for (const q of r.asks || []) {
				const target = byId.get(q);
				if (!target || target.type !== "question") errors.push(`${r.id}: ask '${q}' is not a question`);
			}
		}
		if (r.type === "test_run") {
			const t = byId.get(r.task);
			if (!t || t.type !== "task") errors.push(`${r.id}: test_run task '${r.task}' is not a task`);
			if (!["red", "green"].includes(r.phase)) errors.push(`${r.id}: test_run phase must be red|green`);
			if (!r.cmd) errors.push(`${r.id}: test_run cmd required`);
			if (!Number.isInteger(+r.exit)) errors.push(`${r.id}: test_run exit must be an integer`);
			if (!r.artifact) errors.push(`${r.id}: test_run artifact path required`);
			if (r.artifact && r.artifact.includes("://") && !SHA256_RE.test(r.snapshot_sha256 || "")) {
				errors.push(`${r.id}: external test artifact needs snapshot_sha256`);
			}
		}
		if (r.kind === "derived") {
			for (const ref of r.operands || []) {
				if (!FACT_REF_RE.test(ref)) errors.push(`${r.id}: operand '${ref}' must be F/Q ref`);
			}
		}
	}
	// Event replay: every event must chain from the row's replayed status.
	const state = new Map(rows.map((r) => [r.id, "active"]));
	for (const e of ledger.events || []) {
		if (
			Object.keys(e).length !== 5
			|| !("fact_id" in e && "from" in e && "to" in e && "replacement" in e && "reason" in e)
		) {
			errors.push(`event ${e.fact_id}: must have exactly fact_id,from,to,replacement,reason`);
		}
		if (!byId.has(e.fact_id)) {
			errors.push(`event ${e.fact_id}: unknown row`);
			continue;
		}
		if (state.get(e.fact_id) !== e.from) {
			errors.push(`event ${e.fact_id}: from '${e.from}' != replayed '${state.get(e.fact_id)}'`);
		}
		if (!(TRANSITIONS[e.from] || []).includes(e.to)) {
			errors.push(`event ${e.fact_id}: illegal transition ${e.from} -> ${e.to}`);
		}
		if (e.to === "superseded" && !e.replacement) errors.push(`event ${e.fact_id}: supersede requires replacement`);
		if (!e.reason) errors.push(`event ${e.fact_id}: reason required`);
		state.set(e.fact_id, e.to);
	}
	for (const r of rows) {
		if ((r.status === "superseded" || r.status === "retracted") && state.get(r.id) !== r.status) {
			errors.push(`${r.id}: stored status '${r.status}' != event replay '${state.get(r.id)}'`);
		}
	}
	// Provenance + task deps + capability deps: existence in one pass, then one DFS each.
	const rowIds = [], taskIds = [];
	for (const r of rows) {
		rowIds.push(r.id);
		if (r.type === "task") taskIds.push(r.id);
		for (const ref of r.operands || []) if (!byId.has(ref)) errors.push(`${r.id}: operand ${ref} does not exist`);
		for (const dep of r.deps || []) if (!byId.has(dep)) errors.push(`${r.id}: dep ${dep} does not exist`);
	}
	checkGraph(rowIds, (id) => byId.get(id)?.operands, "provenance", errors);
	checkGraph(taskIds, (id) => byId.get(id)?.deps, "task", errors);
	// Capability map (SDD Phase 0): stable kebab ids, deps exist, acyclic.
	const caps = ledger.capabilities || [], capIds = new Set(), capById = new Map();
	for (const c of caps) {
		if (!SLUG_RE.test(c.id || "")) errors.push(`capability '${c.id}': id must be stable kebab slug`);
		if (capIds.has(c.id)) errors.push(`capability '${c.id}': duplicate id (ids are never renamed or reused)`);
		capIds.add(c.id);
		capById.set(c.id, c);
		if (!c.responsibility) errors.push(`capability '${c.id}': responsibility required`);
	}
	for (const c of caps) {
		for (const dep of c.depends_on || []) {
			if (!capIds.has(dep)) errors.push(`capability '${c.id}': depends_on '${dep}' does not exist`);
		}
	}
	checkGraph(caps.map((c) => c.id), (id) => capById.get(id)?.depends_on, "capability", errors);
	return errors;
}

const skipped = (l, k) => (l.flags?.skip || []).includes(k);
const activeDecision = (l, label) =>
	(l.rows || []).find((r) => r.type === "decision" && r.status === "active" && r.label === label);
const itemCount = (text) =>
	String(text || "")
		.split(/\r?\n|[;|•]/)
		.map((x) => x.trim())
		.filter(Boolean).length;
const deliberateRequired = (l) =>
	Boolean(l.flags?.deliberate) ||
	l.size === "L" ||
	(l.rows || []).some((r) => r.type === "decision" && r.status === "active" && r.irreversible);
const TEST_CLAIM_RE = /\b(?:ran (?:the )?tests?|test run|tests? passed|verified by running)\b/i;

// Execution waves and the dependency matrix are derived from task.deps; the gate checks the render.
function executionErrors(l, planText) {
	const e = [];
	const tasks = (l.rows || []).filter((r) => r.type === "task" && r.status === "active");
	if (!tasks.length) return e;
	const lines = String(planText || "").split("\n").map((x) => x.trimEnd());
	const waves = [];
	for (const line of lines) {
		const m = /^- Wave (\d+): (.*)$/.exec(line);
		if (m) waves[+m[1] - 1] = m[2].split(",").map((s) => s.trim()).filter(Boolean);
	}
	const waveIds = waves.flat();
	for (const t of tasks) {
		if (waveIds.filter((id) => id === t.id).length !== 1) {
			e.push(`plan: execution waves must list ${t.id} exactly once`);
		}
	}
	for (const t of tasks) {
		for (const d of t.deps || []) {
			const tw = waveIds.indexOf(t.id), dw = waveIds.indexOf(d);
			if (tw >= 0 && dw >= 0 && tw <= dw) e.push(`plan: ${t.id} is not after its dependency ${d} in the wave plan`);
		}
	}
	const rowFor = (id) => lines.find((x) => new RegExp(`^\\|\\s*${id}\\s*\\|`).test(x));
	for (const t of tasks) {
		const row = rowFor(t.id);
		if (!row) {
			e.push(`plan: dependency matrix missing ${t.id}`);
			continue;
		}
		const cols = row.split("|").slice(1, -1).map((s) => s.trim());
		const deps = (cols[1] || "").replace(/—/g, "").split(",").map((s) => s.trim()).filter(Boolean);
		if (deps.slice().sort().join(",") !== (t.deps || []).slice().sort().join(",")) {
			e.push(`plan: dependency matrix row ${t.id} does not match deps`);
		}
	}
	return e;
}

// Rigor scales by arithmetic, not by feeling: the size is derived from the task graph.
export function scopeSize(l) {
	const tasks = (l.rows || []).filter((t) => t.type === "task" && t.status === "active");
	const files = new Set(tasks.flatMap((t) => t.files || []));
	const caps = (l.capabilities || []).length;
	const irreversible = (l.rows || []).some((r) => r.type === "decision" && r.status === "active" && r.irreversible);
	if (tasks.length > 8 || caps > 2 || (l.repos || []).length > 1) return "L";
	if (tasks.length <= 2 && files.size <= 3 && caps <= 1 && !irreversible) return "S";
	return "L";
}

// ---- Gates: each returns string[] errors (empty = PASS). ----
export const GATES = {
	G0: (l) => {
		const e = validateLedger(l);
		const dest = (l.rows || []).find(
			(r) => r.type === "decision" && r.status === "active" && r.label === "destination",
		);
		if (!dest || !String(dest.answer || "").trim()) {
			e.push("intake: no active 'destination' decision (one or two lines naming the end state; if this is unclear, use init --map)");
		} else if (String(dest.answer).split("\n").filter((x) => x.trim()).length > 2) {
			e.push("intake: destination must fit in one or two lines (a longer statement is unclear or a spec)");
		}
		if (!l.branch && l.branch !== null) e.push("branch: must be recorded (string, or null when not a git repo)");
		if (l.branch !== null && !/^plan\/[a-z0-9][a-z0-9-]{0,79}$/.test(l.branch || "")) {
			e.push("branch: must be plan/<slug>");
		}
		if (l.branch && l.branch !== `plan/${l.slug}`) e.push(`branch: '${l.branch}' != plan/${l.slug}`);
		if (l.branch === null && !l.flags?.no_branch && l.branch_reason !== "non-git" && !(l.branch_reason === "size-s" && l.size === "S")) {
			e.push("branch: null is only allowed with --no-branch or a verified non-git directory (branch_reason)");
		}
		if (l.flags?.sweep) e.push(...q0Errors(l));
		return e;
	},
	G_AX: (l) => {
		const e = [];
		if (phaseIndex(l.phase) < phaseIndex("P1")) {
			e.push("axis: G_AX before G0 (intake must pass first)");
		}
		if (!l.axes?.length) {
			e.push("axis: axes[] is empty (record at least one `axis --label`)");
		}
		const ids = new Set();
		for (const a of l.axes || []) {
			if (!a?.id || !String(a.label || "").trim()) e.push("axis: every axis needs an id and a non-empty label");
			if (a?.id && ids.has(a.id)) e.push(`axis: duplicate axis id ${a.id}`);
			if (a?.id) ids.add(a.id);
		}
		for (const r of l.rows || []) {
			if (r.type === "fact" && r.status === "active" && r.axis && !ids.has(r.axis)) {
				e.push(`axis: fact ${r.id} names unknown axis ${r.axis}`);
			}
		}
		return e;
	},
	G1: (l) => {
		const e = [];
		if (!l.axes?.length) e.push("evidence: axes[] is empty");
		const perAxis = new Map(), extBad = [];
		for (const r of l.rows || []) {
			if (r.type !== "fact") continue;
			if (r.status === "active" && r.axis) perAxis.set(r.axis, (perAxis.get(r.axis) || 0) + 1);
			if (r.external && !SHA256_RE.test(r.snapshot_sha256 || "")) extBad.push(r.id);
		}
		for (const a of l.axes || []) {
			if (!perAxis.get(a.id)) e.push(`evidence: axis ${a.id} (${a.label}) has 0 active facts`);
		}
		const w = l.waves || [];
		if ((l.rows || []).some((r) => r.type === "fact" && r.wave > w.length)) {
			e.push("evidence: facts recorded after the last wave — close the wave with the wave command before the gate");
		}
		if (l.size === "S") {
			// small scope: one closed wave, any count (the size claim is audited again at publish)
			if (w.length < 1) e.push("evidence: saturation not reached (size S needs one closed wave)");
		} else if (w.length < 2 || w[w.length - 1].new_facts !== 0 || w[w.length - 2].new_facts !== 0) {
			e.push("evidence: saturation not reached (need 2 consecutive waves with new_facts=0 at size L)");
		}
		for (const id of extBad) e.push(`evidence: ${id} external fact missing snapshot_sha256`);
		// Refactor surveys must leave an evidence trail, not a prose opinion.
		if (l.issue_type === "refactor") {
			const surveys = (l.rows || []).filter(
				(r) => r.type === "fact" && r.status === "active" && /^survey-/.test(r.label || "") && /^.+:\d+/.test(String(r.locator || "")),
			);
			if (!surveys.length) {
				e.push("evidence: refactor requires at least one active 'survey-*' fact with a file:line locator");
			}
			const top = activeDecision(l, "top-recommendation");
			if (!top) {
				e.push("evidence: refactor requires an active 'top-recommendation' decision");
			} else {
				const ids = String(top.answer || "").match(/F\d+/g) || [];
				if (!ids.some((id) => surveys.some((s) => s.id === id))) {
					e.push("evidence: 'top-recommendation' must name a survey-* fact id");
				}
			}
		}
		return e;
	},
	G2: (l) => {
		const e = [], open = [];
		if (l.map) {
			e.push("clarify: map mode is gated by G_MAP, not G2 (handoff creates the planning ledger)");
			return e;
		}
		for (const r of l.rows || []) if (r.type === "question" && r.status === "active") open.push(r.id);
		if (open.length) e.push(`clarify: frontier not empty, open questions: ${open.join(",")}`);
		const readyQ = designFrontier(l).map((q) => q.id);
		if (readyQ.length) e.push(`clarify: design frontier not empty, ready questions: ${readyQ.join(",")}`);
		// The frontier is computed from recorded rounds and prerequisites, never from the model's prose.
		const rounds = (l.rows || []).filter((r) => r.type === "round");
		const asked = new Set(rounds.flatMap((r) => r.asks || []));
		for (const q of open) if (!asked.has(q)) e.push(`clarify: ${q} is open but was never put in a round (frontier unrecorded)`);
		for (const q of l.rows.filter((r) => r.type === "question" && r.status === "active")) {
			for (const dep of q.blocked_by || []) {
				const d = l.rows.find((r) => r.id === dep);
				if (!d) e.push(`clarify: ${q.id} blocked_by ${dep} does not exist`);
				else if (d.status === "active") e.push(`clarify: ${q.id} asked before prerequisite ${dep} was settled`);
			}
		}
		if (l.unknowns_open && !l.rows.some((r) => r.type === "decision" && r.status === "active" && r.label === "destination")) {
			e.push("clarify: unknowns are recorded but no active 'destination' decision exists (route to map)");
		}
		for (const k of INTENT_KEYS) if (!l.intent?.[k]) e.push(`clarify: intent.${k} missing`);
		if (l.rows.some((r) => r.type === "decision" && r.label === "early-exit" && r.status === "active")) {
			e.push(
				"clarify: early-exit recorded — clarification was stopped by the user; publish is blocked (start a new slug or supersede the early-exit with a reason and re-run clarification)",
			);
		}
		if (l.flags?.no_interview) {
			// --no-interview does not delete the gate; it changes its evidence.
			if (l.intent?.assumed !== true) {
				e.push(
					"clarify (--no-interview): intent.assumed must be true (fill intent from request+evidence, mark it assumed)",
				);
			}
			const assumed = l.rows.filter((r) => r.type === "fact" && r.kind === "assumed" && r.status === "active");
			const decisions = l.rows.filter((r) => r.type === "decision" && r.status === "active");
			if (!assumed.length) {
				e.push("clarify (--no-interview): need >=1 ACTIVE assumed fact (F, kind=assumed) backing the assumed intent");
			}
			if (!decisions.length) {
				e.push("clarify (--no-interview): need >=1 ACTIVE decision row (the choices that would have been asked)");
			}
			if (l.intent?.confirmed === true) {
				e.push("clarify (--no-interview): intent.confirmed must stay false (no user yes was given)");
			}
		} else if (l.intent?.confirmed !== true) {
			e.push("clarify: intent not confirmed by explicit user yes");
		}
		return e;
	},
	G3: (l) => {
		const e = [];
		const openD = l.rows.filter((r) => r.type === "question" && r.status === "active");
		if (openD.length) e.push("design: open questions remain");
		const approved = (token) =>
			l.approvals?.some(
				(a) => a.gate === "G3" && a.token === token && a.by === "user" && String(a.quote || "").trim().length > 0,
			);
		if (l.flags?.no_interview) {
			const decisions = l.rows.filter((r) => r.type === "decision" && r.status === "active");
			if (!decisions.length) {
				e.push(
					"design (--no-interview): need >=1 active decision row (design proceeds on logged assumptions, not silence)",
				);
			}
		} else if (!approved("approve-design")) {
			e.push(
				"design: no 'approve-design' approval recorded with by=user (timeout/dismiss/silence do not count; the CLI records what the user said in chat, it cannot mint it)",
			);
		}
		// Plan review: a fresh-context pass over the draft design, findings classified, 3 cycles max.
		if (!skipped(l, "plan-review")) {
			const rs = l.plan_reviews || [];
			if (!rs.length) {
				e.push("plan-review: no fresh-context plan review recorded (review the draft design, persist its findings with the finding command; or re-init with --no-plan-review)");
			}
			for (const x of rs) {
				const rows = l.rows.filter((r) => r.type === "finding" && r.review === `plan-review:${x.cycle}`);
				if (x.clean === true) {
					if (!(x.scope || []).length) e.push(`plan-review: cycle ${x.cycle} is clean but records no scope locators (what was reviewed?)`);
					if (rows.some((r) => r.class !== "noise")) e.push(`plan-review: cycle ${x.cycle} is clean but has non-noise finding rows`);
				} else if (!rows.length) {
					e.push(`plan-review: cycle ${x.cycle} has no finding rows (persist each finding with --review plan-review:${x.cycle})`);
				}
				if (x.cycle > 3 && !approved("plan-review-escalated")) {
					e.push(`plan-review: cycle ${x.cycle} exceeds 3 — escalate to the user (approve --gate G3 --token plan-review-escalated --by user --quote "<what the user said>")`);
				}
			}
		}
		// Doubt cycle: every irreversible decision survives a fresh-context adversary before it stands.
		if (!skipped(l, "doubt")) {
			const escalated = approved("doubt-escalated");
			for (const d of l.rows.filter((r) => r.type === "decision" && r.status === "active" && r.irreversible)) {
				const ds = (l.doubts || []).filter((x) => x.decision === d.id);
				if (!ds.length) {
					e.push(`doubt: ${d.id} is irreversible but has no doubt record (run the doubt cycle, or re-init with --no-doubt)`);
				}
				for (const x of ds) {
					const rows = l.rows.filter((r) => r.type === "finding" && r.review === `doubt:${d.id}:${x.cycle}`);
					if (x.clean === true) {
						if (!(x.scope || []).length) e.push(`doubt: ${d.id} cycle ${x.cycle} is clean but records no scope locators`);
						if (rows.some((r) => r.class !== "noise")) e.push(`doubt: ${d.id} cycle ${x.cycle} is clean but has non-noise finding rows`);
					} else if (!rows.length) {
						e.push(`doubt: ${d.id} cycle ${x.cycle} has no finding rows (persist each finding with --review doubt:${d.id}:${x.cycle})`);
					}
					if (x.cycle > 3 && !escalated) {
						e.push(`doubt: ${d.id} cycle ${x.cycle} exceeds 3 — escalate to the user (approve --gate G3 --token doubt-escalated --by user --quote "<what the user said>")`);
					}
				}
			}
		}
		// Deliberate records: large or irreversible work must leave the deliberation record artifacts.
		if (deliberateRequired(l) && !skipped(l, "deliberate")) {
			const principles = activeDecision(l, "principles");
			if (!principles || itemCount(principles.answer) < 3) {
				e.push("deliberate: need an active 'principles' decision with >=3 items (decision --label principles)");
			}
			const drivers = activeDecision(l, "drivers");
			if (!drivers || itemCount(drivers.answer) < 3) {
				e.push("deliberate: need an active 'drivers' decision with >=3 items (decision --label drivers)");
			}
			const options = activeDecision(l, "options"), invalidation = activeDecision(l, "invalidation");
			const optionA = activeDecision(l, "option-a"), optionB = activeDecision(l, "option-b");
			if (!((optionA && optionB) || (options && invalidation))) {
				e.push("deliberate: record option-a and option-b, or options and invalidation");
			}
			const premortem = activeDecision(l, "pre-mortem");
			if (!premortem || itemCount(premortem.answer) < 3) {
				e.push("deliberate: need an active 'pre-mortem' decision with >=3 scenarios");
			}
			const testPlan = activeDecision(l, "expanded-test-plan");
			const planText = String(testPlan?.answer || "").toLowerCase();
			for (const token of ["unit", "integration", "e2e", "observability"]) {
				if (!planText.includes(token)) {
					e.push(`deliberate: 'expanded-test-plan' must name ${token}`);
				}
			}
		}
		// SDD Phase 0: a multi-capability map is gated like any other phase.
		if (l.scope_multi && (l.capabilities || []).length < 2) {
			e.push(
				"capability-map: scope was classified multi-capability at intake but <2 capabilities are recorded (record the map or reclassify with a decision row)",
			);
		}
		if ((l.capabilities || []).length > 1) {
			if (l.flags?.no_interview) {
				const capDecision = l.rows.find((r) =>
					r.type === "decision" && r.status === "active" && /capabilit/i.test(r.label || "")
				);
				if (!capDecision) {
					e.push(
						"capability-map (--no-interview): need an active decision row labelled *capabilit* recording the assumed map",
					);
				} else if (!l.capabilities.every((c) => String(capDecision.answer || "").includes(c.id))) {
					e.push("capability-map (--no-interview): the *capabilit* decision must name every capability id");
				}
			} else if (!approved("approve-capability-map")) {
				e.push("capability-map: >1 capability requires 'approve-capability-map' approval (by=user) before tasks");
			}
		}
		return e;
	},
	G4: (l, planText = "") => {
		const e = validateLedger(l).map((x) => `ledger: ${x}`);
		const tasks = l.rows.filter((r) => r.type === "task" && r.status === "active");
		if (!tasks.length) e.push("plan: 0 tasks");
		for (const t of tasks) {
			for (const k of ["files", "interfaces", "acceptance", "verify"]) {
				if (!t[k] || (Array.isArray(t[k]) && !t[k].length)) e.push(`plan: ${t.id} missing ${k}`);
			}
			if (l.flags.test_first) {
				// Hard evidence at planning time is the test contract, not a claim that red/green happened.
				if (!t.test_seam) {
					e.push(`plan: ${t.id} test-first is on (default) but no test_seam recorded — record one, or re-init with --no-test-first`);
				} else if (
					!/^.+\| catches: .+\| misses: .+\| class: (in-process|local-substitutable|remote-owned|true-external)$/i.test(
						String(t.test_seam).replace(/\s+/g, " ").trim(),
					)
				) {
					e.push(
						`plan: ${t.id} test_seam must read "<interface> | catches: ... | misses: ... | class: in-process|local-substitutable|remote-owned|true-external"`,
					);
				}
				if (!t.test_file) e.push(`plan: ${t.id} test-first is on but no test_file recorded`);
				if (!t.red) e.push(`plan: ${t.id} test-first is on but no red step recorded (the failing test and its expected failure)`);
				if (!t.green) e.push(`plan: ${t.id} test-first is on but no green step recorded (the minimal pass condition)`);
				if (l.flags?.test_runs) {
					const runs = (l.rows || []).filter((r) => r.type === "test_run" && r.task === t.id);
					if (!runs.some((r) => r.phase === "red")) e.push(`plan: ${t.id} requires a test_run row with phase "red" (--test-runs)`);
					if (!runs.some((r) => r.phase === "green")) e.push(`plan: ${t.id} requires a test_run row with phase "green" (--test-runs)`);
				}
				if (t.red && t.green && String(t.red).trim() === String(t.green).trim()) {
					e.push(`plan: ${t.id} red and green steps are identical (no observable change)`);
				}
				if (t.kind === "fix" && !/repro/i.test(String(t.red || ""))) {
					e.push(`plan: ${t.id} is a fix: the red step must name the failing repro test`);
				}
			} else {
				if (t.test_seam) e.push(`plan: ${t.id} has test_seam but --no-test-first was passed (test-first is off)`);
				if (t.test_file || t.red || t.green) e.push(`plan: ${t.id} has test-first fields but --no-test-first was passed (test-first is off)`);
			}
			if (planText && !planText.includes(t.id)) {
				e.push(`plan: plan.md does not mention task ${t.id} (render from the ledger)`);
			}
			// Kind rules (Prove-It for fixes, preserved behaviour for refactors, one concern per task).
			if (t.kind === "fix" && l.flags.test_first && !/repro/i.test(String(t.red || ""))) {
				e.push(`plan: ${t.id} is a fix: the red step must name a failing repro test (Prove-It)`);
			}
			if ((t.deps || []).length && planText) {
				const taskLine = String(planText)
					.split("\n")
					.map((x) => x.trimEnd())
					.find((line) => line.trim().startsWith("- [ ] " + t.id + "."));
				if (!taskLine || !taskLine.includes(`deps: ${t.deps.join(",")}`)) {
					e.push(`plan: plan.md does not render ${t.id}'s blocking edges (deps: ${t.deps.join(",")})`);
				}
			}
			if (t.kind === "refactor" && !/behaviou?r|unchanged|preserv|characteri[sz]/i.test(`${t.acceptance} ${t.steps || ""}`)) {
				e.push(`plan: ${t.id} is a refactor: acceptance/steps must state the preserved behaviour (characterization tests)`);
			}
			if (t.est_lines > 1000) e.push(`plan: ${t.id} est_lines ${t.est_lines} > 1000 — split it`);
			else if (t.est_lines > 500 && !SCRIPTED_RE.test(String(t.steps || ""))) {
				e.push(`plan: ${t.id} est_lines ${t.est_lines} > 500 — plan it as a codemod or scripted transform (name it in steps)`);
			}
			if ((t.files || []).some((x) => LOCKFILE_RE.test(x.replace(/:\d+(-\d+)?$/, "")))) {
				if (t.kind !== "chore" || !/changelog|release notes/i.test(String(t.acceptance || ""))) {
					e.push(`plan: ${t.id} edits a lockfile — must be kind chore and acceptance must record the changelog read and lockfile diff reviewed`);
				}
			}
			if (FAKE_DONE_RE.test([t.acceptance, t.verify, t.steps, t.interfaces].filter(Boolean).join(" \n"))) {
				e.push(`plan: ${t.id} fake completion marker (skip/only/TODO/not implemented) — these are blockers, not evidence`);
			}
		}
		// Ideal state: IDEAL rows are differences named by GAP rows, and every GAP has a delivering task.
		const idealRows = activeDecisions(l, /^ideal-/), gapRows = activeDecisions(l, /^gap-/);
		if (idealRows.length || gapRows.length) {
			const targets = [...idealRows, ...gapRows].map((r) => r.label);
			for (const t of tasks) {
				if (!(t.closes || []).length) e.push(`plan: ${t.id} must name the IDEAL or GAP it delivers (--closes ideal-<n>|gap-<n>)`);
				for (const c of t.closes || []) {
					if (!targets.includes(c)) e.push(`plan: ${t.id} closes '${c}' but no active ideal-* or gap-* decision exists`);
				}
			}
			for (const ideal of idealRows) {
				const delivered = tasks.some(
					(t) =>
						(t.closes || []).includes(ideal.label) ||
						(t.closes || []).some((c) =>
							gapRows.some((g) => g.label === c && String(g.answer || "").toLowerCase().includes(ideal.label.toLowerCase())),
						),
				);
				if (!delivered) e.push(`plan: ${ideal.label.toUpperCase()} has no delivering task (--closes ${ideal.label} or a gap naming it)`);
			}
			for (const g of gapRows) {
				if (!tasks.some((t) => (t.closes || []).includes(g.label))) {
					e.push(`plan: ${g.label} has no delivering task (task --closes ${g.label})`);
				}
			}
			if (!String(planText).includes("| Ideal |")) e.push("plan: success criteria table is missing");
		}
		if (planText) e.push(...executionErrors(l, planText));
		if (l.issue_type === "bug" && tasks.length && !tasks.some((t) => t.kind === "fix")) {
			e.push("plan: issue type bug requires at least one --kind fix task");
		}
		if (l.issue_type === "refactor" && tasks.length && !tasks.some((t) => t.kind === "refactor")) {
			e.push("plan: issue type refactor requires at least one --kind refactor task");
		}
		if (tasks.length && scopeSize(l) !== "S" && !skipped(l, "constraints")) {
			const bar = l.rows.some((r) => r.type === "decision" && r.status === "active" && r.label === "quality-bar");
			if (!bar) e.push("plan: no quality-bar decision (record one: decision --label quality-bar --decision <tests/lint/thresholds that must hold>), or re-init with --no-constraints");
		}
		if (!skipped(l, "adr")) {
			const adrs = l.rows.filter((r) => r.type === "decision" && r.status === "active" && r.adr);
			const conv = l.rows.some((r) => r.type === "fact" && r.status === "active" && r.label === "adr-convention");
			if (adrs.length && !conv) {
				e.push(`plan: ${adrs.map((d) => d.id).join(",")} marked --adr but no 'adr-convention' fact (detect the repo's ADR location/numbering first)`);
			}
			for (const d of adrs) {
				if (!d.adr_file) e.push(`plan: ${d.id} marked --adr but no adr_file path recorded (where the ADR will be written)`);
				else if (!/\.md$/i.test(String(d.adr_file))) e.push(`plan: ${d.id} adr_file must be a Markdown path`);
			}
		}
		// Spec's User Stories and Further Notes survive as required spec subsections.
		if (l.issue_type === "feature" && (l.size === "L" || l.scope_multi)) {
			const stories = l.rows.find((r) => r.type === "decision" && r.status === "active" && r.label === "user-stories");
			if (!stories || !/\bAs an?\b/i.test(String(stories.answer || ""))) {
				e.push("plan: feature plans need an active 'user-stories' decision with at least one 'As a ...' line");
			}
		}
		// A domain term closed during clarification must leave a glossary fact, not a prose claim.
		for (const q of l.rows.filter((r) => r.type === "question" && r.status === "answered" && r.domain_term)) {
			const term = l.rows.find((r) => r.type === "fact" && r.status === "active" && r.label === `term-${q.domain_term}`);
			if (!term) e.push(`plan: ${q.id} closed domain term '${q.domain_term}' but no active 'term-${q.domain_term}' fact was recorded`);
			else if (!/^GLOSSARY(?:-MAP)?\.md:/i.test(String(term.locator || ""))) {
				e.push(`plan: term-${q.domain_term} must cite GLOSSARY.md (or GLOSSARY-MAP.md) with a file:line locator`);
			}
		}
		for (const r of l.rows.filter((x) => x.type === "decision" && x.status === "active" && /^risk-/.test(x.label || ""))) {
			if (String(r.answer || "").split("|").filter((x) => x.trim()).length < 3) {
				e.push(`plan: ${r.label} needs a mitigation — write the decision as "<risk> | <H/M/L impact> | <mitigation>"`);
			}
		}
		const facts = l.rows.filter((r) => r.type === "fact" && r.status === "active");
		if (planText && facts.length && !facts.some((f) => planText.includes(f.id))) {
			e.push("plan: plan.md cites no ledger fact id (render from the ledger; evidence must be visible in the plan)");
		}
		if (/\b(TBD|to be determined|fill in later|placeholder|lorem ipsum)\b|\?\?\?|<fill/i.test(planText)) {
			e.push("plan: plan.md contains TBD/placeholder text");
		}
		// Anchored headings, in skeleton order (substring matches in prose do not count).
		const lines = planText.split("\n").map((x) => x.trimEnd());
		let last = -1;
		for (const s of sectionsFor(l)) {
			const idx = lines.indexOf(s, last + 1);
			if (idx === -1) {
				if (!lines.includes(s)) e.push(`plan: plan.md missing heading '${s}'`);
				else e.push(`plan: plan.md heading '${s}' is out of order`);
			} else last = idx;
		}
		if ((l.issues || []).length && !lines.includes("## Issues")) {
			e.push("plan: issues are declared but plan.md has no '## Issues' heading (render from the ledger)");
		}
		if ((l.capabilities || []).length > 1 && !lines.includes("## Capability map")) {
			e.push("plan: >1 capability requires a '## Capability map' heading in plan.md");
		}
		const approvedG4 = (token) =>
			(l.approvals || []).some(
				(a) => a.gate === "G4" && a.token === token && a.by === "user" && String(a.quote || "").trim().length > 0,
			);
		const needsTaskApproval =
			(Boolean(l.scope_multi) || (l.capabilities || []).length > 1 || (l.repos || []).length > 1 || l.size === "L") &&
			!skipped(l, "task-approval");
		if (needsTaskApproval && !approvedG4("approve-task-graph")) {
			e.push(
				"plan: multi-capability or size L requires 'approve-task-graph' approval (by=user) before publish (approve --gate G4 --token approve-task-graph --by user --quote \"<what the user said>\")",
			);
		}
		e.push(...cpmErrors(l, planText), ...todoMirrorErrors(l, planText), ...ownerConfirmErrors(l), ...repoErrors(l, planText));
		return e;
	},
	G5: (l, planText = "") => {
		// G0 already runs validateLedger; do not pay for it twice.
		const e = [];
		for (const g of ["G0", "G_AX", "G1", "G2", "G3", "G4"]) e.push(...GATES[g](l, planText).map((x) => `${g}: ${x}`));
		if (SIZES.indexOf(scopeSize(l)) > SIZES.indexOf(l.size)) {
			e.push(`size: claimed ${l.size} but the task graph derives ${scopeSize(l)} (understated size relaxed the earlier gates)`);
		}
		if (TEST_CLAIM_RE.test(String(planText || ""))) {
			const runs = (l.rows || []).filter((r) => r.type === "test_run");
			if (!runs.length) {
				e.push(
					"publish: plan.md claims a test run but no test_run row exists (record task, phase, cmd, exit and artifact)",
				);
			}
		}
		if (l.plan_sha256 !== sha256(planText)) {
			e.push("publish: plan_sha256 does not match plan.md (re-run publish after final edit)");
		}
		return [...new Set(e)];
	},
	// Map is a separate branch, not a planning phase: decisions only, no tasks.
	G_MAP: (l, mapText = "") => {
		const e = [];
		if (!l.map) {
			e.push("map: ledger is not in map mode (use init --map)");
			return e;
		}
		const dest = (l.rows || []).find((r) => r.type === "decision" && r.status === "active" && r.label === "destination");
		if (!dest || !String(dest.answer || "").trim()) {
			e.push("map: no destination decision (one or two lines naming the end state)");
		} else if (String(dest.answer).split("\n").filter((x) => x.trim()).length > 2) {
			e.push("map: destination must fit in one or two lines");
		}
		const signed = (l.approvals || []).some(
			(x) =>
				x.gate === "G_MAP" &&
				x.token === "map-destination" &&
				x.by === "user" &&
				String(x.quote || "").trim().length > 0,
		);
		if (!signed) {
			e.push(
				"map: no 'map-destination' approval with by=user and a quote (approve --gate G_MAP --token map-destination --by user --quote \"<the user's words>\")",
			);
		}
		if (l.unknowns_open !== false) e.push("map: unknowns are still recorded (list them, resolve them, then clear them)");
		const open = (l.rows || []).filter((r) => r.type === "question" && r.status === "active" && r.map);
		if (open.length) e.push(`map: open decision tickets: ${open.map((q) => q.id).join(",")}`);
		if (!l.rows.some((r) => r.type === "question" && r.map && r.status === "answered")) {
			e.push("map: no decision ticket has been resolved yet");
		}
		const headings = ["## Destination", "## Notes", "## Decisions so far", "## Not yet specified", "## Out of scope"];
		const lines = String(mapText || "").split("\n").map((x) => x.trim());
		for (const h of headings) if (!lines.includes(h)) e.push(`map: map.md missing heading '${h}'`);
		return e;
	},
};

export const PHASES = ["W0", "P0", "P1", "P2", "P3", "P4", "P5", "P6"];
export const phaseIndex = (p) => Math.max(0, PHASES.indexOf(p));
export const advancePhase = (l, gate) => {
	const next = { G0: "P1", G_AX: "P1", G1: "P2", G2: "P3", G3: "P4", G4: "P5", G_MAP: "P0" }[gate];
	if (next && phaseIndex(l.phase) < phaseIndex(next)) l.phase = next;
	if (gate === "publish") l.phase = "P6";
	return l.phase;
};

const activeDecisions = (l, re) =>
	(l.rows || []).filter((r) => r.type === "decision" && r.status === "active" && re.test(r.label || ""));
const cell = (x) => String(x ?? "").replace(/\|/g, "\\|").replace(/\r?\n/g, " ");
function taskWaves(tasks) {
	const byId = new Map(tasks.map((t) => [t.id, t]));
	const levels = new Map(), visiting = new Set();
	const level = (t) => {
		if (levels.has(t.id)) return levels.get(t.id);
		if (visiting.has(t.id)) return 0;
		visiting.add(t.id);
		let n = 0;
		for (const d of t.deps || []) {
			const dep = byId.get(d);
			if (dep) n = Math.max(n, level(dep) + 1);
		}
		visiting.delete(t.id);
		levels.set(t.id, n);
		return n;
	};
	for (const t of tasks) level(t);
	const max = tasks.reduce((m, t) => Math.max(m, levels.get(t.id) || 0), 0);
	return Array.from({ length: max + 1 }, (_, n) => tasks.filter((t) => levels.get(t.id) === n).map((t) => t.id));
}
function executionSection(l) {
	const tasks = (l.rows || []).filter((r) => r.type === "task" && r.status === "active");
	if (!tasks.length) {
		return "## Execution strategy\n\n### Parallel waves\n\nNone yet.\n\n### Dependency matrix\n\nNone yet.\n";
	}
	const waves = taskWaves(tasks);
	const waveOf = new Map(waves.flatMap((ids, n) => ids.map((id) => [id, n])));
	const blocks = new Map(tasks.map((t) => [t.id, []]));
	for (const t of tasks) for (const d of t.deps || []) if (blocks.has(d)) blocks.get(d).push(t.id);
	const rows = tasks.map((t) => {
		const same = waves[waveOf.get(t.id)].filter((id) => id !== t.id && !(t.deps || []).includes(id));
		return `| ${t.id} | ${(t.deps || []).join(", ") || "—"} | ${blocks.get(t.id).join(", ") || "—"} | ${same.join(", ") || "—"} |`;
	});
	return [
		"## Execution strategy",
		"",
		"### Parallel waves",
		"",
		...waves.map((ids, n) => `- Wave ${n + 1}: ${ids.join(", ")}`),
		"",
		"### Dependency matrix",
		"",
		"| Task | Depends on | Blocks | Parallel with |",
		"|---|---|---|---|",
		...rows,
		"",
		...cpmLines(tasks),
		...todoMirrorLines(l),
	].join("\n");
}
function successCriteriaSection(l) {
	const idealRows = activeDecisions(l, /^ideal-/), gaps = activeDecisions(l, /^gap-/);
	if (!idealRows.length && !gaps.length) return l.intent?.success || "Not recorded.";
	if (!idealRows.length) return `GAP rows: ${gaps.map((g) => g.label).join(", ")}. No IDEAL rows recorded.`;
	const tasks = (l.rows || []).filter((r) => r.type === "task" && r.status === "active");
	const rows = idealRows.map((ideal) => {
		const gs = gaps.filter((g) => String(g.answer || "").toLowerCase().includes(ideal.label.toLowerCase()));
		const ts = tasks.filter(
			(t) => (t.closes || []).includes(ideal.label) || (t.closes || []).some((c) => gs.some((g) => g.label === c)),
		);
		return `| ${ideal.label.toUpperCase()} | ${cell(ideal.answer)} | ${gs.map((g) => g.label).join(", ") || "—"} | ${ts.map((t) => t.id).join(", ") || "unmapped"
			} | ${ts.map((t) => t.verify || "").filter(Boolean).join(" / ") || "unmapped"} |`;
	});
	return ["| Ideal | Statement | Gaps | Delivering tasks | Proving verify |", "|---|---|---|---|---|", ...rows].join("\n");
}
function tldrSection(l) {
	const risks = activeDecisions(l, /^risk-/).map((r) => r.label).join(", ") || "not recorded";
	const top = activeDecision(l, "top-recommendation")?.answer || decisionText(l, "further-notes") || "none";
	return [
		"## TL;DR (For humans)",
		"",
		`**Who this is for:** ${l.intent?.user || "Not recorded."}`,
		`**What changes:** ${l.intent?.outcome || "Not recorded."}`,
		`**Why now:** ${l.intent?.why_now || "Not recorded."}`,
		`**What it will NOT do:** ${l.intent?.out_of_scope || "Not recorded."}`,
		`**Effort:** ${l.size}. **Risk:** ${risks}.`,
		`**Decisions to sanity-check:** ${top}`,
		"**Next move:** approve the design with a quote, then publish and hand off.",
		"",
	].join("\n");
}

const PLAN_SECTIONS = [
	"## TL;DR (For humans)",
	"## Intent",
	"## Evidence",
	"## Decisions",
	"## Spec",
	"### Objective",
	"### User stories",
	"### Commands",
	"### Project structure",
	"### Code style",
	"### Testing strategy",
	"### Boundaries",
	"### Success criteria",
	"### Open questions",
	"### Further notes",
	"## Execution strategy",
	"### Parallel waves",
	"### Dependency matrix",
	"## Tasks",
	"## Verification and review plan",
	"## Risks",
	"## Out of scope",
	"## Handoff",
];
const sectionsFor = (l) =>
	PLAN_SECTIONS.filter((x) =>
		!(x === "## Verification and review plan" && skipped(l, "review-section")) && !(x === "## Handoff" && skipped(l, "handoff"))
	);
const FAKE_DONE_RE = /\b(test\.skip|it\.skip|describe\.skip|xit|xdescribe|TODO|FIXME|unimplemented|not implemented)\b|\.only\(/i;

const decisionText = (l, label) => (l.rows || []).find((r) => r.type === "decision" && r.status === "active" && r.label === label)?.answer || "";

function buildOrder(caps) {
	const left = new Map(caps.map((c) => [c.id, new Set(c.depends_on || [])]));
	const levels = [];
	while (left.size) {
		const ready = [...left].filter(([, d]) => [...d].every((x) => !left.has(x))).map(([id]) => id);
		if (!ready.length) return caps.map((c) => c.id).join(" -> "); // cycle: validateLedger reports it
		levels.push(ready.join(", "));
		for (const id of ready) left.delete(id);
	}
	return levels.join(" -> ");
}

export function planSkeleton(l) {
	// One pass over rows: partition tasks/decisions/open questions/facts/risks.
	const taskLines = [], decisionLines = [], openQLines = [], factLines = [], riskLines = [];
	for (const r of l.rows || []) {
		if ((r.type === "task" || r.type === "decision") && r.status !== "active") continue;
		if (r.type === "decision" && /^risk-/.test(r.label || "")) riskLines.unshift(`- ${r.label}: ${r.answer || ""}`);
		if (r.type === "task") {
			taskLines.push(
				`- [ ] ${r.id}. ${r.label}${r.kind ? ` [${r.kind}]` : ""}${r.issue ? ` (${r.issue})` : ""} — files: ${(r.files || []).join(", ")}; deps: ${(r.deps || []).join(",") || "none"
				}; interfaces: ${r.interfaces || ""}; acceptance: ${r.acceptance || ""}; verify: ${r.verify || ""}${r.test_seam ? `; test-seam: ${r.test_seam}` : ""
				}${r.test_file ? `; test-file: ${r.test_file}` : ""}${r.red ? `; red: ${r.red}` : ""}${r.green ? `; green: ${r.green}` : ""}${(r.closes || []).length ? `; closes: ${(r.closes || []).join(",")}` : ""}${r.repo ? `; repo: ${r.repo}` : ""}${r.effort ? `; effort: ${r.effort}` : ""}${r.category ? `; category: ${r.category}` : ""
				}`,
			);
		} else if (r.type === "decision") {
			decisionLines.push(`- ${r.id} ${r.label}${r.adr ? ` [ADR${r.adr_file ? `: ${r.adr_file}` : ""}]` : ""}: ${r.answer || r.quote || ""}`);
		}
		else if (r.type === "question" && r.status === "active") openQLines.push(`- ${r.id} ${r.label}: ${r.quote || ""}`);
		else if (r.type === "fact" && r.status === "active") {
			factLines.push(`- ${r.id} ${r.label} [${r.kind || ""}] ${r.locator || ""}${r.axis ? ` axis=${r.axis}` : ""}`);
			if (r.kind === "assumed") riskLines.push(`- Assumed ${r.id} ${r.label}: ${r.quote || r.locator || ""}`);
		}
	}
	const capSection = (l.capabilities || []).length
		? `\n## Capability map\n\n| Module id | Responsibility | Depends on |\n|---|---|---|\n${l.capabilities.map((c) => `| ${c.id} | ${c.responsibility} | ${(c.depends_on || []).join(", ") || "—"} |`).join(
			"\n",
		)
		}\n\nBuild order: ${buildOrder(l.capabilities)}\n`
		: "";
	const assumed = l.flags?.no_interview
		? "\nMode: --no-interview (intent assumed from request + evidence; see assumed facts/decisions)\n"
		: "";
	const issueSection = (l.issues || []).length
		? `\n## Issues\n\n${l.issues.map((i) => `- ${i.ref}${i.title ? ` — ${i.title}` : ""}`).join("\n")}\n`
		: "";
	const repoSection = (l.repos || []).length
		? "\n## Repos\n\n| Repo | Path | Role |\n|---|---|---|\n" + l.repos.map((r) => "| " + r.id + " | " + r.path + " | " + (r.role || "—") + " |").join("\n") + "\n\nTask files are relative to the task's repo. Tasks in different repos run in parallel when no dependency links them; tasks that share a repo and a file are serialized.\n"
		: "";
	const adrs = (l.rows || []).filter((r) => r.type === "decision" && r.adr && r.status === "active");
	const reviewSection = [
		"",
		"## Verification and review plan",
		"",
		"Two review axes, reported separately and never merged or reranked. Standards: the change against this repo's documented standards (cite file and rule; baseline smells such as duplicated code, feature envy and speculative generality are judgement calls; skip what tooling already enforces). Spec: the change against this plan (requirements missing or partial, behaviour not asked for, implemented but wrong; quote the plan line).",
		"Lenses under each axis: correctness, readability and simplicity, architecture (a refactor must reduce concepts, not relocate them), security (external data is untrusted), performance. Review the tests first and check they would catch a regression.",
		"Severity labels: Critical (blocks merge), Required, Optional, Nit, FYI. Zero findings is a valid result. Presumptive blockers: relocated complexity, feature logic in a shared module, a near-duplicate of a canonical helper, a file pushed past about 1000 lines without decomposition, a silent fallback hiding an unclear invariant.",
		"Change size: about 100 lines good, about 300 acceptable as one logical change, about 1000 gets split; over 500 is a codemod. Refactors ship separately from features. Dependency upgrades: one package per change, changelog read, lockfile diff reviewed. Orphaned code is listed and its removal asked, never assumed.",
		"Quality bar: never weaken, skip or delete a test to go green; thresholds are never lowered; no new suppressions. The reviewer is a fresh context given the requirements, base and head, and this plan's hash, never the session history, and never the author.",
		"ADRs to write: " + (adrs.length ? adrs.map((d) => d.id).join(", ") : "none (no decision passed the hard-to-reverse + surprising + real-trade-off test)"),
		"Per-task verification is the verify field of each task; a fresh run in the executing session is the only evidence.",
		"",
		"### Final verification wave",
		"",
		"When executing, F1 plan compliance audit, F2 code quality review, F3 real manual QA and F4 ideal-state fidelity run in parallel after all tasks; all must approve; surface the results and wait for the owner's explicit okay before declaring complete. Planning never runs this wave.",
		"",
	].join("\n");
	const handoffSection = [
		"",
		"## Handoff",
		"",
		"Planning ends at the published plan_sha256. Execution is a separate session the user starts (for example `/ulw-execute` on this plan, or mass-ulw with the `dag` export); this plan carries no executor rules. Branch: " + (l.branch || "none") + "; planning makes no commits.",
		"Read-only exports from the ledger: `node scripts/planning.mjs cpm|dag|todos|frontier --slug " + l.slug + "`; `dag` and `todos` also write dag.json and todos.json beside this plan.",
		"",
		"### Commit strategy",
		"",
		"One concern per commit; stage explicit paths; use `type(scope): imperative summary`; never commit a failing suite, a skipped test or a weakened threshold. Planning makes no commits.",
		"",
	].join("\n");
	const sections = { review: skipped(l, "review-section") ? "" : reviewSection, handoff: skipped(l, "handoff") ? "" : handoffSection };
	const tldr = tldrSection(l), execution = executionSection(l), success = successCriteriaSection(l);
	return `# Plan: ${l.slug} (${l.issue_type}, size ${l.size})\n${assumed}\n${tldr}\n## Intent\n\nOutcome: ${l.intent?.outcome || ""}\nUser: ${l.intent?.user || ""
		}\nWhy now: ${l.intent?.why_now || ""}\nConstraint: ${l.intent?.constraint || ""}\n\n## Evidence\n\nAxes: ${(l.axes || []).map((a) => a.label).join(", ")
		}\nSaturation waves: ${(l.waves || []).map((w) => w.new_facts).join(",")}\n\n${factLines.join("\n")
		}\n${issueSection}${repoSection}\n## Decisions\n\n${decisionLines.join("\n")}\n${capSection}\n## Spec\n\n### Objective\n\n${l.intent?.outcome || ""
		}\n\n### User stories\n\n${decisionText(l, "user-stories") || "None recorded."}\n\n### Commands\n\n${decisionText(l, "commands") || "Verify per task (see Tasks). Build/test commands are recorded on each task's verify field."}\n\n### Project structure\n\nSee each task's files list.\n\n### Code style\n\nFollow the repo's existing conventions in the files each task touches.\n\n### Testing strategy\n\n${l.flags?.test_first
			? "test-first on (default): every task has a test_seam; steps are red -> green per seam."
			: "test-first off (--no-test-first): no test-first steps; each task verifies with its stated command."
		}\n\n### Boundaries\n\n${decisionText(l, "boundaries") ? `${decisionText(l, "boundaries")}\n\n` : ""}Planning rules:\n- Always: work from this plan and the ledger; keep the ledger append-only.\n- Ask first: anything that changes scope, the capability map, or a settled decision.\n- Never: open a PR, commit, or implement from within the planning skill.\n\n### Success criteria\n\n${success}\n\n### Open questions\n\n${openQLines.join("\n") || "None."}\n\n### Further notes\n\n${decisionText(l, "further-notes") || "None."
		}\n\n${execution}\n## Tasks\n\n${taskLines.join("\n")
		}\n${sections.review}\n## Risks\n\n${riskLines.join("\n") || "- No assumed facts recorded; risks are carried in the decisions and open questions above."
		}\n\n## Out of scope\n\n${l.intent?.out_of_scope || ""}\n${sections.handoff}`;
}

// The map is an index of decisions, never a task plan.
export function mapSkeleton(l) {
	const dest = decisionText(l, "destination") || "_Not yet named._";
	const notes = decisionText(l, "notes") || "None.";
	const decided = (l.rows || [])
		.filter((r) => r.type === "decision" && r.status === "active" && !["destination", "notes"].includes(r.label))
		.map((r) => `- ${r.label}: ${r.answer || ""}`)
		.join("\n");
	const open = (l.rows || [])
		.filter((r) => r.type === "question" && r.status === "active" && r.map)
		.map((r) => `- ${r.label} (${r.map}): ${r.quote || ""}`)
		.join("\n");
	const unknownItems = (l.unknown_items || []).length
		? l.unknown_items.map((x) => `- ${x}`).join("\n")
		: l.unknowns_open
			? "- (unknowns recorded, not yet itemized)"
			: "None - the way is clear.";
	return `# Map: ${l.slug}\n\n## Destination\n\n${dest}\n\n## Notes\n\n${notes}\n\n## Decisions so far\n\n${decided || "None."
		}\n\n## Not yet specified\n\n${unknownItems}\n\n## Open decision tickets\n\n${open || "None."}\n\n## Out of scope\n\n${l.intent?.out_of_scope || "None."
		}\n`;
}

// Advisory only (never a gate): splitting is a judgement; counting files is not.
export function taskWarnings(l) {
	const w = [];
	for (const t of l.rows || []) {
		if (t.type !== "task" || t.status !== "active") continue;
		if ((t.files || []).length > 5) w.push(`${t.id}: touches ${t.files.length} files (>5) — consider splitting`);
		if (t.est_lines > 300 && t.est_lines <= 1000) w.push(`${t.id}: est_lines ${t.est_lines} (>300) — acceptable only as one logical change`);
		const bullets = String(t.acceptance || "").split(/[;\n]/).filter((x) => x.trim()).length;
		if (bullets > 3) w.push(`${t.id}: ${bullets} acceptance bullets (>3) — consider splitting`);
	}
	return w;
}

// Active questions whose blockers are all settled (answered/superseded/retracted) or absent.
export function designFrontier(l) {
	return (l.rows || []).filter(
		(r) =>
			r.type === "question" &&
			r.status === "active" &&
			(r.blocked_by || []).every((dep) => {
				const d = (l.rows || []).find((x) => x.id === dep);
				return !d || d.status !== "active";
			}),
	);
}

// Tasks ready to start: active, not done, every dep done.
export function frontier(l, done = []) {
	const doneSet = new Set(done);
	return (l.rows || [])
		.filter((t) => t.type === "task" && t.status === "active" && !doneSet.has(t.id))
		.filter((t) => (t.deps || []).every((d) => doneSet.has(d)))
		.map((t) => t.id);
}

// One ticket draft per task (tracer-bullet slice). Drafts only: publishing to a tracker is the user's call.
export function renderIssues(l) {
	const tasks = (l.rows || []).filter((t) => t.type === "task" && t.status === "active");
	const file = new Map(tasks.map((t, i) => [t.id, `${String(i + 1).padStart(2, "0")}-${t.label}.md`]));
	const label = l.plan_sha256 ? "ready-for-agent" : "needs-triage";
	return tasks.map((t) => ({
		file: file.get(t.id),
		body: `# ${t.label}\n\nLabels: ${label}\nParent plan: ${planDir(l.issue_type, l.slug).replaceAll("\\", "/")}/plan.md\n${t.issue ? `Source issue: ${t.issue}\n` : ""
			}\n## What to build\n\nInterfaces: ${t.interfaces}\n\n## Blocked by\n\nBlocked by: ${(t.deps || []).map((d) => file.get(d)?.replace(/\.md$/, "")).filter(Boolean).join(", ") || "none"
			}\n\n## Acceptance\n\n${t.acceptance}\n\n## Verify\n\n${t.verify}\n${(t.closes || []).length ? `\nCloses: ${(t.closes || []).join(", ")}\n` : ""
			}${t.test_seam ? `\nTest seam: ${t.test_seam}\nSteps: ${t.steps || ""}\n` : ""}`,
	}));
}

function readJson(p) {
	return JSON.parse(readFileSync(p, "utf8"));
}
function writeJsonAtomic(p, obj) {
	mkdirSync(dirname(p), { recursive: true });
	const tmp = `${p}.tmp-${process.pid}`;
	writeFileSync(tmp, JSON.stringify(obj, null, 2) + "\n");
	renameSync(tmp, p);
}
const BOOLEAN_ARGS = new Set([
	"test-first",
	"no-test-first",
	"no-interview",
	"no-branch",
	"multi",
	"confirm",
	"assume",
	"external",
	"force",
	"adr",
	"irreversible",
	"no-doubt",
	"no-plan-review",
	"no-review-section",
	"no-handoff",
	"no-adr",
	"no-constraints",
	"lean",
	"map",
	"deliberate",
	"clean",
	"fact-lane",
	"clear",
	"test-runs",
	"no-task-approval",
	"no-sweep",
	"no-cpm",
]);
const KNOWN_FLAGS = new Set([
	...BOOLEAN_ARGS, "slug", "type", "issue", "size", "label", "ref", "title", "id", "responsibility", "deps", "kind",
	"locator", "axis", "source", "sha", "quote", "question", "answer", "decision", "claim", "cycle", "findings", "total", "closes",
	"class", "files", "interfaces", "acceptance", "verify", "test-seam", "steps", "est-lines", "file", "outcome", "user",
	"why-now", "success", "constraint", "out-of-scope", "by", "gate", "token", "reason", "replacement", "done", "ledger",
	"blocked-by", "domain-term", "test-file", "red", "green", "adr-file", "scope", "asks", "review", "note", "artifact", "exit", "add",
	"phase", "task", "cmd", "recommend", "recommendation", "effort", "category", "path", "role", "repo", "from",
]);
function args(argv) {
	const out = { _: [] };
	for (let i = 0; i < argv.length; i++) {
		const a = argv[i];
		if (!a.startsWith("--")) {
			out._.push(a);
			continue;
		}
		const k = a.slice(2), nxt = argv[i + 1];
		if (BOOLEAN_ARGS.has(k)) {
			if (nxt === "true" || nxt === "false") {
				out[k] = nxt === "true";
				i++;
			} else out[k] = true;
		} else if (!KNOWN_FLAGS.has(k)) {
			fail([`unknown flag --${k}`]);
		} else if (nxt === undefined || nxt.startsWith("--")) {
			fail([`--${k} requires a value`]);
		} else {
			const v = argv[++i];
			out[k] = k === "issue" && out[k] ? `${out[k]},${v}` : v;
		}
	}
	return out;
}
// External-evidence check (CLI only; the pure GATES stay importable without a filesystem):
// a code locator must resolve to a real file and line, an external fact to a real snapshot whose hash matches.
function repoRootFromLedgerDir(ledgerDir) {
	const s = String(ledgerDir || "");
	if (/[\\/]maps[\\/]/.test(s) || /[\\/]maps$/.test(s)) {
		return resolve(ledgerDir, "..", "..", "..");
	}
	return resolve(ledgerDir, "..", "..", "..", "..");
}

export function evidenceErrors(l, ledgerDir, root = null) {
	const baseRoot = root ? resolve(root) : repoRootFromLedgerDir(ledgerDir);
	const e = [];
	for (const r of l.rows || []) {
		if (r.type !== "fact" || r.status !== "active" || !r.locator) continue;
		if (/^https?:\/\//.test(r.locator)) {
			if (!r.external) {
				e.push(`evidence: ${r.id} URL fact must be recorded with --external and a snapshot (--source S<n> --sha <sha256>)`);
				continue;
			}
			const dir = join(ledgerDir, "sources", r.source_id || "");
			const files = existsSync(dir) ? readdirSync(dir).filter((f) => statSync(join(dir, f)).isFile()) : [];
			if (files.length !== 1) {
				e.push(`evidence: ${r.id} external fact requires exactly one regular file under sources/${r.source_id || ""}/ (found ${files.length})`);
				continue;
			}
			const h = createHash("sha256").update(readFileSync(join(dir, files[0]))).digest("hex");
			if (h !== r.snapshot_sha256) {
				e.push(`evidence: ${r.id} snapshot hash mismatch (ledger ${r.snapshot_sha256}, file ${h})`);
			}
		} else {
			const m = /^(.+):(\d+)(?:-(\d+))?$/.exec(r.locator);
			if (!m) continue; // e.g. request — a request reference, not a file
			if (m[1].includes("://")) continue; // scheme-like, not a local path
			// A path has a separator or a file extension; bare references like request:1 are not paths.
			if (!/[\\/]/.test(m[1]) && !/\.[A-Za-z0-9]+$/.test(m[1])) continue;
			const rp = r.repo ? (l.repos || []).find((x) => x.id === r.repo) : null;
			const p = resolve(rp ? resolve(baseRoot, rp.path) : baseRoot, m[1]);
			if (!existsSync(p)) {
				e.push(`evidence: ${r.id} locator file not found: ${m[1]}`);
				continue;
			}
			const lines = readFileSync(p, "utf8").split("\n").length;
			if (Number(m[3] || m[2]) > lines) e.push(`evidence: ${r.id} locator ${r.locator} is past end of file (${lines} lines)`);
		}
	}
	// ADR files referenced by active decisions must resolve against the repo root.
	for (const r of l.rows || []) {
		if (r.type !== "decision" || r.status !== "active") continue;
		if (r.adr && r.adr_file) {
			const p = resolve(baseRoot, r.adr_file);
			if (!existsSync(p)) {
				e.push(`evidence: ${r.id} adr_file not found: ${r.adr_file}`);
			}
		}
	}
	return e;
}
// ---- Multi-repo: one plan and ledger over several repos; sources are assimilated, then purged after publish. ----
function repoPath(l, id) {
	return (l.repos || []).find((r) => r.id === id)?.path ?? id;
}
export function repoErrors(l, planText) {
	if (!(l.repos || []).length) return [];
	const e = [];
	const ids = new Set(l.repos.map((r) => r.id));
	for (const t of (l.rows || []).filter((r) => r.type === "task" && r.status === "active")) {
		if (!t.repo) e.push("plan: " + t.id + " has no --repo (a multi-repo plan names the repo every task works in)");
		else if (!ids.has(t.repo)) e.push("plan: " + t.id + " names undeclared repo " + t.repo);
	}
	if (!String(planText || "").split("\n").map((x) => x.trimEnd()).includes("## Repos")) {
		e.push("plan: repos are declared but plan.md has no '## Repos' heading (render from the ledger)");
	}
	return e;
}
const ledgerFileSha = (p) => sha256(readFileSync(p, "utf8"));
export function assimilateLedger(l, src, { repoId = null, dir, sha }) {
	const tag = String(src.slug || "src").slice(0, 12);
	const used = new Set((l.rows || []).map((r) => r.label));
	const uniq = (label) => {
		const base = (tag + "-" + label).slice(0, 32);
		let c = base, n = 1;
		while (used.has(c)) c = (base.slice(0, 28) + "-" + ++n).slice(0, 32);
		used.add(c);
		return c;
	};
	const idMap = new Map();
	const n = { decisions: 0, facts: 0, tasks: 0, tasks_skipped: 0, external_skipped: 0 };
	const active = (src.rows || []).filter((r) => r.status === "active");
	for (const r of active) {
		if (r.type === "decision") {
			idMap.set(r.id, addRow(l, { type: "decision", label: uniq(r.label), answer: r.answer || "", adr: false, adr_file: null, irreversible: Boolean(r.irreversible) }).id);
			n.decisions++;
		} else if (r.type === "fact") {
			if (r.external || /^https?:\/\//.test(String(r.locator || ""))) {
				n.external_skipped++;
				continue;
			}
			idMap.set(r.id, addRow(l, { type: "fact", kind: r.kind || "quote", label: uniq(r.label), locator: r.locator, quote: r.quote || null, axis: null, repo: repoId, wave: (l.waves || []).length + 1 }).id);
			n.facts++;
		}
	}
	const tasks = active.filter((r) => r.type === "task");
	if (phaseIndex(l.phase) < phaseIndex("P4")) n.tasks_skipped = tasks.length;
	else {
		for (const t of tasks) {
			idMap.set(t.id, addRow(l, { type: "task", label: uniq(t.label), files: t.files || [], interfaces: t.interfaces || "", acceptance: t.acceptance || "", verify: t.verify || "", deps: [], test_seam: t.test_seam || null, test_file: t.test_file || null, red: t.red || null, green: t.green || null, steps: t.steps || null, kind: t.kind || "feature", issue: null, est_lines: t.est_lines ?? null, closes: [], effort: t.effort ?? null, category: t.category || null, repo: repoId }).id);
			n.tasks++;
		}
		for (const t of tasks) {
			const row = l.rows.find((r) => r.id === idMap.get(t.id));
			row.deps = (t.deps || []).map((d) => idMap.get(d)).filter(Boolean);
		}
	}
	(l.sources ||= []).push({ slug: src.slug, dir, sha256: sha, repo: repoId, ...n, purged: false });
	return n;
}
// Deletes assimilated source plans and registered chats. Run after publish only; every skip is recorded, never silent.
export function purgeSuperseded(l, currentDir) {
	const out = [];
	const cur = resolve(currentDir).replace(/\\/g, "/");
	const note = (kind, p, status) => {
		if ((l.purges ||= []).some((x) => x.path === p && x.status === status)) return;
		const entry = { at: new Date().toISOString(), kind, path: p, status };
		l.purges.push(entry);
		out.push(entry);
	};
	for (const s of l.sources || []) {
		if (s.purged) continue;
		const d = resolve(s.dir);
		const norm = d.replace(/\\/g, "/");
		if (!existsSync(d)) {
			s.purged = true;
			note("plan", d, "already-gone");
			continue;
		}
		if (!/\/\.rigor\/(?:plans|maps)\//.test(norm + "/") || !existsSync(join(d, "ledger.json"))) {
			note("plan", d, "skipped-not-a-plan-dir");
			continue;
		}
		if (norm === cur || cur.startsWith(norm + "/")) {
			note("plan", d, "skipped-current-plan");
			continue;
		}
		if (s.external_skipped > 0) {
			note("plan", d, "skipped-external-evidence-not-carried");
			continue;
		}
		if (ledgerFileSha(join(d, "ledger.json")) !== s.sha256) {
			note("plan", d, "skipped-changed-since-assimilation");
			continue;
		}
		rmSync(d, { recursive: true, force: true });
		s.purged = true;
		note("plan", d, "purged");
	}
	for (const c of l.chats || []) {
		if (c.purged) continue;
		if (!existsSync(c.path)) {
			c.purged = true;
			note("chat", c.path, "already-gone");
			continue;
		}
		if (!statSync(c.path).isFile()) {
			note("chat", c.path, "skipped-not-a-file");
			continue;
		}
		unlinkSync(c.path);
		c.purged = true;
		note("chat", c.path, "purged");
	}
	return out;
}
function fail(errors) {
	console.error(errors.map((e) => `ERROR ${e}`).join("\n"));
	process.exit(1);
}

function resolveLedgerPath(a) {
	if (a.ledger) return a.ledger;
	if (!a.slug) return null;
	if (a.type) {
		const p = join(planDir(a.type, a.slug), "ledger.json");
		if (!existsSync(p)) fail([`ledger not found: ${p}`]);
		return p;
	}
	const mapHit = join(".rigor", "maps", a.slug, "ledger.json");
	const mapExists = existsSync(mapHit);
	const planHits = ISSUE_TYPES.map((t) => join(planDir(t, a.slug), "ledger.json")).filter((p) => existsSync(p));
	if (mapExists && planHits.length > 0) {
		fail([`slug '${a.slug}' exists under several issue types (${[mapHit, ...planHits].join(", ")}); pass --type <issue-type>`]);
	}
	if (mapExists) return mapHit;
	if (planHits.length > 1) {
		fail([`slug '${a.slug}' exists under several issue types (${planHits.join(", ")}); pass --type <issue-type>`]);
	}
	if (planHits.length === 1) return planHits[0];
	return join(planDir("feature", a.slug), "ledger.json");
}

// A review header is only a pointer to persisted finding rows; counts are derived by G3.
function recordReview(l, en) {
	const cycle = +en.cycle;
	const scope = splitList(en.scope);
	const clean = Boolean(en.clean);
	(l.plan_reviews ||= []).push({ cycle, clean, scope, at: new Date().toISOString() });
	return cycle;
}

function recordDoubt(l, d, en) {
	const cycle = +en.cycle;
	const scope = splitList(en.scope);
	const clean = Boolean(en.clean);
	(l.doubts ||= []).push({ decision: d.id, cycle, claim: en.claim, clean, scope, at: new Date().toISOString() });
	return cycle;
}

const splitList = (v) => String(v === true || v === undefined ? "" : v).split(",").map((x) => x.trim()).filter(Boolean);

export function main(argv = process.argv.slice(2)) {
	const [cmd, ...rest] = argv;
	const a = args(rest);
	const ledgerPath =
		cmd === "init" ? null : cmd === "map-handoff" ? join(".rigor", "maps", a.slug || "", "ledger.json") : resolveLedgerPath(a);
	if (cmd === "init") {
		if (!SLUG_RE.test(a.slug || "")) fail([`slug must match ${SLUG_RE}`]);
		if (a["test-first"] && a["no-test-first"]) fail(["--test-first and --no-test-first together: pick one (test-first defaults on)"]);
		const issueType = a.type === undefined ? "feature" : a.type;
		if (!ISSUE_TYPES.includes(issueType)) fail([`--type must be one of ${ISSUE_TYPES.join("|")}`]);
		const mapSize = a.size === undefined ? "L" : a.size;
		if (!SIZES.includes(mapSize)) fail([`--size must be one of ${SIZES.join("|")}`]);
		if (a.map) {
			// Unknowns branch: a map of decision tickets, never a task plan.
			const dir = join(".rigor", "maps", a.slug), lp = join(dir, "ledger.json");
			if (existsSync(lp)) {
				console.log(`exists: ${lp} (map no-op)`);
				return;
			}
			const wf = emptyLedger({
				slug: a.slug, issueType: "evidence", branch: null, branchReason: "non-git",
				test_first: false, noInterview: false, noBranch: true, skip: [...SKIPPABLE], size: mapSize,
			});
			wf.map = { map: true };
			wf.unknowns_open = true;
			wf.phase = "W0";
			wf.flags.test_first = false;
			wf.intent.out_of_scope = "";
			writeJsonAtomic(lp, wf);
			writeFileSync(join(dir, "map.md"), mapSkeleton(wf));
			console.log(`map: ${lp} map=${join(dir, "map.md")} (decisions only; handoff when G_MAP passes)`);
			return;
		}
		const issueRefs = splitList(a.issue);
		for (const ref of issueRefs) if (!ISSUE_REF_RE.test(ref)) fail([`--issue '${ref}' must be owner/repo#number`]);
		const dir = planDir(issueType, a.slug), lp = join(dir, "ledger.json");
		const want = {
			test_first: a["test-first"] === false ? false : !a["no-test-first"],
			no_interview: Boolean(a["no-interview"]),
			no_branch: Boolean(a["no-branch"]),
			deliberate: Boolean(a.deliberate),
			sweep: !a["no-sweep"],
			cpm: !a["no-cpm"],
		};
		const skip = a.lean ? [...SKIPPABLE] : SKIPPABLE.filter((k) => a[`no-${k}`]);
		const size = a.size === undefined ? "L" : a.size;
		if (!SIZES.includes(size)) fail([`--size must be one of ${SIZES.join("|")}`]);
		if (existsSync(lp)) {
			const old = readJson(lp), diff = Object.keys(want).filter((k) => Boolean(old.flags?.[k]) !== want[k]);
			if (diff.length) {
				fail([
					`ledger already exists with different flags (${diff.join(", ")
					}); flags are set once at init — use a new slug or the stored flags`,
				]);
			}
			const oldSkip = [...(old.flags?.skip || [])].sort().join(","), newSkip = [...skip].sort().join(",");
			if (oldSkip !== newSkip || old.size !== size) {
				fail([`ledger already exists with different feature flags/size; flags are set once at init — use a new slug`]);
			}
			console.log(`exists: ${lp} (no-op, flags match)`);
			return;
		}
		// Auto branch is an action, not a string: create/switch it when in a git repo.
		let branch = null, branchReason = "non-git";
		if (want.no_branch) branchReason = "no-branch";
		else if (size === "S") branchReason = "size-s";
		else {
			const inRepo =
				spawnSync("git", ["rev-parse", "--is-inside-work-tree"], { encoding: "utf8" }).stdout?.trim() === "true";
			if (inRepo) {
				branch = `plan/${a.slug}`;
				branchReason = "git";
				const made = spawnSync("git", ["switch", "-c", branch], { encoding: "utf8" });
				if (made.status !== 0) spawnSync("git", ["switch", branch], { encoding: "utf8" });
			}
		}
		const l = emptyLedger({
			slug: a.slug,
			issueType,
			branch,
			branchReason,
			test_first: want.test_first,
			noInterview: want.no_interview,
			noBranch: want.no_branch,
			deliberate: want.deliberate,
			testRuns: Boolean(a["test-runs"]),
			sweep: want.sweep,
			cpm: want.cpm,
			skip,
			size,
		});
		if (a.multi) l.scope_multi = true;
		l.issues = issueRefs.map((ref) => ({ ref }));
		const skeleton = planSkeleton(l);
		l.render_sha256 = sha256(skeleton);
		writeJsonAtomic(lp, l);
		writeFileSync(join(dir, "plan.md"), skeleton);
		console.log(
			`init: ${lp} type=${issueType} branch=${l.branch} (${branchReason}) test_first=${l.flags.test_first} no_interview=${l.flags.no_interview}`,
		);
		return;
	}
	if (!ledgerPath || !existsSync(ledgerPath)) fail([`ledger not found: ${ledgerPath}`]);
	const l = readJson(ledgerPath);
	const rowState = new Map((l.rows || []).map((r) => [r.id, r.status]));
	const phaseBefore = l.phase, wasPublished = Boolean(l.plan_sha256);
	const save = () => {
		const added = (l.rows || []).filter((r) => !rowState.has(r.id)).map((r) => r.id);
		const changed = (l.rows || []).filter((r) => rowState.has(r.id) && rowState.get(r.id) !== r.status).map((r) => `${r.id}:${r.status}`);
		const entry = { seq: ((l.changes ||= []).length) + 1, at: new Date().toISOString(), cmd, phase_before: phaseBefore, added, changed };
		if (wasPublished && !AMEND_EXEMPT.has(cmd)) {
			if (!a.reason || !String(a.reason).trim()) {
				fail([`plan is published (plan_sha256 ${String(l.plan_sha256).slice(0, 12)}...): ${cmd} changes it, so pass --reason "<why>"; the change is ledgered as an amendment, the plan is unpublished and must pass G4 and publish again`]);
			}
			Object.assign(entry, { amendment: true, reason: String(a.reason), unpublished_sha256: l.plan_sha256 });
			l.plan_sha256 = null;
			if (phaseIndex(l.phase) > phaseIndex("P4")) l.phase = "P4";
		}
		l.changes.push(entry);
		writeJsonAtomic(ledgerPath, l);
	};
	const need = (k) => {
		if (!a[k]) fail([`--${k} required`]);
		return a[k];
	};
	switch (cmd) {
		case "axis": {
			const ax = { id: nextId(l.axes, "A"), label: need("label") };
			l.axes.push(ax);
			save();
			console.log(ax.id);
			return;
		}
		case "plan-review": {
			if (phaseIndex(l.phase) < phaseIndex("P3")) fail([`plan-review before G2: phase=${l.phase}`]);
			if (a.findings || a.total) {
				fail([
					"plan-review no longer accepts --findings/--total (self-reported counts are not evidence); persist each finding with: finding --review plan-review:<cycle> --class <class> --locator <file:line>",
				]);
			}
			const cycle = recordReview(l, { cycle: need("cycle"), clean: Boolean(a.clean), scope: a.scope });
			save();
			console.log(`plan-review cycle ${cycle}: ${a.clean ? "clean" : "findings must be persisted separately"}`);
			return;
		}
		case "size": {
			const c = need("class");
			if (!SIZES.includes(c)) fail([`--class must be one of ${SIZES.join("|")}`]);
			l.size = c;
			save();
			console.log(c);
			return;
		}
		case "doubt": {
			if (phaseIndex(l.phase) < phaseIndex("P3")) fail([`doubt before G2: phase=${l.phase}`]);
			const d = l.rows.find((r) => r.id === need("id"));
			if (!d || d.type !== "decision") fail([`--id must be a decision row`]);
			if (a.findings || a.total) {
				fail([
					"doubt no longer accepts --findings/--total; persist each finding with: finding --review doubt:<decision>:<cycle> --class <class> --locator <file:line>",
				]);
			}
			const cycle = recordDoubt(l, d, { cycle: need("cycle"), claim: need("claim"), clean: Boolean(a.clean), scope: a.scope });
			save();
			console.log(`${d.id} cycle ${cycle}: ${a.clean ? "clean" : "findings must be persisted separately"}`);
			return;
		}
		case "finding": {
			if (phaseIndex(l.phase) < phaseIndex("P3")) fail([`finding before G2: phase=${l.phase}`]);
			const review = need("review");
			if (!/^(plan-review:\d+|doubt:[A-Z]\d+:\d+)$/.test(review)) {
				fail(["--review must be plan-review:<cycle> or doubt:<decision>:<cycle>"]);
			}
			const cls = need("class");
			if (!FINDING_CLASSES.includes(cls)) fail([`--class must be one of ${FINDING_CLASSES.join("|")}`]);
			const r = addRow(l, {
				type: "finding",
				label: `finding-${l.rows.length + 1}`,
				review,
				class: cls,
				locator: a.locator || null,
				snapshot_sha256: a.sha || null,
				note: a.note || null,
			});
			save();
			console.log(r.id);
			return;
		}
		case "round": {
			const asks = splitList(a.asks);
			if (!asks.length) fail(["--asks Q1,Q2 required (the frontier questions asked this round)"]);
			const prior = l.rows.filter((r) => r.type === "round");
			const openPrior = prior
				.flatMap((r) => r.asks || [])
				.filter((id) => l.rows.find((x) => x.id === id)?.status === "active");
			if (!a["fact-lane"] && openPrior.length) {
				fail([`round not closed: answer/retract ${openPrior.join(",")} before another round (or --fact-lane)`]);
			}
			const r = addRow(l, { type: "round", label: `round-${prior.length + 1}`, n: prior.length + 1, asks });
			save();
			console.log(r.id);
			return;
		}
		case "test-run": {
			const task = need("task");
			if (!l.rows.some((r) => r.id === task && r.type === "task")) fail([`--task '${task}' is not a task row`]);
			const phase = need("phase");
			if (!["red", "green"].includes(phase)) fail([`--phase must be red|green`]);
			const r = addRow(l, {
				type: "test_run",
				label: `run-${l.rows.filter((x) => x.type === "test_run").length + 1}`,
				task,
				phase,
				cmd: need("cmd"),
				exit: need("exit"),
				artifact: need("artifact"),
				snapshot_sha256: a.sha || null,
			});
			save();
			console.log(r.id);
			return;
		}
		case "unknowns": {
			if (a.clear) {
				l.unknowns_open = false;
				l.unknown_items = [];
			} else {
				const items = splitList(a.add);
				if (!items.length) fail(["--add <unknown item>[,<item>...] or --clear required"]);
				l.unknown_items.push(...items);
				l.unknowns_open = true;
			}
			save();
			console.log(`unknowns=${l.unknowns_open} items=${l.unknown_items.length}`);
			return;
		}
		case "issue": {
			const ref = need("ref");
			if (!ISSUE_REF_RE.test(ref)) fail([`--ref '${ref}' must be owner/repo#number`]);
			if (!(l.issues ||= []).some((i) => i.ref === ref)) l.issues.push(a.title ? { ref, title: a.title } : { ref });
			save();
			console.log(ref);
			return;
		}
		case "capability": {
			const cap = addCapability(l, {
				id: need("id"),
				responsibility: need("responsibility"),
				deps: a.deps,
			});
			save();
			console.log(cap.id);
			return;
		}
		case "wave": {
			// Saturation is derived, never attested: count facts stamped with the open wave number.
			const open = l.waves.length + 1;
			const n = l.rows.filter((r) => r.type === "fact" && r.wave === open).length;
			l.waves.push({ n: open, new_facts: n });
			save();
			console.log(`wave ${open}: new_facts=${n} (derived from fact rows)`);
			return;
		}
		case "fact": {
			if (a.repo && !(l.repos || []).some((r) => r.id === a.repo)) fail(["--repo " + a.repo + " is not registered (run the repo command first)"]);
			const r = addRow(l, {
				type: "fact",
				kind: a.kind || "quote",
				label: need("label"),
				locator: need("locator"),
				source_id: a.source || null,
				snapshot_sha256: a.sha || null,
				external: Boolean(a.external),
				axis: a.axis || null,
				quote: a.quote || null,
				wave: l.waves.length + 1,
				repo: a.repo || null,
			});
			save();
			console.log(r.id);
			return;
		}
		case "question": {
			const kind = a.map ? (a.kind || "user") : null;
			if (kind && !["evidence", "prototype", "user", "task"].includes(kind)) {
				fail(["--map --kind must be evidence|prototype|user|task"]);
			}
			const r = addRow(l, {
				type: "question",
				label: need("label"),
				quote: need("question"),
				blocked_by: splitList(a["blocked-by"]),
				map: kind,
				domain_term: a["domain-term"] || null,
				recommendation: String(a.recommend || a.recommendation || "").trim() || null,
			});
			save();
			console.log(r.id);
			return;
		}
		case "answer": {
			const r = l.rows.find((x) => x.id === need("id"));
			if (!r) fail([`no such row ${a.id}`]);
			if (r.type !== "question") fail([`${r.id} is not a question`]);
			if (r.status !== "active") {
				fail([
					`${r.id} is ${r.status}; only an active question can be answered (append-only: supersede/retract instead of resurrecting)`,
				]);
			}
			r.answer = need("answer");
			changeStatus(l, r.id, "answered", { reason: "user answer recorded" });
			save();
			console.log(`${r.id} answered`);
			return;
		}
		case "decision": {
			const r = addRow(l, {
				type: "decision",
				label: need("label"),
				answer: need("decision"),
				adr: Boolean(a.adr),
				adr_file: a["adr-file"] || null,
				irreversible: Boolean(a.irreversible),
			});
			save();
			console.log(r.id);
			return;
		}
		case "task": {
			if (a.repo && !(l.repos || []).some((r) => r.id === a.repo)) fail(["--repo " + a.repo + " is not registered (run the repo command first)"]);
			if (phaseIndex(l.phase) < phaseIndex("P4")) {
				fail([`task before G3: phase=${l.phase} (approve the design with gate G3 first; the task graph is not the design)`]);
			}
			const r = addRow(l, {
				type: "task",
				label: need("label"),
				files: splitList(a.files),
				interfaces: a.interfaces || "",
				acceptance: a.acceptance || "",
				verify: a.verify || "",
				deps: String(a.deps || "").split(",").filter(Boolean),
				test_seam: a["test-seam"] || null,
				test_file: a["test-file"] || null,
				red: a.red || null,
				green: a.green || null,
				steps: a.steps || null,
				kind: a.kind || "feature",
				issue: a.issue || null,
				est_lines: a["est-lines"] === undefined ? null : +a["est-lines"],
				closes: splitList(a.closes),
				effort: a.effort === undefined ? null : +a.effort,
				category: a.category || null,
				repo: a.repo || null,
			});
			save();
			console.log(r.id);
			return;
		}
		case "batch": {
			// One spawn, one load, one save for many rows (spawn is the dominant cost).
			const entries = JSON.parse(readFileSync(need("file"), "utf8"));
			if (!Array.isArray(entries)) fail(["batch file must be a JSON array"]);
			const out = [];
			for (const en of entries) {
				if (en.type === "fact") {
					out.push(
						addRow(l, {
							type: "fact",
							kind: en.kind || "quote",
							label: en.label,
							locator: en.locator,
							source_id: en.source || null,
							snapshot_sha256: en.sha || null,
							external: Boolean(en.external),
							axis: en.axis || null,
							quote: en.quote || null,
							wave: l.waves.length + 1,
							repo: en.repo || null,
						}).id,
					);
				} else if (en.type === "axis") {
					const ax = { id: nextId(l.axes, "A"), label: en.label };
					l.axes.push(ax);
					out.push(ax.id);
				} else if (en.type === "wave") {
					const open = l.waves.length + 1;
					const n = l.rows.filter((r) => r.type === "fact" && r.wave === open).length;
					l.waves.push({ n: open, new_facts: n });
					out.push(`wave${open}:${n}`);
				} else if (en.type === "question") {
					const kind = en.map ? (en.kind || "user") : null;
					if (kind && !["evidence", "prototype", "user", "task"].includes(kind)) fail([`batch: map kind must be evidence|prototype|user|task`]);
					out.push(addRow(l, {
						type: "question", label: en.label, quote: en.question,
						blocked_by: en.blocked_by || [], map: kind, domain_term: en.domain_term || null,
						recommendation: String(en.recommendation || en.recommend || "").trim() || null,
					}).id);
				} else if (en.type === "decision") {
					out.push(addRow(l, {
						type: "decision", label: en.label, answer: en.decision,
						adr: Boolean(en.adr), adr_file: en.adr_file || null, irreversible: Boolean(en.irreversible),
					}).id);
				} else if (en.type === "task") {
					if (phaseIndex(l.phase) < phaseIndex("P4")) fail([`batch: task before G3 (phase=${l.phase})`]);
					out.push(
						addRow(l, {
							type: "task",
							label: en.label,
							files: en.files || [],
							interfaces: en.interfaces || "",
							acceptance: en.acceptance || "",
							verify: en.verify || "",
							deps: en.deps || [],
							test_seam: en.test_seam || null,
							test_file: en.test_file || null,
							red: en.red || null,
							green: en.green || null,
							steps: en.steps || null,
							kind: en.kind || "feature",
							issue: en.issue || null,
							est_lines: en.est_lines ?? null,
							closes: en.closes || [],
							effort: en.effort ?? null,
							category: en.category || null,
							repo: en.repo || null,
						}).id,
					);
				} else if (en.type === "finding") {
					if (!FINDING_CLASSES.includes(en.class)) fail([`batch: finding class must be one of ${FINDING_CLASSES.join("|")}`]);
					if (!/^(plan-review:\d+|doubt:[A-Z]\d+:\d+)$/.test(String(en.review || ""))) fail([`batch: finding review must be plan-review:<cycle> or doubt:<decision>:<cycle>`]);
					out.push(addRow(l, {
						type: "finding", label: en.label || `finding-${l.rows.length + 1}`,
						review: en.review, class: en.class, locator: en.locator || null,
						snapshot_sha256: en.sha || null, note: en.note || null,
					}).id);
				} else if (en.type === "round") {
					const asks = en.asks || [];
					if (!asks.length) fail([`batch: round needs asks`]);
					const prior = l.rows.filter((r) => r.type === "round");
					const openPrior = prior.flatMap((r) => r.asks || []).filter((id) => l.rows.find((x) => x.id === id)?.status === "active");
					if (!en.fact_lane && openPrior.length) fail([`batch: round not closed: ${openPrior.join(",")}`]);
					out.push(addRow(l, { type: "round", label: `round-${prior.length + 1}`, n: prior.length + 1, asks }).id);
				} else if (en.type === "test_run") {
					const t = l.rows.find((r) => r.id === en.task);
					if (!t || t.type !== "task") fail([`batch: test_run task '${en.task}' is not a task`]);
					if (!["red", "green"].includes(en.phase)) fail([`batch: test_run phase must be red|green`]);
					out.push(addRow(l, {
						type: "test_run", label: `run-${l.rows.filter((x) => x.type === "test_run").length + 1}`,
						task: en.task, phase: en.phase, cmd: en.cmd, exit: en.exit,
						artifact: en.artifact, snapshot_sha256: en.sha || null,
					}).id);
				} else if (en.type === "issue") {
					if (!ISSUE_REF_RE.test(en.ref || "")) fail([`batch: issue ref '${en.ref}' must be owner/repo#number`]);
					if (!(l.issues ||= []).some((i) => i.ref === en.ref)) l.issues.push(en.title ? { ref: en.ref, title: en.title } : { ref: en.ref });
					out.push(en.ref);
				} else if (en.type === "plan_review") {
					if (en.findings || en.total) fail(["batch: plan_review no longer accepts findings/total; persist finding rows"]);
					out.push(`plan-review:${recordReview(l, en)}`);
				} else if (en.type === "size") {
					if (!SIZES.includes(en.class)) fail([`batch: size class must be one of ${SIZES.join("|")}`]);
					l.size = en.class;
					out.push(en.class);
				} else if (en.type === "intent") {
					for (const k of INTENT_KEYS) if (en[k]) l.intent[k] = en[k];
					if (en.assume) l.intent.assumed = true;
					out.push("intent");
				} else if (en.type === "doubt") {
					const d = l.rows.find((r) => r.id === en.id);
					if (!d || d.type !== "decision") fail([`batch: doubt id '${en.id}' must be a decision row`]);
					if (en.findings || en.total) fail(["batch: doubt no longer accepts findings/total; persist finding rows"]);
					out.push(`${d.id}:${recordDoubt(l, d, en)}`);
				} else if (en.type === "capability") {
					const cap = addCapability(l, { id: en.id, responsibility: en.responsibility, deps: en.deps || [] });
					out.push(cap.id);
				} else fail([`batch: unknown entry type ${en.type}`]);
			}
			save();
			console.log(out.join(" "));
			return;
		}
		case "retract":
		case "supersede":
			changeStatus(l, need("id"), cmd === "retract" ? "retracted" : "superseded", {
				replacement: a.replacement || null,
				reason: need("reason"),
			});
			save();
			console.log("ok");
			return;
		case "intent": {
			for (const k of INTENT_KEYS) {
				const v = a[k.replaceAll("_", "-")];
				if (v) l.intent[k] = v;
			}
			if (a.confirm) {
				if (a.by !== "user") {
					fail([
						"intent --confirm requires --by user (record the user's explicit yes from chat; the agent cannot mint it)",
					]);
				}
				l.intent.confirmed = true;
			}
			if (a.assume) l.intent.assumed = true;
			save();
			console.log("intent updated");
			return;
		}
		case "approve": {
			const gate = need("gate");
			const allowedTokens = {
				"G_MAP": ["map-destination"],
				"G3": ["approve-design", "approve-capability-map", "doubt-escalated", "plan-review-escalated"],
				"G4": ["approve-task-graph"],
			};
			if (!Object.prototype.hasOwnProperty.call(allowedTokens, gate)) {
				fail([`approve: unknown gate '${gate}' (allowed: ${Object.keys(allowedTokens).join("|")})`]);
			}
			if (gate !== "G_MAP" && phaseIndex(l.phase) < phaseIndex("P3")) {
				fail([`approve before G2: phase=${l.phase} (clarification must close before design approval)`]);
			}
			if (a.by !== "user") {
				fail(["approve requires --by user (record the token the user actually said; the agent cannot mint it)"]);
			}
			if (!a.quote || !String(a.quote).trim()) {
				fail([`approve requires --quote "<the user's exact words>" (an unquoted token is not evidence)`]);
			}
			const quoteErr = approvalQuoteError(l, a.quote);
			if (quoteErr) fail([quoteErr]);
			const token = need("token");
			if (!allowedTokens[gate].includes(token)) {
				fail([`approve: token '${token}' is not allowed for ${gate} (allowed: ${allowedTokens[gate].join("|")})`]);
			}
			l.approvals.push({ gate, token, by: "user", quote: String(a.quote), at: new Date().toISOString() });
			save();
			console.log("approval recorded");
			return;
		}
		case "validate": {
			const e = validateLedger(l);
			e.length ? fail(e) : console.log("PASS validate");
			return;
		}
		case "gate": {
			const g = need("id").toUpperCase();
			if (!GATES[g]) fail([`unknown gate ${g}`]);
			const dir = dirname(ledgerPath);
			const planText = existsSync(join(dir, "plan.md")) ? readFileSync(join(dir, "plan.md"), "utf8") : "";
			const mapText = existsSync(join(dir, "map.md")) ? readFileSync(join(dir, "map.md"), "utf8") : "";
			let e = g === "G_MAP" ? GATES.G_MAP(l, mapText) : GATES[g](l, planText);
			if (g === "G1" || g === "G4" || g === "G5") e = [...e, ...evidenceErrors(l, dir)];
			if (g === "G4" || g === "G5") for (const w of taskWarnings(l)) console.log(`WARN ${w}`);
			if (e.length) fail(e.map((x) => `${g} ${x}`));
			advancePhase(l, g);
			save();
			console.log(`PASS ${g} phase=${l.phase}`);
			return;
		}
		case "publish": {
			if (phaseIndex(l.phase) < phaseIndex("P5")) {
				fail([`publish before G4: phase=${l.phase} (G3 approves the design, G4 approves the task graph, then publish)`]);
			}
			const dir = dirname(ledgerPath);
			const planPath = join(dir, "plan.md");
			const planText = readFileSync(planPath, "utf8");
			if (l.render_sha256 && sha256(planText) !== l.render_sha256) {
				fail(["plan.md differs from the last render (hand-edited); run render --force to discard the edits, or record them as decisions"]);
			}
			l.plan_sha256 = sha256(planText);
			l.phase = "P5";
			const e = [...GATES.G5(l, planText), ...evidenceErrors(l, dir)];
			if (e.length) {
				l.plan_sha256 = null;
				l.phase = "P4";
				save();
				fail(e);
			}
			l.phase = "P6";
			l.render_sha256 = l.plan_sha256;
			save();
			const purged = purgeSuperseded(l, dir);
			if (purged.length) writeJsonAtomic(ledgerPath, l);
			console.log(`PASS G5 published plan_sha256=${l.plan_sha256} phase=${l.phase}`);
			for (const d of purged) console.log("purge " + d.kind + " " + d.status + ": " + d.path);
			return;
		}
		case "render": {
			const dir = dirname(ledgerPath);
			const target = l.map ? join(dir, "map.md") : join(dir, "plan.md");
			if (
				existsSync(target) && l.render_sha256 && sha256(readFileSync(target, "utf8")) !== l.render_sha256
				&& !a.force
			) {
				fail([
					`${target} differs from the last render/publish (hand-edited); refusing to overwrite — re-render with --force if the edits are disposable`,
				]);
			}
			const skeleton = l.map ? mapSkeleton(l) : planSkeleton(l);
			writeFileSync(target, skeleton);
			l.render_sha256 = sha256(skeleton);
			save();
			console.log(`rendered ${target}`);
			return;
		}
		case "frontier": {
			// Ready-to-start tasks given the ones already done (--done T1,T2). Read-only.
			const done = splitList(a.done);
			for (const id of done) {
				if (!l.rows.some((r) => r.id === id && r.type === "task")) fail([`--done ${id} is not a task row`]);
			}
			console.log(frontier(l, done).join("\n"));
			return;
		}
		case "repo": {
			const id = need("id"), repoDir = need("path");
			if (!SLUG_RE.test(id)) fail(["--id must match " + SLUG_RE]);
			if ((l.repos ||= []).some((r) => r.id === id)) fail(["repo " + id + " is already registered (ids are stable)"]);
			if (!existsSync(repoDir) || !statSync(repoDir).isDirectory()) fail(["--path must be an existing directory: " + repoDir]);
			l.repos.push({ id, path: repoDir, role: a.role || null });
			save();
			console.log("repo " + id + " -> " + repoDir);
			return;
		}
		case "assimilate": {
			const from = resolve(need("from"));
			const file = from.endsWith(".json") ? from : join(from, "ledger.json");
			if (!existsSync(file)) fail(["--from: ledger not found: " + file]);
			if (a.repo && !(l.repos || []).some((r) => r.id === a.repo)) fail(["--repo " + a.repo + " is not registered (run the repo command first)"]);
			if (resolve(dirname(file)) === resolve(dirname(ledgerPath))) fail(["--from is this plan itself"]);
			if ((l.sources || []).some((x) => resolve(x.dir) === resolve(dirname(file)))) fail(["already assimilated: " + dirname(file)]);
			let src;
			try {
				src = JSON.parse(readFileSync(file, "utf8"));
			} catch {
				fail(["--from: not valid JSON: " + file]);
			}
			if (src?.schemaVersion !== 2 || !Array.isArray(src.rows)) fail(["--from: not a rigorous-planning ledger: " + file]);
			const n = assimilateLedger(l, src, { repoId: a.repo || null, dir: resolve(dirname(file)), sha: ledgerFileSha(file) });
			save();
			console.log("assimilated " + src.slug + ": " + JSON.stringify(n) + "; the source plan is purged automatically after publish");
			return;
		}
		case "chat": {
			const p = resolve(need("path"));
			if (!existsSync(p) || !statSync(p).isFile()) fail(["--path must be an existing file: " + p]);
			if ((l.chats ||= []).some((c) => c.path === p)) fail(["chat already registered: " + p]);
			l.chats.push({ path: p, purged: false });
			save();
			console.log("chat registered; it is deleted automatically after publish: " + p);
			return;
		}
		case "purge": {
			if (!l.plan_sha256) fail(["purge: the plan is not published; sources are deleted only once their content lives in a published plan"]);
			const done = purgeSuperseded(l, dirname(ledgerPath));
			writeJsonAtomic(ledgerPath, l);
			for (const d of done) console.log("purge " + d.kind + " " + d.status + ": " + d.path);
			if (!done.length) console.log("purge: nothing to do");
			return;
		}
		case "todos": {
			// JSON for the harness todo tool: one phase per wave, one item per task. Read-only on the ledger.
			const done = splitList(a.done);
			for (const id of done) {
				if (!l.rows.some((r) => r.id === id && r.type === "task")) fail([`--done ${id} is not a task row`]);
			}
			const list = todoPhases(l, done);
			if (!list.length) fail(["todos: no remaining active tasks"]);
			const todoJson = JSON.stringify({ op: "init", list }, null, 2);
			writeFileSync(join(dirname(ledgerPath), "todos.json"), todoJson + "\n");
			console.log(todoJson);
			return;
		}
		case "cpm": {
			// Read-only CPM schedule over the active task graph.
			const tasks = (l.rows || []).filter((r) => r.type === "task" && r.status === "active");
			if (!tasks.length) fail(["cpm: no active tasks"]);
			const { rows, length, path } = cpmSchedule(tasks);
			console.log(`length ${length}\ncritical ${path.join(",")}`);
			for (const r of rows) console.log(`${r.id} es=${r.es} ef=${r.ef} ls=${r.ls} lf=${r.lf} slack=${r.slack}${r.critical ? " critical" : ""}`);
			return;
		}
		case "dag": {
			// mass-ulw workflow definition (JSON on stdout); planning never starts the run. --done T1,T2 drops finished tasks.
			const done = splitList(a.done);
			for (const id of done) {
				if (!l.rows.some((r) => r.id === id && r.type === "task")) fail([`--done ${id} is not a task row`]);
			}
			const { definition, serialized } = dagDefinition(l, done);
			if (!definition.nodes.length) fail(["dag: no remaining active tasks"]);
			for (const s of serialized) console.error(`serialized: ${s.before} after ${s.after} (shared files: ${s.files.join(", ")})`);
			const dagJson = JSON.stringify(definition, null, 2);
			writeFileSync(join(dirname(ledgerPath), done.length ? `dag-after-${done.join("-")}.json` : "dag.json"), dagJson + "\n");
			console.log(dagJson);
			return;
		}
		case "design-frontier": {
			console.log(designFrontier(l).map((q) => q.id).join("\n"));
			return;
		}
		case "next": {
			const say = (cmd, why) =>
				console.log(`${cmd} --slug ${l.slug}\n# ${why}\n# Keep going: run this, then next again. Do not stop until DONE published.`);
			if (l.map) {
				say("gate --id G_MAP", `map ${l.phase}: finish the map and sign the destination`);
				return;
			}
			if (l.phase === "P6" && l.plan_sha256) {
				console.log(`DONE published plan_sha256=${l.plan_sha256}\n# Executor: mirror every wave and task into the harness todo tool with: todos --slug ${l.slug}`);
				return;
			}
			const activeQs = (l.rows || []).filter((r) => r.type === "question" && r.status === "active" && !r.map);
			if (l.phase === "P0") {
				const sweep = l.flags?.sweep ? q0Errors(l) : [];
				if (sweep.length) {
					console.log(`question --slug ${l.slug} --label ${/q0-doubt-\d+/.exec(sweep[0])?.[0] ?? "q0-<category>"} --question "..."\n# Q0 sweep open: ${sweep[0]}\n# Ask every category in one batch (ask), record each answer, scope out the rest with a q0-<category> decision, then next again.`);
					return;
				}
				return say("gate --id G0", "intake: destination, type, size, branch");
			}
			if (l.phase === "P1") {
				if (!l.axes?.length) return say("gate --id G_AX", "P1 axes: record at least one axis");
				return say("gate --id G1", "P2 evidence: facts, waves, saturation");
			}
			if (l.phase === "P2") return say("gate --id G2", "P3 clarify: intent, rounds, questions");
			if (l.phase === "P3") {
				if (activeQs.length) {
					const rounds = (l.rows || []).filter((r) => r.type === "round");
					const unrounded = activeQs.filter((q) => !rounds.some((r) => (r.asks || []).includes(q.id)));
					if (unrounded.length) return say(`round --asks ${unrounded.map((q) => q.id).join(",")}`, "record the ready frontier");
					const ready = designFrontier(l);
					if (ready.length) return say("ask", "call the question tool with the exact JSON from ask, record every answer, then next again");
					return say("design-frontier", "all remaining questions are blocked; resolve a blocker or retract one");
				}
				if (!l.flags?.skip?.includes("plan-review") && !(l.plan_reviews || []).length) {
          return say("plan-review --cycle 1", "the fresh-context plan review is mandatory and runs now: spawn the reviewer, persist every finding with finding --review plan-review:1; never ask whether to run it");
        }
        return say("gate --id G3", "P4 design: approvals, review, doubt, deliberate record");
			}
			if (l.phase === "P4") return say("gate --id G4", "P5 tasks: task graph, test-first, waves, ideal/gap, headings");
			if (l.phase === "P5") {
				if (!existsSync(join(dirname(ledgerPath), "plan.md"))) return say("render", "P5 tasks: render plan.md from the ledger");
				return say("publish", "P6 publish: G5, evidence, size, hash");
			}
			return say("publish", "P6 publish: G5, evidence, size, hash");
		}
		case "ask": {
			const activeQs = (l.rows || []).filter((r) => r.type === "question" && r.status === "active" && !r.map);
			if (!activeQs.length) fail(["ask: no active questions"]);
			const byId = new Map((l.rows || []).map((r) => [r.id, r]));
			const ready = [];
			for (const q of activeQs) {
				const blockers = q.blocked_by || [];
				let isReady = true;
				for (const dep of blockers) {
					const d = byId.get(dep);
					if (!d) {
						fail([`ask: ${q.id}: blocked_by '${dep}' does not exist`]);
						return;
					}
					if (d.type !== "question") {
						fail([`ask: ${q.id}: blocked_by '${dep}' is not a question`]);
						return;
					}
					if (!["answered", "superseded", "retracted"].includes(d.status)) {
						isReady = false;
					}
				}
				if (isReady) ready.push(q);
			}
			const asked = new Set((l.rows || []).filter((r) => r.type === "round").flatMap((r) => r.asks || []));
			const unrecorded = ready.filter((q) => !asked.has(q.id));
			if (unrecorded.length) {
				fail(["ask: record a round first (round --asks ...)"]);
				return;
			}
			const questions = ready.map((q) => {
				const rec = String(q.recommendation || "").trim();
				const header = `${q.id} ${q.label || ""}`.trim().slice(0, 30);
				const entry = { header, question: q.quote || "" };
				if (rec) entry.options = [{ label: rec, description: "Recommended" }];
				return entry;
			});
			console.log(JSON.stringify({ questions }));
			return;
		}
		case "render-issues": {
			// Ticket drafts only; nothing is sent to a tracker.
			if (phaseIndex(l.phase) < phaseIndex("P4")) {
				fail([`render-issues before G3: phase=${l.phase} (approve the design first)`]);
			}
			const outDir = join(dirname(ledgerPath), "issues");
			mkdirSync(outDir, { recursive: true });
			const drafts = renderIssues(l);
			for (const d of drafts) writeFileSync(join(outDir, d.file), d.body);
			console.log(`rendered ${drafts.length} issue drafts in ${outDir}`);
			return;
		}
		case "map-handoff": {
			const dir = dirname(ledgerPath);
			const mapText = existsSync(join(dir, "map.md")) ? readFileSync(join(dir, "map.md"), "utf8") : "";
			const e = GATES.G_MAP(l, mapText);
			if (e.length) fail(e.map((x) => `G_MAP ${x}`));
			const type = a.type || "feature";
			if (!ISSUE_TYPES.includes(type)) fail([`--type must be one of ${ISSUE_TYPES.join("|")}`]);
			const target = join(planDir(type, l.slug), "ledger.json");
			if (existsSync(target)) fail([`plan already exists: ${target} (use a new slug)`]);
			const n = emptyLedger({
				slug: l.slug, issueType: type, branch: null, branchReason: "non-git",
				test_first: true, noInterview: false, noBranch: true, skip: [], size: "L",
			});
			n.rows = (l.rows || []).filter((r) => (r.type === "decision" || r.type === "fact") && r.status === "active");
			n.intent.out_of_scope = l.intent?.out_of_scope || "";
			n.intent.outcome = (l.rows.find((r) => r.label === "destination")?.answer) || "";
			n.phase = "P0";
			n.render_sha256 = sha256(planSkeleton(n));
			writeJsonAtomic(target, n);
			writeFileSync(join(planDir(type, l.slug), "plan.md"), planSkeleton(n));
			console.log(`handoff: ${target} (phase P0; run gate G0)`);
			return;
		}
		default:
			fail([
				`unknown command: ${cmd}. Use init|axis|issue|capability|wave|fact|question|answer|decision|task|batch|retract|supersede|intent|approve|validate|gate|publish|render|render-issues|frontier|cpm|dag|todos|size|doubt|plan-review|finding|round|test-run|unknowns|next|ask|map-handoff`,
			]);
	}
}
if (import.meta.url === `file://${process.argv[1]}` || process.argv[1]?.endsWith("planning.mjs")) {
	try {
		main();
	} catch (err) {
		fail([err?.message || String(err)]);
	}
}
