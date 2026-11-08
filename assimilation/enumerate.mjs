#!/usr/bin/env node
// Build-time enumerator. `build <source>` splits every file of every skill in a source pack into Units;
// `verify <source>` re-reads the disk and proves the Units reassemble to exactly the bytes on disk,
// with no file missing and none added since the build; `claims` lists installed skills no pack claims.
//   node assimilation/enumerate.mjs build addyosmani
//   node assimilation/enumerate.mjs verify addyosmani
//   node assimilation/enumerate.mjs claims
// Unit ids are "<source>:<skill>/<file>#<seq>" so they stay unique across packs.
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath, pathToFileURL } from "node:url";
import { fileUnits, norm } from "./units.mjs";

export const HERE = path.dirname(fileURLToPath(import.meta.url));
const UNITS = path.join(HERE, "units");
const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");

export const readSources = () => JSON.parse(fs.readFileSync(path.join(HERE, "sources.json"), "utf8"));

export function walk(dir, rel = "") {
	const out = [];
	for (const e of fs.readdirSync(path.join(dir, rel), { withFileTypes: true })) {
		const r = rel ? `${rel}/${e.name}` : e.name;
		if (e.isDirectory()) out.push(...walk(dir, r));
		else out.push(r);
	}
	return out;
}

const skillFirst = (a, b) => (a === "SKILL.md" ? -1 : b === "SKILL.md" ? 1 : a < b ? -1 : a > b ? 1 : 0);

function sourceOf(name) {
	const src = readSources()[name];
	if (!src || name.startsWith("_")) {
		const known = Object.keys(readSources()).filter((k) => !k.startsWith("_"));
		throw new Error(`unknown source "${name}"; known: ${known.join(", ")}`);
	}
	return src;
}

export function build(source) {
	const src = sourceOf(source);
	const records = [];
	const manifest = [];
	for (const skill of src.skills) {
		const dir = path.join(src.root, skill);
		if (!fs.existsSync(path.join(dir, "SKILL.md"))) throw new Error(`${skill}: no SKILL.md under ${dir}`);
		for (const rel of walk(dir).sort(skillFirst)) {
			const buf = fs.readFileSync(path.join(dir, rel));
			const units = fileUnits(rel, buf);
			units.forEach((u, seq) =>
				records.push({
					id: `${source}:${skill}/${rel}#${String(seq).padStart(4, "0")}`,
					source,
					skill,
					file: rel,
					seq,
					...u,
				}),
			);
			manifest.push({ skill, file: rel, bytes: buf.length, sha256: sha256(buf), units: units.length });
		}
	}
	// Exact-duplicate marking inside this pack: identical normalised text of 24+ chars; first occurrence is canonical.
	const first = new Map();
	for (const r of records) {
		if (r.text == null || r.kind === "heading" || r.kind === "fm-field") continue;
		const k = norm(r.text);
		if (k.length < 24) continue;
		if (first.has(k)) r.dupOf = first.get(k);
		else first.set(k, r.id);
	}
	fs.mkdirSync(UNITS, { recursive: true });
	fs.writeFileSync(path.join(UNITS, `${source}.jsonl`), records.map((r) => JSON.stringify(r)).join("\n") + "\n");
	fs.writeFileSync(path.join(UNITS, `${source}.manifest.json`), JSON.stringify(manifest, null, 1) + "\n");
	return { skills: src.skills.length, files: manifest.length, units: records.length };
}

const parseJsonl = (f) =>
	fs
		.readFileSync(f, "utf8")
		.split("\n")
		.filter(Boolean)
		.map((l) => JSON.parse(l));

export const readUnits = (source) => {
	const f = path.join(UNITS, `${source}.jsonl`);
	if (!fs.existsSync(f)) throw new Error(`${f} missing: run "node assimilation/enumerate.mjs build ${source}" first`);
	return parseJsonl(f);
};

export function readAllUnits() {
	if (!fs.existsSync(UNITS)) return [];
	return fs
		.readdirSync(UNITS)
		.filter((f) => f.endsWith(".jsonl"))
		.sort()
		.flatMap((f) => parseJsonl(path.join(UNITS, f)));
}

