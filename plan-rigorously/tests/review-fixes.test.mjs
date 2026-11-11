// Regression tests for the independent review (B1-B3, M1-M8, m1-m4).
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import {
  mkdirSync, utimesSync, writeFileSync,
} from 'node:fs';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { check2, check3, lightCheck } from '../scripts/lib/checks.mjs';
import { parsePlan, stripReview } from '../scripts/lib/parse.mjs';
import { findRoot, readJsonl } from '../scripts/lib/state.mjs';
import {
  Flow, PLAN_FULL, PLAN_LIGHT, call, fakeCtx, hashesOf, makeRepo, mutate, post, pre, promptEvent, q, repoAt,
} from './helpers.mjs';

const HOOK = fileURLToPath(new URL('../scripts/hook.mjs', import.meta.url));
const mk = (t, repo) => {
  t.after(repo.cleanup);
  return repo;
};
const plan = (text) => parsePlan(text).plan;
const writeEvent = (repo, rel, cwd = repo.root) => pre(cwd, 'Write', { file_path: repo.p(rel), content: rel.endsWith('plan.md') ? PLAN_FULL : 'x' });
const FILES = { 'src/theme.ts': 3, 'src/settings/page.tsx': 1 };
function ctxFor(text, extra = {}) {
  return fakeCtx({
    files: FILES,
    state: { intent: { hash: plan(text).hashes.intent } },
    commands: [{ command: 'npm test' }],
    fetches: [{ url: 'https://example.org/page' }],
    ...extra,
  });
}

// ---- B1 rival roots

test('B1: a nested .rigor can never become its own root', (t) => {
  const repo = mk(t, repoAt('intent'));
  for (const rel of ['src/.rigor/plan.md', 'src/.rigor/state/state.json', '.rigor/.rigor/plan.md', '.rigor/.rigor/state/state.json']) {
    assert.equal(call(writeEvent(repo, rel)).decision, 'deny', rel);
  }
  assert.match(call(writeEvent(repo, 'src/.rigor/plan.md')).reason, /second \.rigor folder below it is not allowed/);
  assert.equal(call(writeEvent(repo, '.rigor/plan.md')).decision, 'allow', 'the real plan is still writable');
  // an inner folder that already exists on disk does not take over either
  repo.write('.rigor/.rigor/x.txt', '');
  const fromInside = pre(`${repo.root}\\.rigor\\.rigor`, 'Write', { file_path: 'plan.md', content: 'x' });
  assert.equal(call({ ...fromInside, cwd: repo.p('.rigor/.rigor') }).decision, 'deny');
  assert.equal(findRoot(repo.p('.rigor/.rigor')), repo.root);
});

test('B1: the first plan must sit at the git root, and .rigor/state cannot be pre-created', (t) => {
  const git = mk(t, makeRepo({ git: true }));
  const sub = call(writeEvent(git, 'sub/.rigor/plan.md'));
  assert.equal(sub.decision, 'deny');
  assert.match(sub.reason, /must sit at the project root/);
  assert.equal(call(writeEvent(git, '.rigor/plan.md')).decision, 'allow');

  const plain = mk(t, makeRepo());
  assert.equal(call(writeEvent(plain, '.rigor/state/state.json')).decision, 'deny', 'no .rigor yet: only plan.md or map.md may start it');
  assert.equal(call(writeEvent(plain, '.rigor/done.log')).decision, 'deny');
  assert.equal(call(writeEvent(plain, 'sub/.rigor/plan.md')).decision, 'allow', 'no git repo: the folder that will contain .rigor is the root');
});

// ---- B2 globs

test('B2: light Files rejects * and ?, accepts [ ] { } as ordinary characters', () => {
  const star = plan(mutate(PLAN_LIGHT, '- README.md', '- src/*.ts'));
  assert.match(lightCheck(star, fakeCtx()).join('\n'), /src\/\*\.ts contains \* or \?/);
  assert.match(lightCheck(plan(mutate(PLAN_LIGHT, '- README.md', '- docs/a?.md')), fakeCtx()).join('\n'), /contains \* or \?/);
  assert.deepEqual(lightCheck(plan(mutate(PLAN_LIGHT, '- README.md', '- src/pages/[id].tsx')), fakeCtx()), []);
  assert.deepEqual(lightCheck(plan(mutate(PLAN_LIGHT, '- README.md', '- src/{a}.tsx')), fakeCtx()), []);
});

