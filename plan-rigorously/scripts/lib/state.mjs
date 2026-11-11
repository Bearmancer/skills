// Engine state, evidence and config on disk. Knows nothing about any harness.
import {
  appendFileSync, closeSync, existsSync, mkdirSync, openSync, readFileSync, realpathSync, renameSync, rmSync, statSync, writeFileSync,
} from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

export const DEFAULT_CONFIG = {
  reviewer: { model: 'sonnet' },
  light: {
    maxFiles: 3,
    riskPatterns: [
      '(^|[/._-])auth(n|z|entication|orization|0)?([/._-]|$)',
      '(^|[/._-])(security|secrets?|credentials?)([/._-]|$)',
      '(^|/)\\.env(\\..*)?$',
      '(^|/)migrations?(/|$)',
      '(^|/)\\.github/workflows/',
      '(^|/)(\\.gitlab-ci\\.ya?ml|azure-pipelines\\.ya?ml|Jenkinsfile|\\.travis\\.yml)$',
      '(^|/)(package-lock\\.json|npm-shrinkwrap\\.json|yarn\\.lock|pnpm-lock\\.yaml|bun\\.lockb?|Cargo\\.lock|poetry\\.lock|Pipfile\\.lock|Gemfile\\.lock|composer\\.lock|go\\.sum)$',
      '(^|/)(infra|infrastructure|terraform|k8s|kubernetes|helm|ansible|deploy)(/|$)|\\.tf$|(^|/)Dockerfile',
      '(^|[/._-])(payments?|billing|checkout|stripe)([/._-]|$)',
      '(^|/)\\.(claude|git|rigor|githooks|husky)(/|$)',
      '(^|/)(CLAUDE|AGENTS)\\.md$',
    ],
  },
  rounds: { soft: 10, hard: 20, stall: 3 },
  review: { maxRounds: 3 },
};

export const DEFAULT_CONFIG_PATH = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'config.json');

function pickNumber(v, fallback) {
  return Number.isFinite(v) && v > 0 ? v : fallback;
}

/** Reads config.json; anything missing or unreadable falls back to built-in defaults. */
export function loadConfig(path = DEFAULT_CONFIG_PATH) {
  let raw = {};
  try {
    raw = JSON.parse(readFileSync(path, 'utf8')) ?? {};
  } catch {
    raw = {};
  }
  const d = DEFAULT_CONFIG;
  const patterns = Array.isArray(raw.light?.riskPatterns) ? raw.light.riskPatterns : d.light.riskPatterns;
  const compiled = [];
  for (const p of patterns) {
    try {
      compiled.push(new RegExp(p, 'i'));
    } catch {
      // an invalid pattern is skipped rather than disabling the whole config
    }
  }
  const model = typeof raw.reviewer?.model === 'string' && raw.reviewer.model.trim() ? raw.reviewer.model.trim() : d.reviewer.model;
  return {
    reviewer: { model },
    light: { maxFiles: pickNumber(raw.light?.maxFiles, d.light.maxFiles), riskPatterns: compiled },
    rounds: {
      soft: pickNumber(raw.rounds?.soft, d.rounds.soft),
      hard: pickNumber(raw.rounds?.hard, d.rounds.hard),
      stall: pickNumber(raw.rounds?.stall, d.rounds.stall),
    },
    review: { maxRounds: pickNumber(raw.review?.maxRounds, d.review.maxRounds) },
  };
}

export function sha256(text) {
  return createHash('sha256').update(text).digest('hex');
}

export function rigorPaths(root) {
  const dir = join(root, '.rigor');
  return {
    dir,
    plan: join(dir, 'plan.md'),
    map: join(dir, 'map.md'),
    evidenceDir: join(dir, 'evidence'),
    commands: join(dir, 'evidence', 'commands.jsonl'),
    fetches: join(dir, 'evidence', 'fetches.jsonl'),
    stateDir: join(dir, 'state'),
    stateFile: join(dir, 'state', 'state.json'),
    answers: join(dir, 'state', 'answers.jsonl'),
    snapshot: join(dir, 'state', 'snapshot.md'),
    doneLog: join(dir, 'done.log'),
  };
}

