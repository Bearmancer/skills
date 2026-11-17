// Claude Code adapter: hook stdin object -> { decision, reason?, context?, note? }.
// All plan logic lives in the core modules; this file maps events onto it and
// performs the engine-only state writes.
import { existsSync } from 'node:fs';
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { check1, check2, check3 } from './checks.mjs';
import { foldCase } from './paths.mjs';
import { parsePlan, stripReview } from './parse.mjs';
import { deriveStage, inScope, nextGaps, nextStepText } from './stage.mjs';
import {
  appendJsonl, canonicalPath, closePlan, defaultState, ensureGitExclude, fileLineCount, findGitRoot, findRoot, loadConfig,
  readJsonl, readState, readText, resetPlanFiles, rigorPaths, withLock, writeSnapshot, writeState,
} from './state.mjs';

const WRITE_TOOLS = new Set(['Write', 'Edit', 'NotebookEdit']);
const SHELL_TOOLS = new Set(['Bash', 'PowerShell', 'Monitor']);
const AGENT_TOOLS = new Set(['Agent', 'Task']);
const RESERVED = new Set(['sign intent', 'approve plan', 'close plan', 'amend plan', 'replace plan']);
const ENGINE_ONLY_PATH = /(^|\/)\.rigor\/(state|evidence)(\/|$)|(^|\/)\.rigor\/done\.log$/i;
const FORCED_PATH = /^\s*\/?plan-rigorously\s*:?\s*(quick|full)\b/i;
const OUTPUT_HEAD_CAP = 4096;
const COMMANDS_CAP = 500;
const STATUS_BULLETS = 10;
const ALLOW = { decision: 'allow' };

const deny = (reason) => ({ decision: 'deny', reason });
const asText = (v) => (typeof v === 'string' ? v : '');
// 'yesterday' and 'yes but' are not consent: a bare yes, a 'Yes,' prefix, or an offered option label starting with Yes
const yes = (answer, labels = []) => {
  const text = String(answer ?? '').trim();
  return /^yes\s*([.!]\s*)?$/i.test(text) || /^yes\s*,/i.test(text) || labels.some((l) => /^yes/i.test(l) && l === text);
};

/** What was blocked and why, what is missing (one bullet each), what to do next. */
function block(what, bullets, next) {
  const lines = [what];
  for (const b of bullets.slice(0, 15)) lines.push(`- ${b}`);
  if (bullets.length > 15) lines.push(`- ...and ${bullets.length - 15} more.`);
  if (next) lines.push(next);
  return lines.join('\n');
}

const ASK_AMEND = 'Ask the user with a question whose header is `Amend plan`.';

// ---------------------------------------------------------------- environment

function makeCtx(root, state, config, extra = {}) {
  const p = rigorPaths(root);
  const memo = {};
  const lazy = (key, read) => (memo[key] ??= read());
  return {
    root,
    config,
    state,
    forcedPath: state.forcedPath,
    observeFetches: true,
    relaxCreates: false,
    ...extra,
    exists: (rel) => existsSync(join(root, rel)),
    lineCount: (rel) => fileLineCount(join(root, rel)),
    get commands() { return lazy('commands', () => readJsonl(p.commands)); },
    get fetches() { return lazy('fetches', () => readJsonl(p.fetches)); },
    get answers() { return lazy('answers', () => readJsonl(p.answers)); },
  };
}

function load(root, opts) {
  const config = opts.config ?? loadConfig(opts.configPath);
  const state = readState(root, config);
  const p = rigorPaths(root);
  const text = readText(p.plan);
  const parsed = text === null ? null : parsePlan(text);
  // once a plan was approved, files made by finished tasks exist already; that is not a gap
  const ctx = makeCtx(root, state, config, { relaxCreates: Boolean(state.approval) });
  return {
    root, config, state, p, parsed, ctx, plan: parsed?.ok ? parsed.plan : null,
    stage: deriveStage(parsed, state, ctx),
  };
}

const nowIso = (opts) => (opts.now ? new Date(opts.now) : new Date()).toISOString();

function cwdOf(input) {
  return canonicalPath(input.cwd ? resolve(input.cwd) : process.cwd());
}

function targetPath(input) {
  const ti = input.tool_input ?? {};
  const raw = ti.file_path ?? ti.notebook_path ?? ti.path;
  return typeof raw === 'string' && raw ? resolve(cwdOf(input), raw) : null;
}

