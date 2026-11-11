import assert from 'node:assert/strict';
import { test } from 'node:test';
import { check1, check2, check3, lightCheck } from '../scripts/lib/checks.mjs';
import { parsePlan } from '../scripts/lib/parse.mjs';
import {
  PLAN_FULL, PLAN_LIGHT, fakeCtx, mutate,
} from './helpers.mjs';

const plan = (text) => parsePlan(text).plan;
const FILES = { 'src/theme.ts': 3, 'src/settings/page.tsx': 1 };

/** A ctx under which PLAN_FULL passes check 2. */
function goodCtx(text = PLAN_FULL, extra = {}) {
  return fakeCtx({
    files: FILES,
    state: { intent: { hash: plan(text).hashes.intent } },
    commands: [{ command: 'npm test' }],
    fetches: [{ url: 'https://example.org/page' }],
    ...extra,
  });
}

// ---- light check

test('light check: a small ordinary plan passes', () => {
  assert.deepEqual(lightCheck(plan(PLAN_LIGHT), fakeCtx()), []);
});

test('light check: too many files fails unless the user forced quick', () => {
  const four = mutate(PLAN_LIGHT, '- docs/setup.md', '- docs/setup.md\n- a.md\n- b.md');
  assert.match(lightCheck(plan(four), fakeCtx()).join('\n'), /4 files are listed; the light path allows at most 3/);
  assert.deepEqual(lightCheck(plan(four), fakeCtx({ forcedPath: 'quick' })), []);
});

test('light check: every default risk pattern is caught, ordinary names are not', () => {
  const risky = ['src/auth/login.ts', 'config/.env', '.env.production', 'package-lock.json', 'db/migrations/001_init.sql',
    '.github/workflows/ci.yml', 'infra/main.tf', 'Dockerfile', 'src/payments/charge.ts', 'src/security/policy.ts', 'src/secrets.ts'];
  for (const f of risky) {
    const gaps = lightCheck(plan(mutate(PLAN_LIGHT, '- README.md', `- ${f}`)), fakeCtx());
    assert.match(gaps.join('\n'), /risk pattern/, f);
  }
  for (const f of ['src/author.ts', 'src/theme.ts', 'docs/environment.md']) {
    assert.deepEqual(lightCheck(plan(mutate(PLAN_LIGHT, '- README.md', `- ${f}`)), fakeCtx()), [], f);
  }
});

test('light check: absolute, drive and escaping paths fail; forced full fails; empty list fails', () => {
  for (const f of ['/etc/passwd', 'C:\\Windows\\x.txt', '../outside.md']) {
    assert.match(lightCheck(plan(mutate(PLAN_LIGHT, '- README.md', `- ${f}`)), fakeCtx()).join('\n'), /not a path relative to, and inside/, f);
  }
  assert.match(lightCheck(plan(PLAN_LIGHT), fakeCtx({ forcedPath: 'full' })).join('\n'), /full path/);
  assert.match(lightCheck(plan('---\nname: a-b\npath: light\n---\n## Files\n'), fakeCtx()).join('\n'), /lists no files/);
});

// ---- check 1

test('check 1 passes on a complete intent with a recorded answer', () => {
  const ctx = fakeCtx({ answers: [{ question: 'Q-1 Which pages get dark mode?' }] });
  assert.deepEqual(check1(plan(PLAN_FULL), ctx), []);
});

test('check 1: every intent bullet must be present and non-empty', () => {
  const ctx = fakeCtx({ answers: [{ question: 'Q-1 x' }] });
  for (const [from, label] of [['- Outcome: The settings page supports dark mode', 'Outcome'], ['- User: Any signed-in user', 'User'],
    ['- Why now: Support tickets about glare', 'Why now'], ['- Success: Toggling the switch changes the palette', 'Success'],
    ['- Constraint: No new dependencies', 'Constraint'], ['- Out of scope: Other pages', 'Out of scope']]) {
    assert.match(check1(plan(mutate(PLAN_FULL, from, '')), ctx).join('\n'), new RegExp(`"${label}" is missing`), `${label} removed`);
    const key = from.split(':')[0];
    for (const bad of ['...', 'TBD', '?', '-']) {
      assert.match(check1(plan(mutate(PLAN_FULL, from, `${key}: ${bad}`)), ctx).join('\n'), new RegExp(`"${label}" is missing`), `${label}=${bad}`);
    }
  }
});

test('check 1: open and waiting questions fail', () => {
  const ctx = fakeCtx({ answers: [] });
  const open = mutate(PLAN_FULL, '[answered] Which pages get dark mode? -> Settings only', '[open] Which pages?');
  assert.match(check1(plan(open), ctx).join('\n'), /Q-1 is still open/);
  const waiting = mutate(PLAN_FULL, '[answered] Which pages get dark mode? -> Settings only', '[waiting Q-9] Which pages?');
  assert.match(check1(plan(waiting), ctx).join('\n'), /Q-1 is still waiting on Q-9/);
});

