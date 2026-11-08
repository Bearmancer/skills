#!/usr/bin/env node
// Every answered unit of one skill next to its answer, for a human or verifier to judge. Read-only.
//   node assimilation/review.mjs <source> <skill> [file] [--all]     (boilerplate drops are collapsed unless --all)
import { readUnits } from "./enumerate.mjs";
import { loadAnswers } from "./check.mjs";
import { expandAnswers } from "./expand.mjs";
const args = process.argv.slice(2).filter((a) => a !== "--all");
const all = process.argv.includes("--all");
const [source, skill, file] = args;
if (!source || !skill) {
  console.error("usage: node assimilation/review.mjs <source> <skill> [file] [--all]");
  process.exit(2);
}
const units = readUnits(source).filter((u) => u.skill === skill && (!file || u.file === file));
const { answered } = expandAnswers(units, loadAnswers().filter((a) => a.skill === source + ":" + skill));
let last = "";
let bp = 0;
const flush = () => {
  if (bp) console.log("      ... " + bp + " boilerplate unit(s) collapsed");
  bp = 0;
};
for (const u of units) {
  if (u.file !== last) {
    flush();
    console.log("== " + u.file);
    last = u.file;
  }
  const r = answered.get(u.id);
  if (!r) {
    flush();
    console.log(String(u.seq).padStart(4) + " UNANSWERED|" + (u.text ?? "").replace(/\s+/g, " ").trim().slice(0, 120));
    continue;
  }
  if (r.d === "dropped" && r.why === "boilerplate" && !all) {
    bp++;
    continue;
  }
  flush();
  const ans = r.d === "absorbed" ? "ABS " + r.to.skill + " / " + r.to.section : r.d === "dropped" ? "DROP " + r.why + (r.note ? " (" + r.note + ")" : "") : "DUP " + r.of;
  console.log(String(u.seq).padStart(4) + " " + u.kind + "|" + (u.text ?? "").replace(/\s+/g, " ").trim().slice(0, 170));
  console.log("       => " + ans);
}
flush();