export function verify(source) {
	const src = sourceOf(source);
	const errors = [];
	const manifest = JSON.parse(fs.readFileSync(path.join(UNITS, `${source}.manifest.json`), "utf8"));
	const byFile = new Map();
	for (const r of readUnits(source)) {
		const k = `${r.skill}/${r.file}`;
		if (!byFile.has(k)) byFile.set(k, []);
		byFile.get(k).push(r);
	}
	const known = new Set(manifest.map((m) => `${m.skill}/${m.file}`));
	for (const skill of src.skills) {
		for (const rel of walk(path.join(src.root, skill))) {
			if (!known.has(`${skill}/${rel}`)) errors.push(`on disk but not in the manifest: ${skill}/${rel}`);
		}
	}
	let bytes = 0;
	let units = 0;
	const kinds = {};
	for (const m of manifest) {
		const key = `${m.skill}/${m.file}`;
		const file = path.join(src.root, m.skill, m.file);
		if (!fs.existsSync(file)) {
			errors.push(`in the manifest but gone from disk: ${key}`);
			continue;
		}
		const buf = fs.readFileSync(file);
		if (sha256(buf) !== m.sha256) errors.push(`${key}: changed on disk since the build`);
		const us = (byFile.get(key) ?? []).sort((a, b) => a.seq - b.seq);
		if (us.length !== m.units) errors.push(`${key}: manifest says ${m.units} units, found ${us.length}`);
		let pos = 0;
		const parts = [];
		us.forEach((u, idx) => {
			kinds[u.kind] = (kinds[u.kind] ?? 0) + 1;
			if (u.seq !== idx) errors.push(`${key}: unit sequence broken at ${u.id}`);
			if (u.bytes[0] !== pos) errors.push(`${key}: ${u.bytes[0] > pos ? "gap" : "overlap"} before ${u.id}`);
			pos = u.bytes[1];
			if (u.text != null) parts.push(Buffer.from(u.text, "utf8"));
		});
		if (pos !== buf.length) errors.push(`${key}: units end at byte ${pos}, file has ${buf.length}`);
		if (us.every((u) => u.text != null) && !Buffer.concat(parts).equals(buf)) {
			errors.push(`${key}: reassembled bytes differ from the file`);
		}
		bytes += buf.length;
		units += us.length;
	}
	return { errors, files: manifest.length, units, bytes, kinds };
}

// Installed skill folders that no pack, out-of-scope entry or old rigorous skill claims.
export function claims() {
	const s = readSources();
	const inst = s._installed;
	const claimed = new Map();
	const claim = (name, by) => claimed.set(name, [...(claimed.get(name) ?? []), by]);
	for (const [k, v] of Object.entries(s)) {
		if (k.startsWith("_")) continue;
		if (path.resolve(v.root) === path.resolve(inst.root)) v.skills.forEach((n) => claim(n, k));
	}
	inst.outOfScope.forEach((n) => claim(n, "out-of-scope"));
	inst.rigorous.forEach((n) => claim(n, "old-rigorous"));
	const present = fs
		.readdirSync(inst.root, { withFileTypes: true })
		.filter((e) => e.isDirectory() && fs.existsSync(path.join(inst.root, e.name, "SKILL.md")))
		.map((e) => e.name);
	return {
		present: present.length,
		unclaimed: present.filter((n) => !claimed.has(n)),
		doubleClaimed: [...claimed].filter(([, by]) => by.length > 1).map(([n, by]) => `${n}: ${by.join(" + ")}`),
		claimedButAbsent: [...claimed.keys()].filter((n) => !present.includes(n)),
	};
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;
if (isMain) {
	const [cmd, source] = process.argv.slice(2);
	try {
		if (cmd === "build") {
			const r = build(source);
			console.log(`built ${source}: ${r.skills} skills, ${r.files} files, ${r.units} units`);
		} else if (cmd === "verify") {
			const r = verify(source);
			console.log(`kinds: ${JSON.stringify(r.kinds)}`);
			if (r.errors.length) {
				console.log(`FAIL (${r.errors.length}):\n${r.errors.slice(0, 20).join("\n")}`);
				process.exit(1);
			}
			console.log(
				`PASS: ${r.files} files, ${r.units} units, ${r.bytes} bytes reassemble exactly; no file missing or added`,
			);
		} else if (cmd === "claims") {
			const r = claims();
			console.log(`installed skill folders: ${r.present}`);
			if (r.doubleClaimed.length) console.log(`claimed twice:\n${r.doubleClaimed.join("\n")}`);
			if (r.claimedButAbsent.length) console.log(`claimed but not installed: ${r.claimedButAbsent.join(", ")}`);
			if (r.unclaimed.length) {
				console.log(`FAIL: ${r.unclaimed.length} unclaimed: ${r.unclaimed.join(", ")}`);
				process.exit(1);
			}
			console.log("PASS: every installed skill folder is claimed exactly once");
		} else {
			console.log("usage: node assimilation/enumerate.mjs <build|verify> <source> | claims");
			process.exit(2);
		}
	} catch (e) {
		console.error(e.message);
		process.exit(2);
	}
}
