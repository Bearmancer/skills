---
name: rigorous-planning
description: "Plan non-trivial work before code: a ledger-backed pipeline from fog or intake through research, clarification, design, TDD task slices and tickets to a fail-closed publish. Hard gates only; plans, never implementation."
---

# Rigorous planning

One linear pipeline absorbs the planning, clarification, design, issue-shaping, review-planning and agent-writing disciplines this project uses. This file is the always-loaded contract: principles, flags, the state machine, the CLI, the gates, and one-line pointers to the playbooks. Read a phase playbook when you enter that phase; read a method when its branch fires. Nothing here sends you to another skill: every method is in `methods/` and every phase is in `phases/`.

The model does the thinking; `scripts/planning.mjs` does the enforcing. A rule a regex, count, hash or exit code can check is a **gate** and lives in the script. A rule that cannot be scripted is a **method** in a playbook and never blocks or passes anything on its own.

## Principles

1. **Maximal by default, off by flag.** Every feature runs unless the user switches it off at init with its `--no-<feature>` flag. Flags are set once and are sticky.
2. **Hard evidence over prose.** A gate passes only on a persisted row, a resolvable file/hash, a captured exit status, or an owner token with the quoted words. A sentence claiming the work was done is not evidence. Counts are derived from rows, never supplied as totals.
3. **One phase, one artifact, one exit gate.** No phase is skipped by judgement; ambiguity diverts to the wayfinder branch before planning. The ledger records the phase, and the CLI refuses task/approval/publish commands before their gate.
4. **No ceremony by arithmetic.** Scope sets the path: size `S` takes the fast path automatically; anything that does not apply (one capability, one obvious way, complete intent) is skipped by a recorded predicate or flag, not by feeling.

Planning only. This skill never edits product code, never commits, never pushes, never opens a PR, never files or labels tracker issues. Whoever executes starts from the published `plan_sha256`.

## Flags (everything defaults ON)

| Flag at `init` | Turns off | Effect on gates |
| --- | --- | --- |
| `--lean` | plan-review, doubt, review section, handoff, ADR, constraints | Alias for those six `--no-*` flags; tdd, interview and branch keep their own. |
| `--no-tdd` | test-first tasks | Tasks carry no `test_seam`, `test_file`, `red` or `green`; G4 rejects any of them. |
| `--no-interview` | all questions to the user | Assumption mode (P3): intent filled from request + research, marked assumed, backed by facts/decisions. |
| `--no-branch` | auto `plan/<slug>` branch | `branch_reason` recorded as `no-branch`. |
| `--no-doubt` | adversarial cycle on irreversible decisions | G3 skips the doubt-record check. |
| `--no-plan-review` | fresh-context review of the draft design | G3 needs no review header or finding rows. |
| `--no-review-section` | `Verification and review plan` section | Section not rendered, not required. |
| `--no-handoff` | `Handoff` section | Section not rendered, not required. |
| `--no-adr` | ADR convention check | `--adr` decisions need no `adr-convention` fact or `adr_file`. |
| `--no-constraints` | quality-bar requirement | M/L plans need no `quality-bar` decision. |
| `--size S\|M\|L` | (default `M`) claimed scope class | `S` implies no branch and one closed research wave; G5 audits the claim against the task graph. |
| `--type <issue-type>` | (default `feature`) | Picks `docs/plans/<issue-type>/<slug>/` and the task-kind rules. |
| `--issue owner/repo#n` | (default none; repeatable or comma list) | Links source issues read-only; renders `## Issues`. |
| `--multi` | (default off) | Declares multi-capability scope; G3 requires the map. |
| `--deliberate` | (default off) | Forces the RALPLAN-DR record even at small size. |
| `--wayfinder` | (default off) | Creates `docs/maps/<slug>/` at phase W0: a decision map, never a task plan. |

`--tdd` is accepted as the explicit spelling of the default. Prose such as "don't ask me anything" does not waive a gate: only the flag does, and it swaps in a different evidence check, never deletes the gate.

## Fast path (early exit by predicate)

Use the fast path when the work is small: at most 2 tasks, at most 3 distinct files, one capability, no irreversible decision (the script derives this as size `S`). Init with `init --slug S --type T --size S --lean`, record `decision --label destination --decision "<one line>"`, then `gate --id G0`. Then:

