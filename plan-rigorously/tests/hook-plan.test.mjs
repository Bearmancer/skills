import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  Flow, PLAN_FULL, PLAN_LIGHT, call, hashesOf, makeRepo, mutate, pre, repoAt,
} from './helpers.mjs';

const WIN = process.platform === 'win32';
const mk = (t, repo) => {
  t.after(repo.cleanup);
  return repo;
};
const writeInput = (repo, rel, content) => pre(repo.root, 'Write', { file_path: repo.p(rel), content });

// ---- inert fast path

test('inert: with no .rigor folder nothing is blocked and nothing is created', (t) => {
  const repo = mk(t, makeRepo());
  assert.equal(call(writeInput(repo, 'src/new.ts', 'x')).decision, 'allow');
  assert.equal(call(pre(repo.root, 'Bash', { command: 'cat .rigor/state/state.json' })).decision, 'allow');
  assert.equal(call(pre(repo.root, 'AskUserQuestion', { questions: [] })).decision, 'allow');
  assert.equal(repo.has('.rigor'), false);
});

test('inert: a .rigor folder without plan.md blocks nothing outside it', (t) => {
  const repo = mk(t, makeRepo());
  repo.write('.rigor/done.log', '2026-01-01 old done\n');
  assert.equal(call(writeInput(repo, 'src/new.ts', 'x')).decision, 'allow');
});

// ---- writes inside .rigor

