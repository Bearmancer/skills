import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parsePlan } from '../scripts/lib/parse.mjs';
import { deriveStage, inScope, nextGaps } from '../scripts/lib/stage.mjs';
import {
  PLAN_FULL, PLAN_LIGHT, fakeCtx, mutate,
} from './helpers.mjs';

function stageOf(text, state = {}, ctxExtra = {}) {
  const ctx = fakeCtx({ state, ...ctxExtra });
  return deriveStage(text === null ? null : parsePlan(text), ctx.state, ctx);
}
const h = parsePlan(PLAN_FULL).plan.hashes;

test('stage none: there is no plan.md', () => {
  assert.equal(stageOf(null), 'none');
});

test('stage invalid: plan.md does not parse', () => {
  assert.equal(stageOf('no frontmatter'), 'invalid');
});

test('stage light / light-invalid follows the light check', () => {
  assert.equal(stageOf(PLAN_LIGHT), 'light');
  assert.equal(stageOf(mutate(PLAN_LIGHT, '- README.md', '- src/auth/login.ts')), 'light-invalid');
  assert.equal(stageOf(PLAN_LIGHT, {}, { forcedPath: 'full' }), 'light-invalid');
});

test('stage intent: no signature, or a hash that no longer matches', () => {
  assert.equal(stageOf(PLAN_FULL), 'intent');
  assert.equal(stageOf(PLAN_FULL, { intent: { hash: 'stale' } }), 'intent');
  const changed = mutate(PLAN_FULL, 'Other pages', 'Everything');
  assert.equal(stageOf(changed, { intent: { hash: h.intent } }), 'intent');
});

test('stage drafting: intent signed, approval missing or stale', () => {
  assert.equal(stageOf(PLAN_FULL, { intent: { hash: h.intent } }), 'drafting');
  assert.equal(stageOf(PLAN_FULL, { intent: { hash: h.intent }, approval: { hash: 'stale' } }), 'drafting');
});

test('stage build: approval hash matches, even after a checkbox is ticked', () => {
  const state = { intent: { hash: h.intent }, approval: { hash: h.plan } };
  assert.equal(stageOf(PLAN_FULL, state), 'build');
  assert.equal(stageOf(mutate(PLAN_FULL, '- [ ] T-1', '- [x] T-1'), state), 'build');
});

test('inScope: light files, build edits and glob creates; nothing else', () => {
  const light = parsePlan(PLAN_LIGHT).plan;
  assert.equal(inScope('light', light, 'README.md'), true);
  assert.equal(inScope('light', light, 'docs\\setup.md'), true);
  assert.equal(inScope('light', light, 'other.md'), false);
  const full = parsePlan(PLAN_FULL).plan;
  assert.equal(inScope('build', full, 'src/theme.ts'), true);
  assert.equal(inScope('build', full, 'src/theme/dark-mode.ts'), true);
  assert.equal(inScope('build', full, 'src/theme/deep/dark-mode.ts'), false);
  assert.equal(inScope('build', full, 'src/other.ts'), false);
  assert.equal(inScope('drafting', full, 'src/theme.ts'), false);
});

test('nextGaps reports the checkpoint the stage is heading for', () => {
  const full = parsePlan(PLAN_FULL);
  assert.match(nextGaps('intent', full, fakeCtx()).join('\n'), /Q-1 is marked answered/);
  assert.match(nextGaps('drafting', full, fakeCtx()).join('\n'), /intent has not been signed|No soundness review/);
  assert.deepEqual(nextGaps('build', full, fakeCtx()), ['T-1 is not done yet.']);
});