- P1 records axes; P2 needs one closed wave of any count (G1).
- P3 is a single restate-and-yes when intent is already complete (CLEAR); no topology round, no challenge modes.
- No quality-bar decision, no capability map, no plan-review record, no doubt cycle (an irreversible decision makes the plan size M by definition).
- P5 writes 1-2 tasks; P6 publishes. The intent yes and `approve-design` still apply: put both to the user in one round and record each from its own answer.

G5 audits the claim: if the finished task graph derives a bigger size than claimed, publish fails with `understated size`. Claiming `S` is free when true and impossible when false.

Skip planning entirely, and say so, when the change is a single-line fix, a typo, or an unambiguous self-contained edit (a 2-line spec would still need acceptance criteria; a one-line change does not need a plan). An execution request with no concrete anchor (file path, issue or PR number, symbol, test command, acceptance criteria) is planned first; a `force:` or `!` prefix skips planning.

## The linear pipeline

```text
W0 wayfinder (fog only)
  -> P0 intake -> P1 axes -> P2 research -> P3 clarify
  -> P4 design/spec -> P5 tasks/plan -> P6 publish
```

| Phase | Entry (hard) | Work | Artifact | Exit gate | Failure route |
| --- | --- | --- | --- | --- | --- |
| W0 wayfinder | fog test fails: destination not one or two lines, or the first three decisions are not statable | name the destination, chart the map, resolve decision tickets one at a time | `docs/maps/<slug>/map.md` + wayfinder ledger | `G_WF`: destination, map headings, fog cleared, no open ticket, >=1 resolved ticket, owner `wayfinder-destination` approval with quote | stay in the map; `task` is refused |
| P0 intake | request received | destination, type, size, capability triage, branch | initialized ledger, branch `plan/<slug>` | `G0`: slug/type/refs/flags/branch + full validation + phase P0 | re-init or stop/ask |
| P1 axes | G0 PASS | split the topic into axes | `axes[]` | G1 entry: every axis has a lane | add an axis |
| P2 research | axes exist | parallel read-only lanes, facts + snapshots, waves | F rows, `sources/S<n>/`, `waves[]` | `G1`: per-axis active fact, saturation (S: 1 closed wave; M/L: 2x `new_facts=0`), locator resolves, external hash matches | another wave; re-snapshot |
| P3 clarify | G1 PASS | topology, frontier rounds, intent restate | answered Q rows, `intent.*`, confirmation | `G2`: ready frontier empty, every open Q in a round, no Q asked before a blocker, 6 intent fields, explicit yes (or `--no-interview` assumed set) | `early-exit` blocks publish; silence is not an answer |
| P4 design/spec | G2 PASS | approaches, seams, consensus, plan review, doubt | D/A rows, spec sections, finding rows | `G3`: approvals by user, capability map approved, review finding rows, doubt finding rows | one more cycle; escalate at 3 |
| P5 tasks/plan | G3 PASS | tracer-bullet tasks, test contracts, ticket drafts | T rows, rendered `plan.md`, `issues/` drafts | `G4`: task fields, seam contract, red/green contract, deps rendered, kinds, quality bar, ADR/glossary artifacts, headings, no placeholders | fix and re-render |
| P6 publish | G4 PASS | render, publish | `plan_sha256` | `G5`: G0-G4 + derived size <= claimed + hash match + phase P6 | exit 1; no partial credit |

Wayfinder rejoins at P1, never at P5: the map hands off to a spec, and collapsing it straight into tasks throws away linked decisions.

## CLI contract

All commands: `node scripts/planning.mjs <cmd> --slug <slug> [--type <issue-type>]`.

