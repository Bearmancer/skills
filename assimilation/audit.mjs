#!/usr/bin/env node
// Random spot-check of answered units: shows the unit text next to the answer so a person can judge it.
//   node assimilation/audit.mjs [source] [--skill name] [-n 15] [--seed 1] [--why example-only|noise|runtime|superseded|out-of-scope|absorbed|duplicate]
import { readAllUnits } from "./enumerate.mjs";
import { loadAnswers } from "./check.mjs";
import { expandAnswers } from "./expand.mjs";
const args = process.argv.slice(2);
const opt = (n, d) => (args.includes(n) ? args[args.indexOf(n) + 1] : d);
const source = args[0] && !args[0].startsWith("-") ? args[0] : null;
const skill = opt("--skill");
const n = Number(opt("-n", 15));
const want = opt("--why");
let seed = Number(opt("--seed", 1));
const rnd = () => {
  seed |= 0;
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};
const units = readAllUnits();
const { answered } = expandAnswers(units, loadAnswers());
const pool = units.filter((u) => {
  const r = answered.get(u.id);
  if (!r || (source && u.source !== source) || (skill && u.skill !== skill)) return false;
  if (r.d === "dropped" && r.why === "boilerplate") return false;
  const label = r.d === "dropped" ? r.why : r.d;
  return !want || label === want;
});
for (let i = pool.length - 1; i > 0; i--) {
  const j = Math.floor(rnd() * (i + 1));
  [pool[i], pool[j]] = [pool[j], pool[i]];
}
console.log("pool: " + pool.length + " answered non-boilerplate units");
for (const u of pool.slice(0, n)) {
  const r = answered.get(u.id);
  const ans = r.d === "absorbed" ? "ABSORBED -> " + r.to.skill + " / " + r.to.section : r.d === "dropped" ? "DROPPED " + r.why + (r.note ? " (" + r.note + ")" : "") : "DUPLICATE of " + r.of;
  console.log("\n" + u.id + "  [" + u.kind + "] " + u.section.slice(-60));
  console.log("  " + (u.text ?? "").replace(/\s+/g, " ").trim().slice(0, 220));
  console.log("  => " + ans);
}
