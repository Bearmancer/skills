---
name: rigorous-planning
description: "Plan non-trivial work before code: a ledger-backed pipeline from unknowns or intake through evidence, clarification, design, test-first task slices and tickets to a fail-closed publish. Hard gates only; plans, never implementation."
---

# Rigorous planning

One linear pipeline absorbs this project's planning, design, issue-shaping, review-planning and agent-writing. This file is the always-loaded contract: principles, flags, state machine, CLI, gates and playbook pointers. Read a phase playbook on entry; a method when its branch fires. Methods live in `methods/`; phases in `phases/`.

The model thinks; `scripts/planning.mjs` enforces. A regex, count, hash or exit-code rule is a **gate** in the script. An unscriptable rule is a **method** and never blocks or passes on its own.

## Principles

1. Maximal by default, off by flag: features run unless `--no-<feature>` at init; flags sticky.
2. Hard evidence over prose: gates pass only on persisted rows, resolvable files/hashes, exit statuses, or owner tokens with quotes.
3. One phase, one artifact, one exit gate: no judgement skips; ambiguity goes to map first.
4. No ceremony by arithmetic: size `S` takes the fast path; skips need a recorded predicate or flag.
5. P3 uses the harness `question` tool only; never end a turn with an open Q.

Planning only: no product edits, commits, pushes, PRs, or tracker writes. Execution starts from `plan_sha256`.

## Flags (everything defaults ON)

| Flag | Turns off | Gate effect |
| --- | --- | --- |
| `--lean` | plan-review, doubt, review section, handoff, ADR, constraints | alias for those six `--no-*`; test-first/interview/branch keep own |
| `--no-test-first` | test-first tasks | no seam/test_file/red/green; G4 rejects them |
| `--no-interview` | user questions | assumption mode (P3): intent from request+evidence, assumed, backed by facts/decisions |
| `--no-branch` | auto branch | `branch_reason=no-branch` |
| `--no-doubt` | adversarial cycle on irreversible decisions | G3 skips doubt-record check |
| `--no-plan-review` | fresh-context review | G3 needs no review header/findings |
| `--no-review-section` | review-plan section | not rendered/required |
| `--no-handoff` | handoff section | not rendered/required |
| `--no-adr` | ADR convention check | `--adr` needs no convention fact/file |
| `--no-constraints` | quality-bar requirement | M/L need no quality-bar decision |
| `--no-task-approval` | task-graph approval | multi-cap or size L needs no `approve-task-graph` |
| `--size S|M|L` | scope class (default M) | S implies no branch + one closed wave; G5 audits claim |
| `--type <issue-type>` | issue type (default feature) | picks `docs/plans/<type>/<slug>/` and task-kind rules |
| `--issue owner/repo#n` | source issues (none; repeatable/comma) | read-only links; renders `## Issues` |
| `--multi` | multi-capability (off) | G3 requires capability map |
| `--deliberate` | deliberate record (off) | forces deliberation record even small |
| `--map` | map (off) | creates `docs/maps/<slug>/` at W0 |

`--test-first` spells the default. Only a flag swaps the evidence check; prose never waives.

## Fast path (early exit by predicate)

Small work: <=2 tasks, <=3 files, one capability, no irreversible decision (size `S`). Init `--size S --lean`, record `destination`, `gate G0`; P1 axes, P2 one closed wave, P3 restate-and-yes, P5 1-2 tasks, P6 publish. Intent yes and `approve-design` apply. G5 fails on understated size.

Skip planning for a single-line fix, typo, or unambiguous self-contained edit. Plan first without a concrete anchor (path, issue/PR, symbol, test, acceptance); `force:`/`!` skips.

## The linear pipeline

```text
W0 map (unknowns only) -> P0 intake -> P1 axes -> P2 evidence -> P3 clarify -> P4 design/spec -> P5 tasks/plan -> P6 publish
```

| Phase | Entry | Work | Artifact | Exit | Failure |
| --- | --- | --- | --- | --- | --- |
| W0 map | unknowns test fails | destination, map, tickets | `docs/maps/<slug>/map.md` + ledger | `G_MAP` | stay in map; task refused |
| P0 intake | request | destination, type, size, caps, branch | ledger, branch | `G0` | re-init/ask |
| P1 axes | G0 | split topic; one lane per axis | `axes[]` | `G_AX` | add axis |
| P2 evidence | `G_AX` | facts, snapshots, waves | F rows, sources, waves | `G1` | another wave |
| P3 clarify | G1 | topology, rounds, intent | Q rows, intent | `G2` | early-exit blocks |
| P4 design | G2 | approaches, seams, consensus, review, doubt | D/A rows, spec, findings | `G3` | cycle/escalate |
| P5 tasks | G3 | tracer bullets, contracts, tickets | T rows, plan.md, issues/ | `G4` | fix/re-render |
| P6 publish | G4 | render, publish | `plan_sha256` | `G5` | exit 1 |

Map rejoins at P1, never P5.

## CLI contract

All commands: `node scripts/planning.mjs <cmd> --slug <slug> [--type <issue-type>]`.

