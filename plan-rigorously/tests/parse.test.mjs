import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parsePlan, stripReview } from '../scripts/lib/parse.mjs';
import { PLAN_FULL, PLAN_LIGHT, mutate } from './helpers.mjs';

test('a valid full plan parses into the model', () => {
  const { ok, errors, plan } = parsePlan(PLAN_FULL);
  assert.deepEqual(errors, []);
  assert.equal(ok, true);
  assert.equal(plan.name, 'dark-mode-settings');
  assert.equal(plan.path, 'full');
  assert.equal(plan.intent.outcome, 'The settings page supports dark mode');
  assert.equal(plan.intent['out of scope'], 'Other pages');
  assert.deepEqual(plan.questions.map((x) => [x.id, x.status]), [['Q-1', 'answered']]);
  assert.deepEqual(plan.behaviours.map((b) => b.id), ['B-1']);
  assert.deepEqual(plan.criteria[0].covers, ['B-1']);
  assert.deepEqual(plan.claims.map((c) => c.proof.kind), ['code', 'cmd', 'doc']);
  assert.deepEqual(plan.claims[0].proof, { kind: 'code', path: 'src/theme.ts', line: 2 });
  assert.equal(plan.claims[1].proof.command, 'npm test');
  assert.equal(plan.claims[2].proof.url, 'https://example.org/page');
  const t = plan.tasks[0];
  assert.deepEqual([t.id, t.done, t.covers, t.edits, t.creates, t.depends], ['T-1', false, ['AC-1'], ['src/theme.ts'], ['src/theme/dark-*.ts'], []]);
  assert.equal(t.verify, 'npm test -- theme');
  assert.equal(plan.review.noFindings, true);
});

test('a valid light plan parses', () => {
  const { ok, plan } = parsePlan(PLAN_LIGHT);
  assert.equal(ok, true);
  assert.equal(plan.path, 'light');
  assert.deepEqual(plan.files, ['README.md', 'docs/setup.md']);
});

test('duplicate ids are rejected, per kind', () => {
  const dup = mutate(PLAN_FULL, '### Criteria', '- B-1: Another behaviour.\n### Criteria');
  const res = parsePlan(dup);
  assert.equal(res.ok, false);
  assert.match(res.errors.join('\n'), /Duplicate id B-1/);
  const dupTask = mutate(PLAN_FULL, '## Review', '- [ ] T-1: again\n\n## Review');
  assert.match(parsePlan(dupTask).errors.join('\n'), /Duplicate id T-1/);
});

test('an unknown question status or finding severity is rejected', () => {
  const badQ = mutate(PLAN_FULL, '[answered]', '[maybe]');
  assert.match(parsePlan(badQ).errors.join('\n'), /Unknown status "\[maybe\]" on Q-1/);
  const badF = mutate(PLAN_FULL, '- No findings (round 1)', '- F-1 [huge] "x" -- y -> fixed');
  assert.match(parsePlan(badF).errors.join('\n'), /Unknown severity "\[huge\]"/);
});

test('missing, unclosed or invalid frontmatter is rejected', () => {
  assert.match(parsePlan('# no frontmatter\n').errors.join('\n'), /frontmatter/);
  assert.match(parsePlan('---\nname: a-b\npath: full\n# oops\n').errors.join('\n'), /not closed/);
  assert.match(parsePlan(mutate(PLAN_FULL, 'name: dark-mode-settings', 'name: Dark Mode')).errors.join('\n'), /kebab-case/);
  assert.match(parsePlan(mutate(PLAN_FULL, 'path: full', 'path: medium')).errors.join('\n'), /`path` must be/);
});

test('waiting questions, dispositions and malformed ids are understood', () => {
  const text = mutate(PLAN_FULL, '- Q-1 [answered] Which pages get dark mode? -> Settings only',
    '- Q-1 [open] First?\n- Q-2 [waiting Q-1] Second?');
  const res = parsePlan(mutate(text, '- No findings (round 1)',
    '- F-1 [major] "a -> b" -- bad -> fixed\n- F-2 [minor] "x" -- y -> rejected: not needed\n- F-3 [blocker] "z" -- w -> user: keep it\n- F-4 [minor] "q" -- open one'));
  assert.equal(res.ok, true);
  assert.deepEqual(res.plan.questions.map((x) => x.status), ['open', 'waiting']);
  assert.equal(res.plan.questions[1].waitsOn, 'Q-1');
  const kinds = res.plan.review.findings.map((f) => f.disposition?.kind ?? null);
  assert.deepEqual(kinds, ['fixed', 'rejected', 'user', null]);
  assert.match(parsePlan(mutate(PLAN_FULL, '- B-1:', '- B-1 oops')).errors.join('\n'), /Malformed behaviour/);
});

test('hashes: checkboxes and the Review section do not move the plan hash, the spec does', () => {
  const base = parsePlan(PLAN_FULL).plan.hashes;
  const ticked = parsePlan(mutate(PLAN_FULL, '- [ ] T-1', '- [x] T-1')).plan.hashes;
  assert.equal(ticked.plan, base.plan);
  const reviewed = parsePlan(mutate(PLAN_FULL, '- No findings (round 1)', '- F-1 [minor] "x" -- y -> fixed')).plan.hashes;
  assert.equal(reviewed.plan, base.plan);
  const spec = parsePlan(mutate(PLAN_FULL, 'within one frame', 'within two frames')).plan.hashes;
  assert.notEqual(spec.spec, base.spec);
  assert.notEqual(spec.plan, base.plan);
  assert.equal(spec.intent, base.intent);
  const task = parsePlan(mutate(PLAN_FULL, 'Theme tokens', 'Theme token')).plan.hashes;
  assert.equal(task.spec, base.spec);
  assert.notEqual(task.plan, base.plan);
  const intent = parsePlan(mutate(PLAN_FULL, 'Other pages', 'No pages')).plan.hashes;
  assert.notEqual(intent.intent, base.intent);
});

test('CRLF and trailing whitespace do not change hashes', () => {
  const crlf = PLAN_FULL.replace(/\n/g, '\r\n');
  assert.deepEqual(parsePlan(crlf).plan.hashes, parsePlan(PLAN_FULL).plan.hashes);
  assert.equal(parsePlan(mutate(PLAN_FULL, 'Other pages', 'Other pages   ')).plan.hashes.intent, parsePlan(PLAN_FULL).plan.hashes.intent);
});

test('a skeleton plan (placeholders, empty or missing sections) parses; emptiness is left to the checks', () => {
  const skeleton = `---
name: dark-mode-settings
path: full
---
# Plan: x

## Intent
- Outcome: ...
- User: ...
- Why now: ...
- Success: ...
- Constraint: ...
- Out of scope: ...

## Questions

## Spec
### Behaviours
### Criteria

## Claims

## Tasks

## Review
`;
  const res = parsePlan(skeleton);
  assert.deepEqual(res.errors, []);
  assert.equal(res.plan.tasks.length, 0);
  assert.equal(parsePlan('---\nname: a-b\npath: full\n---\n').ok, true, 'missing sections are fine too');
});

test('stripReview removes only the Review section', () => {
  const s = stripReview(PLAN_FULL);
  assert.ok(!s.includes('## Review'));
  assert.ok(s.includes('## Tasks'));
  const extra = `${PLAN_FULL}\n## Decisions\n- keep\n`;
  assert.ok(stripReview(extra).includes('## Decisions'));
});
