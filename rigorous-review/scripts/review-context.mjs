#!/usr/bin/env node
// Deterministic review-context collector for the `rigorous-review` skill.
// Gathers the fixed point, commit list, changed files, diff stat, standards/spec
// candidates, and context mining (history, TODO markers, importers) as JSON.
// It never checks anything out and never edits: read-only git inspection only.
import { spawnSync } from "node:child_process";
import { existsSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

function git(args, fallback = "") {
  const r = spawnSync("git", args, { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  return r.status === 0 ? r.stdout.trim() : fallback;
}
function lines(s) {
  return s ? s.split("\n").filter(Boolean) : [];
}

const argv = process.argv.slice(2);
const opt = {};
for (let i = 0; i < argv.length; i++) {
  if (argv[i].startsWith("--")) opt[argv[i].slice(2)] = argv[i + 1]?.startsWith("--") ? true : argv[++i];
}
const fixed = opt.fixed || opt.base;
if (!fixed) {
  console.error("ERROR --fixed <ref> required (commit, branch, tag, or merge-base ref)");
  process.exit(1);
}
if (!git(["rev-parse", "--verify", fixed])) {
  console.error(`ERROR fixed point does not resolve: ${fixed}`);
  process.exit(1);
}

const mergeBase = git(["merge-base", fixed, "HEAD"]);
const range = `${fixed}...HEAD`; // three-dot: compare against merge-base
const commits = lines(git(["log", `${fixed}..HEAD`, "--oneline"]));
const changedFiles = lines(git(["diff", "--name-only", range]));
const diffStat = git(["diff", "--stat", range]);
const numstat = lines(git(["diff", "--numstat", range])).map((l) => {
  const [a, d, f] = l.split("\t");
  return { file: f, added: a === "-" ? null : Number(a), deleted: d === "-" ? null : Number(d) };
});
const totalChanged = numstat.reduce((n, x) => n + (x.added || 0) + (x.deleted || 0), 0);

// Standards discovery: repo documents how code should be written.
const STANDARD_NAMES = [
  "CODING_STANDARDS.md",
  "CONTRIBUTING.md",
  "CLAUDE.md",
  "AGENTS.md",
  "STYLE_GUIDE.md",
  ".editorconfig",
];
const standards = [];
for (const n of STANDARD_NAMES) if (existsSync(n)) standards.push(n);
for (const d of ["docs", "docs/standards"]) {
  if (existsSync(d)) {
    for (const f of readdirSync(d)) if (/standard|style|contribut/i.test(f)) standards.push(join(d, f));
  }
}
// Spec candidates: issue refs in commit messages + spec files matching the branch.
const branch = git(["branch", "--show-current"]);
const issueRefs = [...new Set(commits.flatMap((c) => c.match(/#\d+|!\d+/g) || []))];
const specCandidates = [];
for (const d of ["docs", "specs", ".scratch"]) {
  if (!existsSync(d)) continue;
  const walk = (p) => {
    for (const f of readdirSync(p)) {
      const fp = join(p, f);
      statSync(fp).isDirectory() ? walk(fp) : specCandidates.push(fp);
    }
  };
  walk(d);
}
const specMatches = specCandidates.filter((f) =>
  branch && f.toLowerCase().includes(branch.toLowerCase().split("/").pop())
);

// Context mining: recent history per changed file + leftover author warnings.
const mining = changedFiles.slice(0, 20).map((f) => ({
  file: f,
  recent: lines(git(["log", "--oneline", "-5", "--", f])),
  warnings: lines(git(["grep", "-n", "-E", "TODO|FIXME|HACK", "--", f])).slice(0, 5),
}));

console.log(JSON.stringify(
  {
    fixed_point: fixed,
    merge_base: mergeBase,
    range,
    branch,
    commits,
    changed_files: changedFiles,
    diff_stat: diffStat,
    lines_changed_total: totalChanged,
    size_class: totalChanged <= 100
      ? "good (~100)"
      : totalChanged <= 300
      ? "acceptable (~300, single logical change)"
      : totalChanged < 1000
      ? "large — consider splitting"
      : "too large (~1000+) — split it",
    standards_candidates: [...new Set(standards)],
    issue_refs_in_commits: issueRefs,
    spec_candidates_for_branch: specMatches,
    run_command_candidates: {
      package_json: existsSync("package.json"),
      makefile: existsSync("Makefile"),
      docker_compose: existsSync("docker-compose.yml"),
    },
    context_mining: mining,
  },
  null,
  2,
));
if (!changedFiles.length) {
  console.error("ERROR empty diff against fixed point — failing here, not inside the reviewers");
  process.exit(1);
}