```text
init     --slug S [--type T] [--issue owner/repo#n,...] [--size S|M|L] [--multi] [--deliberate] [--map] [--no-test-first] [--no-interview] [--no-branch] [--no-plan-review] [--no-doubt] [--no-review-section] [--no-handoff] [--no-adr] [--no-constraints] [--lean]
axis --label L
issue --ref owner/repo#n [--title text]
capability --id kebab --responsibility text [--deps id1,id2]
fact --label L --kind quote|measured|derived|assumed|converted --locator file:line|URL [--axis A1] [--source S1] [--external --sha <sha256>] [--quote text]
wave
question --label L --question text [--recommend text] [--blocked-by Q1,Q2] [--domain-term term] [--map [--kind evidence|prototype|user|task]]
round --asks Q1,Q3 [--fact-lane]
ask --slug S [--id Q1]  (JSON for harness question tool; call exact JSON same turn)
answer --id Q1 --answer text
decision --label L --decision text [--adr --adr-file docs/adr/NNNN-x.md] [--irreversible]
doubt --id D1 --claim text --cycle n [--clean --scope file:line,...]
finding --review plan-review:<cycle>|doubt:<decision>:<cycle> --class CLASS [--locator file:line] [--sha <sha256>] [--note text]
plan-review --cycle n [--clean --scope file:line,...]
size --class S|M|L
task --label L --files a,b --interfaces text --acceptance text --verify cmd [--deps T1,T2] [--kind feature|fix|refactor|docs|chore] [--issue owner/repo#n] [--est-lines n] [--closes ideal-n|gap-n] [--test-seam "..." --test-file path --red "..." --green "..."]
batch --file rows.json
intent --outcome .. --user .. --why-now .. --success .. --constraint .. --out-of-scope .. [--confirm --by user] [--assume]
approve --gate G_MAP|G3|G4 --token map-destination|approve-design|approve-capability-map|doubt-escalated|plan-review-escalated --by user --quote "..."
supersede --id X --reason text --replacement Y | retract --id X --reason text
unknowns --add "item[,item]" | --clear
render | render-issues | frontier [--done T1,T2] | validate | next | gate --id G0..G5|G_AX|G_MAP | publish
map-handoff --type feature
```

One process per call; batch a wave or findings; never write one ledger in parallel. Ledger found by slug; map under `docs/maps/`, plan under `docs/plans/<type>/`; pass `--type` if both.

## Gates

`gate --id Gx` prints PASS + new phase, or `ERROR` lines and exits 1. `publish` reruns all gates/evidence/size then stamps `plan_sha256`. Re-run affected gate after any ledger/plan edit.

| Gate | Phase | Checks |
| --- | --- | --- |
| `G0` | intake | destination 1-2 lines; slug/type/refs/flags/size/branch; full ledger validation |
| `G_AX` | axes | at least one axis; unique ids and non-empty labels; every active fact names an existing axis; phase P1 |
| `G1` | evidence | per-axis fact; saturation; no late fact; external hash+file; locators resolve; refactor survey/top-rec |
| `G2` | clarify | no active Q; every Q in a round; answers recorded; no prose questions; six intent fields; yes/assumed; early-exit/unknowns |
| `G3` | design | approve-design quote; map approval if >1; review/doubt findings; cycle cap; deliberate record |
| `G4` | plan | task fields; test-first seam or none; deps rendered; kinds; no fake-done; lockfile chore; quality bar M/L; adr; domain term; user-stories L; task-graph approval for multi-cap/L unless skipped; waves/matrix; ideal/gap; headings |
| `G5` | publish | G0-G4 + `G_AX`; evidence; size; test_run if claimed; hash |
| `G_MAP` | map | ledger; destination <=2 lines; unknowns cleared; no open ticket; >=1 resolved; approval; map headings |

A gate is never a score, confidence %, self verdict, prior test run, or silence. Approval tokens come only from user chat with quote.

## Ledger and evidence

State lives in `docs/plans/<issue-type>/<slug>/` (or `docs/maps/<slug>/` for W0):

```text
ledger.json append-only rows+events (CLI only)
plan.md rendered; never hand-edited first
map.md map (W0 only)
sources/ hashed snapshots for external facts
issues/ ticket drafts, never sent
```

Rows: F/Q/D/A/T/N/R/X<n>. Ids max+1; labels unique forever; facts have locator; external facts have snapshot hash. No deletes/rewrites; corrections are supersede/retract with reason. Ledger is record; harness todos are a view. Never overwrite unfinished work for other scope.

## Playbooks

Read the file named by the branch; pointer says what and when.

| When | Read |
| --- | --- |
| unknowns / not statable / too big | `phases/W0-map.md` |
| intake / type / size / branch | `phases/00-intake.md` |
| axes / lanes | `phases/01-axes.md` |
| evidence | `phases/02-evidence.md` |
| clarify | `phases/03-clarify.md` |
| design | `phases/04-design.md` |
| tasks | `phases/05-tasks.md` |
| publish / audit | `phases/06-publish.md` |
| open design decisions | `methods/frontier.md` |
| fuzzy term / ADR | `methods/glossary.md` |
| external docs / conflicts | `methods/evidence.md` |
| interface / seam contested | `methods/seams.md` |
| test contract / red-green | `methods/test-first.md` |
| no quality bar | `methods/quality-bar.md` |
| ticket drafts / handoff | `methods/issue-drafts.md` |
| plan-writing | `methods/plan-writing.md` |
| execution handoff shape | `methods/handoff-shape.md` |