const sameDir = (a, b) => foldCase(resolve(a)) === foldCase(resolve(b));

/**
 * Finds the repo root and the root-relative path (forward slashes) for a file target.
 * Returns null (inert), { violation } for a misplaced `.rigor`, or { root, rel, inside }.
 * The OUTERMOST `.rigor` segment of the path decides, so `.rigor/.rigor/plan.md` and
 * `src/.rigor/plan.md` can never become rival roots.
 */
function locate(target) {
  // 8.3 short names (RIGOR~1), case and symlinks are settled before any name is compared
  const abs = canonicalPath(target);
  let cur = abs;
  const below = [];
  let outer = null;
  for (;;) {
    const up = dirname(cur);
    // Windows ignores trailing dots and spaces in a name, so `.rigor.` is `.rigor`
    if (foldCase(basename(cur).replace(/[. ]+$/, '')) === '.rigor') outer = { x: up, tail: [...below] };
    if (up === cur) break;
    below.unshift(basename(cur));
    cur = up;
  }
  if (outer) {
    const { x, tail } = outer;
    const rel = ['.rigor', ...tail].join('/');
    const name = tail.length === 1 ? foldCase(tail[0]) : '';
    const existing = findRoot(x);
    if (existing && !sameDir(existing, x)) {
      return { violation: block(
        `Writing ${rel} under ${x} was blocked because the plan root is ${existing}, and a second .rigor folder below it is not allowed.`,
        [],
        'Use .rigor/plan.md and .rigor/map.md at the plan root only.',
      ) };
    }
    if (!existing) {
      if (name !== 'plan.md' && name !== 'map.md') {
        return { violation: block(`Writing ${rel} was blocked because the .rigor folder does not exist yet and only plan.md or map.md may be written first.`, [], 'Write .rigor/plan.md first.') };
      }
      const git = findGitRoot(x);
      if (git && !sameDir(git, x)) {
        return { violation: block(`Creating ${rel} here was blocked because .rigor must sit at the project root (${git}), not in a subfolder.`, [], 'Put the plan at the project root instead.') };
      }
    }
    return { root: x, rel, inside: true };
  }
  const root = findRoot(dirname(abs));
  if (!root) return null;
  const rel = relative(root, abs).split(sep).join('/');
  const f = foldCase(rel);
  return { root, rel, inside: f === '.rigor' || f.startsWith('.rigor/') };
}

function statusLine(env) {
  if (env.stage === 'invalid') return 'plan-rigorously: .rigor/plan.md cannot be read; repair it so it parses.';
  return `plan-rigorously: plan "${env.plan.name}" is in stage ${env.stage}. Next: ${nextStepText(env.stage, env.plan)}.`;
}

function statusBlock(env) {
  const gaps = nextGaps(env.stage, env.parsed, env.ctx);
  const lines = [statusLine(env)];
  for (const g of gaps.slice(0, STATUS_BULLETS)) lines.push(`- ${g}`);
  if (gaps.length > STATUS_BULLETS) lines.push(`- ...and ${gaps.length - STATUS_BULLETS} more.`);
  return lines.join('\n');
}

// ---------------------------------------------------------------- dispatch

export function handleHook(input, opts = {}) {
  try {
    return dispatch(input ?? {}, opts);
  } catch (err) {
    let protectedCall = false;
    try {
      protectedCall = isEngineOnlyCall(input);
    } catch {
      // the call cannot even be inspected, so it cannot be shown to touch engine files
    }
    if (protectedCall) {
      return deny('This call touches files that only the plan tool may change, and it could not be checked safely, so it was blocked.');
    }
    return { decision: 'allow', note: `plan-rigorously: ignored an unexpected error (${err?.message ?? err})` };
  }
}

function isEngineOnlyCall(input) {
  if (input?.hook_event_name !== 'PreToolUse') return false;
  const tool = input.tool_name;
  const ti = input.tool_input ?? {};
  if (SHELL_TOOLS.has(tool)) return namesRigor(ti.command);
  if (WRITE_TOOLS.has(tool)) {
    const raw = asText(ti.file_path ?? ti.notebook_path);
    if (ENGINE_ONLY_PATH.test(raw.replace(/\\/g, '/'))) return true;
    try {
      return ENGINE_ONLY_PATH.test(canonicalPath(resolve(cwdOf(input), raw)).replace(/\\/g, '/'));
    } catch {
      return false;
    }
  }
  return false;
}

