#!/usr/bin/env node
// Append one answer line for a run of units of one file, without typing ids.
//   node assimilation/answer.mjs <source> <skill> <file> <from>[-<to>] absorbed <target-skill> "<section>" [--part <name>]
//   node assimilation/answer.mjs <source> <skill> <file> <from>[-<to>] dropped <why> ["<note>"] [--ref <unit id>] [--part <name>]
//   node assimilation/answer.mjs <source> <skill> <file> <seq> duplicate <unit id> [--part <name>]
// <from>/<to> are the unit numbers shown by list.mjs. Without --part the line goes to answers/<source>/<skill>.jsonl.
import fs from "node:fs";
import path from "node:path";
import { HERE, readUnits } from "./enumerate.mjs";
const raw = process.argv.slice(2);
const flags = {};
const pos = [];
for (let i = 0; i < raw.length; i++) {
  if (raw[i] === "--part" || raw[i] === "--ref") flags[raw[i].slice(2)] = raw[++i];
  else pos.push(raw[i]);
}
const [source, skill, file, span, d, a, b] = pos;
const die = (m) => {
  console.error(m);
  process.exit(2);
};
if (!source || !skill || !file || !span || !d) die("usage: see the header of assimilation/answer.mjs");
const units = readUnits(source).filter((u) => u.skill === skill && u.file === file);
if (!units.length) die("no units for " + source + ":" + skill + "/" + file);
const [from, to = from] = span.split("-").map(Number);
if (!Number.isInteger(from) || !Number.isInteger(to) || from > to || !units[from] || !units[to]) die("bad span " + span + "; this file has units 0.." + (units.length - 1));
const rec = from === to ? { id: units[from].id } : { range: [units[from].id, units[to].id] };
if (d === "absorbed") {
  if (!a || !b) die('absorbed needs <target-skill> "<section>"');
  Object.assign(rec, { d, to: { skill: a, section: b } });
} else if (d === "duplicate") {
  if (from !== to) die("duplicate names a single unit");
  if (!a) die("duplicate needs the unit id it repeats");
  Object.assign(rec, { d, of: a });
} else if (d === "dropped") {
  if (!a) die("dropped needs <why>");
  Object.assign(rec, { d, why: a });
  if (b) rec.note = b;
  if (flags.ref) {
    if (from !== to) die("--ref needs a single unit");
    rec.ref = flags.ref;
  }
} else die("d must be absorbed, dropped or duplicate");
const dir = path.join(HERE, "answers", source);
fs.mkdirSync(dir, { recursive: true });
const out = path.join(dir, skill + (flags.part ? "." + flags.part : "") + ".jsonl");
fs.appendFileSync(out, JSON.stringify(rec) + "\n");
console.log("wrote " + path.relative(HERE, out) + ": " + JSON.stringify(rec));