/**
 * Canonical form of a path: the deepest existing ancestor goes through `realpathSync.native`
 * (which expands Windows 8.3 short names such as RIGOR~1 and settles case), the not-yet-existing
 * tail is appended as given.
 */
export function canonicalPath(abs) {
  const tail = [];
  let cur = abs;
  for (;;) {
    try {
      return join(realpathSync.native(cur), ...tail);
    } catch {
      // this level does not exist (or cannot be read); try its parent
    }
    const up = dirname(cur);
    if (up === cur) return abs;
    tail.unshift(basename(cur));
    cur = up;
  }
}

/**
 * The one root finder. Walks up from `startDir` (inclusive) and returns the OUTERMOST folder holding a
 * `.rigor` folder. A `.git` FILE (a linked worktree or submodule) marks an independent checkout and cuts the
 * search off above it; a nested `.git` folder does not, so everything under the root is in scope. A folder
 * that is itself named `.rigor` is never a root. Returns null when there is no root.
 */
export function findRoot(startDir) {
  let dir = resolve(startDir);
  let found = null;
  for (;;) {
    if (basename(dir).toLowerCase() !== '.rigor' && existsSync(join(dir, '.rigor'))) found = dir;
    try {
      if (!statSync(join(dir, '.git')).isDirectory()) return found;
    } catch {
      // no .git here
    }
    const up = dirname(dir);
    if (up === dir) return found;
    dir = up;
  }
}

/** Nearest ancestor (including `startDir`) holding `.git`, or null. */
export function findGitRoot(startDir) {
  let dir = resolve(startDir);
  for (;;) {
    if (existsSync(join(dir, '.git'))) return dir;
    const up = dirname(dir);
    if (up === dir) return null;
    dir = up;
  }
}

