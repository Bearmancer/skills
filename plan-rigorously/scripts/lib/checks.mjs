// Light check and checks 1-3. Pure: every outside fact arrives through `ctx`.
//
// ctx = {
//   config,                     // see state.mjs loadConfig
//   forcedPath,                 // null | 'quick' | 'full'
//   state,                      // engine state (intent, approval, reviews, ...)
//   exists(rel) -> boolean,     // path relative to the repo root
//   lineCount(rel) -> number|null,
//   commands: [{command}], fetches: [{url}], answers: [{question}],
//   observeFetches: boolean,    // can the adapter see doc fetches?
//   relaxCreates: boolean,      // build-stage amendments: files may exist already
// }
import { INTENT_KEYS, INTENT_LABELS } from './parse.mjs';
import {
  creatableGlobOk, foldCase, hasGlob, isSafeRel, matchesPathSpec, normRel,
} from './paths.mjs';

const PLACEHOLDERS = new Set(['', '...', '…', 'tbd', '?', '-', 'todo']);
const MAX_PATHS_PER_TASK = 5;
const MIN_QUOTE = 12;

export function intentIsSigned(plan, state) {
  return Boolean(state?.intent?.hash) && state.intent.hash === plan.hashes.intent;
}

export function approvalIsValid(plan, state) {
  return Boolean(state?.approval?.hash) && state.approval.hash === plan.hashes.plan;
}

export function lightCheck(plan, ctx) {
  const gaps = [];
  const files = plan.files;
  if (ctx.forcedPath === 'full') gaps.push('The user asked for the full path, so a light plan is not allowed.');
  if (files.length === 0) gaps.push('`## Files` lists no files.');
  const maxFiles = ctx.config.light.maxFiles;
  if (files.length > maxFiles && ctx.forcedPath !== 'quick') {
    gaps.push(`${files.length} files are listed; the light path allows at most ${maxFiles}.`);
  }
  const risky = ctx.config.light.riskPatterns;
  for (const f of files) {
    if (hasGlob(f)) {
      gaps.push(`${f} contains * or ?; \`## Files\` must list exact files.`);
      continue;
    }
    if (!isSafeRel(f)) {
      gaps.push(`${f} is not a path relative to, and inside, the repo.`);
      continue;
    }
    const rel = normRel(f);
    if (risky.some((re) => re.test(rel))) gaps.push(`${rel} matches a risk pattern (auth, security, secrets, migrations, CI, lockfiles, infra, payment, .claude, .git*, .husky, CLAUDE.md or AGENTS.md).`);
  }
  return gaps;
}

export function check1(plan, ctx) {
  const gaps = [];
  for (const key of INTENT_KEYS) {
    const value = (plan.intent[key] ?? '').trim();
    if (PLACEHOLDERS.has(value.toLowerCase())) gaps.push(`Intent line "${INTENT_LABELS[key]}" is missing or empty.`);
  }
  for (const q of plan.questions) {
    if (q.status === 'open') gaps.push(`${q.id} is still open.`);
    else if (q.status === 'waiting') gaps.push(`${q.id} is still waiting on ${q.waitsOn}.`);
  }
  const answers = ctx.answers ?? [];
  for (const q of plan.questions.filter((x) => x.status === 'answered')) {
    const re = new RegExp(`^\\s*${q.id}(?=[:\\s]|$)`);
    if (!answers.some((a) => re.test(String(a.question ?? '')))) {
      gaps.push(`${q.id} is marked answered but the user's answer to it was never recorded.`);
    }
  }
  return gaps;
}

function looksLikePath(token, ctx) {
  if (token.includes('://') || !token) return false;
  if (/^[\w.-]+(?:\/[\w.-]+)+\.[A-Za-z0-9]+$/.test(token)) return true;
  const fileish = token.includes('/') || /^[\w-]+\.[A-Za-z0-9]{1,6}$/.test(token);
  return fileish && isSafeRel(token) && ctx.exists(normRel(token));
}

function findCycle(tasks) {
  const byId = new Map(tasks.map((t) => [t.id, t]));
  const state = new Map();
  let cycle = null;
  const visit = (id, trail) => {
    if (cycle) return;
    if (state.get(id) === 'done') return;
    if (state.get(id) === 'active') {
      cycle = [...trail.slice(trail.indexOf(id)), id];
      return;
    }
    state.set(id, 'active');
    for (const dep of byId.get(id)?.depends ?? []) if (byId.has(dep)) visit(dep, [...trail, id]);
    state.set(id, 'done');
  };
  for (const t of tasks) visit(t.id, []);
  return cycle;
}