```text
init     --slug S [--type T] [--issue owner/repo#n,...] [--size S|M|L] [--multi] [--deliberate] [--wayfinder]
         [--no-tdd] [--no-interview] [--no-branch] [--no-plan-review] [--no-doubt]
         [--no-review-section] [--no-handoff] [--no-adr] [--no-constraints] [--lean]
axis     --label L
issue    --ref owner/repo#n [--title text]
capability --id kebab --responsibility text [--deps id1,id2]
fact     --label L --kind quote|measured|derived|assumed|converted --locator file:line|URL
         [--axis A1] [--source S1] [--external --sha <sha256>] [--quote text]
wave     (closes the open wave; new_facts is DERIVED from fact rows)
question --label L --question text [--blocked-by Q1,Q2] [--domain-term term]
         [--wayfinder [--kind research|prototype|grilling|task]]
round    --asks Q1,Q3 [--fact-lane]
answer   --id Q1 --answer text
decision --label L --decision text [--adr --adr-file docs/adr/NNNN-x.md] [--irreversible]
doubt    --id D1 --claim text --cycle n [--clean --scope file:line,...]
finding  --review plan-review:<cycle>|doubt:<decision>:<cycle> --class CLASS [--locator file:line] [--sha <sha256>] [--note text]
plan-review --cycle n [--clean --scope file:line,...]
size     --class S|M|L
task     --label L --files a,b --interfaces text --acceptance text --verify cmd [--deps T1,T2]
         [--kind feature|fix|refactor|docs|chore] [--issue owner/repo#n] [--est-lines n] [--closes gap-n]
         [--test-seam "<interface> | catches: ... | misses: ..." --test-file path --red "..." --green "..."]
batch    --file rows.json     (one process for many rows; row types mirror the commands)
intent   --outcome .. --user .. --why-now .. --success .. --constraint .. --out-of-scope .. [--confirm --by user] [--assume]
approve  --gate G_WF|G3|G4 --token wayfinder-destination|approve-design|approve-capability-map|doubt-escalated|plan-review-escalated
         --by user --quote "<the user's exact words>"
supersede --id X --reason text --replacement Y   |   retract --id X --reason text
fog      --add "item[,item]" | --clear
render | render-issues | frontier [--done T1,T2] | validate | gate --id G0..G5|G_WF | publish
wayfinder-handoff --type feature   (requires G_WF; seeds a planning ledger at P0)
```

One CLI call is one process start: batch a research wave or a review's findings into one `batch` call, and never write the same ledger in parallel. Commands find the ledger by slug; a wayfinder map is found under `docs/maps/`, a plan under `docs/plans/<type>/`; if a slug exists in both, pass `--type`.

## Gates

`gate --id Gx` prints PASS plus the new phase, or `ERROR` lines and exits 1. `publish` re-runs all gates, the evidence check and the size audit, then stamps `plan_sha256`. Freshness: after any ledger or `plan.md` edit, re-run the affected gate; a completion claim without a fresh run in this session is not a claim this skill makes.

| Gate | Phase | Checks |
| --- | --- | --- |
| `G0` | intake | an active `destination` decision in one or two lines; slug regex; issue type in the closed set; issue refs; skip flags in the closed set; size; branch recorded (`plan/<slug>`, or null with `--no-branch`/size S/non-git); full ledger validation (ids, unique labels, append-only events, acyclic provenance/task/capability graphs). |
| `G1` | research | every axis has an active fact; saturation (S: one closed wave; M/L: last two waves derived 0 new facts); no fact after the last wave; every external fact has a 64-hex `snapshot_sha256` and a matching `sources/S<n>/` file; every `file:line` locator resolves; a refactor plan needs a resolvable `survey-*` fact and a `top-recommendation` naming it. |
| `G2` | clarify | no active Q; every open Q is in a recorded round; no Q asked before a `blocked_by` is settled; six intent fields; interview mode needs an explicit user yes; `--no-interview` needs `assumed`, an assumed fact and a decision, and `confirmed` stays false; an active `early-exit` blocks publish; a recorded fog needs a `destination`. |
| `G3` | design | no open questions; `approve-design` by user with a non-empty quote; >1 capability needs `approve-capability-map` (same evidence); each plan-review header needs persisted finding rows (or `clean` + scope); each irreversible decision needs a doubt header + finding rows (or `clean` + scope); max 3 cycles unless escalated; size L, an irreversible decision, or `--deliberate` needs `principles`, `drivers`, `option-a`+`option-b` (or `options`+`invalidation`), `pre-mortem` (>=3), `expanded-test-plan` (unit/integration/e2e/observability). |
| `G4` | plan | tasks have files/interfaces/acceptance/verify; TDD on: seam is `"<interface> | catches: ... | misses: ... | class: in-process|local-substitutable|remote-owned|true-external"`, `test_file`, `red`, `green` (distinct; `fix` names a repro in red); TDD off: none of those fields; each task's `deps` are rendered in `plan.md`; kinds; no fake-done marker; `fix`/`refactor` rules; lockfile edits are chore + changelog; quality bar at M/L; `--adr` needs an `adr-convention` fact and an `adr_file`; a closed domain term has a `term-<term>` fact citing `GLOSSARY.md`; feature size L has `user-stories`; execution waves and dependency matrix match task `deps`; IS/GAP rows are closed by tasks when present; `plan.md` has every required heading in order and no TBD/placeholder. |
| `G5` | publish | G0-G4 together; evidence re-check; derived size not larger than claimed; a `plan.md` claim that tests ran needs a `test_run` row; `plan_sha256` equals the hash of `plan.md`. |
| `G_WF` | wayfinder | wayfinder ledger; destination decision in <=2 lines; fog cleared; no open `wayfinder` ticket; >=1 resolved ticket; an owner `wayfinder-destination` approval with a quote; `map.md` has Destination, Notes, Decisions so far, Not yet specified, Out of scope. |