test('B2: a light plan with a wildcard is light-invalid; a bracketed file name is editable', (t) => {
  const repo = mk(t, makeRepo());
  repo.write('.rigor/plan.md', mutate(PLAN_LIGHT, '- README.md', '- src/*.ts'));
  assert.match(call(writeEvent(repo, 'src/theme.ts')).reason, /light-invalid/);
  const ok = mk(t, makeRepo());
  ok.write('src/pages/[id].tsx', 'x');
  ok.write('.rigor/plan.md', mutate(PLAN_LIGHT, '- README.md', '- src/pages/[id].tsx'));
  assert.equal(call(writeEvent(ok, 'src/pages/[id].tsx')).decision, 'allow');
  assert.equal(call(writeEvent(ok, 'src/pages/other.tsx')).decision, 'deny');
});

test('B2: Edits takes no wildcards but allows brackets; Creates wildcards only in the file name', () => {
  const edits = (value) => mutate(PLAN_FULL, 'Edits: src/theme.ts', `Edits: ${value}`);
  const files = { ...FILES, 'src/pages/[id].tsx': 1 };
  assert.deepEqual(check2(plan(edits('src/pages/[id].tsx')), ctxFor(PLAN_FULL, { files })), []);
  assert.match(check2(plan(edits('src/th?me.ts')), ctxFor(PLAN_FULL)).join('\n'), /contains glob characters/);
  const creates = (value) => mutate(PLAN_FULL, 'Creates: src/theme/dark-*.ts', `Creates: ${value}`);
  for (const bad of ['src/**/x.ts', 'src/*/x.ts', 'src/theme/**', 'src/a*/b.ts']) {
    assert.match(check2(plan(creates(bad)), ctxFor(PLAN_FULL)).join('\n'), /only in the file name/, bad);
  }
  for (const good of ['src/theme/dark-*.ts', 'src/theme/dark-?.ts', 'src/[new]/x.ts']) {
    assert.deepEqual(check2(plan(creates(good)), ctxFor(PLAN_FULL)), [], good);
  }
});

// ---- B3 hash and parser agree

const FENCE = '```';

test('B3: a code fence inside the frontmatter is a parse error', () => {
  const res = parsePlan(mutate(PLAN_FULL, 'path: full', `path: full\n${FENCE}`));
  assert.equal(res.ok, false);
  assert.match(res.errors.join('\n'), /frontmatter block must not contain code fences/);
});

test('B3: hidden-task scenarios either fail to parse or change the plan hash', () => {
  const base = hashesOf(PLAN_FULL).plan;
  const sneaky = '- [ ] T-9: sneaky\n  - Covers: AC-1\n  - Creates: z.ts\n  - Verify: `x`\n';
  // the reviewer's scenario: a fence line in the frontmatter shifts the fence state of the old stripReview
  const shifted = mutate(PLAN_FULL, 'path: full', `path: full\n${FENCE}`)
    .replace('## Review', `${FENCE}\n## Review\n${sneaky}${FENCE}\n## Review2`);
  assert.equal(parsePlan(shifted).ok, false);
  // a fenced heading is not a heading for the parser, the hash, or stripReview
  const fenced = mutate(PLAN_FULL, '## Review', `${FENCE}\n## Review\n${FENCE}\n${sneaky}\n## Review`);
  const res = parsePlan(fenced);
  assert.equal(res.plan.tasks.some((x) => x.id === 'T-9'), true, 'the task sits in the Tasks section for the parser');
  assert.notEqual(res.plan.hashes.plan, base, 'and therefore also in the hash');
  // an unclosed fence swallows later headings identically everywhere
  const unclosed = mutate(PLAN_FULL, '## Review', `${FENCE}\n${sneaky}## Review\n- No findings (round 9)\n`);
  const u = parsePlan(unclosed);
  assert.notEqual(u.plan.hashes.plan, base);
  assert.ok(stripReview(unclosed).includes('T-9'), 'stripReview agrees the text after the fence is not Review');
});

// ---- M1 hostile input

test('M1: very long lines and huge files are refused fast', () => {
  const start = Date.now();
  const hostile = [
    ` ${' '.repeat(100000)}x`,
    `- Q-1 [open] ${' '.repeat(100000)}x`,
    `## ${' '.repeat(100000)}x`,
    `- Outcome:${' '.repeat(100000)}x`,
    'a'.repeat(100000),
  ];
  for (const line of hostile) {
    const res = parsePlan(mutate(PLAN_FULL, '## Claims', `${line}\n## Claims`));
    assert.equal(res.ok, false);
    assert.match(res.errors.join('\n'), /longer than 2000 characters/);
  }
  assert.ok(Date.now() - start < 1000, `took ${Date.now() - start} ms`);
  const big = parsePlan(`${PLAN_FULL}\n${'filler line\n'.repeat(30000)}`);
  assert.equal(big.ok, false);
  assert.match(big.errors.join('\n'), /larger than 300 KB/);
  assert.equal(parsePlan(mutate(PLAN_FULL, '## Claims', `${'x'.repeat(2000)}\n## Claims`)).ok, true, 'exactly 2000 characters is fine');
});