test('first plan write is allowed; the post hook creates state and the git exclude line', (t) => {
  const repo = mk(t, makeRepo({ git: true }));
  const flow = new Flow(repo);
  const { pre: before, post } = flow.write('.rigor/plan.md', PLAN_FULL);
  assert.equal(before.decision, 'allow');
  assert.match(post.context, /^plan-rigorously: plan "dark-mode-settings" is in stage intent\./);
  assert.equal(repo.state().planName, 'dark-mode-settings');
  assert.match(repo.read('.git/info/exclude'), /^\.rigor\/$/m);
  assert.doesNotMatch(repo.read('.rigor/state/state.json'), /\r/);
  flow.write('.rigor/plan.md', mutate(PLAN_FULL, 'Other pages', 'No pages'));
  assert.equal(repo.read('.git/info/exclude').match(/\.rigor\//g).length, 1, 'the exclude line is added once');
});

test('a plan that does not parse is blocked with the reasons', (t) => {
  const repo = mk(t, makeRepo());
  const bad = call(writeInput(repo, '.rigor/plan.md', '# no frontmatter\n'));
  assert.equal(bad.decision, 'deny');
  assert.match(bad.reason, /would not parse/);
  assert.match(bad.reason, /\n- .*frontmatter/);
  assert.match(bad.reason, /write the plan again\.$/);
  const dup = call(writeInput(repo, '.rigor/plan.md', mutate(PLAN_FULL, '### Criteria', '- B-1: dup\n### Criteria')));
  assert.equal(dup.decision, 'deny');
  assert.match(dup.reason, /Duplicate id B-1/);
  const status = call(writeInput(repo, '.rigor/plan.md', mutate(PLAN_FULL, '[answered]', '[done]')));
  assert.match(status.reason, /Unknown status/);
});

test('only plan.md and map.md may be written inside .rigor', (t) => {
  const repo = mk(t, repoAt('intent'));
  for (const rel of ['.rigor/plan-v2.md', '.rigor/state/state.json', '.rigor/state/answers.jsonl', '.rigor/evidence/commands.jsonl', '.rigor/done.log', '.rigor/notes.txt']) {
    const r = call(writeInput(repo, rel, 'x'));
    assert.equal(r.decision, 'deny', rel);
    assert.match(r.reason, /only \.rigor\/plan\.md and \.rigor\/map\.md/);
  }
  assert.equal(call(writeInput(repo, '.rigor/map.md', '# map')).decision, 'allow');
  assert.equal(call(pre(repo.root, 'NotebookEdit', { notebook_path: repo.p('.rigor/plan.md'), new_source: 'x' })).decision, 'deny');
});

test('a different plan name needs the Replace plan answer; the answer is spent by the next plan write', (t) => {
  const repo = mk(t, repoAt('drafting'));
  const flow = new Flow(repo);
  const other = mutate(PLAN_FULL, 'name: dark-mode-settings', 'name: other-job');
  const blocked = call(writeInput(repo, '.rigor/plan.md', other));
  assert.equal(blocked.decision, 'deny');
  assert.match(blocked.reason, /"dark-mode-settings"/);
  assert.match(blocked.reason, /header is `Replace plan`/);

  const answered = flow.ask([{ header: 'Replace plan', question: 'Replace the plan?', options: [], multiSelect: false }], ['Yes, replace it']);
  assert.equal(answered.pre.decision, 'allow');
  assert.equal(repo.state().replaceOk, true);

  const done = flow.write('.rigor/plan.md', other);
  assert.equal(done.pre.decision, 'allow');
  const state = repo.state();
  assert.equal(state.replaceOk, false);
  assert.equal(state.planName, 'other-job');
  assert.equal(state.intent, null, 'a replaced plan starts again');
  assert.equal(call(writeInput(repo, '.rigor/plan.md', mutate(other, 'name: other-job', 'name: third'))).decision, 'deny');
});

test('rewriting the same plan (same name) never needs Replace plan', (t) => {
  const repo = mk(t, repoAt('intent'));
  assert.equal(call(writeInput(repo, '.rigor/plan.md', mutate(PLAN_FULL, 'Other pages', 'No pages'))).decision, 'allow');
});

// ---- Edit simulation

test('Edit is simulated: a valid result is allowed, an invalid result is blocked', (t) => {
  const repo = mk(t, repoAt('intent'));
  const edit = (old_string, new_string, replace_all = false) =>
    call(pre(repo.root, 'Edit', { file_path: repo.p('.rigor/plan.md'), old_string, new_string, replace_all }));
  assert.equal(edit('Other pages', 'No pages').decision, 'allow');
  const bad = edit('[answered]', '[maybe]');
  assert.equal(bad.decision, 'deny');
  assert.match(bad.reason, /Unknown status "\[maybe\]"/);
});

test('Edit simulation: text that is absent or ambiguous is left to the tool itself', (t) => {
  const repo = mk(t, repoAt('intent'));
  const edit = (old_string, new_string, replace_all = false) =>
    call(pre(repo.root, 'Edit', { file_path: repo.p('.rigor/plan.md'), old_string, new_string, replace_all }));
  assert.equal(edit('this text is not in the file', '[maybe]').decision, 'allow');
  assert.equal(edit('B-1', 'B-X').decision, 'allow', 'two matches without replace_all: the tool fails by itself');
  const all = edit('B-1', 'B-X', true);
  assert.equal(all.decision, 'deny', 'replace_all is applied before parsing');
  assert.match(all.reason, /Malformed/);
  assert.equal(call(pre(repo.root, 'Edit', { file_path: repo.p('.rigor/missing.md'), old_string: 'a', new_string: 'b' })).decision, 'deny');
});

// ---- the build lock and amendments

test('build stage: checkbox ticks and Review edits pass, any other plan change needs Amend plan', (t) => {
  const repo = mk(t, repoAt('build'));
  const flow = new Flow(repo);
  assert.equal(flow.edit('.rigor/plan.md', '- [ ] T-1', '- [x] T-1').pre.decision, 'allow');
  assert.equal(flow.edit('.rigor/plan.md', '- No findings (round 1)', '- No findings (round 1)\n- F-1 [minor] "x" -- y -> fixed').pre.decision, 'allow');
  const blocked = flow.edit('.rigor/plan.md', 'Theme tokens', 'Theme token');
  assert.equal(blocked.pre.decision, 'deny');
  assert.match(blocked.pre.reason, /read-only during the build/);
  assert.match(blocked.pre.reason, /header is `Amend plan`/);
  assert.equal(call(writeInput(repo, '.rigor/plan.md', mutate(PLAN_FULL, 'Other pages', 'No pages'))).decision, 'deny');
  assert.equal(repo.state().approval.hash, hashesOf(PLAN_FULL).plan, 'ticking did not disturb the approval');
});

test('amendment: after Amend plan a spec-unchanged edit keeps the approval', (t) => {
  const repo = mk(t, repoAt('build'));
  const flow = new Flow(repo);
  flow.ask([{ header: 'Amend plan', question: 'Allow a plan change?', options: [], multiSelect: false }], ['Yes']);
  assert.equal(repo.state().amendOpen, true);
  const r = flow.edit('.rigor/plan.md', 'Theme tokens and toggle state', 'Theme tokens, toggle state and storage');
  assert.equal(r.pre.decision, 'allow');
  assert.match(r.post.context, /plan "dark-mode-settings" is in stage build/);
  assert.match(r.post.context, /approval carried over/);
  assert.equal(repo.state().approval.hash, hashesOf(repo.plan()).plan);
  assert.equal(repo.state().amendOpen, true, 'the window stays open until the first non-plan edit');
});

test('amendment: a spec change drops the approval and the plan goes back to drafting', (t) => {
  const repo = mk(t, repoAt('build'));
  const flow = new Flow(repo);
  flow.ask([{ header: 'Amend plan', question: 'Allow a plan change?', options: [], multiSelect: false }], ['Yes']);
  const r = flow.edit('.rigor/plan.md', 'within one frame', 'within two frames');
  assert.match(r.post.context, /is in stage drafting/);
  assert.match(r.post.context, /No soundness review was run on the current spec/);
  const s = repo.state();
  assert.equal(s.approval, null);
  assert.equal(s.amendOpen, false);
  assert.deepEqual(s.reviews, []);
});

test('amendment: an edit that breaks check 2 does not carry the approval over', (t) => {
  const repo = mk(t, repoAt('build'));
  const flow = new Flow(repo);
  flow.ask([{ header: 'Amend plan', question: 'Allow a plan change?', options: [], multiSelect: false }], ['Yes']);
  const r = flow.edit('.rigor/plan.md', 'Edits: src/theme.ts', 'Edits: src/missing.ts');
  assert.match(r.post.context, /is in stage drafting/);
  assert.match(r.post.context, /src\/missing\.ts, which does not exist/);
});

test('amendment: the first allowed non-plan edit closes the window', (t) => {
  const repo = mk(t, repoAt('build'));
  const flow = new Flow(repo);
  flow.ask([{ header: 'Amend plan', question: 'Allow a plan change?', options: [], multiSelect: false }], ['Yes']);
  flow.edit('.rigor/plan.md', 'Theme tokens', 'Theme token');
  assert.equal(repo.state().amendOpen, true);
  assert.equal(call(writeInput(repo, 'GLOSSARY.md', 'x')).decision, 'allow');
  assert.equal(repo.state().amendOpen, true, 'glossary edits do not count');
  assert.equal(call(writeInput(repo, 'src/theme.ts', 'x')).decision, 'allow');
  assert.equal(repo.state().amendOpen, false);
  assert.equal(call(writeInput(repo, '.rigor/plan.md', mutate(PLAN_FULL, 'Other pages', 'No pages'))).decision, 'deny');
});

test('amendment: a build-stage amendment may keep files that the build already created', (t) => {
  const repo = mk(t, repoAt('build'));
  const flow = new Flow(repo);
  repo.write('src/theme/dark-tokens.ts', 'x');
  repo.write('src/made.ts', 'x');
  flow.ask([{ header: 'Amend plan', question: 'Allow a plan change?', options: [], multiSelect: false }], ['Yes']);
  const r = flow.edit('.rigor/plan.md', 'Creates: src/theme/dark-*.ts', 'Creates: src/theme/dark-*.ts, src/made.ts');
  assert.match(r.post.context, /is in stage build/);
});

// ---- writes outside .rigor, per stage

test('planning stages block everything except plan, map, glossary and ADRs', (t) => {
  for (const stage of ['intent', 'drafting']) {
    const repo = mk(t, repoAt(stage));
    const r = call(writeInput(repo, 'src/theme.ts', 'x'));
    assert.equal(r.decision, 'deny', stage);
    assert.match(r.reason, new RegExp(`still in the ${stage} stage`));
    for (const rel of ['GLOSSARY.md', 'docs/adr/0001-dark-mode.md', 'glossary.md']) {
      assert.equal(call(writeInput(repo, rel, 'x')).decision, 'allow', `${stage} ${rel}`);
    }
    assert.equal(call(writeInput(repo, 'docs/other/0001.md', 'x')).decision, 'deny');
    assert.equal(call(writeInput(repo, 'sub/GLOSSARY.md', 'x')).decision, 'deny', 'only the root glossary');
  }
});

test('NotebookEdit follows the same scope rules', (t) => {
  const repo = mk(t, repoAt('intent'));
  assert.equal(call(pre(repo.root, 'NotebookEdit', { notebook_path: repo.p('analysis.ipynb'), new_source: 'x' })).decision, 'deny');
  const build = mk(t, repoAt('build'));
  build.write('analysis.ipynb', '{}');
  assert.equal(call(pre(build.root, 'NotebookEdit', { notebook_path: build.p('analysis.ipynb'), new_source: 'x' })).decision, 'deny');
});

test('light stage allows only the listed files and says how to escalate', (t) => {
  const repo = mk(t, makeRepo());
  repo.write('.rigor/plan.md', PLAN_LIGHT);
  repo.seed({ planName: 'fix-readme-links' });
  assert.equal(call(writeInput(repo, 'README.md', 'x')).decision, 'allow');
  assert.equal(call(writeInput(repo, 'docs/setup.md', 'x')).decision, 'allow');
  const r = call(writeInput(repo, 'src/theme.ts', 'x'));
  assert.equal(r.decision, 'deny');
  assert.match(r.reason, /not listed under `## Files`/);
  assert.match(r.reason, /Rewrite the plan as `path: full`, or ask the user\.$/);
  assert.equal(call(writeInput(repo, 'GLOSSARY.md', 'x')).decision, 'allow');
});

test('light-invalid blocks edits and tells the model to rewrite as full', (t) => {
  const repo = mk(t, makeRepo());
  repo.write('.rigor/plan.md', mutate(PLAN_LIGHT, '- README.md', '- src/auth/login.ts'));
  const r = call(writeInput(repo, 'README.md', 'x'));
  assert.equal(r.decision, 'deny');
  assert.match(r.reason, /light-invalid/);
  assert.match(r.reason, /Rewrite the plan as `path: full`\./);
});

test('build stage allows exact Edits, glob Creates and nothing else', (t) => {
  const repo = mk(t, repoAt('build'));
  assert.equal(call(writeInput(repo, 'src/theme.ts', 'x')).decision, 'allow');
  assert.equal(call(writeInput(repo, 'src/theme/dark-tokens.ts', 'x')).decision, 'allow');
  const r = call(writeInput(repo, 'src/other.ts', 'x'));
  assert.equal(r.decision, 'deny');
  assert.match(r.reason, /no task in the approved plan lists it/);
  assert.match(r.reason, /header is `Amend plan`\.$/);
  assert.equal(call(writeInput(repo, 'src/theme/sub/dark-tokens.ts', 'x')).decision, 'deny');
});

test('an unreadable plan.md blocks outside edits until it is repaired', (t) => {
  const repo = mk(t, makeRepo());
  repo.write('.rigor/plan.md', 'oops, not a plan\n');
  const r = call(writeInput(repo, 'src/theme.ts', 'x'));
  assert.equal(r.decision, 'deny');
  assert.match(r.reason, /cannot be read/);
  assert.equal(call(writeInput(repo, '.rigor/plan.md', PLAN_FULL)).decision, 'allow');
});

test('Windows paths: forward slashes, mixed case and spaces in the root all resolve', { skip: !WIN }, (t) => {
  const repo = mk(t, repoAt('build'));
  assert.match(repo.root, / /, 'the temp root contains a space');
  const upper = repo.p('src/theme.ts').toUpperCase();
  assert.equal(call(pre(repo.root, 'Write', { file_path: upper, content: 'x' })).decision, 'allow');
  const forward = repo.p('src/other.ts').replace(/\\/g, '/');
  assert.equal(call(pre(repo.root, 'Write', { file_path: forward, content: 'x' })).decision, 'deny');
  assert.equal(call(pre(repo.root, 'Write', { file_path: repo.p('.rigor/state/state.json').replace(/\\/g, '/'), content: 'x' })).decision, 'deny');
});

test('a relative file_path resolves against cwd', (t) => {
  const repo = mk(t, repoAt('build'));
  assert.equal(call(pre(repo.root, 'Write', { file_path: 'src/theme.ts', content: 'x' })).decision, 'allow');
  assert.equal(call(pre(repo.root, 'Write', { file_path: 'src/zzz.ts', content: 'x' })).decision, 'deny');
});

test('status context lists at most ten bullets', (t) => {
  const repo = mk(t, repoAt('intent'));
  const flow = new Flow(repo);
  const many = mutate(PLAN_FULL, '- Q-1 [answered] Which pages get dark mode? -> Settings only',
    Array.from({ length: 14 }, (_, i) => `- Q-${i + 1} [open] Question ${i + 1}?`).join('\n'));
  const { post } = flow.write('.rigor/plan.md', many);
  const lines = post.context.split('\n');
  assert.match(lines[0], /stage intent/);
  assert.equal(lines.filter((l) => l.startsWith('- ')).length, 11);
  assert.match(lines.at(-1), /^- \.\.\.and 4 more\.$/);
});
