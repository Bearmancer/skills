#!/usr/bin/env node
// Compact unit listing for answering. A * after the number means the unit already has an answer.
//   node assimilation/list.mjs <source> <skill> [file]
import { readUnits } from "./enumerate.mjs";
import { loadAnswers } from "./check.mjs";
const [source, skill, file] = process.argv.slice(2);
if (!source || !skill) {
  console.error("usage: node assimilation/list.mjs <source> <skill> [file]");
  process.exit(2);
}
const units = readUnits(source).filter((u) => u.skill === skill);
if (!units.length) {
  console.error("no units for " + source + ":" + skill);
  process.exit(2);
}
const byId = new Map(units.map((u) => [u.id, u]));
const answered = new Set();
for (const { skill: k, rec } of loadAnswers()) {
  if (!rec || k !== source + ":" + skill) continue;
  if (rec.id) answered.add(rec.id);
  else if (rec.range) {
    const a = byId.get(rec.range[0]);
    const b = byId.get(rec.range[1]);
    if (a && b) for (const u of units) if (u.file === a.file && u.seq >= a.seq && u.seq <= b.seq) answered.add(u.id);
  }
}
let last = "";
for (const u of units) {
  if (file && u.file !== file) continue;
  if (u.file !== last) {
    console.log("== " + u.file);
    last = u.file;
  }
  const text = (u.text ?? "(binary)").replace(/\s+/g, " ").trim().slice(0, 110);
  console.log(String(u.seq).padStart(4) + (answered.has(u.id) ? "*" : " ") + "|" + u.kind + "|L" + u.lines[0] + "-" + u.lines[1] + "|" + (u.dupOf ? "DUP " + u.dupOf + "|" : "") + text);
}