/** Splits a command on && || ; | outside quotes. */
function commandSegments(command) {
  const out = [];
  let cur = '';
  let quote = null;
  for (let i = 0; i < command.length; i++) {
    const c = command[i];
    if (quote) {
      if (c === quote) quote = null;
      cur += c;
    } else if (c === '"' || c === "'" || c === '`') {
      quote = c;
      cur += c;
    } else if (c === ';' || c === '|' || (c === '&' && command[i + 1] === '&')) {
      if (c === '&' || (c === '|' && command[i + 1] === '|')) i += 1;
      out.push(cur);
      cur = '';
    } else {
      cur += c;
    }
  }
  out.push(cur);
  return out.map((s) => s.trim()).filter(Boolean);
}

/** Creates patterns of every task that `task` transitively depends on. */
function inheritedCreates(task, byId) {
  const seen = new Set();
  const out = [];
  const stack = [...task.depends];
  while (stack.length) {
    const id = stack.pop();
    if (seen.has(id) || !byId.has(id)) continue;
    seen.add(id);
    const dep = byId.get(id);
    out.push(...dep.creates);
    stack.push(...dep.depends);
  }
  return out;
}

function claimGaps(plan, ctx) {
  const gaps = [];
  for (const c of plan.claims) {
    const p = c.proof;
    if (!p || p.kind === 'unknown') {
      gaps.push(`${c.id} has no valid proof (use doc: <url> "<quote>", code: <path>:<line>, or cmd: \`<command>\`).`);
    } else if (p.kind === 'code') {
      const rel = normRel(p.path);
      const len = isSafeRel(rel) && ctx.exists(rel) ? ctx.lineCount(rel) : null;
      if (len === null) gaps.push(`${c.id} cites ${p.path}, which does not exist.`);
      else if (p.line < 1 || p.line > len) gaps.push(`${c.id} cites line ${p.line} of ${rel}, which has ${len} lines.`);
    } else if (p.kind === 'cmd') {
      const want = p.command.trim();
      const ran = (ctx.commands ?? []).some((e) => {
        const recorded = String(e.command ?? '').trim();
        return recorded === want || commandSegments(recorded).includes(want);
      });
      if (!want || !ran) gaps.push(`${c.id} cites a command ("${p.command}") that was not run in this session.`);
    } else if (p.kind === 'doc') {
      if (p.quote.trim().length < MIN_QUOTE) gaps.push(`${c.id} needs a quoted passage of at least ${MIN_QUOTE} characters.`);
      if (ctx.observeFetches) {
        const strip = (u) => u.replace(/#.*$/, '').replace(/\/+$/, '');
        const fetched = (ctx.fetches ?? []).some((f) => strip(String(f.url ?? '')) === strip(p.url));
        if (!fetched) gaps.push(`${c.id} cites ${p.url}, which was not fetched in this session.`);
      }
    }
  }
  return gaps;
}

export function check2(plan, ctx) {
  const gaps = [];
  if (!intentIsSigned(plan, ctx.state)) gaps.push('The intent has not been signed, or it changed after signing.');

  const bIds = new Set(plan.behaviours.map((b) => b.id));
  const acIds = new Set(plan.criteria.map((a) => a.id));
  const taskIds = new Set(plan.tasks.map((t) => t.id));
  const byId = new Map(plan.tasks.map((t) => [t.id, t]));

  if (plan.behaviours.length === 0) gaps.push('The spec has no behaviours (B-n).');
  for (const ac of plan.criteria) {
    for (const b of ac.covers) if (!bIds.has(b)) gaps.push(`${ac.id} covers ${b}, which does not exist.`);
  }
  for (const b of plan.behaviours) {
    if (!plan.criteria.some((ac) => ac.covers.includes(b.id))) gaps.push(`${b.id} is not covered by any criterion.`);
  }
  for (const t of plan.tasks) {
    for (const a of t.covers) if (!acIds.has(a)) gaps.push(`${t.id} covers ${a}, which does not exist.`);
  }
  for (const ac of plan.criteria) {
    if (!plan.tasks.some((t) => t.covers.includes(ac.id))) gaps.push(`${ac.id} is not covered by any task.`);
  }

  for (const t of plan.tasks) {
    if (!t.verify) gaps.push(`${t.id} has no Verify line.`);
    if (t.edits.length + t.creates.length === 0) gaps.push(`${t.id} lists no files in Edits or Creates.`);
    for (const f of t.edits) {
      if (hasGlob(f)) gaps.push(`${t.id} Edits entry "${f}" contains glob characters; list exact paths.`);
      else if (!isSafeRel(f)) gaps.push(`${t.id} Edits entry "${f}" is not a path inside the repo.`);
      else if (!ctx.exists(normRel(f)) && !inheritedCreates(t, byId).some((c) => matchesPathSpec(c, f))) {
        gaps.push(`${t.id} edits ${normRel(f)}, which does not exist (and no task it depends on creates it).`);
      }
    }
    for (const f of t.creates) {
      if (!isSafeRel(f)) gaps.push(`${t.id} Creates entry "${f}" is not a path inside the repo.`);
      else if (!creatableGlobOk(f)) gaps.push(`${t.id} Creates entry "${f}" may use * or ? only in the file name (never ** or in a folder name); a wildcard name must not start with a dot and needs a letter or digit.`);
      else if (!hasGlob(f) && !ctx.relaxCreates && !t.done && ctx.exists(normRel(f))) gaps.push(`${t.id} creates ${normRel(f)}, which already exists; a file that is there already belongs under Edits:, so move it there.`);
    }
    if (t.edits.length + t.creates.length > MAX_PATHS_PER_TASK && t.batch !== 'wide-refactor') {
      gaps.push(`${t.id} declares ${t.edits.length + t.creates.length} files; split it or mark it "Batch: wide-refactor".`);
    }
    for (const d of t.depends) if (!taskIds.has(d)) gaps.push(`${t.id} depends on ${d}, which does not exist.`);
  }
  const cycle = findCycle(plan.tasks);
  if (cycle) gaps.push(`Task dependencies form a cycle: ${cycle.join(' -> ')}.`);

  const specText = [...plan.behaviours, ...plan.criteria].map((x) => `${x.id} ${x.text}`);
  const seenPaths = new Set();
  for (const line of specText) {
    for (const raw of line.split(/\s+/)) {
      const token = raw.replace(/^[\s"'`([<]+|[\s"'`)\],;:!?>]+$/g, '').replace(/\.$/, '');
      if (looksLikePath(token, ctx) && !seenPaths.has(foldCase(token))) {
        seenPaths.add(foldCase(token));
        gaps.push(`The spec mentions the file path "${token}"; the spec must not name files.`);
      }
    }
  }

  gaps.push(...claimGaps(plan, ctx));
  return gaps;
}

export const LENSES = ['soundness', 'completeness'];

export function check3(plan, ctx) {
  const gaps = [];
  const state = ctx.state;
  const reviews = state.reviews ?? [];
  const last = reviews.at(-1);
  const latestSpec = last?.specHash;
  const missing = LENSES.filter((lens) => !reviews.some((r) => r.lens === lens && r.specHash === latestSpec));
  const exhausted = Math.max(0, ...reviews.map((r) => r.round)) >= ctx.config.review.maxRounds;
  // Once the round limit is used up AND both lenses ran on the latest reviewed spec, a spec that moved on
  // after that cannot be reviewed any more; the change must be recorded as a `-> user: <decision>` finding.
  if (plan.hashes.spec !== state.reviewedSpecHash) {
    if (exhausted && plan.hashes.spec !== latestSpec) {
      if (missing.length) {
        gaps.push(`No ${missing.join(' or ')} review was run on the last reviewed spec, and no round is left for a changed spec: put the Spec lines back as in .rigor/state/snapshot.md, run the missing review on them, then make the change again.`);
      } else {
        if (!plan.review.findings.some((f) => f.disposition?.kind === 'user')) {
          gaps.push('The spec changed after the last review round and no round is left: put the change to the user in an ordinary question (not the `Approve plan` header), then record the answer in `## Review` as a finding with `-> user: <decision>`.');
        }
      }
    } else {
      for (const lens of LENSES) {
        const done = reviews.some((r) => r.lens === lens && r.specHash === plan.hashes.spec);
        if (!done) gaps.push(`No ${lens} review was run on the current spec.`);
      }
    }
  }
  const { findings, noFindings } = plan.review;
  if (findings.length === 0 && !noFindings) gaps.push('`## Review` is empty; record each finding or "No findings (round n)".');
  for (const f of findings) {
    if (!f.disposition) gaps.push(`${f.id} has no disposition (fixed, rejected: <reason>, or user: <decision>).`);
    else if (f.severity === 'blocker' && f.disposition.kind === 'rejected') {
      gaps.push(`${f.id} is a blocker that was rejected without a user decision (needs "user: <decision>").`);
    }
  }
  return gaps;
}