function dispatch(input, opts) {
  switch (input.hook_event_name) {
    case 'PreToolUse':
      return preTool(input, opts);
    case 'PostToolUse':
      return postTool(input, opts);
    case 'UserPromptSubmit':
      return promptSubmit(input, opts);
    case 'SessionStart':
      return sessionStart(input, opts);
    default:
      return ALLOW;
  }
}

function preTool(input, opts) {
  const tool = input.tool_name;
  if (WRITE_TOOLS.has(tool)) return preWrite(input, opts);
  if (SHELL_TOOLS.has(tool)) return preShell(input);
  if (tool === 'AskUserQuestion') return preAsk(input, opts);
  if (AGENT_TOOLS.has(tool)) return preAgent(input, opts);
  return ALLOW;
}

function postTool(input, opts) {
  const tool = input.tool_name;
  if (tool === 'Write' || tool === 'Edit') return postPlanWrite(input, opts);
  if (SHELL_TOOLS.has(tool)) return postShell(input, opts);
  if (tool === 'WebFetch') return postFetch(input, opts);
  if (tool === 'AskUserQuestion') return postAsk(input, opts);
  return ALLOW;
}

// ---------------------------------------------------------------- PreToolUse: writes

/** The file content after the tool runs, or null when the tool will fail by itself. */
function wouldBeContent(input, file) {
  const ti = input.tool_input ?? {};
  if (input.tool_name === 'Write') return typeof ti.content === 'string' ? ti.content : null;
  const current = readText(file);
  if (current === null || typeof ti.old_string !== 'string' || ti.old_string === '') return null;
  const text = current.replace(/\r\n?/g, '\n');
  const oldS = ti.old_string.replace(/\r\n?/g, '\n');
  const newS = asText(ti.new_string).replace(/\r\n?/g, '\n');
  const count = text.split(oldS).length - 1;
  if (count === 0 || (count > 1 && !ti.replace_all)) return null;
  return ti.replace_all ? text.split(oldS).join(newS) : text.replace(oldS, () => newS);
}

function preWrite(input, opts) {
  const target = targetPath(input);
  if (!target) return ALLOW;
  const loc = locate(target);
  if (!loc) return ALLOW;
  if (loc.violation) return deny(loc.violation);
  const env = load(loc.root, opts);
  return loc.inside ? preWriteInside(input, loc, env) : preWriteOutside(loc, env);
}

function preWriteInside(input, loc, env) {
  const name = foldCase(loc.rel.slice('.rigor/'.length));
  const notebook = input.tool_name === 'NotebookEdit';
  if (name === 'map.md' && !notebook) return ALLOW;
  if (name !== 'plan.md' || notebook) {
    return deny(block(
      `Writing ${loc.rel} was blocked because only .rigor/plan.md and .rigor/map.md may be written by hand; everything else in .rigor is managed by the plan tool.`,
      [],
      'Put the content in .rigor/plan.md (or .rigor/map.md for a decision map) instead.',
    ));
  }
  const next = wouldBeContent(input, env.p.plan);
  if (next === null) return ALLOW;
  const res = parsePlan(next);
  if (!res.ok) {
    return deny(block('This write to .rigor/plan.md was blocked because the plan would not parse.', res.errors, 'Fix those points and write the plan again.'));
  }
  if (env.plan && env.plan.name !== res.plan.name) {
    if (env.state.replaceOk) return ALLOW;
    return deny(block(
      `This write was blocked because .rigor/plan.md already holds the unfinished plan "${env.plan.name}" and there is only ever one plan.`,
      [`The new plan is named "${res.plan.name}".`],
      'Ask the user with a question whose header is `Replace plan`, or keep working on the current plan.',
    ));
  }
  if (env.stage === 'build' && !env.state.amendOpen && res.plan.hashes.plan !== env.plan.hashes.plan) {
    return deny(block(
      'This change to .rigor/plan.md was blocked because the plan is approved and read-only during the build; only ticking task checkboxes and the Review section may change.',
      [],
      env.state.replaceOk
        ? 'To replace an approved plan, write the new plan under a new `name:`; a rewrite under the same name works only before approval.'
        : ASK_AMEND,
    ));
  }
  return ALLOW;
}

