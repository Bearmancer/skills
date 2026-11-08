#!/usr/bin/env node
// Answers checker. Every Unit of the selected skills must have exactly one answer from a closed vocabulary.
// It checks shape, coverage and references (across all packs); it cannot judge whether an answer is wise.
//   node assimilation/check.mjs                                  every pack
//   node assimilation/check.mjs addyosmani,omc                   these packs
//   node assimilation/check.mjs addyosmani --skill interview-me  just these skills (comma list)
//   node assimilation/check.mjs --build <skills-dir>             also require each absorbed section to exist as a heading
//
// Answer files: assimilation/answers/<source>/<skill>.jsonl, one JSON object per line:
//   {"id":"<unit id>" | "range":["<first id>","<last id>"], "d":"absorbed", "to":{"skill":"planning-rigorously","section":"Heading text"}}
//   {"id":"<unit id>", "d":"duplicate", "of":"<unit id answered absorbed>"}
//   {"id|range":..., "d":"dropped", "why":"noise|runtime|boilerplate|example-only|superseded|out-of-scope", "note":"...", "ref":"<unit id>"}
// `ref` is required for superseded, optional for example-only, forbidden otherwise; with ref the answer names a single id.
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { HERE, readAllUnits, walk } from "./enumerate.mjs";

const WHY = new Set(["noise", "runtime", "boilerplate", "example-only", "superseded", "out-of-scope"]);
const NEEDS_REF = new Set(["superseded"]);
const MAY_REF = new Set(["example-only"]);
const KEYS = { absorbed: ["to"], duplicate: ["of"], dropped: ["why", "ref", "note"] };
const normHeading = (s) => s.toLowerCase().replace(/\s+/g, " ").trim();
export const ukey = (u) => `${u.source}:${u.skill}`;