test('M1: near-limit whitespace-heavy lines parse in linear time', () => {
  const lines = Array.from({ length: 120 }, (_, i) => `- B-${i + 2}:${' '.repeat(1900)}x${' '.repeat(50)}`).join('\n');
  const start = Date.now();
  const res = parsePlan(mutate(PLAN_FULL, '### Criteria', `${lines}\n### Criteria`));
  assert.ok(Date.now() - start < 1000, `took ${Date.now() - start} ms`);
  assert.equal(res.plan.behaviours.length, 121);
});

test('M1: the hook denies a plan write with an over-long line', (t) => {
  const repo = mk(t, repoAt('intent'));
  const r = call(pre(repo.root, 'Write', { file_path: repo.p('.rigor/plan.md'), content: mutate(PLAN_FULL, '## Claims', `${'y'.repeat(5000)}\n## Claims`) }));
  assert.equal(r.decision, 'deny');
  assert.match(r.reason, /longer than 2000 characters/);
});

// ---- M3 un-simulated plan edits

test('M3: a plan changed outside the allowed edits loses its approval', (t) => {
  const repo = mk(t, repoAt('build'));
  repo.write('.rigor/plan.md', mutate(PLAN_FULL, 'Theme tokens', 'Theme token'));
  const r = call(post(repo.root, 'Write', { file_path: repo.p('.rigor/plan.md') }, {}));
  assert.match(r.context, /approval was dropped/);
  assert.match(r.context, /`Amend plan` cannot restore it/);
  assert.match(r.context, /is in stage drafting/);
  assert.equal(repo.state().approval, null);
  assert.equal(call(writeEvent(repo, 'src/theme.ts')).decision, 'deny', 'source edits are blocked again');
});

test('M3: ticking a checkbox or editing the Review keeps the approval', (t) => {
  const repo = mk(t, repoAt('build'));
  repo.write('.rigor/plan.md', mutate(PLAN_FULL, '- [ ] T-1', '- [x] T-1'));
  const r = call(post(repo.root, 'Edit', { file_path: repo.p('.rigor/plan.md') }, {}));
  assert.match(r.context, /stage build/);
  assert.notEqual(repo.state().approval, null);
});

test('M3: a plan that no longer parses is reported in the note', (t) => {
  const repo = mk(t, repoAt('build'));
  repo.write('.rigor/plan.md', '# broken\n');
  const r = call(post(repo.root, 'Write', { file_path: repo.p('.rigor/plan.md') }, {}));
  assert.match(r.context, /cannot be read/);
  assert.match(r.context, /\n- .*frontmatter/);
  assert.notEqual(repo.state().approval, null, 'the approval is kept so that restoring the file restores the build');
});

// ---- M4 default risk patterns

test('M4: harness and repo-control files are risky by default', () => {
  for (const f of ['.claude/settings.json', '.git/hooks/pre-commit', '.rigor/plan.md', 'CLAUDE.md', 'agents.md', 'AGENTS.md',
    'pkg/.githooks/pre-push', '.husky/pre-commit']) {
    assert.match(lightCheck(plan(mutate(PLAN_LIGHT, '- README.md', `- ${f}`)), fakeCtx()).join('\n'), /risk pattern/, f);
  }
  for (const f of ['src/claude.ts', '.github/README.md', 'docs/agents-guide.md', '.gitignore']) {
    assert.deepEqual(lightCheck(plan(mutate(PLAN_LIGHT, '- README.md', `- ${f}`)), fakeCtx()), [], f);
  }
});

// ---- M5 concurrency

function runHook(event) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [HOOK], { stdio: ['pipe', 'pipe', 'pipe'] });
    let out = '';
    child.stdout.on('data', (d) => { out += d; });
    child.on('close', (code) => resolve({ code, out, at: Date.now() }));
    child.stdin.end(JSON.stringify(event));
  });
}

