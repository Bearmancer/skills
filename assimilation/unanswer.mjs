#!/usr/bin/env node
// Remove the existing answer from a run of units so they can be answered again (ranges are split, other lines untouched).
//   node assimilation/unanswer.mjs <source> <skill> <file> <from>[-<to>]
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { readUnits } from "./enumerate.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));

// lines: answer-file lines; fileUnits: units of one file sorted by seq; remove: Set of seq numbers.
export function removeSeqs(lines, fileUnits, remove) {
  const bySeq = new Map(fileUnits.map((u) => [u.id, u.seq]));
  const idOf = (seq) => fileUnits[seq].id;
  const out = [];
  let removed = 0;
  for (const line of lines) {
    if (!line.trim()) continue;
    let rec;
    try {
      rec = JSON.parse(line);
    } catch {
      out.push(line);
      continue;
    }
    const seqs = rec.id !== undefined ? [bySeq.get(rec.id)] : Array.isArray(rec.range) && bySeq.has(rec.range[0]) && bySeq.has(rec.range[1]) ? range(bySeq.get(rec.range[0]), bySeq.get(rec.range[1])) : null;
    if (!seqs || seqs.some((s) => s === undefined) || !seqs.some((s) => remove.has(s))) {
      out.push(line);
      continue;
    }
    const { id, range: _r, ...rest } = rec;
    const keep = seqs.filter((s) => !remove.has(s));
    removed += seqs.length - keep.length;
    let i = 0;
    while (i < keep.length) {
      let j = i;
      while (j + 1 < keep.length && keep[j + 1] === keep[j] + 1) j++;
      out.push(JSON.stringify(i === j ? { id: idOf(keep[i]), ...rest } : { range: [idOf(keep[i]), idOf(keep[j])], ...rest }));
      i = j + 1;
    }
  }
  return { lines: out, removed };
}
const range = (a, b) => Array.from({ length: b - a + 1 }, (_, k) => a + k);

const isMain = process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;
if (isMain) {
  const [source, skill, file, span] = process.argv.slice(2);
  const die = (m) => {
    console.error(m);
    process.exit(2);
  };
  if (!source || !skill || !file || !span) die("usage: node assimilation/unanswer.mjs <source> <skill> <file> <from>[-<to>]");
  const fu = readUnits(source).filter((u) => u.skill === skill && u.file === file).sort((a, b) => a.seq - b.seq);
  if (!fu.length) die("no units for " + source + ":" + skill + "/" + file);
  const [from, to = from] = span.split("-").map(Number);
  if (!Number.isInteger(from) || !Number.isInteger(to) || from > to || !fu[from] || !fu[to]) die("bad span " + span + "; this file has units 0.." + (fu.length - 1));
  const remove = new Set(range(from, to));
  const dir = path.join(HERE, "answers", source);
  let total = 0;
  for (const f of fs.existsSync(dir) ? fs.readdirSync(dir) : []) {
    if (!f.endsWith(".jsonl") || f.split(".")[0] !== skill) continue;
    const p = path.join(dir, f);
    const r = removeSeqs(fs.readFileSync(p, "utf8").split("\n"), fu, remove);
    if (r.removed) {
      fs.writeFileSync(p, r.lines.length ? r.lines.join("\n") + "\n" : "");
      console.log(f + ": cleared " + r.removed + " unit(s)");
      total += r.removed;
    }
  }
  console.log(total ? "cleared " + total + " unit answer(s); answer them again with answer.mjs" : "nothing to clear: those units had no answer");
}