test('check 1: an answered question needs a recorded answer naming it exactly', () => {
  assert.match(check1(plan(PLAN_FULL), fakeCtx()).join('\n'), /Q-1 is marked answered but the user's answer/);
  assert.match(check1(plan(PLAN_FULL), fakeCtx({ answers: [{ question: 'Q-12 something else' }] })).join('\n'), /Q-1 is marked answered/);
  assert.deepEqual(check1(plan(PLAN_FULL), fakeCtx({ answers: [{ question: 'Q-1: which pages?' }] })), []);
  assert.deepEqual(check1(plan(PLAN_FULL), fakeCtx({ answers: [{ question: '  Q-1 which pages?' }] })), []);
});

test('check 1: a recorded question counts only when it STARTS with the Q-n token', () => {
  for (const question of ['About Q-1: which pages?', 'See Q-1', 'Q-1x which', 'Q-12: other']) {
    assert.match(check1(plan(PLAN_FULL), fakeCtx({ answers: [{ question }] })).join('\n'), /Q-1 is marked answered/, question);
  }
});

// ---- check 2

test('check 2 passes on the full fixture', () => {
  assert.deepEqual(check2(plan(PLAN_FULL), goodCtx()), []);
});

const check2Cases = [
  ['intent not signed', (t) => t, { state: { intent: null } }, /intent has not been signed/],
  ['no behaviours', (t) => mutate(t, /- B-1:.*\n/.exec(t)[0], ''), {}, /no behaviours/],
  ['behaviour not covered', (t) => mutate(t, '### Criteria', '- B-2: Another behaviour.\n### Criteria'), {}, /B-2 is not covered by any criterion/],
  ['criterion covers a missing behaviour', (t) => mutate(t, 'Covers: B-1)', 'Covers: B-1, B-7)'), {}, /AC-1 covers B-7, which does not exist/],
  ['criterion not covered by a task', (t) => mutate(t, '## Claims', '- AC-3 (Covers: B-1): Another.\n\n## Claims'), {}, /AC-3 is not covered by any task/],
  ['task covers a missing criterion', (t) => mutate(t, 'Covers: AC-1', 'Covers: AC-1, AC-9'), {}, /T-1 covers AC-9, which does not exist/],
  ['task without Verify', (t) => mutate(t, '  - Verify: `npm test -- theme`\n', ''), {}, /T-1 has no Verify line/],
  ['task without files', (t) => mutate(mutate(t, '  - Edits: src/theme.ts\n', ''), '  - Creates: src/theme/dark-*.ts\n', ''), {}, /T-1 lists no files/],
  ['glob in Edits', (t) => mutate(t, 'Edits: src/theme.ts', 'Edits: src/*.ts'), {}, /contains glob characters/],
  ['Edits file missing', (t) => mutate(t, 'Edits: src/theme.ts', 'Edits: src/nope.ts'), {}, /edits src\/nope\.ts, which does not exist/],
  ['Creates file exists', (t) => mutate(t, 'Creates: src/theme/dark-*.ts', 'Creates: src/settings/page.tsx'), {}, /creates src\/settings\/page\.tsx, which already exists/],
  ['too many files', (t) => mutate(t, 'Creates: src/theme/dark-*.ts', 'Creates: a1.ts, a2.ts, a3.ts, a4.ts, a5.ts'), {}, /declares 6 files/],
  ['depends on missing task', (t) => mutate(t, 'Depends: -', 'Depends: T-9'), {}, /T-1 depends on T-9/],
  ['dependency cycle', (t) => mutate(mutate(t, 'Depends: -', 'Depends: T-2'), '## Review',
    '- [ ] T-2: Second\n  - Covers: AC-1\n  - Creates: z.ts\n  - Depends: T-1\n  - Verify: `x`\n\n## Review'), {}, /cycle: T-1 -> T-2 -> T-1/],
  ['file path in spec (exists)', (t) => mutate(t, 'dark palette.', 'dark palette from src/theme.ts.'), {}, /spec mentions the file path "src\/theme\.ts"/],
  ['file path in spec (shape)', (t) => mutate(t, 'dark palette.', 'dark palette from lib/new/thing.css.'), {}, /file path "lib\/new\/thing\.css"/],
  ['claim without proof', (t) => mutate(t, ' -- cmd: `npm test`', ''), {}, /C-2 has no valid proof/],
  ['code claim, file missing', (t) => mutate(t, 'code: src/theme.ts:2', 'code: src/gone.ts:2'), {}, /C-1 cites src\/gone\.ts, which does not exist/],
  ['code claim, line past end', (t) => mutate(t, 'code: src/theme.ts:2', 'code: src/theme.ts:99'), {}, /line 99 of src\/theme\.ts, which has 3 lines/],
  ['cmd claim not run', (t) => t, { commands: [] }, /C-2 cites a command \("npm test"\) that was not run/],
  ['doc quote too short', (t) => mutate(t, '"supported in all target browsers"', '"short"'), {}, /C-3 needs a quoted passage/],
  ['doc url not fetched', (t) => t, { fetches: [] }, /C-3 cites https:\/\/example\.org\/page, which was not fetched/],
];
for (const [name, edit, extra, expected] of check2Cases) {
  test(`check 2 blocks: ${name}`, () => {
    const text = edit(PLAN_FULL);
    const ctx = goodCtx(PLAN_FULL, extra);
    const gaps = check2(plan(text), ctx);
    assert.match(gaps.join('\n'), expected);
  });
}

test('check 2 allows: wide-refactor batches, glob Creates, cmd contained in a longer command, unobservable fetches', () => {
  const wide = mutate(PLAN_FULL, 'Creates: src/theme/dark-*.ts', 'Creates: a1.ts, a2.ts, a3.ts, a4.ts, a5.ts\n  - Batch: wide-refactor');
  assert.deepEqual(check2(plan(wide), goodCtx()), []);
  assert.deepEqual(check2(plan(PLAN_FULL), goodCtx(PLAN_FULL, { commands: [{ command: 'cd x && npm test' }] })), []);
  assert.deepEqual(check2(plan(PLAN_FULL), goodCtx(PLAN_FULL, { commands: [{ command: '  npm test | tail -5; echo done ' }] })), []);
  assert.deepEqual(check2(plan(PLAN_FULL), goodCtx(PLAN_FULL, { fetches: [], observeFetches: false })), []);
  assert.deepEqual(check2(plan(PLAN_FULL), goodCtx(PLAN_FULL, { fetches: [{ url: 'https://example.org/page/#frag' }] })), []);
});

test('check 2: relaxCreates (build amendments) tolerates files the build already made', () => {
  const text = mutate(PLAN_FULL, 'Creates: src/theme/dark-*.ts', 'Creates: src/settings/page.tsx');
  const ctx = goodCtx(PLAN_FULL);
  ctx.relaxCreates = true;
  assert.deepEqual(check2(plan(text), ctx), []);
});

// ---- check 3

const reviewed = (lens, specHash) => ({ lens, specHash, round: 1, hash: 'h', model: 'sonnet' });

test('check 3 passes with both lenses on the current spec and a resolved Review', () => {
  const p = plan(PLAN_FULL);
  const state = { reviews: [reviewed('soundness', p.hashes.spec), reviewed('completeness', p.hashes.spec)] };
  assert.deepEqual(check3(p, fakeCtx({ state })), []);
});

test('check 3 passes without reviews when the spec equals the already reviewed spec', () => {
  const p = plan(PLAN_FULL);
  assert.deepEqual(check3(p, fakeCtx({ state: { reviewedSpecHash: p.hashes.spec } })), []);
});

test('check 3 blocks: missing lens, stale review, empty Review, open and rejected-blocker findings', () => {
  const p = plan(PLAN_FULL);
  const one = { reviews: [reviewed('soundness', p.hashes.spec)] };
  assert.match(check3(p, fakeCtx({ state: one })).join('\n'), /No completeness review/);
  assert.doesNotMatch(check3(p, fakeCtx({ state: one })).join('\n'), /No soundness review/);
  const stale = { reviews: [reviewed('soundness', 'old'), reviewed('completeness', 'old')] };
  assert.match(check3(p, fakeCtx({ state: stale })).join('\n'), /No soundness review[\s\S]*No completeness review/);

  const ok = { reviewedSpecHash: p.hashes.spec };
  const empty = plan(mutate(PLAN_FULL, '- No findings (round 1)', ''));
  assert.match(check3(empty, fakeCtx({ state: ok })).join('\n'), /Review` is empty/);
  const open = plan(mutate(PLAN_FULL, '- No findings (round 1)', '- F-1 [major] "x" -- y'));
  assert.match(check3(open, fakeCtx({ state: ok })).join('\n'), /F-1 has no disposition/);
  const rejected = plan(mutate(PLAN_FULL, '- No findings (round 1)', '- F-1 [blocker] "x" -- y -> rejected: no'));
  assert.match(check3(rejected, fakeCtx({ state: ok })).join('\n'), /F-1 is a blocker that was rejected/);
  const userOk = plan(mutate(PLAN_FULL, '- No findings (round 1)', '- F-1 [blocker] "x" -- y -> user: keep it\n- F-2 [minor] "z" -- w -> rejected: fine'));
  assert.deepEqual(check3(userOk, fakeCtx({ state: ok })), []);
});