test('M5: parallel evidence recordings all survive', async (t) => {
  const repo = mk(t, repoAt('intent'));
  const runs = await Promise.all(Array.from({ length: 10 }, (_, i) => runHook(post(repo.root, 'Bash', { command: `cmd-${i}` }, { stdout: 'ok' }))));
  assert.ok(runs.every((r) => r.code === 0));
  const seen = readJsonl(repo.p('.rigor/evidence/commands.jsonl')).map((e) => e.command).sort();
  assert.deepEqual(seen, Array.from({ length: 10 }, (_, i) => `cmd-${i}`).sort());
});

test('M5: two interleaved review recordings both survive', async (t) => {
  const repo = mk(t, repoAt('drafting'));
  const spawnEvent = (lens) => pre(repo.root, 'Agent', { prompt: `x\nrigor-review: ${lens}`, model: 'sonnet', subagent_type: 'general-purpose' });
  await Promise.all([runHook(spawnEvent('soundness')), runHook(spawnEvent('completeness'))]);
  assert.deepEqual(repo.state().reviews.map((r) => r.lens).sort(), ['completeness', 'soundness']);
});

test('M5: a held lock makes a writer wait, a stale lock is broken, and state files are never left half-written', async (t) => {
  const repo = mk(t, repoAt('intent'));
  const lock = repo.p('.rigor/.lock');
  writeFileSync(lock, '');
  const started = Date.now();
  const running = runHook(post(repo.root, 'Bash', { command: 'waited' }, { stdout: 'ok' }));
  await new Promise((r) => setTimeout(r, 600));
  const released = Date.now();
  writeFileSync(lock, '');
  utimesSync(lock, new Date(0), new Date(0)); // keep it, but make it look old
  const done = await running;
  assert.ok(done.at >= released, 'the writer could not finish while the lock was held');
  assert.ok(done.at - started < 7000);
  assert.equal(readJsonl(repo.p('.rigor/evidence/commands.jsonl')).at(-1).command, 'waited');
  assert.equal(repo.has('.rigor/.lock'), false, 'the lock is released');

  writeFileSync(lock, '');
  utimesSync(lock, new Date(0), new Date(0));
  new Flow(repo).bash('after-stale');
  assert.equal(readJsonl(repo.p('.rigor/evidence/commands.jsonl')).at(-1).command, 'after-stale');
});

// ---- M6 round dead end

const LATE = /spec changed after the last review round and no round is left/;
const userFinding = (id = 'F-1') => `- ${id} [major] "x" -- spec changed late -> user: accepted`;

test('M6: once the round limit is used up, a later spec change needs a finding the user decided', () => {
  const p = plan(PLAN_FULL);
  const rev = (lens, round, extra = {}) => ({
    lens, round, specHash: 'older', hash: 'h', model: 'sonnet', ...extra,
  });
  const used = fakeCtx({ state: { reviews: [rev('soundness', 3), rev('completeness', 3)] } });
  assert.match(check3(p, used).join('\n'), LATE, 'F3: the round limit alone no longer waves a changed spec through');
  const decided = plan(mutate(PLAN_FULL, '- No findings (round 1)', userFinding()));
  assert.deepEqual(check3(decided, used), [], 'a finding the user decided covers the late change');
  const rejected = plan(mutate(PLAN_FULL, '- No findings (round 1)', '- F-1 [major] "x" -- y -> fixed'));
  assert.match(check3(rejected, used).join('\n'), LATE, 'only a user decision counts');
  const notUsed = fakeCtx({ state: { reviews: [rev('soundness', 2), rev('completeness', 2)] } });
  assert.match(check3(p, notUsed).join('\n'), /No soundness review/);
  const open = plan(mutate(PLAN_FULL, '- No findings (round 1)', '- F-1 [major] "x" -- y'));
  assert.match(check3(open, used).join('\n'), /F-1 has no disposition/, 'dispositions are still required');
});

test('M6: after the limit, Approve plan needs the late change decided by the user, and further spawns say what to do', (t) => {
  const repo = mk(t, repoAt('drafting'));
  const rev = (lens) => ({ lens, round: 3, specHash: 'older', hash: 'h', model: 'sonnet' });
  repo.seed({ ...repo.state(), reviews: [rev('soundness'), rev('completeness')], snapshotHash: 'older' });
  const ask = () => call(pre(repo.root, 'AskUserQuestion', { questions: [q('Approve plan', 'Approve?')] }));
  assert.equal(ask().decision, 'deny');
  assert.match(ask().reason, LATE);
  repo.write('.rigor/plan.md', mutate(PLAN_FULL, '- No findings (round 1)', userFinding()));
  assert.equal(ask().decision, 'allow');
  const spawnDenied = new Flow(repo).agent('x\nrigor-review: soundness');
  assert.equal(spawnDenied.decision, 'deny');
  assert.match(spawnDenied.reason, /^Round limit reached: the spec changed after review round 3/);
  assert.match(spawnDenied.reason, /`-> user: <decision>`, then ask `Approve plan`/);
});