export function checkAnswers({ units, answers, lanes, selected, headingsFor }) {
	const errors = [];
	const err = (m) => errors.push(m);
	const byId = new Map(units.map((u) => [u.id, u]));
	const files = new Map();
	for (const u of units) {
		const k = `${ukey(u)}/${u.file}`;
		if (!files.has(k)) files.set(k, []);
		files.get(k).push(u);
	}
	for (const l of files.values()) l.sort((a, b) => a.seq - b.seq);
	const sel = selected ?? new Set(units.map(ukey));
	const laneSet = new Set(lanes.skills);

	const answered = new Map(); // unit id -> { rec, loc }
	const recs = [];
	for (const { skill, loc, rec } of answers) {
		if (!rec || typeof rec !== "object") {
			err(`${loc}: not an object`);
			continue;
		}
		if (!KEYS[rec.d]) {
			err(`${loc}: d must be one of ${Object.keys(KEYS).join("|")}, got ${JSON.stringify(rec.d)}`);
			continue;
		}
		const allowed = new Set(["id", "range", "d", ...KEYS[rec.d]]);
		const stray = Object.keys(rec).filter((k) => !allowed.has(k));
		if (stray.length) {
			err(`${loc}: unexpected key(s) ${stray.join(",")} for d=${rec.d}`);
			continue;
		}
		if ((rec.id === undefined) === (rec.range === undefined)) {
			err(`${loc}: give exactly one of id / range`);
			continue;
		}
		let ids;
		if (rec.id !== undefined) {
			if (!byId.has(rec.id)) {
				err(`${loc}: unknown unit ${rec.id}`);
				continue;
			}
			ids = [rec.id];
		} else {
			const r = rec.range;
			if (!Array.isArray(r) || r.length !== 2 || !byId.has(r[0]) || !byId.has(r[1])) {
				err(`${loc}: range must be [firstId, lastId] of known units`);
				continue;
			}
			const a = byId.get(r[0]);
			const b = byId.get(r[1]);
			if (ukey(a) !== ukey(b) || a.file !== b.file || a.seq > b.seq) {
				err(`${loc}: range ends must be in the same file, first before last`);
				continue;
			}
			ids = files.get(`${ukey(a)}/${a.file}`).slice(a.seq, b.seq + 1).map((u) => u.id);
		}
		const multi = rec.range !== undefined;
		if (rec.d === "duplicate" && multi) {
			err(`${loc}: duplicate must name a single id`);
			continue;
		}
		if (rec.d === "dropped" && rec.ref !== undefined && multi) {
			err(`${loc}: a dropped answer with ref must name a single id`);
			continue;
		}
		let clash = false;
		for (const id of ids) {
			if (ukey(byId.get(id)) !== skill) {
				err(`${loc}: answers file for "${skill}" covers a unit of "${ukey(byId.get(id))}" (${id})`);
				clash = true;
				break;
			}
			if (answered.has(id)) {
				err(`${loc}: ${id} already answered at ${answered.get(id).loc}`);
				clash = true;
				break;
			}
		}
		if (clash) continue;
		for (const id of ids) answered.set(id, { rec, loc });
		recs.push({ rec, loc, ids });
	}

	// coverage
	const perSkill = {};
	for (const skill of sel) perSkill[skill] = { total: 0, answered: 0 };
	for (const u of units) {
		if (!sel.has(ukey(u))) continue;
		perSkill[ukey(u)].total++;
		if (answered.has(u.id)) perSkill[ukey(u)].answered++;
	}
	for (const [skill, c] of Object.entries(perSkill)) {
		if (c.total === 0) err(`skill "${skill}" has no units: not enumerated`);
		else if (c.answered < c.total) {
			const first = units.find((u) => ukey(u) === skill && !answered.has(u.id));
			err(`${skill}: ${c.total - c.answered} of ${c.total} units unanswered (first: ${first.id})`);
		}
	}

	// meaning-free semantic checks: references resolve, vocabulary is closed
	const target = (ref, who, what) => {
		const t = byId.get(ref);
		if (!t) return err(`${who}: ${what} ${ref} is not a unit`);
		if (!sel.has(ukey(t))) return;
		const a = answered.get(ref)?.rec;
		if (!a) err(`${who}: ${what} ${ref} is unanswered`);
		else if (a.d !== "absorbed") err(`${who}: ${what} ${ref} is "${a.d}", must be absorbed`);
	};
	const headingCache = new Map();
	const byDisposition = {};
	for (const { rec, loc, ids } of recs) {
		const inSel = ids.filter((id) => sel.has(ukey(byId.get(id))));
		if (!inSel.length) continue;
		byDisposition[rec.d] = (byDisposition[rec.d] ?? 0) + inSel.length;
		if (rec.d === "absorbed") {
			const to = rec.to;
			if (!to || typeof to.skill !== "string" || typeof to.section !== "string" || !to.section.trim()) {
				err(`${loc}: absorbed needs to:{skill, section}`);
			} else if (!laneSet.has(to.skill)) {
				err(`${loc}: target skill "${to.skill}" is not in lanes.json (${[...laneSet].join(", ")})`);
			} else if (headingsFor) {
				if (!headingCache.has(to.skill)) headingCache.set(to.skill, headingsFor(to.skill));
				const hs = headingCache.get(to.skill);
				if (!hs) err(`${loc}: target skill "${to.skill}" is not built yet`);
				else if (!hs.has(normHeading(to.section))) err(`${loc}: no heading "${to.section}" in built skill ${to.skill}`);
			}
		} else if (rec.d === "duplicate") {
			if (rec.of === ids[0]) err(`${loc}: a unit cannot duplicate itself`);
			else target(rec.of, loc, "duplicate of");
		} else {
			if (!WHY.has(rec.why)) err(`${loc}: why must be one of ${[...WHY].join("|")}, got ${JSON.stringify(rec.why)}`);
			if (rec.why !== "boilerplate" && !(typeof rec.note === "string" && rec.note.trim())) {
				err(`${loc}: dropped (${rec.why}) needs a note`);
			}
			if (rec.ref === undefined) {
				if (NEEDS_REF.has(rec.why)) err(`${loc}: ${rec.why} needs ref to the unit that replaces it`);
			} else if (!NEEDS_REF.has(rec.why) && !MAY_REF.has(rec.why)) {
				err(`${loc}: ref is only for superseded / example-only`);
			} else if (rec.ref === ids[0]) {
				err(`${loc}: ref points at itself`);
			} else {
				target(rec.ref, loc, "ref");
			}
		}
	}
	return { errors, stats: { perSkill, byDisposition } };
}