function sleepMs(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

/** Temp file + rename, so a reader never sees half a file. */
function atomicWrite(file, text) {
  mkdirSync(dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.${Math.random().toString(36).slice(2)}.tmp`;
  writeFileSync(tmp, String(text).replace(/\r\n?/g, '\n'));
  for (let attempt = 0; ; attempt++) {
    try {
      renameSync(tmp, file);
      return;
    } catch (err) {
      if (attempt >= 8) {
        rmSync(tmp, { force: true });
        throw err;
      }
      sleepMs(10 * (attempt + 1));
    }
  }
}

const LOCK_STALE_MS = 5000;
// well under the 10 s hook timeout, so a hook that gave up waiting still answers in time
const LOCK_WAIT_MS = 4000;

/** Runs `fn` while holding the per-repo lock (exclusive-create lock file, stale after 5 s). */
export function withLock(root, fn) {
  const lock = join(rigorPaths(root).dir, '.lock');
  mkdirSync(dirname(lock), { recursive: true });
  const started = Date.now();
  let held = false;
  while (!held) {
    try {
      closeSync(openSync(lock, 'wx'));
      held = true;
    } catch (err) {
      if (err.code !== 'EEXIST' && err.code !== 'EPERM' && err.code !== 'EBUSY') throw err;
      try {
        if (Date.now() - statSync(lock).mtimeMs > LOCK_STALE_MS) rmSync(lock, { force: true });
      } catch {
        // the lock vanished between the two calls; just try again
      }
      if (Date.now() - started > LOCK_WAIT_MS) break;
      sleepMs(15);
    }
  }
  try {
    return fn();
  } finally {
    if (held) rmSync(lock, { force: true });
  }
}

function writeLf(file, text) {
  atomicWrite(file, text);
}

export function readText(file) {
  try {
    return readFileSync(file, 'utf8');
  } catch {
    return null;
  }
}

export function defaultState(config) {
  return {
    planName: null,
    forcedPath: null,
    intentHash: null,
    replaceAt: null,
    intent: null,
    approval: null,
    reviewedSpecHash: null,
    reviews: [],
    snapshotHash: null,
    amendOpen: false,
    replaceOk: false,
    rounds: 0,
    roundCap: config.rounds.hard,
    stall: 0,
    lastOpenCount: null,
  };
}

export function readState(root, config) {
  const base = defaultState(config);
  const text = readText(rigorPaths(root).stateFile);
  if (text === null) return base;
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === 'object' ? { ...base, ...parsed } : base;
  } catch {
    return base;
  }
}

function findGitDir(root) {
  let dir = root;
  for (;;) {
    const g = join(dir, '.git');
    if (existsSync(g)) {
      if (statSync(g).isDirectory()) return g;
      const m = /gitdir:\s*(.+)/.exec(readText(g) ?? '');
      if (!m) return null;
      let gitDir = resolve(dir, m[1].trim());
      const common = readText(join(gitDir, 'commondir'));
      if (common) gitDir = resolve(gitDir, common.trim());
      return gitDir;
    }
    const up = dirname(dir);
    if (up === dir) return null;
    dir = up;
  }
}

/** Adds `.rigor/` to `.git/info/exclude` when a git dir exists and the line is missing. */
export function ensureGitExclude(root) {
  const gitDir = findGitDir(root);
  if (!gitDir) return;
  const file = join(gitDir, 'info', 'exclude');
  const current = readText(file) ?? '';
  const has = current.split(/\r?\n/).some((l) => ['.rigor/', '/.rigor/', '.rigor', '/.rigor'].includes(l.trim()));
  if (has) return;
  const prefix = current === '' || current.endsWith('\n') ? current : `${current}\n`;
  writeLf(file, `${prefix}.rigor/\n`);
}

export function writeState(root, state) {
  writeLf(rigorPaths(root).stateFile, `${JSON.stringify(state, null, 2)}\n`);
  ensureGitExclude(root);
}

export function readJsonl(file) {
  const text = readText(file);
  if (!text) return [];
  const out = [];
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    try {
      out.push(JSON.parse(line));
    } catch {
      // skip a damaged line
    }
  }
  return out;
}

/** Append one record; when `cap` is set the oldest records are dropped beyond it. */
export function appendJsonl(file, record, cap = Infinity) {
  if (cap === Infinity) {
    mkdirSync(dirname(file), { recursive: true });
    appendFileSync(file, `${JSON.stringify(record)}\n`);
    return;
  }
  const all = [...readJsonl(file), record].slice(-cap);
  writeLf(file, all.map((r) => JSON.stringify(r)).join('\n') + '\n');
}

export function writeSnapshot(root, text) {
  writeLf(rigorPaths(root).snapshot, text);
}

/**
 * Drops everything tied to the previous plan (answers, evidence, review snapshot); state.json is rewritten by
 * the caller. Command and fetch records stamped at or after `keepEvidenceSince` (an ISO time) are kept: they
 * were gathered for the plan that is being written now.
 */
export function resetPlanFiles(root, keepEvidenceSince = null) {
  const p = rigorPaths(root);
  for (const f of [p.answers, p.snapshot]) rmSync(f, { force: true });
  for (const f of [p.commands, p.fetches]) {
    const kept = keepEvidenceSince ? readJsonl(f).filter((r) => typeof r.at === 'string' && r.at >= keepEvidenceSince) : [];
    if (kept.length) writeLf(f, kept.map((r) => JSON.stringify(r)).join('\n') + '\n');
    else rmSync(f, { force: true });
  }
}

/** Appends the done.log line, then removes plan, map, evidence and state. */
export function closePlan(root, doneLine) {
  const p = rigorPaths(root);
  mkdirSync(p.dir, { recursive: true });
  appendFileSync(p.doneLog, `${doneLine}\n`);
  rmSync(p.plan, { force: true });
  rmSync(p.map, { force: true });
  rmSync(p.evidenceDir, { recursive: true, force: true });
  rmSync(p.stateDir, { recursive: true, force: true });
  ensureGitExclude(root);
}

export function fileLineCount(file) {
  const text = readText(file);
  if (text === null) return null;
  const n = text.split('\n').length;
  return text.endsWith('\n') ? n - 1 : n;
}