A gate may never be: a score the agent assigns, a confidence percentage, a reviewer verdict on its own, a test "run earlier", or the user's silence. Approval tokens are recorded only from what the user said in chat, with the quote; the CLI cannot mint a yes.

## Ledger and evidence

State lives in `docs/plans/<issue-type>/<slug>/` (or `docs/maps/<slug>/` for W0) and nowhere else:

```text
ledger.json   append-only rows + events; the single source of truth (written only through the CLI)
plan.md       rendered from the ledger; never edited ahead of it
map.md        rendered wayfinder map (W0 only)
sources/      raw snapshots for external facts (S1, S2, ...), hashed
issues/       ticket drafts, one per task (render-issues); never sent to a tracker
```

Rows: facts `F<n>`, questions `Q<n>`, decisions `D<n>`, axes `A<n>`, tasks `T<n>`, findings `N<n>`, rounds `R<n>`, test runs `X<n>`. Each id is max+1; each label is unique forever; facts carry a `locator` (`file:line` or URL) and external facts a `snapshot_sha256`. Rows are never deleted or rewritten: a correction is a `supersede`/`retract` event with a reason. Todos in the harness are a view; the ledger is the record. Never overwrite an incomplete plan for different work: if the directory holds unfinished work for something else, stop and ask (finish it, discard it explicitly, or use a new slug).

## Playbooks

Read the file named by the branch you are in; the pointer says what it is and when to reach it.

| When | Read |
| --- | --- |
| The fog test fails, the destination is not statable, or the effort is too big for one session | `phases/W0-wayfinder.md` — the map and decision-ticket branch, exit `G_WF`, handoff. |
| Entering intake or choosing type/size/branch (P0-P1) | `phases/00-intake.md` — destination, fog test, outcome/issue/size, capability map, branch, ledger init. |
| Entering research (P2) | `phases/02-research.md` — axes and lanes, facts vs decisions, sources, repo-first lanes, ideal state, waves. |
| Entering clarification (P3) | `phases/03-clarify.md` — topology, question discipline, interviews, rounds, playback, delivery form, early exit, quality bar. |
| Entering design (P4) | `phases/04-design.md` — spec, seams, dependency categories, design-twice, consensus, plan review, doubt, ADR, approvals. |
| Entering tasks (P5) | `phases/05-tasks.md` — tracer bullets, TDD contract, kinds, incremental rules, parallelism, review plan, tickets, criteria, render. |
| Entering publish or auditing an existing plan (P6) | `phases/06-publish.md` — publish, feedback, audit plans, handoff. |
| A design tree has open decisions and intent is complete | `methods/grilling.md` — frontier rounds, recommended answers, facts vs decisions. |
| A term is fuzzy, overloaded, or conflicts with the glossary; an ADR is due | `methods/domain-modeling.md` — glossary/ADR formats, three-part test, multi-context maps. |
| External docs/APIs are in play, or sources conflict | `methods/research.md` — primary-source ladder, background lanes, snapshots, version detection, conflict records. |
| The interface, seam or module shape is contested | `methods/codebase-design.md` — deep-module vocabulary, dependency categories, design-twice. |
| Writing a test contract or executing red-green | `methods/tdd.md` — seams, good tests, anti-patterns, mocking, sizes. |
| The repo has no written quality bar | `methods/quality-bar.md` — floor, questions, thresholds, weakened-bar signals. |
| Writing ticket drafts or a tracker handoff | `methods/ticket-drafts.md` — body shape, blocking edges, triage vocabulary. |
| Writing a plan, handoff or agent brief | `methods/writing.md` — context pointers, two loads, information hierarchy, completion criteria. |
| Shaping the plan as an execution handoff (TL;DR, waves, matrix, IS/GAP, final wave) | `methods/ulw-plan.md` — the ULW plan shape and what is derived versus written. |