export function loadAnswers() {
	const root = path.join(HERE, "answers");
	const out = [];
	if (!fs.existsSync(root)) return out;
	const sources = fs
		.readdirSync(root, { withFileTypes: true })
		.filter((e) => e.isDirectory())
		.map((e) => e.name)
		.sort();
	for (const source of sources) {
		const dir = path.join(root, source);
		for (const f of fs.readdirSync(dir).filter((x) => x.endsWith(".jsonl")).sort()) {
			const skill = `${source}:${f.replace(/\.jsonl$/, "").split(".")[0]}`;
			fs.readFileSync(path.join(dir, f), "utf8")
				.split("\n")
				.forEach((line, i) => {
					if (!line.trim()) return;
					const loc = `${source}/${f}:${i + 1}`;
					try {
						out.push({ skill, loc, rec: JSON.parse(line) });
					} catch {
						out.push({ skill, loc, rec: null });
					}
				});
		}
	}
	return out;
}

export function headingsFromDir(root) {
	return (skill) => {
		const dir = path.join(root, skill);
		if (!fs.existsSync(dir)) return null;
		const set = new Set();
		for (const rel of walk(dir).filter((f) => /\.md$/i.test(f))) {
			for (const l of fs.readFileSync(path.join(dir, rel), "utf8").split("\n")) {
				const m = /^ {0,3}#{1,6}[ \t]+(.*?)[ \t]*$/.exec(l);
				if (m) set.add(normHeading(m[1]));
			}
		}
		return set;
	};
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;
if (isMain) {
	const args = process.argv.slice(2);
	const opt = (name) => (args.includes(name) ? args[args.indexOf(name) + 1] : undefined);
	try {
		const units = readAllUnits();
		if (!units.length) throw new Error('no units: run "node assimilation/enumerate.mjs build <source>" first');
		const lanes = JSON.parse(fs.readFileSync(path.join(HERE, "lanes.json"), "utf8"));
		const first = args[0] && !args[0].startsWith("--") ? args[0] : "all";
		const sources = first === "all" ? null : new Set(first.split(","));
		const skills = opt("--skill")?.split(",");
		const selected = new Set(
			units
				.filter((u) => (!sources || sources.has(u.source)) && (!skills || skills.includes(u.skill)))
				.map(ukey),
		);
		if (!selected.size) throw new Error("nothing selected: check the source / --skill names");
		const buildRoot = opt("--build");
		const r = checkAnswers({
			units,
			answers: loadAnswers(),
			lanes,
			selected,
			headingsFor: buildRoot ? headingsFromDir(buildRoot) : undefined,
		});
		const rows = Object.entries(r.stats.perSkill);
		const done = rows.filter(([, c]) => c.answered === c.total).length;
		for (const [s, c] of rows) if (rows.length <= 40 || c.answered < c.total) console.log(`${s.padEnd(44)} ${c.answered}/${c.total}`);
		console.log(`skills complete: ${done}/${rows.length}; dispositions: ${JSON.stringify(r.stats.byDisposition)}`);
		if (r.errors.length) {
			console.log(`FAIL: ${r.errors.length} problem(s)`);
			console.log(r.errors.slice(0, 25).join("\n"));
			process.exit(1);
		}
		console.log("PASS: every unit answered once, every reference resolves");
	} catch (e) {
		console.error(e.message);
		process.exit(2);
	}
}