function preWriteOutside(loc, env) {
  if (env.stage === 'none') return ALLOW;
  const f = foldCase(loc.rel);
  if (f === 'glossary.md' || f.startsWith('docs/adr/')) return ALLOW;
  const { stage, plan } = env;
  switch (stage) {
    case 'invalid':
      return deny(block(`Editing ${loc.rel} was blocked because .rigor/plan.md cannot be read.`, env.parsed.errors, 'Repair .rigor/plan.md first.'));
    case 'light':
      if (inScope(stage, plan, loc.rel)) return ALLOW;
      return deny(block(
        `Editing ${loc.rel} was blocked because it is not listed under \`## Files\` in the light plan.`,
        [],
        'Rewrite the plan as `path: full`, or ask the user.',
      ));
    case 'build':
      if (inScope(stage, plan, loc.rel, env.config.light.riskPatterns)) {
        if (env.state.amendOpen) {
          withLock(env.root, () => writeState(env.root, { ...readState(env.root, env.config), amendOpen: false }));
        }
        return ALLOW;
      }
      return deny(block(`Editing ${loc.rel} was blocked because no task in the approved plan lists it under Edits or Creates.`, [], ASK_AMEND));
    default:
      return deny(block(
        `Editing ${loc.rel} was blocked because the plan is still in the ${stage} stage, and planning only allows writes to .rigor/plan.md, .rigor/map.md, GLOSSARY.md and docs/adr/.`,
        [],
        stage === 'light-invalid'
          ? 'Rewrite the plan as `path: full`.'
          : 'Finish the plan and get it approved; code changes start after the user approves it.',
      ));
  }
}

// ---------------------------------------------------------------- PreToolUse: shell, agent, questions

