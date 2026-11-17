import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import {
  existsSync, mkdtempSync, readdirSync, readFileSync, realpathSync, rmSync, writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { applyHooks, runInstall } from '../scripts/install.mjs';

const INSTALL = fileURLToPath(new URL('../scripts/install.mjs', import.meta.url));
const HOOK = resolve(fileURLToPath(new URL('../scripts/hook.mjs', import.meta.url)));
// the suite may run from a linked worktree, where install refuses the default hook path; pass it explicitly

function temp(t) {
  const dir = realpathSync.native(mkdtempSync(join(tmpdir(), 'rigor install ')));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  return { dir, settings: join(dir, 'settings.json') };
}
const read = (file) => JSON.parse(readFileSync(file, 'utf8'));

const EXISTING = {
  model: 'opus',
  permissions: { allow: ['Bash(git status)'] },
  hooks: {
    PreToolUse: [{ matcher: 'Bash', hooks: [{ type: 'command', command: 'echo before' }] }],
    Stop: [{ hooks: [{ type: 'command', command: 'echo stop' }] }],
  },
};

test('install into a missing file creates the four hook entries in exec form', (t) => {
  const { settings } = temp(t);
  const r = runInstall({ settingsPath: settings, hookPath: HOOK });
  assert.equal(r.changed, true);
  const hooks = read(settings).hooks;
  assert.deepEqual(Object.keys(hooks).sort(), ['PostToolUse', 'PreToolUse', 'SessionStart', 'UserPromptSubmit']);
  assert.deepEqual(hooks.PreToolUse, [{
    matcher: 'Write|Edit|NotebookEdit|Bash|PowerShell|Monitor|AskUserQuestion|Agent',
    hooks: [{ type: 'command', command: 'node', args: [HOOK], timeout: 10, onFailure: 'block' }],
  }]);
  assert.equal(hooks.PostToolUse[0].matcher, 'Write|Edit|Bash|PowerShell|Monitor|WebFetch|AskUserQuestion');
  assert.equal('matcher' in hooks.SessionStart[0], false);
  assert.equal('matcher' in hooks.UserPromptSubmit[0], false);
  assert.equal(readFileSync(settings, 'utf8').includes('\r'), false);
});

test('install keeps every existing key and hook, and writes a .bak of the original', (t) => {
  const { settings } = temp(t);
  writeFileSync(settings, JSON.stringify(EXISTING, null, 2));
  runInstall({ settingsPath: settings, hookPath: HOOK });
  const now = read(settings);
  assert.equal(now.model, 'opus');
  assert.deepEqual(now.permissions, EXISTING.permissions);
  assert.deepEqual(now.hooks.Stop, EXISTING.hooks.Stop);
  assert.deepEqual(now.hooks.PreToolUse[0], EXISTING.hooks.PreToolUse[0]);
  assert.equal(now.hooks.PreToolUse.length, 2);
  assert.deepEqual(read(`${settings}.bak`), EXISTING);
});

test('the first .bak is kept: later changes never overwrite it, and no temp files are left', (t) => {
  const { dir, settings } = temp(t);
  writeFileSync(settings, JSON.stringify(EXISTING, null, 2));
  runInstall({ settingsPath: settings, hookPath: HOOK });
  const afterInstall = read(settings);
  writeFileSync(settings, JSON.stringify({ ...afterInstall, extra: true }));
  runInstall({ settingsPath: settings, uninstall: true });
  assert.deepEqual(read(`${settings}.bak`), EXISTING);
  assert.deepEqual(readdirSync(dir).sort(), ['settings.json', 'settings.json.bak']);
});

test('running install again is a no-op that does not touch the file', (t) => {
  const { settings } = temp(t);
  writeFileSync(settings, JSON.stringify(EXISTING, null, 2));
  runInstall({ settingsPath: settings, hookPath: HOOK });
  const first = readFileSync(settings, 'utf8');
  writeFileSync(`${settings}.bak`, 'sentinel');
  const again = runInstall({ settingsPath: settings, hookPath: HOOK });
  assert.equal(again.changed, false);
  assert.equal(readFileSync(settings, 'utf8'), first);
  assert.equal(readFileSync(`${settings}.bak`, 'utf8'), 'sentinel', 'no new backup for a no-op');
});

test('an entry left at an old location is replaced, not duplicated', (t) => {
  const { settings } = temp(t);
  const old = 'C:\\old place\\plan-rigorously\\scripts\\hook.mjs';
  writeFileSync(settings, JSON.stringify(applyHooks({}, { hookPath: old })));
  runInstall({ settingsPath: settings, hookPath: HOOK });
  const hooks = read(settings).hooks;
  for (const groups of Object.values(hooks)) {
    assert.equal(groups.length, 1);
    assert.deepEqual(groups[0].hooks[0].args, [HOOK]);
  }
});

test('dry run reports the change and writes nothing', (t) => {
  const { settings } = temp(t);
  writeFileSync(settings, JSON.stringify(EXISTING));
  const r = runInstall({ settingsPath: settings, hookPath: HOOK, dryRun: true });
  assert.equal(r.changed, true);
  assert.deepEqual(read(settings), EXISTING);
  assert.equal(existsSync(`${settings}.bak`), false);
  const missing = join(temp(t).dir, 'none.json');
  runInstall({ settingsPath: missing, hookPath: HOOK, dryRun: true });
  assert.equal(existsSync(missing), false);
});

test('uninstall restores the original settings exactly', (t) => {
  const { settings } = temp(t);
  writeFileSync(settings, JSON.stringify(EXISTING, null, 2));
  runInstall({ settingsPath: settings, hookPath: HOOK });
  const r = runInstall({ settingsPath: settings, uninstall: true });
  assert.equal(r.changed, true);
  assert.deepEqual(read(settings), EXISTING);
  assert.equal(runInstall({ settingsPath: settings, uninstall: true }).changed, false);
});

test('uninstall after a fresh install leaves an empty object; unrelated empty hooks stay', (t) => {
  const a = temp(t);
  runInstall({ settingsPath: a.settings, hookPath: HOOK });
  runInstall({ settingsPath: a.settings, uninstall: true });
  assert.deepEqual(read(a.settings), {});
  const b = temp(t);
  writeFileSync(b.settings, JSON.stringify({ hooks: {} }));
  assert.equal(runInstall({ settingsPath: b.settings, uninstall: true }).changed, false);
  assert.deepEqual(read(b.settings), { hooks: {} });
});

test('uninstall keeps other hooks that share a matcher group with ours', (t) => {
  const { settings } = temp(t);
  const shared = {
    hooks: {
      SessionStart: [{ hooks: [{ type: 'command', command: 'echo hi' }, { type: 'command', command: 'node', args: [HOOK], timeout: 10 }] }],
    },
  };
  writeFileSync(settings, JSON.stringify(shared));
  runInstall({ settingsPath: settings, uninstall: true });
  assert.deepEqual(read(settings).hooks.SessionStart, [{ hooks: [{ type: 'command', command: 'echo hi' }] }]);
});

test('a settings file that is not valid JSON is refused and left alone', (t) => {
  const { settings } = temp(t);
  writeFileSync(settings, '{ nope');
  assert.throws(() => runInstall({ settingsPath: settings, hookPath: HOOK }), /not valid JSON/);
  assert.equal(readFileSync(settings, 'utf8'), '{ nope');
  writeFileSync(settings, JSON.stringify({ hooks: [] }));
  assert.throws(() => runInstall({ settingsPath: settings, hookPath: HOOK }), /not an object/);
});

test('install.mjs as a command: --settings with --dry-run, install, and uninstall', (t) => {
  const { settings } = temp(t);
  const run = (...args) => spawnSync(process.execPath, [INSTALL, '--settings', settings, '--hook-path', HOOK, ...args], { encoding: 'utf8' });
  const dry = run('--dry-run');
  assert.equal(dry.status, 0);
  assert.match(dry.stdout, /Would change/);
  assert.equal(existsSync(settings), false);
  assert.match(run().stdout, /hooks installed in/);
  assert.match(run().stdout, /No change: hooks already installed/);
  assert.match(run('--uninstall').stdout, /hooks removed from/);
  const bad = spawnSync(process.execPath, [INSTALL, '--bogus'], { encoding: 'utf8' });
  assert.equal(bad.status, 1);
  assert.match(bad.stderr, /Unknown option --bogus/);
});
