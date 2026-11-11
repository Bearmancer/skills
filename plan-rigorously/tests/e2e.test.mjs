import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  Flow, PLAN_FULL, makeRepo, mutate, q,
} from './helpers.mjs';

const INTENT_ONLY = `---
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
- Q-1 [open] Which pages get dark mode?
`;

test('one plan walked from the first write to Close plan', (t) => {
  const repo = makeRepo({ git: true });
  t.after(repo.cleanup);
  const flow = new Flow(repo);
  const stageOf = () => /in stage ([a-z-]+)\./.exec(flow.write('.rigor/plan.md', repo.plan()).post.context)[1];

  // 1. the plan starts in the intent stage, and code is off limits
  assert.match(flow.write('.rigor/plan.md', INTENT_ONLY).post.context, /stage intent/);
  assert.equal(flow.write('src/theme.ts', 'x').pre.decision, 'deny');

  // 2. the intent cannot be signed while Q-1 is open
  const sign = [q('Sign intent', 'Is this the intent?')];
  assert.match(flow.ask(sign, ['Yes']).pre.reason, /Q-1 is still open/);

  // 3. the user answers Q-1, the plan records it, the intent is signed
  assert.equal(flow.ask([q('Scope', 'Q-1 Which pages get dark mode?', ['Settings only', 'All pages'])], ['Settings only']).pre.decision, 'allow');
  flow.edit('.rigor/plan.md', '[open] Which pages get dark mode?', '[answered] Which pages get dark mode? -> Settings only');
  assert.equal(flow.ask(sign, ['Yes, that is right']).pre.decision, 'allow');
  assert.equal(stageOf(), 'drafting');

  // 4. the model drafts the spec, claims and tasks (review still empty)
  const draft = mutate(PLAN_FULL, '- No findings (round 1)\n', '');
  assert.equal(flow.write('.rigor/plan.md', draft).pre.decision, 'allow');
  const approve = [q('Approve plan', 'Approve this plan?')];
  const early = flow.ask(approve, ['Yes']).pre;
  assert.equal(early.decision, 'deny');
  assert.match(early.reason, /C-2 cites a command \("npm test"\) that was not run/);
  assert.match(early.reason, /C-3 cites https:\/\/example\.org\/page, which was not fetched/);

  // 5. evidence arrives through the tools the hooks watch
  flow.bash('npm test');
  flow.fetch('https://example.org/page');
  assert.match(flow.ask(approve, ['Yes']).pre.reason, /No soundness review was run/);

  // 6. two reviewers on one frozen snapshot, then the Review section is filled in
  assert.equal(flow.agent('Review this.\nrigor-review: soundness').decision, 'allow');
  assert.equal(flow.agent('Review this.\nrigor-review: completeness').decision, 'allow');
  assert.match(flow.ask(approve, ['Yes']).pre.reason, /`## Review` is empty/);
  flow.edit('.rigor/plan.md', '## Review\n', '## Review\n- No findings (round 1)\n');

  // 7. approval moves the plan into build
  assert.equal(flow.ask(approve, ['Yes, approve']).pre.decision, 'allow');
  assert.equal(stageOf(), 'build');

  // 8. the build may touch declared files only, and the plan is read-only apart from ticks
  assert.equal(flow.write('src/theme.ts', 'export const theme = {};\nexport const dark = {};\nexport const x = 2;\n').pre.decision, 'allow');
  assert.equal(flow.write('src/theme/dark-tokens.ts', 'export {};\n').pre.decision, 'allow');
  assert.match(flow.write('src/unplanned.ts', 'x').pre.reason, /`Amend plan`/);
  assert.match(flow.edit('.rigor/plan.md', 'Theme tokens', 'Theme token').pre.reason, /read-only during the build/);
  assert.equal(flow.edit('.rigor/plan.md', '- [ ] T-1', '- [x] T-1').pre.decision, 'allow');
  assert.equal(stageOf(), 'build');

  // 9. closing the plan leaves one line behind
  assert.equal(flow.ask([q('Close plan', 'Close the plan?')], ['Yes']).pre.decision, 'allow');
  assert.match(repo.read('.rigor/done.log'), /^\d{4}-\d{2}-\d{2} dark-mode-settings done\n$/);
  for (const rel of ['.rigor/plan.md', '.rigor/state', '.rigor/evidence', '.rigor/map.md']) assert.equal(repo.has(rel), false, rel);
  assert.equal(flow.write('src/anything.ts', 'x').pre.decision, 'allow', 'with no plan the edit rules are off again');
  assert.match(repo.read('.git/info/exclude'), /^\.rigor\/$/m);
});
