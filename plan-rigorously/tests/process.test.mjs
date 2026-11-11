import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import {
  makeRepo, pre, repoAt, sessionEvent,
} from './helpers.mjs';

const HOOK = fileURLToPath(new URL('../scripts/hook.mjs', import.meta.url));
const run = (stdin) => spawnSync(process.execPath, [HOOK], { input: stdin, encoding: 'utf8' });
const write = (repo, rel) => JSON.stringify(pre(repo.root, 'Write', { file_path: repo.p(rel), content: 'x' }));

test('hook.mjs as a child process: an allowed call prints nothing and exits 0', (t) => {
  const repo = repoAt('build');
  t.after(repo.cleanup);
  const r = run(write(repo, 'src/theme.ts'));
  assert.equal(r.status, 0);
  assert.equal(r.stdout, '');
});

test('hook.mjs as a child process: a denied call prints the deny JSON', (t) => {
  const repo = repoAt('build');
  t.after(repo.cleanup);
  const r = run(write(repo, 'src/unplanned.ts'));
  assert.equal(r.status, 0);
  const out = JSON.parse(r.stdout);
  assert.equal(out.hookSpecificOutput.hookEventName, 'PreToolUse');
  assert.equal(out.hookSpecificOutput.permissionDecision, 'deny');
  assert.match(out.hookSpecificOutput.permissionDecisionReason, /`Amend plan`/);
});

test('hook.mjs as a child process: malformed or empty input fails open', () => {
  for (const input of ['this is not json', '{"hook_event_name":', '']) {
    const r = run(input);
    assert.equal(r.status, 0, JSON.stringify(input));
    assert.equal(r.stdout, '');
  }
});

test('hook.mjs as a child process: with no .rigor folder it prints nothing', (t) => {
  const repo = makeRepo();
  t.after(repo.cleanup);
  for (const stdin of [write(repo, 'src/theme.ts'), JSON.stringify(sessionEvent(repo.root))]) {
    const r = run(stdin);
    assert.equal(r.status, 0);
    assert.equal(r.stdout, '');
    assert.equal(r.stderr, '');
  }
  assert.equal(repo.has('.rigor'), false);
});

test('hook.mjs as a child process: SessionStart context uses the additionalContext shape', (t) => {
  const repo = repoAt('drafting');
  t.after(repo.cleanup);
  const out = JSON.parse(run(JSON.stringify(sessionEvent(repo.root))).stdout);
  assert.equal(out.hookSpecificOutput.hookEventName, 'SessionStart');
  assert.match(out.hookSpecificOutput.additionalContext, /stage drafting/);
});
