// Shared fixtures for the plan-rigorously tests.
import {
  existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { handleHook } from '../scripts/lib/claude-code.mjs';
import { parsePlan } from '../scripts/lib/parse.mjs';
import { defaultState, loadConfig, readState, writeState } from '../scripts/lib/state.mjs';

export const NOW = '2026-11-10T12:00:00.000Z';
export const config = loadConfig();

export const PLAN_FULL = `---
name: dark-mode-settings
path: full
---
# Plan: Dark mode on the settings page

## Intent
- Outcome: The settings page supports dark mode
- User: Any signed-in user
- Why now: Support tickets about glare
- Success: Toggling the switch changes the palette
- Constraint: No new dependencies
- Out of scope: Other pages

## Questions
- Q-1 [answered] Which pages get dark mode? -> Settings only

## Spec
### Behaviours
- B-1: When the user turns on dark mode, the settings page shall render with the dark palette.
### Criteria
- AC-1 (Covers: B-1): Toggling the switch changes the page background within one frame.

## Claims
- C-1: the theme is read in exactly one place -- code: src/theme.ts:2
- C-2: the test suite passes today -- cmd: \`npm test\`
- C-3: prefers-color-scheme is supported -- doc: https://example.org/page "supported in all target browsers"

## Tasks
- [ ] T-1: Theme tokens and toggle state
  - Covers: AC-1
  - Edits: src/theme.ts
  - Creates: src/theme/dark-*.ts
  - Depends: -
  - Verify: \`npm test -- theme\`

## Review
- No findings (round 1)
`;

export const PLAN_LIGHT = `---
name: fix-readme-links
path: light
---
## Files
- README.md
- docs/setup.md
## Steps
1. Fix the links
`;

/** Replace `from` with `to`; fails loudly when `from` is absent so tests cannot rot silently. */
export function mutate(text, from, to) {
  if (!text.includes(from)) throw new Error(`fixture does not contain: ${from}`);
  return text.replace(from, () => to);
}

export const hashesOf = (text) => parsePlan(text).plan.hashes;

export function makeRepo({ git = false } = {}) {
  const root = realpathSync.native(mkdtempSync(join(tmpdir(), 'rigor test ')));
  const repo = {
    root,
    p: (rel) => join(root, ...rel.split('/')),
    write(rel, text) {
      mkdirSync(dirname(repo.p(rel)), { recursive: true });
      writeFileSync(repo.p(rel), text);
    },
    read: (rel) => readFileSync(repo.p(rel), 'utf8'),
    has: (rel) => existsSync(repo.p(rel)),
    cleanup: () => rmSync(root, { recursive: true, force: true }),
    state: () => readState(root, config),
    seed(patch) {
      writeState(root, { ...defaultState(config), ...patch });
    },
    plan: () => repo.read('.rigor/plan.md'),
  };
  repo.write('src/theme.ts', 'export const theme = {};\nexport const dark = {};\nexport const x = 1;\n');
  repo.write('src/settings/page.tsx', 'export default 1;\n');
  repo.write('README.md', '# readme\n');
  repo.write('docs/setup.md', '# setup\n');
  if (git) {
    // a bare `.git` folder is all the exclude logic needs; no git binary involved
    mkdirSync(join(root, '.git', 'info'), { recursive: true });
  }
  return repo;
}

// ---- hook stdin objects

const base = (cwd, name) => ({
  session_id: 's1', transcript_path: join(cwd, 't.jsonl'), cwd, permission_mode: 'default', hook_event_name: name,
});
export const pre = (cwd, tool_name, tool_input) => ({
  ...base(cwd, 'PreToolUse'), tool_name, tool_input, tool_use_id: 'tu1',
});
export const post = (cwd, tool_name, tool_input, tool_response = {}) => ({
  ...base(cwd, 'PostToolUse'), tool_name, tool_input, tool_response, tool_use_id: 'tu1',
});
export const promptEvent = (cwd, prompt) => ({ ...base(cwd, 'UserPromptSubmit'), prompt });
export const sessionEvent = (cwd) => ({ ...base(cwd, 'SessionStart'), source: 'startup' });
export const q = (header, question, labels = ['Yes', 'No']) => ({
  question, header, options: labels.map((label) => ({ label, description: 'd' })), multiSelect: false,
});

export const call = (event) => handleHook(event, { now: NOW });

/** Drives the adapter the way Claude Code does: pre-hook, the real tool effect, post-hook. */
export class Flow {
  constructor(repo) {
    this.repo = repo;
    this.cwd = repo.root;
  }

  write(rel, content) {
    const file_path = this.repo.p(rel);
    const before = call(pre(this.cwd, 'Write', { file_path, content }));
    if (before.decision === 'deny') return { pre: before };
    this.repo.write(rel, content);
    return { pre: before, post: call(post(this.cwd, 'Write', { file_path, content }, { type: 'update' })) };
  }

  edit(rel, old_string, new_string, replace_all = false) {
    const file_path = this.repo.p(rel);
    const input = { file_path, old_string, new_string, replace_all };
    const before = call(pre(this.cwd, 'Edit', input));
    if (before.decision === 'deny') return { pre: before };
    const text = this.repo.read(rel);
    this.repo.write(rel, replace_all ? text.split(old_string).join(new_string) : text.replace(old_string, () => new_string));
    return { pre: before, post: call(post(this.cwd, 'Edit', input, { type: 'update' })) };
  }

  /** answers: array of chosen labels, one per question. */
  ask(questions, answers) {
    const input = { questions };
    const before = call(pre(this.cwd, 'AskUserQuestion', input));
    if (before.decision === 'deny') return { pre: before };
    const response = { questions, answers: Object.fromEntries(questions.map((x, i) => [x.question, answers[i]])) };
    return { pre: before, post: call(post(this.cwd, 'AskUserQuestion', input, response)) };
  }

  bash(command, response = { stdout: 'ok', stderr: '', exit_code: 0 }) {
    const input = { command };
    const before = call(pre(this.cwd, 'Bash', input));
    if (before.decision === 'deny') return { pre: before };
    return { pre: before, post: call(post(this.cwd, 'Bash', input, response)) };
  }

  fetch(url) {
    return call(post(this.cwd, 'WebFetch', { url, prompt: 'x' }, { result: 'page' }));
  }

  agent(prompt, extra = {}) {
    return call(pre(this.cwd, 'Agent', { prompt, subagent_type: 'general-purpose', model: 'sonnet', description: 'review', ...extra }));
  }
}

/** Repo with the full plan on disk and state seeded to a given stage. */
export function repoAt(stage, { git = false } = {}) {
  const repo = makeRepo({ git });
  repo.write('.rigor/plan.md', PLAN_FULL);
  const h = hashesOf(PLAN_FULL);
  const at = NOW;
  const patch = { planName: 'dark-mode-settings' };
  if (stage === 'drafting' || stage === 'build') patch.intent = { hash: h.intent, at };
  if (stage === 'build') {
    patch.approval = { hash: h.plan, specHash: h.spec, at };
    patch.reviewedSpecHash = h.spec;
  }
  repo.seed(patch);
  if (stage === 'drafting' || stage === 'build') {
    // the evidence and answers that check 1 and check 2 look for
    recordAnswer(repo, { header: 'Scope', question: 'Q-1 Which pages get dark mode?', answer: 'Settings only' });
    recordCommand(repo, 'npm test');
    recordFetch(repo, 'https://example.org/page');
  }
  return repo;
}

export function recordAnswer(repo, record) {
  const file = repo.p('.rigor/state/answers.jsonl');
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify({ at: NOW, ...record })}\n`, { flag: 'a' });
}

export function recordCommand(repo, command) {
  const file = repo.p('.rigor/evidence/commands.jsonl');
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify({ command, at: NOW })}\n`, { flag: 'a' });
}

export function recordFetch(repo, url) {
  const file = repo.p('.rigor/evidence/fetches.jsonl');
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify({ url, at: NOW })}\n`, { flag: 'a' });
}

/** A pure ctx for checks.test.mjs: `files` maps repo-relative path -> line count. */
export function fakeCtx({ files = {}, state = {}, commands = [], fetches = [], answers = [], forcedPath = null, observeFetches = true } = {}) {
  const key = (p) => p.replace(/\\/g, '/');
  return {
    config,
    forcedPath,
    state: { ...defaultState(config), ...state },
    exists: (rel) => key(rel) in files,
    lineCount: (rel) => files[key(rel)] ?? null,
    commands,
    fetches,
    answers,
    observeFetches,
    relaxCreates: false,
  };
}