// The guard stops accidental edits of .rigor. Deliberate evasion through the shell is out of scope.
const RIGOR_WORD = /(^|[\s\\/'"=([{,;:])\.rigor([\\/\s'"]|$)/i;
const namesRigor = (command) => RIGOR_WORD.test(asText(command).replace(/\\/g, '/').replace(/[`^'"]/g, ''));

function preShell(input) {
  const command = asText(input.tool_input?.command);
  if (!namesRigor(command)) return ALLOW;
  const roots = new Set();
  const cwdRoot = findRoot(cwdOf(input));
  if (cwdRoot) roots.add(cwdRoot);
  // an absolute path token can name .rigor in a checkout other than the cwd's
  for (const m of command.matchAll(/"[^"]*"|'[^']*'|`[^`]*`|\S+/g)) {
    const path = m[0].replace(/^["'`]+|["'`]+$/g, '');
    if (!isAbsolute(path) || !/\.rigor/i.test(path)) continue;
    const root = findRoot(dirname(path));
    if (root) roots.add(root);
  }
  for (const root of roots) {
    // the plan file, not state.json: a plan written from the shell has no state until the first answer
    if (existsSync(rigorPaths(root).plan)) {
      return deny(block(
        'This command was blocked because it names .rigor while a plan is live.',
        [],
        'Use the file tools for .rigor/plan.md and .rigor/map.md; nothing else in .rigor is yours to touch.',
      ));
    }
  }
  return ALLOW;
}

function preAgent(input, opts) {
  const ti = input.tool_input ?? {};
  const marker = /^[ \t]*rigor-review:[ \t]*(soundness|completeness)[ \t]*$/im.exec(asText(ti.prompt));
  if (!marker) return ALLOW;
  const root = findRoot(cwdOf(input));
  if (!root) return ALLOW;
  return withLock(root, () => reviewGate(ti, opts, root, marker[1].toLowerCase()));
}

function reviewGate(ti, opts, root, lens) {
  const env = load(root, opts);
  if (env.stage !== 'drafting') {
    return deny(block(`The ${lens} review was blocked because a review can only start while the plan is in the drafting stage (it is in ${env.stage}).`, [], 'Finish the earlier stage first.'));
  }
  const gaps = check2(env.plan, env.ctx);
  if (gaps.length) {
    return deny(block(`The ${lens} review was blocked because the plan is not fully drafted yet.`, gaps, 'Fix these points in .rigor/plan.md, then start the review again.'));
  }
  const model = asText(ti.model).trim();
  if (!model || /fable|inherit/i.test(model)) {
    return deny(block(
      `The ${lens} review was blocked because the reviewer must run on an explicit model that is not Fable and is not "inherit".`,
      [`Pass the model \`${env.config.reviewer.model}\`.`],
      'Start the review again with that model set.',
    ));
  }
  if (asText(ti.subagent_type).toLowerCase() === 'fork') {
    return deny(block(`The ${lens} review was blocked because a fork would inherit the planner's reasoning.`, [], 'Start a fresh reviewer agent (not a fork) with only the snapshot.'));
  }

  const state = { ...env.state, reviews: [...env.state.reviews] };
  const hash = env.plan.hashes.plan;
  const specHash = env.plan.hashes.spec;
  let round = Math.max(0, ...state.reviews.map((r) => r.round));
  if (state.snapshotHash !== hash || round === 0) {
    // a round is a new version of the SPEC under review; edits to tasks, claims or wording reuse the round
    if (round === 0 || state.reviews.at(-1)?.specHash !== specHash) {
      round += 1;
      if (round > env.config.review.maxRounds) {
        const open = env.plan.review.findings.filter((f) => !f.disposition).map((f) => `${f.id} is still open.`);
        const lastSpec = state.reviews.at(-1)?.specHash;
        const missing = ['soundness', 'completeness'].filter((l) => !state.reviews.some((r) => r.lens === l && r.specHash === lastSpec));
        return deny(block(
          `Round limit reached: the spec changed after review round ${env.config.review.maxRounds}, and no further reviewer can be started for it.`,
          open,
          missing.length
            ? `The ${missing.join(' and ')} review never ran on the last reviewed spec. Put the Spec lines back as in .rigor/state/snapshot.md, run that review on them (allowed: the spec is the same), then make the change again.`
            : 'Put the open findings and the late spec change to the user in an ordinary question (not the `Approve plan` header), record each answer in `## Review` as a finding with `-> user: <decision>`, then ask `Approve plan`.',
        ));
      }
    }
    writeSnapshot(env.root, stripReview(env.plan.text));
    state.snapshotHash = hash;
  }
  if (!state.reviews.some((r) => r.lens === lens && r.hash === hash)) {
    state.reviews.push({
      round, lens, hash, specHash, model, at: nowIso(opts),
    });
  }
  writeState(env.root, state);
  return ALLOW;
}

function preAsk(input, opts) {
  const root = findRoot(cwdOf(input));
  if (!root) return ALLOW;
  const questions = Array.isArray(input.tool_input?.questions) ? input.tool_input.questions : [];
  if (questions.length === 0) return ALLOW;
  const env = load(root, opts);
  for (const q of questions) {
    const header = asText(q?.header).trim().toLowerCase();
    // a double quote anywhere in a checkpoint question can fake answer pairs in the text fallback
    if (RESERVED.has(header) && hasQuote(q)) {
      return deny(block(
        `The \`${asText(q?.header).trim()}\` question was blocked because it contains a double quote, which could fake answer pairs when the answers are read as text.`,
        [],
        'Use single quotes instead of double quotes in the question, header, option labels, descriptions and previews, then ask again.',
      ));
    }
    const refusal = askRefusal(header, env);
    if (refusal) return deny(refusal);
  }
  return ALLOW;
}

function askRefusal(header, env) {
  const { stage } = env;
  if (header === 'sign intent') {
    if (stage === 'invalid') return block('The `Sign intent` question was blocked because .rigor/plan.md cannot be read.', env.parsed.errors, 'Repair the plan first.');
    if (!env.plan || env.plan.path !== 'full') return null;
    const gaps = check1(env.plan, env.ctx);
    return gaps.length ? block('The `Sign intent` question was blocked because the intent is not ready to be signed.', gaps, 'Settle these points in .rigor/plan.md (asking the user where needed), then ask again.') : null;
  }
  if (header === 'approve plan') {
    if (stage === 'invalid') return block('The `Approve plan` question was blocked because .rigor/plan.md cannot be read.', env.parsed.errors, 'Repair the plan first.');
    if (stage === 'build') return block('The `Approve plan` question was blocked because the plan is already approved.', [], ASK_AMEND);
    if (stage === 'light' || stage === 'light-invalid') return block('The `Approve plan` question was blocked because a light plan needs no approval.', [], 'Edit the listed files, or rewrite the plan as `path: full` if it grew.');
    if (!env.plan) return null;
    const gaps = [...check2(env.plan, env.ctx), ...check3(env.plan, env.ctx)];
    return gaps.length ? block('The `Approve plan` question was blocked because the plan is not ready for approval.', gaps, 'Fix these points in .rigor/plan.md (and run the reviews that are missing), then ask again.') : null;
  }
  if (RESERVED.has(header)) return null;
  if (stage === 'intent' && env.state.rounds >= env.state.roundCap) {
    const open = env.plan.questions.filter((q) => q.status !== 'answered').map((q) => `${q.id} is unsettled.`);
    return block(
      `This question was blocked because the interview already used ${env.state.rounds} rounds, which is the limit.`,
      open,
      'Stop asking: tell the user in your reply what is still unsettled and let them decide (a new message from them allows more rounds).',
    );
  }
  return null;
}

// ---------------------------------------------------------------- PostToolUse

function postPlanWrite(input, opts) {
  const target = targetPath(input);
  if (!target) return ALLOW;
  const loc = locate(target);
  if (!loc || !loc.inside || foldCase(loc.rel) !== '.rigor/plan.md') return ALLOW;
  return withLock(loc.root, () => recordPlanWrite(loc.root, opts));
}

/** Always works from the real file on disk, never from what the pre-hook simulated. */
function recordPlanWrite(root, opts) {
  const env = load(root, opts);
  if (!env.plan) return env.parsed ? { decision: 'allow', context: statusBlock(env) } : ALLOW;
  const { plan } = env;

  let state = env.state;
  // A replacing plan starts clean: another name, or (right after the user approved `Replace plan`) a rewrite
  // with a different Intent. Old answers, sign-off, approval and evidence must not satisfy it.
  const rewritten = state.replaceOk && state.intentHash && state.intentHash !== plan.hashes.intent;
  if (state.planName && (state.planName !== plan.name || rewritten)) {
    const since = state.replaceAt; // evidence gathered after the user agreed to replace belongs to the new plan
    state = { ...defaultState(env.config), forcedPath: null };
    resetPlanFiles(root, since);
  }
  state = {
    ...state,
    planName: plan.name,
    replaceOk: false,
    replaceAt: null,
    intentHash: plan.hashes.intent,
  };
  let note = '';
  if (state.approval && state.amendOpen) {
    if (state.approval.specHash === plan.hashes.spec) {
      const relaxed = makeCtx(root, state, env.config, { relaxCreates: true });
      if (check2(plan, relaxed).length === 0) {
        state.approval = { ...state.approval, hash: plan.hashes.plan, at: nowIso(opts) };
        note = '\nThe approval carried over to the amended plan.';
      }
    } else {
      state = { ...state, approval: null, amendOpen: false, reviews: [], snapshotHash: null };
    }
  } else if (state.approval && state.approval.hash !== plan.hashes.plan) {
    state = { ...state, approval: null };
    note = '\nThe approved plan was changed outside an amendment, so its approval was dropped and the plan is back in drafting. `Amend plan` cannot restore it; get it approved again with the `Approve plan` question.';
  }
  writeState(root, state);

  return { decision: 'allow', context: statusBlock(load(root, opts)) + note };
}

function outputHead(response) {
  let text;
  if (response && typeof response === 'object') {
    const parts = ['stdout', 'stderr', 'output'].map((k) => response[k]).filter((v) => typeof v === 'string' && v);
    text = parts.length ? parts.join('\n') : JSON.stringify(response);
  } else {
    text = typeof response === 'string' ? response : JSON.stringify(response ?? '');
  }
  return text.slice(0, OUTPUT_HEAD_CAP);
}

function evidenceEnv(input, opts) {
  const root = findRoot(cwdOf(input));
  if (!root) return null;
  const env = load(root, opts);
  return env.stage === 'intent' || env.stage === 'drafting' ? env : null;
}

function postShell(input, opts) {
  const env = evidenceEnv(input, opts);
  if (!env) return ALLOW;
  const r = input.tool_response;
  const exit = r && typeof r === 'object' ? (r.exit_code ?? r.exitCode ?? r.returncode ?? r.code) : undefined;
  const entry = {
    command: asText(input.tool_input?.command), at: nowIso(opts), outputHead: outputHead(r),
  };
  if (Number.isInteger(exit)) entry.exitCode = exit;
  withLock(env.root, () => appendJsonl(env.p.commands, entry, COMMANDS_CAP));
  ensureGitExclude(env.root);
  return ALLOW;
}

function postFetch(input, opts) {
  const env = evidenceEnv(input, opts);
  if (!env) return ALLOW;
  const url = asText(input.tool_input?.url) || asText(input.tool_response?.url);
  if (!url) return ALLOW;
  withLock(env.root, () => appendJsonl(env.p.fetches, { url, at: nowIso(opts) }, COMMANDS_CAP));
  ensureGitExclude(env.root);
  return ALLOW;
}

const hasQuote = (q) => [q?.question, q?.header, ...(Array.isArray(q?.options) ? q.options.flatMap((o) => [o?.label, o?.description, o?.preview]) : [])]
  .some((v) => typeof v === 'string' && v.includes('"'));

/** [{ header, question, answer }] from the AskUserQuestion input and response. */
function extractAnswers(input) {
  const questions = Array.isArray(input.tool_input?.questions) ? input.tool_input.questions : [];
  const resp = input.tool_response;
  let pairs = [];
  if (resp && typeof resp === 'object' && resp.answers && typeof resp.answers === 'object' && !Array.isArray(resp.answers)) {
    pairs = Object.entries(resp.answers);
  } else {
    let text = typeof resp === 'string' ? resp : '';
    if (resp && typeof resp === 'object') {
      const content = Array.isArray(resp.content) ? resp.content.map((c) => asText(c?.text)).join('\n') : asText(resp.content);
      text = asText(resp.text) || content || JSON.stringify(resp).replace(/\\"/g, '"');
    }
    // The text embeds model-written strings (question, header, option labels). One containing a double
    // quote could fake `"question"="answer"` pairs, so the text is not read at all (fail safe).
    if (!questions.some(hasQuote)) for (const m of text.matchAll(/"([^"]*)"="([^"]*)"/g)) pairs.push([m[1], m[2]]);
  }
  const structured = Boolean(resp && typeof resp === 'object' && resp.answers && typeof resp.answers === 'object' && !Array.isArray(resp.answers));
  const out = [];
  for (const [question, answer] of pairs) {
    const q = questions.find((x) => x?.question === question)
      ?? questions.find((x) => asText(x?.question).trim() === question.trim());
    // Text pairs are scraped from a string that embeds the model's own question text, so a pair whose
    // question is not one of the asked questions may have been forged inside a question: drop it.
    if (!q && !structured) continue;
    const text = Array.isArray(answer) ? answer.join(', ') : String(answer ?? '');
    const labels = Array.isArray(q?.options) ? q.options.map((o) => asText(o?.label)) : [];
    out.push({ header: asText(q?.header).trim(), question, answer: text, labels });
  }
  return out;
}

const openCount = (plan) => plan.questions.filter((q) => q.status !== 'answered').length;

function postAsk(input, opts) {
  const root = findRoot(cwdOf(input));
  if (!root) return ALLOW;
  const answers = extractAnswers(input);
  if (answers.length === 0) return ALLOW;
  return withLock(root, () => recordAnswers(root, answers, opts));
}

function recordAnswers(root, answers, opts) {
  const env = load(root, opts);
  const at = nowIso(opts);
  for (const a of answers) appendJsonl(env.p.answers, { at, header: a.header, question: a.question, answer: a.answer });

  let state = { ...env.state };
  const contexts = [];
  let closed = false;
  let interviewRound = false;
  for (const a of answers) {
    const header = a.header.toLowerCase();
    if (!RESERVED.has(header)) {
      interviewRound = true;
      continue;
    }
    if (!yes(a.answer, a.labels)) continue;
    // the plan may have changed between the question and the answer: check again before recording
    if (header === 'sign intent' && env.plan) {
      const gaps = check1(env.plan, env.ctx);
      if (gaps.length) {
        contexts.push(block('The `Sign intent` answer was not recorded because the intent is not ready to be signed.', gaps, 'Settle these points in .rigor/plan.md (asking the user where needed), then ask again.'));
        continue;
      }
      state.intent = { hash: env.plan.hashes.intent, at };
    } else if (header === 'approve plan' && env.plan) {
      const gaps = [...check2(env.plan, env.ctx), ...check3(env.plan, env.ctx)];
      if (gaps.length) {
        contexts.push(block('The `Approve plan` answer was not recorded because the plan is not ready for approval.', gaps, 'Fix these points in .rigor/plan.md (and run the reviews that are missing), then ask again.'));
        continue;
      }
      state.approval = { hash: env.plan.hashes.plan, specHash: env.plan.hashes.spec, at };
      state.reviewedSpecHash = env.plan.hashes.spec;
      state.amendOpen = false;
    } else if (header === 'amend plan') state.amendOpen = true;
    else if (header === 'replace plan') {
      state.replaceOk = true;
      state.replaceAt = at;
    }
    else if (header === 'close plan') {
      closePlan(root, doneLine(env, a.answer, opts));
      closed = true;
    }
  }
  if (closed) return ALLOW;

  if (interviewRound && env.stage === 'intent' && env.plan) {
    state.rounds += 1;
    const open = openCount(env.plan);
    const stalled = state.lastOpenCount !== null && open >= state.lastOpenCount;
    state.stall = stalled ? state.stall + 1 : 0;
    state.lastOpenCount = open;
    if (state.rounds === env.config.rounds.soft) {
      contexts.push(`plan-rigorously: soft limit reached (${state.rounds} interview rounds). Offer the user to wrap up with what is settled.`);
    }
    if (state.stall >= env.config.rounds.stall) {
      contexts.push(`plan-rigorously: ${state.stall} rounds in a row without fewer open questions. Step back: restate what is settled and ask what is blocking.`);
      state.stall = 0;
    }
  }
  writeState(root, state);
  return contexts.length ? { decision: 'allow', context: contexts.join('\n') } : ALLOW;
}

function doneLine(env, answer, opts) {
  const d = opts.now ? new Date(opts.now) : new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const name = env.plan?.name || /^name:\s*(\S+)/m.exec(env.parsed?.plan?.text ?? '')?.[1] || 'unknown';
  const finished = env.plan && (env.plan.path === 'light' || (env.plan.tasks.length > 0 && env.plan.tasks.every((t) => t.done)));
  const outcome = /abandon/i.test(answer) ? 'abandoned' : finished ? 'done' : 'closed';
  return `${date} ${name} ${outcome}`;
}

// ---------------------------------------------------------------- prompt and session

function promptSubmit(input, opts) {
  const cwd = cwdOf(input);
  const forced = FORCED_PATH.exec(asText(input.prompt))?.[1]?.toLowerCase() ?? null;
  // a forced path is only ever stored at a git root; outside a repo nothing is created
  const root = findRoot(cwd) ?? (forced ? findGitRoot(cwd) : null);
  if (!root) return ALLOW;
  return withLock(root, () => recordPrompt(root, forced, opts));
}

function recordPrompt(root, forced, opts) {
  const env = load(root, opts);
  const state = { ...env.state };
  let changed = false;
  const lines = [];
  if (forced) {
    state.forcedPath = forced;
    changed = true;
    lines.push(`plan-rigorously: the user chose the ${forced} path.`);
  }
  if (state.rounds >= state.roundCap) {
    state.roundCap += 10;
    changed = true;
  }
  if (changed) writeState(root, state);
  if (env.parsed) {
    const after = load(root, opts);
    lines.push(statusLine(after));
  }
  return lines.length ? { decision: 'allow', context: lines.join('\n') } : ALLOW;
}

function sessionStart(input, opts) {
  const root = findRoot(cwdOf(input));
  if (!root) return ALLOW;
  const env = load(root, opts);
  return env.parsed ? { decision: 'allow', context: statusLine(env) } : ALLOW;
}

// ---------------------------------------------------------------- output

/** The JSON object to print for an event, or null to print nothing. One place per shape. */
export function formatOutput(input, result) {
  const event = input?.hook_event_name;
  if (event === 'PreToolUse') {
    if (result.decision !== 'deny') return null;
    return {
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'deny',
        permissionDecisionReason: result.reason,
      },
    };
  }
  if (!result.context) return null;
  if (event === 'PostToolUse' || event === 'UserPromptSubmit' || event === 'SessionStart') {
    return { hookSpecificOutput: { hookEventName: event, additionalContext: result.context } };
  }
  return null;
}