// ---- M7 and M8 task ordering and preparatory tasks

const T2 = (extra) => `- [ ] T-2: Use it\n  - Covers: AC-1\n  - Edits: src/made.ts\n${extra}  - Verify: \`x\`\n\n`;
const withMade = (t2) => mutate(mutate(PLAN_FULL, 'Creates: src/theme/dark-*.ts', 'Creates: src/made.ts'), '## Review', `${t2}## Review`);

test('M7: an Edits path another task creates is valid when that task is a dependency', () => {
  assert.deepEqual(check2(plan(withMade(T2('  - Depends: T-1\n'))), ctxFor(PLAN_FULL)), []);
  assert.match(check2(plan(withMade(T2(''))), ctxFor(PLAN_FULL)).join('\n'), /T-2 edits src\/made\.ts, which does not exist/);
  const transitive = withMade(T2('  - Depends: T-3\n')).replace('## Review', '- [ ] T-3: Middle\n  - Covers: AC-1\n  - Creates: src/mid.ts\n  - Depends: T-1\n  - Verify: `x`\n\n## Review');
  assert.deepEqual(check2(plan(transitive), ctxFor(PLAN_FULL)), []);
  const pattern = mutate(PLAN_FULL, 'Creates: src/theme/dark-*.ts', 'Creates: src/gen/*.ts')
    .replace('## Review', '- [ ] T-2: Gen user\n  - Covers: AC-1\n  - Edits: src/gen/a.ts\n  - Depends: T-1\n  - Verify: `x`\n\n## Review');
  assert.deepEqual(check2(plan(pattern), ctxFor(PLAN_FULL)), []);
});

test('M8: a task may cover nothing, but every criterion still needs a task', () => {
  const prep = mutate(PLAN_FULL, '## Review', '- [ ] T-2: Prep refactor\n  - Covers: -\n  - Creates: src/prep.ts\n  - Verify: `x`\n\n## Review');
  assert.equal(parsePlan(prep).plan.tasks[1].covers.length, 0);
  assert.deepEqual(check2(plan(prep), ctxFor(PLAN_FULL)), []);
  const onlyPrep = mutate(prep, 'Covers: AC-1\n  - Edits: src/theme.ts', 'Covers: -\n  - Edits: src/theme.ts');
  assert.match(check2(plan(onlyPrep), ctxFor(PLAN_FULL)).join('\n'), /AC-1 is not covered by any task/);
});

// ---- m1 forced path

test('m1: a forced path never creates .rigor outside a git repo, and is dropped for a different plan', (t) => {
  const plain = mk(t, makeRepo());
  const r = call(promptEvent(plain.root, '/plan-rigorously quick fix links'));
  assert.equal(r.context, undefined);
  assert.equal(plain.has('.rigor'), false);

  const repo = mk(t, repoAt('drafting'));
  repo.seed({ ...repo.state(), forcedPath: 'quick' });
  const flow = new Flow(repo);
  flow.ask([q('Replace plan', 'Replace?')], ['Yes']);
  flow.write('.rigor/plan.md', mutate(PLAN_FULL, 'name: dark-mode-settings', 'name: other-job'));
  assert.equal(repo.state().forcedPath, null);

  const closing = mk(t, repoAt('build'));
  closing.seed({ ...closing.state(), forcedPath: 'full' });
  new Flow(closing).ask([q('Close plan', 'Close?')], ['Yes']);
  assert.equal(closing.has('.rigor/state'), false);
  assert.equal(closing.state().forcedPath, null);
});

// ---- m4 command proof

test('m4: a cmd proof must equal a recorded command or one of its segments, outside quotes', () => {
  const run = (command) => check2(plan(PLAN_FULL), ctxFor(PLAN_FULL, { commands: [{ command }] })).filter((g) => g.startsWith('C-2'));
  for (const ok of ['npm test', '  npm test  ', 'cd app && npm test', 'npm test; echo done', 'npm test | tail -3', 'echo a || npm test']) {
    assert.deepEqual(run(ok), [], ok);
  }
  for (const bad of ['echo "npm test"', "echo 'x && npm test'", 'npm test --silent', 'npm testing', 'xnpm test', 'echo "a; npm test"']) {
    assert.equal(run(bad).length, 1, bad);
  }
});
