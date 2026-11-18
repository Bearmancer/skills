# Ledger — Dev\Skills

Assimilated 2026-11-17 from the frozen archive `C:\Users\Lance\.claude\ledger\epics\` (settled decisions and durable facts). Open questions recovered from the Linear export 2026-11-18 and appended below in full detail; the `.claude\ledger` archive has since been deleted.

## plan-rigorously skill: review, merge, install (PLAN)

Source: `C:\Users\Lance\.claude\ledger\epics\plan-rigorously-skill`

Settled design decisions (user, 2026-11-10, handoff-super-skill.md §2 and §4a):

- Local only: no GitHub or tracker mirror at all in the first version — user's final-word override.
- One fresh skill `plan-rigorously` replaces every planning/grilling/spec/decision-map skill; first stage of a plan → execute → review pipeline; only planning stage + shared engine built now.
- State lives in `.rigor/` in the working repo, plan at `.rigor/plan.md`, exactly one plan ever — replaces the earlier per-job `.plan/` folder design.
- §4a.1 Layout: `plan.md` (Intent/Spec/Tasks/Review in ONE file), `map.md` (big foggy jobs only), `evidence/`, `state/` (engine only), `done.log`.
- §4a.2 `.rigor/` entirely git-ignored — via `.git/info/exclude`, never edits a tracked `.gitignore`.
- §4a.3 Clarity score DROPPED; clarity enforced by six intent lines filled, zero open questions, every asked question has a recorded user answer, explicit yes on restated intent.
- §4a.3 No "advance" command: hooks validate plan files on write, stage derived from disk.
- §4a.3 Claude Code adapter first; opencode adapter later (event names unverified).
- §4a.4 Decision-map assumptions confirmed: many decisions per session; finished map becomes the signed intent; map is just a file.
- §4a.5 Light path: exactly 1 file touched writes no plan; 2+ files write a short `plan.md` (Files + Steps) and the single-plan rule applies.
- §4a.6 Old failed `plan-rigorously/` deleted from `~/dev/skills` (checked 2026-11-10); fresh start, mine for parts at most.
- Two paths light/full; `quick`/`full` as first word forces a path; light = declared file scope checked against facts, hook blocks out-of-scope edits and escalates to full.
- Stage-one interview runs only when the ask is unclear: destination sentence + first three decisions + one concrete anchor skip it.
- Frontier batches: each round asks every question whose prerequisites are settled, each with a recommended answer worded so "yes" accepts it.
- Ask everything; the planner makes no decisions of its own — user chose this over "decide small things and list them".
- User away: keep working on what is unblocked, never apply a default, stop when all left is blocked.
- Scope cuts proposed, never taken without the user's answer; explicit out-of-scope section required.
- Facts are looked up by the agent; decisions are the user's.
- Interview stop gate: all sections filled + zero open questions + frontier empty, then explicit yes on restated intent; soft prompt at 10 rounds, hard stop at 20, step back after 3 stalled rounds.
- Spec: numbered B-n behaviours and AC-n criteria, each AC naming its B; no file paths in the spec; EARS templates are guidance, not gated.
- Tasks: vertical slices, ≤5 declared files each unless `Batch: wide-refactor`; exact paths for Edits (checked to exist), globs only for Creates; tasks point at AC ids, never copy text.
- During planning the only writes allowed: plan state folder, `GLOSSARY.md`, `docs/adr/`.
- Prototypes allowed during planning only on a throwaway branch/worktree, never merged; verdict folds into the spec.
- ADR offered only when hard to reverse AND surprising without context AND a real trade-off.
- Competing designs only when the plan adds/changes an interface other files call: 2-3 structurally different designs, loser's reason recorded.
- Every factual claim needs proof (docs URL + quoted passage, code file:line, or command actually run); any unverified claim blocks the plan; prototype verdicts are NOT proof.
- Three script checkpoints (intent signed, plan drafted, review resolved) plus one always-on edit-scope hook; state folder writable only by the engine.
- Explicitly superfluous, do not build: per-stage gates, count quotas, hash-chained ledger, gates passed by saying "passed", separate answer-logging step, grammar regex checks, light-path machinery beyond scope, blocking reads/research, stop hooks during planning, tracker publish gates, re-running checks on unchanged input.
- Plan review: two independent adversarial reviewers (soundness, completeness) on one frozen snapshot, never the planner's reasoning; blocker/major/minor findings quoting the plan; max 3 rounds then open findings go to the user; reviewer models from config, default Sonnet, never Fable.
- After approval: auto-advance into execution (user chose over "stop and I advance"); plan read-only during build; amendments need the user's yes; full review reruns only if a behaviour or criterion changed.
- Sprawl control: fixed file names edited in place, never `plan-v2.md`; finished plan deleted, one line (date, name, outcome) in `done.log`.
- Hard enforcement day one: Claude Code hooks; opencode plugin second; other harnesses advisory only.

Settled question answers:

- PLAN-02: rerun the mutation check on the 4 new guard tests — done 2026-11-13, 7 mutations of shell guard and findRoot all caught.
- PLAN-06.05: add "(Not checked by the system.)" after "Reviewers only read" in review.md — done 2026-11-13; the engine does not block reviewer writes.
- PLAN-12.01: add test that evidence recorded after Yes to Replace plan survives — added 2026-11-13, then dropped as a duplicate of text N10 in the test cut.
- PLAN-30: commit on the worktree branch — done, `ab5f897`.
- PLAN-35: light plan abandoned logs `done` while labelled abandoned — fixed via the `doneLine` edit (PLAN-01).
- PLAN-42: forced path outside git creates nothing — verified.

Test cut (Lance, 2026-11-13):

- Suite cut 184 tests / 2,496 lines → 22 tests / 717 lines (uncommitted in the worktree).
- Rule: one end-to-end walk plus one test per gate whose failure lets an unapproved change through or loses user data.
- Kept: e2e 1, process 2, install 3, hook-guards 5, hook-plan 6, review-fixes 2, round2-fixes 3 (incl. junction/8.3 and evidence-after-Replace).
- Restore any deleted test: `git checkout ab5f897 -- plan-rigorously/tests`.

Durable facts:

- Work location: `C:\Users\Lance\Dev\skills\.claude\worktrees\plan-rigorously`, branch `worktree-plan-rigorously`; repo remote `Bearmancer/skills` (PUBLIC), main.
- Committed state `ab5f897`: 35 files, 183/183 tests at commit time; never merged, never pushed, hooks never installed.
- Four SKILL.md files carry edits no agent made (arr-api-reference, ps-wizard, shell-gotchas, work-audit) — kept uncommitted, not plan-rigorously work (PLAN-34.x unanswered).
- PLAN-49: run `install.mjs` from the final merged location, never the worktree — the hook path comes from the script path.
- Hook facts verified 2026-11-10 against code.claude.com docs (build-spec appendix): settings.json hooks DO fire for subagent tool calls; skill-frontmatter hooks not used; exec form `{"type":"command","command":"node","args":["<abs>/scripts/hook.mjs"],"timeout":10}`; block via stdout JSON `permissionDecision:"deny"` on exit 0 (exit 2 overrides JSON, never mix); AskUserQuestion `tool_response.answers` object observed in transcripts, text-pair fallback kept because the real shape is unverified; Windows `file_path` arrives with backslashes, normalise before comparing; crashed/timed-out hooks fail open.
- Engine: Node ≥20, ESM, zero dependencies, no network; core (parse/checks/stage/state) harness-agnostic so an opencode adapter is one file; hooks fail open except `.rigor/state` protection which fails closed.
- Standing user rules recorded here: never delegate to Fable, Sonnet for medium-to-high work, always pass `model` explicitly; judge skills only after reading the full directory; ask through the question tool with explanations inside option previews; plain language.

End state: parked in the worktree. Uncommitted: the 22-test cut, review.md line-16 edit, the 4 foreign SKILL.md edits. Merge (PLAN-31.01), push (PLAN-32), real hook install (PLAN-33) and disabling the old planning skills (PLAN-44.x) all gated on a live scratch run (PLAN-16.01) and a post-purge review (PLAN-90 / PLAN-50, never completed). 54 questions unanswered at freeze; opencode adapter, execute stage and post-build review stage parked, not started.

## Skills repo: live tests and quality audit (SKILLS)

Source: `C:\Users\Lance\.claude\ledger\epics\skills-repo-live-tests`

Settled decisions:

- SKILLS-20: sync repo github-create to the live fixed version before tests — sync + push, landed as `0bde53b`.
- SKILLS-21: remove github-sweep from the repo (assimilated into github-create housekeeping) — removed in `0bde53b`.
- SKILLS-22: plan-rigorously stays out of this campaign — left to the PLAN epic; campaign tests main-branch skills only.
- SKILLS-23: delete all 16 verified tailscale orphan branches — each verified ahead_by=0 by 4 methods (mirror, ancestor, clone, GraphQL).
- SKILLS-02 eval matrix DROPPED at Lance's decision 2026-11-14: direct tests only — 14 direct live tests, max 3 at a time; standing rules: verify skills directly instead of eval loops, at most 3 agents and 3 rounds per task.
- SKILLS-24: live create test = real fix PR for omo#8229 (skills.enable allowlist), using Sonnet 5.5 via github-create.
- SKILLS-25: arr-api-reference live test — config writes ALLOWED (over the read-only recommendation).
- SKILLS-26: ps-wizard live test — sandbox only (temp dirs + test registry hive, no real installs).
- SKILLS-27: subtitle-triage live test — writes ALLOWED next to real D:\Media.
- SKILLS-90: keep opencode PR #61120 open — underlying issue closed NOT_PLANNED by a bot, Lance's dispute active.
- SKILLS-91/92/93: answered "add the link" but moot on live check — issues already named their PRs; no edit made.
- SKILLS-101/102/104/106/107: fix + push the CONFLICTING PRs (senpi#4253, omo#10704, #10519, #9832, #9741) — full local gate green then force-with-lease; Lance: use Sonnet 5.5 for all these fixes.
- SKILLS-109: work-audit live test target = Dev\skills repo.
- SKILLS-110: rigorous-review live test target = the github-create sync diff `5d5d2cb..0bde53b`.
- SKILLS-94..100, 103, 105 skipped as moot on live gh evidence (bodies already linked; #10521/#10415 MERGEABLE).

Live-test outcomes (durable):

- Create path: omo PR #13379 open, `Fixes #8229`, CI green — fix wraps the native-skills object once at the registry (`applySkillsEnableToNativeSkills`), both `skill` and `task` consumers covered; 14 skill defects recorded for remediation.
- senpi#4253: CONFLICTING → MERGEABLE (head `5470e36d1`); generated `.manifest.json` conflict resolved by REGENERATING with the repo's own model-data helpers, never hand-merge; new-base realm-census + knip gates satisfied like sibling providers; repo merges on the local whole-suite receipt (no hosted PR CI without run-full-ci label).
- omo 3-PR rebase run (#10704/#10519/#9832) interrupted mid-gate; run record incomplete.
- rigorous-review verdict REQUEST CHANGES: BLOCKER at `purge_branches.py:407` — branch names put into REST paths unencoded, `gh api` cuts at `#`/`?`, so purging `fix#12` deletes `fix`; fix (`urllib.parse.quote(b, safe="/")`) verified on branch `fix/purge-branches-encode-refs` in Dev\skills, UNCOMMITTED, needs Lance's commit/PR answer (SKILLS-32).
- work-audit: mechanical half passes (21 indices, report.json), review half not run; `purge-safety` dependency skill does not exist anywhere.

Open remediation obligations at freeze:

- SKILLS-30: 14 github-create defects from live-create-8229.md (issue-form check cannot pass for an adopted issue; AI-policy detector false positives; PR check demands Screenshots heading the template says to delete; step 12 no path without a subagent; step 11 base-state command lacks --paginate; step 13 delete not robust on Windows; scripts write into the skill's own folder unless GITHUB_CREATE_STATE_DIR is set).
- SKILLS-31: 10 work-audit defects (missing purge-safety dependency; named tests absent; unpushed count attributed to main; indices 17/19/20 unusable on a skills repo; no single-agent review path).
- SKILLS-33: github-create fixes from review findings 2-7 (merged-PR purge text vs ahead>0 preserve; exit 0 on failed listings; worktree scan case-sensitive and cwd/~/Dev-only; dead branch :383; hard-coded Bearmancer fallback).

Durable facts:

- Repo `C:\Users\Lance\Dev\skills` at `main@ba81e3f`, 13 skills (github-sweep removed); installed copies in `~/.agents/skills` and `~/.claude/skills`.
- Drift at inventory: github-create, shell-gotchas, work-audit differ in both installed copies; rigorous-research and rigorous-review missing from `~/.claude/skills`; the live tree is not a git repo, repo changes land by PR to Bearmancer/skills.
- Eval workspace: `C:\Users\Lance\AppData\Local\Temp\opencode\skills-test-workspace`.
- Windows git-bash has no /tmp: workspaces go under `AppData\Local\Temp`; `codegraph init -y` must run detached on big repos (blows a 300 s foreground budget); senpi/omo `lint-ratchet` fails natively on Windows (oxlint .cmd shim / 32k argv limit) — needs a loader shim or smaller batches.

End state: campaign in flight at freeze — 8 tasks open, 20 questions unanswered; arr, wizard and subtitle live tests not started; github-create housekeeping work OPEN items only (14 open PRs, 35 open issues, 7 forks), council per repo, max 3 concurrent agents, executed-fix gate unchanged.

## GitHub: third-party PRs, issues and fork cleanup (GITHUB)

Source: `C:\Users\Lance\.claude\ledger\epics\github-third-party-prs`

Settled decisions and completed work:

- GITHUB-24: github-sweep capability fully assimilated into github-create housekeeping mode — parity confirmed, housekeeping rename + uv-only invocations applied, zero leftovers.
- GITHUB-26: `~/.claude/skills/github-sweep` purged (user-ratified) after parity + evals; housekeeping invariants verified: no empty rebase, no user questions, review requests executed red-green per point, run until exhausted.
- GITHUB-25: dry-run evals complete — iteration-1 6/6 matrix, iteration-2 2/2 on fixed scripts; zero GitHub mutations across ~5,600 logged commands.
- GITHUB-27: speed/token audit — census 25.9 s, preflight 3.4 s, ci_status 1.2 s, full purge dry-run 93.8 s for 1,338 branches; SKILL.md split 64→31 lines, housekeeping context load ~11.5k→~8.1k (-29%).
- User rule from the Muse sweep: "never mere rebase" — conflict work must carry an executed fix, not a bare rebase.
- Fixed purge v2 verified: 1,338/1,338 branches covered, 16/16 ground-truth tailscale candidates (batched GraphQL compares 50/query + REST fallback, fail-closed PR census); squash-merged branches preserved while ahead>0.

Durable facts:

- Muse deleted `C:\Users\Lance\senpi` during the sweep without a visible answer; the GitHub fork holds all branches (re-clone question GITHUB-21 unanswered).
- omo#9741: maintainer rule — generated bundles regenerate on Linux at the merge slot; a pushed regen would be overwritten.
- omo#11329: PR #12796 declined 2026-11-08; maintainer welcomes a new PR meeting 3 acceptance conditions (author must not pick what the reviewer re-checks).
- winget#6579: PR #6597 closed; maintainer wanted better error reporting, not a spawned PowerShell process.
- claude-code#103043: closed-source product repo — a fix PR is not possible there.
- Muse posted a verification reply on opencode#61120 without approval (GITHUB-22 unanswered); the reply is accurate per the bot's own numbers.

End state: parked. Audit/merge half done; live cleanup (GITHUB-20.x fork-branch and Temp deletions, GITHUB-21/22/23) all unanswered and carried into the SKILLS epic. Eval workspace `Temp\opencode\github-create-workspace` purge waits on Lance confirming the review viewers (review-iteration-1.html, review-iteration-2.html).

---

# Recovered open backlog — Linear export 2026-11-18 (faithful, full detail)

> Provenance: frozen archive `C:/Users/Lance/.claude/ledger/epics/` via Linear export. Original ledger ids preserved. Open questions retained in full (options, code blocks, recommended rationale); settled answers live in the assimilated sections above and in the repo ledgers.

<!-- ===== BEA-324 ===== -->

# GitHub: third-party PRs, issues and fork cleanup Ledger epic **GITHUB** · folder `epics/github-third-party-prs` Where: your open PRs and issues on other people's repos (omo, senpi and others), plus local forks and branches. Depends on: none Open at export: 7 tasks · 39 questions Source: `C:/Users/Lance/.claude/ledger/epics/github-third-party-prs/` (frozen archive) Topic sub-issues: 8. Every microscopic question is retained as an individually answerable checkbox section inside its topic; original ledger ids are preserved in each description. Reservation: only Lance writes the `Reserved by` label (agent:claude-code / agent:opencode / agent:muse / agent:omo). Agents read, verify, work, never write the enum.
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-324/github-third-party-prs-issues-and-fork-cleanup](https://linear.app/bearmancer/issue/BEA-324/github-third-party-prs-issues-and-fork-cleanup)
- Identifier: BEA-324
- Status: Todo
- Priority: Low - Assignee: Unassigned
- Labels: Epic, GITHUB
- Project: [GitHub: third-party PRs, issues and fork cleanup](https://linear.app/bearmancer/project/github-third-party-prs-issues-and-fork-cleanup-dcf66b895bf6/overview).
- Created: 2026-11-14T06:33:54.901Z
- Updated: 2026-11-14T06:34:57.628Z
## Sub-issues - [BEA-347 Open PR decisions: #9741, #9832, #10521](https://linear.app/bearmancer/issue/BEA-347/open-pr-decisions-9741-9832-10521) - [BEA-348 Cleanup: fork branches & temp files (check = delete)](https://linear.app/bearmancer/issue/BEA-348/cleanup-fork-branches-and-temp-files-check-delete) - [BEA-350 senpi re-clone, PR #61120 reply & close, cfr3](https://linear.app/bearmancer/issue/BEA-350/senpi-re-clone-pr-61120-reply-and-close-cfr3) - [BEA-351 PR work: #9741 bundle, #9832 re-review, #10521 tests, issue links](https://linear.app/bearmancer/issue/BEA-351/pr-work-9741-bundle-9832-re-review-10521-tests-issue-links) - [BEA-352 Fix PRs for 15 open third-party issues (check = write fix PR)](https://linear.app/bearmancer/issue/BEA-352/fix-prs-for-15-open-third-party-issues-check-write-fix-pr) - [BEA-353 Reference sheets (check = write) & issue-to-PR links](https://linear.app/bearmancer/issue/BEA-353/reference-sheets-check-write-and-issue-to-pr-links) - [BEA-354 Merge conflicts: #10415, #10704, #10521](https://linear.app/bearmancer/issue/BEA-354/merge-conflicts-10415-10704-10521) - [BEA-355 Housekeeping: reference sheets, orphan branches, workspace purge, pickup](https://linear.app/bearmancer/issue/BEA-355/housekeeping-reference-sheets-orphan-branches-workspace-purge-pickup)

<!-- ===== BEA-347 ===== -->

# Open PR decisions: #9741, #9832, #10521
> Consolidated from the frozen local ledger · original ids: GITHUB-03, GITHUB-04, GITHUB-05.
> Answer each section: check exactly one option (or every applicable one when marked multi-select). Comment for anything else.
## GITHUB-03 · For omo PR #9741, wait for the maintainer's Linux bundle regeneration instead of doing it yourself? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Wait (Recommended)** — Maintainer rule: regen at merge slot.
``` PR #9741 (task planner live config) state: CONFLICTING, no review decision conflict: generated bundles only maintainer already pushed reload fix (head 7094ea632a) and regenerated once rule on PR: regen on Linux at merge slot Your pushed regen would be overwritten.
```
- [ ] **2. Regen it now** — Run a Linux regen and push anyway.
``` Needs Linux container: node 24, bun 1.4.4. A previous attempt (subagent fe3c3a80) ended mid-regen with no result. Goes against the stated maintainer rule.
```
- [ ] **3. Close the PR** — Withdraw #9741.
``` Closes oh-my-openagent#9741. Issue #9725 stays open.
```
## GITHUB-04 · For omo PR #9832, post a comment asking the maintainer to re-review the requested changes? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Ask for re-review** — One short comment on the PR.
``` PR #9832 (mid-sentence skill expansion) review: CHANGES_REQUESTED your fixes already pushed: detector tests 41/41, type minor 107/107 state: CONFLICTING now Comment would say the items are addressed and ask for re-review.
```
- [ ] **2. Stay silent** — Wait for the maintainer.
``` Nothing posted. Review stays CHANGES_REQUESTED until they return.
```
- [ ] **3. Close the PR** — Withdraw #9832.
``` Closes oh-my-openagent#9832. The work stays in your fork branch.
```
## GITHUB-05 · For omo PR #10521, skip adding more browser-doctor tests, since the identity tests are already in the head? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Skip more tests (Recommended)** — Main found them already present.
``` PR #10521 (Vivaldi identity) Muse main found identity tests already in head; the helper ended before listing any real gap. state now: CONFLICTING No new test code written.
```
- [ ] **2. Add tests anyway** — Re-run a test-gap check first.
``` Re-checks the review items against the tests, adds only missing cases. Costs one more test pass.
```
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [GitHub docs](<https://docs.github.com/>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-347/open-pr-decisions-9741-9832-10521](https://linear.app/bearmancer/issue/BEA-347/open-pr-decisions-9741-9832-10521)
- Identifier: BEA-347
- Status: Todo
- Priority: Low - Assignee: Unassigned
- Labels: GITHUB, Question
- Project: [GitHub: third-party PRs, issues and fork cleanup](https://linear.app/bearmancer/project/github-third-party-prs-issues-and-fork-cleanup-dcf66b895bf6/overview).
- Created: 2026-11-14T06:34:57.628Z
- Updated: 2026-11-14T06:34:57.628Z

<!-- ===== BEA-348 ===== -->

# Cleanup: fork branches & temp files (check = delete)
> Consolidated from the frozen local ledger · original ids: GITHUB-20.01, GITHUB-20.02, GITHUB-20.03, GITHUB-20.04, GITHUB-20.05, GITHUB-20.06, GITHUB-20.07, GITHUB-20.08.
>
**Row semantics:** Check = DELETE the item (recommended where marked). Leave unchecked = keep. Comment for nuance.
## Items
- [ ] **GITHUB-20.01** · Delete your fork branch fix/62678-shell-spool-not-indexed in Bearmancer/opencode?
- [ ] **1. Keep it** — Branch stays; no PR exists for it yet.
``` Bearmancer/opencode fix/62678-shell-spool-not-indexed 1 commit ahead, 229 behind dev commit: fix(shell): mark Windows spool files not-content-indexed (#62678) no PR; issue opencode#62678 open Keeping preserves the only fix attempt.
```
- [ ] **2. Delete it** — Remove the branch from your fork.
``` git push Bearmancer --delete fix/62678-shell-spool-not-indexed The 1 commit would become unreachable after GitHub's cleanup. Issue 62678 remains open without a fix branch.
```
- [ ] **GITHUB-20.02** · Delete your fork branch feat/11329-plan-review-ledger in Bearmancer/oh-my-openagent?
- [ ] **1. Delete it** — Its PR #12796 was closed; branch is dead.
``` Bearmancer/oh-my-openagent feat/11329-plan-review-ledger 1 commit ahead, 1225 behind dev PR #12796: CLOSED 11-08, declined by maintainer (3 conditions unmet) issue #11329: still open Deleting loses the code; PR page keeps diff.
```
- [ ] **2. Keep it** — Keep the code for issue #11329.
``` Branch stays on your fork. Issue #11329 (plan-reviewer ledger) is still open, so the code could seed a new PR later.
```
- [ ] **GITHUB-20.03** · Delete your fork branch temp/gen-golden in Bearmancer/oh-my-openagent?
- [ ] **1. Delete it** — Branch looks like scratch; commits stay on PR work.
``` temp/gen-golden: 6 ahead, 2056 behind dev c846a314a docs(computer-use): document Chromium background input refusal be3d2a91b build(computer-use): sync staged plugin assets 0aee1df3a test(computer-use): update sha256 fixture 5945057d9 docs(computer-use): add Windows/ X11 scope, regenerate assets 7ecbb8830 chore(senpi): update assets.json ec8656026 ci: temp golden generator No PR. Looks like PR #10519 work + a temp CI.
```
- [ ] **2. Keep it** — Keep the 6 commits for now.
``` Branch stays on your fork. Last commit says "temp golden generator"; the other 5 repeat PR #10519 subjects (not diff-checked).
```
- [ ] **GITHUB-20.04** · Delete your fork branch fix/windows-exit-telemetry-assertion in Bearmancer/vercel-skills?
- [ ] **1. Delete it (Recommended)** — Its PR vercel-labs/skills#2462 is merged.
``` Bearmancer/vercel-skills fix/windows-exit-telemetry-assertion PR vercel-labs/skills#2462: MERGED Work lives upstream now; the branch is redundant.
```
- [ ] **2. Keep it** — Branch stays on your fork.
``` No effect on upstream. Only clutter on your fork.
```
- [ ] **GITHUB-20.05** · Delete the 582 MB leftover folder %TEMP%\\muse-wf-rebase?
- [ ] **1. Delete it (Recommended)** — Only a stale dev clone; nothing unpushed.
``` %TEMP%\muse-wf-rebase (exists, 582 MB) holds one clone: omo\ branches: dev only, in sync w/ origin/dev worktrees: none working tree: many files deleted hung git processes already stopped No local-only commits found.
```
- [ ] **2. Keep it** — Leave the folder in place.
``` Uses 582 MB until you delete it. No unpushed branch or commit inside.
```
- [ ] **GITHUB-20.06** · Delete these leftover Temp scratch files from the sweep?
- [ ] **1. bun-check.log** — Typecheck log, 804 bytes, 11-11 14:49.
- [ ] **2. bun-test.log** — Test log, 2.9 KB, 11-11 14:48.
- [ ] **3. check-md.log** — Markdown check log, 1.4 KB, 11-11 14:48.
- [ ] **4. tsgo.log** — Typecheck log, 758 bytes, 11-11 15:40.
- [ ] **GITHUB-20.07** · Delete these other leftover Temp scratch files from the sweep?
- [ ] **1. ce-dev.yml** — Copy of omo CI workflow, 3.6 KB.
- [ ] **2. ce-dev.b64** — Base64 of that same workflow, 10 KB.
- [ ] **3. mb.txt** — One 40-char commit hash, 86 bytes.
- [ ] **4. reviews.txt** — PR review text dump, 15 KB.
- [ ] **GITHUB-20.08** · Delete the leftover Temp file myissues.json (516 KB dump of your issue list)?
- [ ] **1. Delete it (Recommended)** — Sweep scratch dump; the data is on GitHub.
``` %TEMP%\myissues.json 516 KB, 11-11 14:23 JSON list of your authored issues. Regenerable with gh search issues.
```
- [ ] **2. Keep it** — Leave the file in place.
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [GitHub docs](<https://docs.github.com/>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-348/cleanup-fork-branches-and-temp-files-check-delete](https://linear.app/bearmancer/issue/BEA-348/cleanup-fork-branches-and-temp-files-check-delete)
- Identifier: BEA-348
- Status: Todo
- Priority: Low - Assignee: Unassigned
- Labels: GITHUB, Question
- Project: [GitHub: third-party PRs, issues and fork cleanup](https://linear.app/bearmancer/project/github-third-party-prs-issues-and-fork-cleanup-dcf66b895bf6/overview).
- Blocking: BEA-353
- Created: 2026-11-14T06:34:57.860Z
- Updated: 2026-11-14T06:34:57.860Z

<!-- ===== BEA-350 ===== -->

# senpi re-clone, PR #61120 reply & close, cfr3
> Consolidated from the frozen local ledger · original ids: GITHUB-21, GITHUB-22, GITHUB-22.01, GITHUB-23.
> Answer each section: check exactly one option (or every applicable one when marked multi-select). Comment for anything else.
## GITHUB-21 · Re-clone the deleted C:\\Users\\Lance\\senpi folder from your GitHub fork? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Leave it deleted** — Fork on GitHub holds all branches; re-clone later if needed.
``` Bearmancer/senpi (GitHub, checked now): main + 4 branches, all present feat/1708-commandcode-provider 3bb04e4393 = head of PR 4253 (matches) fix/3492, fix/4265, fix/10416: heads match PRs 3651, 6196, 3648 Clone was clean: UNVERIFIED. Muse ran git status but its output is not in the transcript; only Muse's final text says "verified clean". senpi-tmp-*.ts files: gone.
```
- [ ] **2. Re-clone it** — Clone Bearmancer/senpi into C:\\Users\\Lance\\senpi.
``` gh repo clone Bearmancer/senpi -> C:\Users\Lance\senpi Branches come back from the fork: main, feat/1708-commandcode-provider, fix/3492-background-wake-source-rpc, fix/4265-live-channel-stall-streak, fix/10416-tool-name-suggestion Costs disk and time; no work lost either way.
```
## GITHUB-22 · Keep the verification reply Muse posted on opencode PR #61120 without your approval? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Keep the reply** — It is accurate; leave it posted.
``` Posted reply says: get() returns the memoized cachedGet and never takes the lock, so the lock-split changes nothing observable on the default path. The reviewing bot's own ~240 ms numbers agree. Reply is public on the PR.
```
- [ ] **2. Delete the reply** — Remove the comment from the PR.
``` Removes your reply from the review thread. The bot's concern stays unanswered. The PR still has Muse's earlier rebase.
```
## GITHUB-22.01 · Close opencode PR #61120, since its own code check says the lock change has no visible effect? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Leave it open** — Let the maintainers decide.
``` PR #61120 stays open. Bot review 2026-11-11: change only moved onto newer dev; no reproduction that get() ever blocks on the lock. Maintainers decide.
```
- [ ] **2. Close it** — Withdraw the PR.
``` Closes anomalyco/opencode#61120. Issue #61118 stays as it is. You can reopen later.
```
## GITHUB-23 · Drop your message "cfr3" with no action, since Muse could not read it? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Drop it (Recommended)** — Nothing pending came from it; no action.
``` Transcript lines 244-251: user: cfr3??! Muse: "Your message is unclear to me" Muse asked: [Status of fix item 3] No answer is recorded. Muse then reported fix 3 (#9741 bundle regen) as blocked, nothing pushed. Not interpreted here; the guess is Muse's, not yours.
```
- [ ] **2. Tell me what it meant** — Skip; ask again with your own words.
``` You type what cfr3 meant (a fix item, a CFR rule, a typo) and it is recorded.
```
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [GitHub docs](<https://docs.github.com/>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-350/senpi-re-clone-pr-61120-reply-and-close-cfr3](https://linear.app/bearmancer/issue/BEA-350/senpi-re-clone-pr-61120-reply-and-close-cfr3)
- Identifier: BEA-350
- Status: Todo
- Priority: Low - Assignee: Unassigned
- Labels: GITHUB, Question
- Project: [GitHub: third-party PRs, issues and fork cleanup](https://linear.app/bearmancer/project/github-third-party-prs-issues-and-fork-cleanup-dcf66b895bf6/overview).
- Created: 2026-11-14T06:34:58.267Z
- Updated: 2026-11-14T06:34:58.267Z

<!-- ===== BEA-351 ===== -->

# PR work: #9741 bundle, #9832 re-review, #10521 tests, issue links
> Consolidated from the frozen local ledger · original ids: GITHUB-03, GITHUB-04, GITHUB-05, GITHUB-06.
> Tasks: check each box when its real effect is verified; comment the result. Issue Done when all boxes are checked.
## Tasks
- [ ] **GITHUB-03** · PR #9741: bundle regeneration blocked by a maintainer rule; still conflicting
- [ ] **GITHUB-04** · PR #9832: changes requested; needs maintainer dismissal or re-review
- [ ] **GITHUB-05** · PR #10521 browser-doctor tests: subagent ended early; tests appear already in head, unconfirmed
- [ ] **GITHUB-06** · Issue-to-PR links for remaining issues (#10695 and other omo and senpi issues)
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [GitHub docs](<https://docs.github.com/>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-351/pr-work-9741-bundle-9832-re-review-10521-tests-issue-links](https://linear.app/bearmancer/issue/BEA-351/pr-work-9741-bundle-9832-re-review-10521-tests-issue-links)
- Identifier: BEA-351
- Status: Todo
- Priority: Low - Assignee: Unassigned
- Labels: GITHUB, Task
- Project: [GitHub: third-party PRs, issues and fork cleanup](https://linear.app/bearmancer/project/github-third-party-prs-issues-and-fork-cleanup-dcf66b895bf6/overview).
- Blocking: BEA-354
- Created: 2026-11-14T06:35:01.849Z
- Updated: 2026-11-14T06:35:01.849Z

<!-- ===== BEA-352 ===== -->

# Fix PRs for 15 open third-party issues (check = write fix PR)
> Consolidated from the frozen local ledger · original ids: GITHUB-06.90, GITHUB-06.11, GITHUB-06.12, GITHUB-06.14, GITHUB-06.16, GITHUB-06.19, GITHUB-06.21, GITHUB-06.22, GITHUB-06.25, GITHUB-06.27, GITHUB-06.28, GITHUB-06.29, GITHUB-06.30, GITHUB-06.31, GITHUB-06.32, GITHUB-06.33.
> Answer each section: check exactly one option (or every applicable one when marked multi-select). Comment for anything else.
>
**Row semantics:** Check = WRITE a fix PR via the github-create path. Leave unchecked = leave to maintainer (recommended for all). Unchecking everything equals GITHUB-06.90 option 1.
## GITHUB-06.90 · Write fix PRs for any of your 15 other open issues on third-party repos? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. No, leave all (Recommended)** — Skips 15 per-issue questions; maintainers triage.
``` 15 issues, nothing in the sources shows you wanted fixes for them: omo: 11330 11329 10406 10336 9993 9855 8229 senpi: 3498 3496 3495 opencode 61233; tailscale 22191 claude-code 103043; winget 6579 command-code 687 8 more issues already have an open fix PR and were dropped from the list.
```
- [ ] **2. Decide per issue** — Ask me about each of the 15 issues.
``` 15 short questions follow, each: Leave to maintainer / Write fix PR
```
## Items
- [ ] **GITHUB-06.11** · Open a fix PR for omo issue #11330 (task spawn drives matching todo)?
- [ ] **1. Leave to maintainer (Recommended)** — No action; maintainers triage it.
``` code-yeongyu/oh-my-openagent#11330 task spawn drives matching todo open (checked 2026-11-12), filed by you No linked PR. No maintainer reply yet. Nothing is done.
```
- [ ] **2. Write fix PR** — Build a fix and open a PR via the github-create path.
``` code-yeongyu/oh-my-openagent#11330 Clone, fix, test, open PR. Takes a full pass. Blocked if the maintainer has declined it.
```
- [ ] **GITHUB-06.12** · Open a fix PR for omo issue #11329 (plan-reviewer reads review ledger)?
- [ ] **1. Leave to maintainer (Recommended)** — No action; maintainers triage it.
``` code-yeongyu/oh-my-openagent#11329 plan-reviewer reads review ledger open (checked 2026-11-12), filed by you Your PR #12796 was declined 2026-11-08. Maintainer: welcome a new PR meeting 3 acceptance conditions (author must not pick what the reviewer re-checks). Nothing is done.
```
- [ ] **2. Write fix PR** — Build a fix and open a PR via the github-create path.
``` code-yeongyu/oh-my-openagent#11329 Clone, fix, test, open PR. Takes a full pass. Blocked if the maintainer has declined it.
```
- [ ] **GITHUB-06.14** · Open a fix PR for omo issue #10406 (CDP navigate detaches mid-command)?
- [ ] **1. Leave to maintainer (Recommended)** — No action; maintainers triage it.
``` code-yeongyu/oh-my-openagent#10406 CDP navigate detaches mid-command open (checked 2026-11-12), filed by you Your PR #10522 closed as superseded. Maintainer is tracing it and asked for more detail; you replied with a re-check. Nothing is done.
```
- [ ] **2. Write fix PR** — Build a fix and open a PR via the github-create path.
``` code-yeongyu/oh-my-openagent#10406 Clone, fix, test, open PR. Takes a full pass. Blocked if the maintainer has declined it.
```
- [ ] **GITHUB-06.16** · Open a fix PR for omo issue #10336 (shutdown handlers vs senpi caps)?
- [ ] **1. Leave to maintainer (Recommended)** — No action; maintainers triage it.
``` code-yeongyu/oh-my-openagent#10336 shutdown handlers vs senpi caps open (checked 2026-11-12), filed by you Your PR #12795 (comment fix) merged 11-09. Maintainer asked if a handler ever hit the 10 s cap; you replied with log lines. Nothing is done.
```
- [ ] **2. Write fix PR** — Build a fix and open a PR via the github-create path.
``` code-yeongyu/oh-my-openagent#10336 Clone, fix, test, open PR. Takes a full pass. Blocked if the maintainer has declined it.
```
- [ ] **GITHUB-06.19** · Open a fix PR for omo issue #9993 (dag sdk.cancel kills no children)?
- [ ] **1. Leave to maintainer (Recommended)** — No action; maintainers triage it.
``` code-yeongyu/oh-my-openagent#9993 dag sdk.cancel kills no children open (checked 2026-11-12), filed by you No linked PR. No maintainer fix seen. Nothing is done.
```
- [ ] **2. Write fix PR** — Build a fix and open a PR via the github-create path.
``` code-yeongyu/oh-my-openagent#9993 Clone, fix, test, open PR. Takes a full pass. Blocked if the maintainer has declined it.
```
- [ ] **GITHUB-06.21** · Open a fix PR for omo issue #9855 (bsk installer dies on PS7 dirs)?
- [ ] **1. Leave to maintainer (Recommended)** — No action; maintainers triage it.
``` code-yeongyu/oh-my-openagent#9855 bsk installer dies on PS7 dirs open (checked 2026-11-12), filed by you Others' PRs mention it (#12203 open, but it closes a different issue). No fix PR yours. Nothing is done.
```
- [ ] **2. Write fix PR** — Build a fix and open a PR via the github-create path.
``` code-yeongyu/oh-my-openagent#9855 Clone, fix, test, open PR. Takes a full pass. Blocked if the maintainer has declined it.
```
- [ ] **GITHUB-06.22** · Open a fix PR for omo issue #8229 (skills.enable allowlist has no effect)?
- [ ] **1. Leave to maintainer (Recommended)** — No action; maintainers triage it.
``` code-yeongyu/oh-my-openagent#8229 skills.enable allowlist has no effect open (checked 2026-11-12), filed by you Others' PRs #8357 merged, #9011 closed unmerged; issue still open. Nothing is done.
```
- [ ] **2. Write fix PR** — Build a fix and open a PR via the github-create path.
``` code-yeongyu/oh-my-openagent#8229 Clone, fix, test, open PR. Takes a full pass. Blocked if the maintainer has declined it.
```
- [ ] **GITHUB-06.25** · Open a fix PR for senpi issue #3498 (notified_epoch stays -1)?
- [ ] **1. Leave to maintainer (Recommended)** — No action; maintainers triage it.
``` code-yeongyu/senpi#3498 notified_epoch stays -1 open (checked 2026-11-12), filed by you No linked PR. Nothing is done.
```
- [ ] **2. Write fix PR** — Build a fix and open a PR via the github-create path.
``` code-yeongyu/senpi#3498 Clone, fix, test, open PR. Takes a full pass. Blocked if the maintainer has declined it.
```
- [ ] **GITHUB-06.27** · Open a fix PR for senpi issue #3496 (reload_deferred never retried)?
- [ ] **1. Leave to maintainer (Recommended)** — No action; maintainers triage it.
``` code-yeongyu/senpi#3496 reload_deferred never retried open (checked 2026-11-12), filed by you No linked PR. Nothing is done.
```
- [ ] **2. Write fix PR** — Build a fix and open a PR via the github-create path.
``` code-yeongyu/senpi#3496 Clone, fix, test, open PR. Takes a full pass. Blocked if the maintainer has declined it.
```
- [ ] **GITHUB-06.28** · Open a fix PR for senpi issue #3495 (background shell missing bun, exit 127)?
- [ ] **1. Leave to maintainer (Recommended)** — No action; maintainers triage it.
``` code-yeongyu/senpi#3495 background shell missing bun, exit 127 open (checked 2026-11-12), filed by you No linked PR. Nothing is done.
```
- [ ] **2. Write fix PR** — Build a fix and open a PR via the github-create path.
``` code-yeongyu/senpi#3495 Clone, fix, test, open PR. Takes a full pass. Blocked if the maintainer has declined it.
```
- [ ] **GITHUB-06.29** · Open a fix PR for opencode issue #61233 (Windows TUI cold start update check)?
- [ ] **1. Leave to maintainer (Recommended)** — No action; maintainers triage it.
``` anomalyco/opencode#61233 Windows TUI cold start update check open (checked 2026-11-12), filed by you PR #62273 (other author) cross-refs it but closes a different issue (#62246). Nothing is done.
```
- [ ] **2. Write fix PR** — Build a fix and open a PR via the github-create path.
``` anomalyco/opencode#61233 Clone, fix, test, open PR. Takes a full pass. Blocked if the maintainer has declined it.
```
- [ ] **GITHUB-06.30** · Open a fix PR for tailscale issue #22191 (Windows service cold-boot race)?
- [ ] **1. Leave to maintainer (Recommended)** — No action; maintainers triage it.
``` tailscale/tailscale#22191 Windows service cold-boot race open (checked 2026-11-12), filed by you No linked PR. Big upstream project. Nothing is done.
```
- [ ] **2. Write fix PR** — Build a fix and open a PR via the github-create path.
``` tailscale/tailscale#22191 Clone, fix, test, open PR. Takes a full pass. Blocked if the maintainer has declined it.
```
- [ ] **GITHUB-06.31** · Open a fix PR for claude-code issue #103043 (bg dispatch rewrote settings.json)?
- [ ] **1. Leave to maintainer (Recommended)** — No action; maintainers triage it.
``` anthropics/claude-code#103043 bg dispatch rewrote settings.json open (checked 2026-11-12), filed by you No linked PR. Closed-source product repo: a fix PR is not possible there. Nothing is done.
```
- [ ] **2. Write fix PR** — Build a fix and open a PR via the github-create path.
``` anthropics/claude-code#103043 Clone, fix, test, open PR. Takes a full pass. Blocked if the maintainer has declined it.
```
- [ ] **GITHUB-06.32** · Open a fix PR for winget issue #6579 (uninstall MSIX fails 0x80070520)?
- [ ] **1. Leave to maintainer (Recommended)** — No action; maintainers triage it.
``` microsoft/winget-cli#6579 uninstall MSIX fails 0x80070520 open (checked 2026-11-12), filed by you Your PR #6597 closed 2026-10-27. Maintainer wanted better error reporting, not a spawned PowerShell process. Nothing is done.
```
- [ ] **2. Write fix PR** — Build a fix and open a PR via the github-create path.
``` microsoft/winget-cli#6579 Clone, fix, test, open PR. Takes a full pass. Blocked if the maintainer has declined it.
```
- [ ] **GITHUB-06.33** · Open a fix PR for command-code issue #687 (config rename EPERM report)?
- [ ] **1. Leave to maintainer (Recommended)** — No action; maintainers triage it.
``` CommandCodeAI/command-code#687 config rename EPERM report open (checked 2026-11-12), filed by you No linked PR. A diagnostic report issue. Nothing is done.
```
- [ ] **2. Write fix PR** — Build a fix and open a PR via the github-create path.
``` CommandCodeAI/command-code#687 Clone, fix, test, open PR. Takes a full pass. Blocked if the maintainer has declined it.
```
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [GitHub docs](<https://docs.github.com/>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-352/fix-prs-for-15-open-third-party-issues-check-write-fix-pr](https://linear.app/bearmancer/issue/BEA-352/fix-prs-for-15-open-third-party-issues-check-write-fix-pr)
- Identifier: BEA-352
- Status: Todo
- Priority: Low - Assignee: Unassigned
- Labels: GITHUB, Question
- Project: [GitHub: third-party PRs, issues and fork cleanup](https://linear.app/bearmancer/project/github-third-party-prs-issues-and-fork-cleanup-dcf66b895bf6/overview).
- Created: 2026-11-14T06:35:01.990Z
- Updated: 2026-11-14T06:35:01.990Z

<!-- ===== BEA-353 ===== -->

# Reference sheets (check = write) & issue-to-PR links
> Consolidated from the frozen local ledger · original ids: GITHUB-06.01, GITHUB-06.03, GITHUB-01.01, GITHUB-01.02, GITHUB-01.03.
> Answer each section: check exactly one option (or every applicable one when marked multi-select). Comment for anything else.
>
**Row semantics:** Check = WRITE the reference sheet. Leave unchecked = skip (live GitHub data is enough).
## GITHUB-06.01 · Add 'Fixes #4265' to senpi PR #6196 so it closes its proposal issue? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Add the link (Recommended)** — Edit the PR body only; one line added.
``` senpi PR #6196 (branch fix/4265-...) body: "Closes nothing; linked to #4265 as a proposal" (checked on GitHub) closing issues today: none Issue #4265 (your proposal): open. Adds: Fixes #4265 -> merging closes it.
```
- [ ] **2. Leave unlinked** — Maintainers link it themselves.
``` No edit. The PR already names #4265 in text, but GitHub will not close the issue on merge.
```
## GITHUB-06.03 · Open a PR from your branch fix/62678-shell-spool-not-indexed for opencode issue #62678? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Leave it** — No PR now.
``` Issue #62678: Windows Search indexes shell spool files. Open, no PR. Branch is 1 commit, diverged from dev.
```
- [ ] **2. Open the PR** — Rebase on dev, then open it.
``` Needs a fresh rebase onto upstream dev, tests, then 'gh pr create'. Best handled by the github-create path.
```
## Items
- [ ] **GITHUB-01.01** · Write a reference sheet for your opencode (anomalyco) PRs and issues?
- [ ] **1. Skip it** — Live data on GitHub is enough.
``` opencode: 3 open PRs (57361, 61120, 62691) 4 open issues (57354, 61119, 61233, 62678) Anyone can re-list with gh in seconds.
```
- [ ] **2. Write the sheet** — One file listing state per PR/issue.
``` Sheet columns: number, title, state, CI, review status, next step. Goes in the ledger folder; goes stale.
```
- [ ] **GITHUB-01.02** · Write a reference sheet for your oh-my-openagent PRs and issues?
- [ ] **1. Skip it** — Live data on GitHub is enough.
``` omo: 7 open PRs (9741, 9832, 10415, 10519, 10520, 10521, 10704) ~19 open issues Re-list any time with gh.
```
- [ ] **2. Write the sheet** — One file listing state per PR/issue.
``` Sheet columns: number, title, state, CI, review status, next step. Goes in the ledger folder; goes stale.
```
- [ ] **GITHUB-01.03** · Write a reference sheet for your senpi PRs and issues?
- [ ] **1. Skip it** — Live data on GitHub is enough.
``` senpi: 4 open PRs (3648, 3651, 4253, 6196) 8 open issues Re-list any time with gh.
```
- [ ] **2. Write the sheet** — One file listing state per PR/issue.
``` Sheet columns: number, title, state, CI, review status, next step. Goes in the ledger folder; goes stale.
```
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [GitHub docs](<https://docs.github.com/>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-353/reference-sheets-check-write-and-issue-to-pr-links](https://linear.app/bearmancer/issue/BEA-353/reference-sheets-check-write-and-issue-to-pr-links)
- Identifier: BEA-353
- Status: Todo
- Priority: Low - Assignee: Unassigned
- Labels: GITHUB, Question
- Project: [GitHub: third-party PRs, issues and fork cleanup](https://linear.app/bearmancer/project/github-third-party-prs-issues-and-fork-cleanup-dcf66b895bf6/overview).
- Blocked by: BEA-348
- Created: 2026-11-14T06:35:02.263Z
- Updated: 2026-11-14T06:37:34.992Z

<!-- ===== BEA-354 ===== -->

# Merge conflicts: #10415, #10704, #10521
> Consolidated from the frozen local ledger · original ids: GITHUB-03.10, GITHUB-03.11, GITHUB-03.12.
> Answer each section: check exactly one option (or every applicable one when marked multi-select). Comment for anything else.
## GITHUB-03.10 · Fix the merge conflict on omo PR #10415 (GOOGLE_CLOUD_PROJECT passthrough)? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Leave it** — Conflict is just dev moving on.
``` PR #10415: CONFLICTING, no review yet. Closes issue #10414. You told Muse 'never mere rebase' (fixes only), so a bare rebase is out.
```
- [ ] **2. Resolve conflict** — Merge dev and push with a comment.
``` Merge dev into fix/env-cleaner-google- project-passthrough, rerun tests, push. No review items yet to address.
```
## GITHUB-03.11 · Fix the merge conflict on omo PR #10704 (parent_dirty paths)? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Leave it** — Muse already rebased it once today.
``` PR #10704: CONFLICTING again. Closes issue #10695. Muse rebased it (8af8a00515), then dev moved. CI reds were env-only.
```
- [ ] **2. Resolve conflict** — Merge dev and push with a comment.
``` Merge dev into fix/parent-dirty-names- paths, rerun tests, push.
```
## GITHUB-03.12 · Fix the merge conflict on omo PR #10521 (Vivaldi identity)? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Leave it** — Muse already rebased it once today.
``` PR #10521: CONFLICTING again. Closes issue #10407. Muse rebased it (8705b471b0), then dev moved.
```
- [ ] **2. Resolve conflict** — Merge dev and push with a comment.
``` Merge dev into fix/browser-doctor-vivaldi-id, rerun tests, push.
```
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [GitHub docs](<https://docs.github.com/>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-354/merge-conflicts-10415-10704-10521](https://linear.app/bearmancer/issue/BEA-354/merge-conflicts-10415-10704-10521)
- Identifier: BEA-354
- Status: Todo
- Priority: Low - Assignee: Unassigned
- Labels: GITHUB, Question
- Project: [GitHub: third-party PRs, issues and fork cleanup](https://linear.app/bearmancer/project/github-third-party-prs-issues-and-fork-cleanup-dcf66b895bf6/overview).
- Blocked by: BEA-351
- Created: 2026-11-14T06:35:02.372Z
- Updated: 2026-11-14T06:37:31.522Z

<!-- ===== BEA-355 ===== -->

# Housekeeping: reference sheets, orphan branches, workspace purge, pickup
> Consolidated from the frozen local ledger · original ids: GITHUB-01, GITHUB-02, GITHUB-28.
> Tasks: check each box when its real effect is verified; comment the result. Issue Done when all boxes are checked.
## Tasks
- [ ] **GITHUB-01** · Per-repo reference sheets: none written; census notes exist only in the summary
- [ ] **GITHUB-02** · Orphan branch check: census done, nothing verified
- [ ] **GITHUB-28** · Pickup (plan todos 1, 2): note that the skill-refactor chat tail is superseded and closed by GITHUB-24..27; remaining work is purging Temp\\opencode\\github-create-workspace per this epic's CHECKPOINT. Do not release GITHUB: its checkpoint is already correct. Spec: epics\\ledger-and-question-gate\\PLAN-ledger-pickup.md (reviewer-approved, executor uses --as omo, never --force, never `ledger now`). · added 2026-11-13 by omo
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [GitHub docs](<https://docs.github.com/>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-355/housekeeping-reference-sheets-orphan-branches-workspace-purge-pickup](https://linear.app/bearmancer/issue/BEA-355/housekeeping-reference-sheets-orphan-branches-workspace-purge-pickup)
- Identifier: BEA-355
- Status: Todo
- Priority: Low - Assignee: Unassigned
- Labels: GITHUB, Task
- Project: [GitHub: third-party PRs, issues and fork cleanup](https://linear.app/bearmancer/project/github-third-party-prs-issues-and-fork-cleanup-dcf66b895bf6/overview).
- Created: 2026-11-14T06:35:05.652Z
- Updated: 2026-11-14T06:35:05.652Z

<!-- ===== BEA-329 ===== -->

# Skills repo: maximalist live tests and quality audit Ledger epic **SKILLS** · folder `epics/skills-repo-live-tests` Where: `C:\Users\Lance\Dev\skills` ([github.com/Bearmancer/skills](<http://github.com/Bearmancer/skills>), main@5d5d2cb), 14 skills; installed copies in `~/.agents/skills` and `~/.claude/skills`. Eval workspace: `C:\Users\Lance\AppData\Local\Temp\opencode\skills-test-workspace`. Depends on: none Claimed by omo at 2026-11-14T02:19:37.852Z (frozen ledger state at export) Open at export: 9 tasks · 11 questions Source: `C:/Users/Lance/.claude/ledger/epics/skills-repo-live-tests/` (frozen archive) Topic sub-issues: 6. Every microscopic question is retained as an individually answerable checkbox section inside its topic; original ledger ids are preserved in each description. Reservation: only Lance writes the `Reserved by` label (agent:claude-code / agent:opencode / agent:muse / agent:omo). Agents read, verify, work, never write the enum.
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-329/skills-repo-maximalist-live-tests-and-quality-audit](https://linear.app/bearmancer/issue/BEA-329/skills-repo-maximalist-live-tests-and-quality-audit)
- Identifier: BEA-329
- Status: In Progress
- Priority: Urgent - Assignee: Unassigned
- Labels: Epic, SKILLS
- Project: [Skills repo: maximalist live tests and quality audit](https://linear.app/bearmancer/project/skills-repo-maximalist-live-tests-and-quality-audit-03f90fb239d7/overview).
- Created: 2026-11-14T06:34:01.236Z
- Updated: 2026-11-14T06:36:16.120Z
## Sub-issues - [BEA-404 Repo hygiene: .omc state, Claude copy sync, scorecard fixes](https://linear.app/bearmancer/issue/BEA-404/repo-hygiene-omc-state-claude-copy-sync-scorecard-fixes) - [BEA-405 Live-test methods: research topic, execute, fast-tests, kotlin, shell-gotchas](https://linear.app/bearmancer/issue/BEA-405/live-test-methods-research-topic-execute-fast-tests-kotlin-shell) - [BEA-406 Live-test fixtures: music release, ghazal, subtitle case](https://linear.app/bearmancer/issue/BEA-406/live-test-fixtures-music-release-ghazal-subtitle-case) - [BEA-407 Live tests & deepwork quality passes](https://linear.app/bearmancer/issue/BEA-407/live-tests-and-deepwork-quality-passes) - [BEA-409 Remediation: github-create housekeeping & defects, work-audit, purge_branches, script fixes](https://linear.app/bearmancer/issue/BEA-409/remediation-github-create-housekeeping-and-defects-work-audit-purge) - [BEA-410 Reconciliation & final report](https://linear.app/bearmancer/issue/BEA-410/reconciliation-and-final-report)

<!-- ===== BEA-404 ===== -->

# Repo hygiene: .omc state, Claude copy sync, scorecard fixes
> Consolidated from the frozen local ledger · original ids: SKILLS-126, SKILLS-127, SKILLS-128.
> Answer each section: check exactly one option (or every applicable one when marked multi-select). Comment for anything else.
## SKILLS-126 · Delete the untracked .omc session-state folders in Dev\\skills? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Delete (Recommended)** — Dead-chat session state (purged chat d8eb0d62), not skill content; repo ships skills only.
``` .omc/sessions/d8eb0d62...json .omc/state/session-end-jobs/... ps-wizard/.omc/ (same kind) chat d8eb0d62 purged 2026-11-12 not referenced by any skill
```
- [ ] **2. Keep** — Stays untracked; harness state remains in the repo working tree.
``` no change; .omc stays untracked
```
## SKILLS-127 · Sync \~/.claude/skills/github-create to the fixed version too? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Sync it (Recommended)** — Claude Code loads this copy; keeps both harnesses on the verified skill.
``` ~/.claude/skills/github-create SKILL.md differs from fixed live ~/.agents copy = repo @ 0bde53b no junction: real separate copy
```
- [ ] **2. Leave it stale** — Claude Code keeps the pre-fix version until separately synced.
``` no change; Claude copy stays stale
```
## SKILLS-128 · Rigor-scorecard fixes: apply to the repo skills, or report-only? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Apply + re-test (Recommended)** — Each weakness fixed in the skill, then re-tested red-green; commits only via answered questions.
``` 6 gates per skill: unattended end, fail-closed, executed evidence, bundled scripts, lean load, ledger/report discipline fix = edit + re-test, not prose
```
- [ ] **2. Report-only** — Scorecard and proposals delivered; no skill files changed.
``` scorecard + proposals only no skill files changed
```
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [OpenCode skills](<https://opencode.ai/docs/skills/>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-404/repo-hygiene-omc-state-claude-copy-sync-scorecard-fixes](https://linear.app/bearmancer/issue/BEA-404/repo-hygiene-omc-state-claude-copy-sync-scorecard-fixes)
- Identifier: BEA-404
- Status: Todo
- Priority: Urgent - Assignee: Unassigned
- Labels: Question, SKILLS
- Project: [Skills repo: maximalist live tests and quality audit](https://linear.app/bearmancer/project/skills-repo-maximalist-live-tests-and-quality-audit-03f90fb239d7/overview).
- Created: 2026-11-14T06:36:16.120Z
- Updated: 2026-11-14T06:36:16.120Z

<!-- ===== BEA-405 ===== -->

# Live-test methods: research topic, execute, fast-tests, kotlin, shell-gotchas
> Consolidated from the frozen local ledger · original ids: SKILLS-111, SKILLS-113, SKILLS-114, SKILLS-115, SKILLS-116.
> Answer each section: check exactly one option (or every applicable one when marked multi-select). Comment for anything else.
## SKILLS-111 · rigorous-research live test topic: OpenCode Go/Zen free-model rate limits? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Free-tier limits (Recommended)** — Directly useful: this campaign runs on those free tiers; claims verified and published.
``` question: what rate limits apply to opencode-go / opencode free models? output: ledgered, verified claims
```
- [ ] **2. Different topic** — Name another concrete research question.
``` choose another research topic
```
## SKILLS-113 · execute-rigorously live test: execute a gated plan on a scratch fixture repo? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Scratch fixture (Recommended)** — Real worktree, commits and red-green ledger on a throwaway repo under temp.
``` fixture repo in Temp\opencode plan -> worktree -> red-green tasks -> review gate -> ledger, all real
```
- [ ] **2. Real repo worktree** — Runs against a real project worktree; heavier, riskier.
``` real project worktree real commits on a real branch
```
- [ ] **3. Skip live test** — Static review of the skill only.
``` no execution; text review only
```
## SKILLS-114 · fast-tests live test: measure and cut a fixture suite with planted slow tests? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Planted fixture (Recommended)** — Known bottlenecks (sleeps, process spawns); verifies the measure-first method.
``` fixture suite: planted sleeps, process spawns, shared state skill must measure, then cut
```
- [ ] **2. Use a real repo** — Name a repo with a genuinely slow suite.
``` choose a real slow suite
```
## SKILLS-115 · kotlin-modern-syntax live test: scan a fixture with planted antipatterns? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Planted fixture (Recommended)** — Fixture carries context receivers, kotlinOptions, Char.toInt etc.; scanner must flag them.
``` planted: context receivers, kotlinOptions, readLine, Char.toInt, backing properties scanner must flag each one
```
- [ ] **2. Real Kotlin repo** — Name a Kotlin repo on this machine to scan.
``` choose a real Kotlin codebase
```
## SKILLS-116 · shell-gotchas live test: reproduce its documented gotchas in scratch shells? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Scratch only (Recommended)** — Real pwsh/git-bash failures reproduced and recovered in temp; nothing real touched.
``` reproduce quoting/splatting/ process-kill gotchas in scratch shells under Temp\opencode
```
- [ ] **2. Skip live test** — Static review of the skill only.
``` no execution; text review only
```
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [OpenCode skills](<https://opencode.ai/docs/skills/>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-405/live-test-methods-research-topic-execute-fast-tests-kotlin-shell](https://linear.app/bearmancer/issue/BEA-405/live-test-methods-research-topic-execute-fast-tests-kotlin-shell)
- Identifier: BEA-405
- Status: Todo
- Priority: Urgent - Assignee: Unassigned
- Labels: Question, SKILLS
- Project: [Skills repo: maximalist live tests and quality audit](https://linear.app/bearmancer/project/skills-repo-maximalist-live-tests-and-quality-audit-03f90fb239d7/overview).
- Created: 2026-11-14T06:36:16.251Z
- Updated: 2026-11-14T06:36:16.251Z

<!-- ===== BEA-406 ===== -->

# Live-test fixtures: music release, ghazal, subtitle case
> Consolidated from the frozen local ledger · original ids: SKILLS-117, SKILLS-118, SKILLS-119.
> Answer each section: check exactly one option (or every applicable one when marked multi-select). Comment for anything else.
## SKILLS-117 · Which release should the lookup-music-artists live test extract artists from? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Solti/Chicago release (Recommended)** — I locate a concrete MusicBrainz URL from your TAGS library before the run.
``` TAGS library: Solti / Chicago Symphony releases; I pin one MusicBrainz URL before the run
```
- [ ] **2. Need details** — Skip; ask again with the missing detail.
``` defer until a URL is pinned
```
## SKILLS-118 · lyric-romanizer live test: use the Faiz ghazal Mujh Se Pehli Si Mohabbat? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Faiz ghazal (Recommended)** — Urdu ghazal, public text; exercises romanization, translation and dedupe.
``` Faiz Ahmed Faiz Mujh Se Pehli Si Mohabbat Urdu -> romanized study sheet
```
- [ ] **2. Different song** — Name the song and language.
``` choose another song
```
## SKILLS-119 · subtitle-triage live test: let me find a real problem case on D:\\Media? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Find a real case (Recommended)** — I scan for a subtitle with a measurable fit/provenance problem, then triage it.
``` scan D:\Media for a subtitle with measurable fit/provenance problem; pin it before the run
```
- [ ] **2. Need details** — Skip; ask again with the missing detail.
``` defer until a case is pinned
```
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [OpenCode skills](<https://opencode.ai/docs/skills/>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-406/live-test-fixtures-music-release-ghazal-subtitle-case](https://linear.app/bearmancer/issue/BEA-406/live-test-fixtures-music-release-ghazal-subtitle-case)
- Identifier: BEA-406
- Status: Todo
- Priority: Urgent - Assignee: Unassigned
- Labels: Question, SKILLS
- Project: [Skills repo: maximalist live tests and quality audit](https://linear.app/bearmancer/project/skills-repo-maximalist-live-tests-and-quality-audit-03f90fb239d7/overview).
- Created: 2026-11-14T06:36:16.581Z
- Updated: 2026-11-14T06:36:16.581Z

<!-- ===== BEA-407 ===== -->

# Live tests & deepwork quality passes
> Consolidated from the frozen local ledger · original ids: SKILLS-03, SKILLS-04.
> Tasks: check each box when its real effect is verified; comment the result. Issue Done when all boxes are checked.
## Tasks
- [ ] **SKILLS-03** · Live tests per ratified envelope (GitHub mutations, arr probes, wizard sandbox, media reads)
- [ ] **SKILLS-04** · Deepwork quality passes: oracle gates, remediation, re-validation
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [OpenCode skills](<https://opencode.ai/docs/skills/>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-407/live-tests-and-deepwork-quality-passes](https://linear.app/bearmancer/issue/BEA-407/live-tests-and-deepwork-quality-passes)
- Identifier: BEA-407
- Status: Todo
- Priority: Urgent - Assignee: Unassigned
- Labels: SKILLS, Task
- Project: [Skills repo: maximalist live tests and quality audit](https://linear.app/bearmancer/project/skills-repo-maximalist-live-tests-and-quality-audit-03f90fb239d7/overview).
- Created: 2026-11-14T06:36:19.740Z
- Updated: 2026-11-14T06:36:19.740Z

<!-- ===== BEA-409 ===== -->

# Remediation: github-create housekeeping & defects, work-audit, purge_branches, script fixes
> Consolidated from the frozen local ledger · original ids: SKILLS-29, SKILLS-30, SKILLS-31, SKILLS-32, SKILLS-33.
> Tasks: check each box when its real effect is verified; comment the result. Issue Done when all boxes are checked.
## Tasks
- [ ] **SKILLS-29** · github-create housekeeping: work OPEN items only (14 open PRs, 35 open issues, 7 forks) - no closed/merged history inventory; expedite. Council per repo settles verdicts (omo split PRs/issues), max 3 concurrent agents; executed-fix gate unchanged. · added 2026-11-13 by opencode
- [ ] **SKILLS-30** · github-create remediation from live create test (14 defects in live-create-8229.md, Skill defects section): fix at least 1 issue-form check cannot pass for an adopted issue, 3 AI-policy detector false positives, 4 PR check demands a Screenshots heading the template says to delete, 5 step 12 has no path without a subagent, 6 step 11 base-state command lacks --paginate, 14 step 13 delete not robust on Windows; each fix re-tested, landed by PR to Bearmancer/skills · added 2026-11-14 by omo
- [ ] **SKILLS-31** · work-audit remediation from live test (10 defects in live-work-audit.md): at least 1 purge-safety dependency missing, 2 skill tests named but absent, 4 unpushed count attributed to main, 5-7 indices 17/19/20 unusable on a skills repo, 9 no single-agent path for the review step; each fix re-tested, landed by PR to Bearmancer/skills · added 2026-11-14 by omo
- [ ] **SKILLS-32** · Land purge_branches.py ref-encoding fix (BLOCKER from live-rigorous-review.md finding 1): uncommitted on branch fix/purge-branches-encode-refs in Dev\\skills, verified (ref_path encodes
# ? %, slash kept; dry-run on Bearmancer/senpi exit 0). Needs Lance's answer to commit, PR, squash-merge, then sync both installed copies · added 2026-11-14 by omo
- [ ] **SKILLS-33** · github-create script fixes from live-rigorous-review.md findings 2-7: docstring and branch-hygiene.md say merged PRs are purged but ahead>0 always preserves; purge_branches.py and [sweep.py](<http://sweep.py>) exit 0 on a failed fork/branch/census listing; worktree scan case-sensitive and limited to cwd and \~/Dev; dead branch at :383; hard-coded user fallback · added 2026-11-14 by omo
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [OpenCode skills](<https://opencode.ai/docs/skills/>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-409/remediation-github-create-housekeeping-and-defects-work-audit-purge](https://linear.app/bearmancer/issue/BEA-409/remediation-github-create-housekeeping-and-defects-work-audit-purge)
- Identifier: BEA-409
- Status: Todo
- Priority: Urgent - Assignee: Unassigned
- Labels: SKILLS, Task
- Project: [Skills repo: maximalist live tests and quality audit](https://linear.app/bearmancer/project/skills-repo-maximalist-live-tests-and-quality-audit-03f90fb239d7/overview).
- Created: 2026-11-14T06:36:20.208Z
- Updated: 2026-11-14T06:36:20.208Z

<!-- ===== BEA-410 ===== -->

# Reconciliation & final report
> Consolidated from the frozen local ledger · original ids: SKILLS-05, SKILLS-06.
> Tasks: check each box when its real effect is verified; comment the result. Issue Done when all boxes are checked.
## Tasks
- [ ] **SKILLS-05** · Repo reconciliation: apply ratified sync/removals; commit+push only as answered
- [ ] **SKILLS-06** · Final report + ledger/EPIC updates, known-issues handover
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [OpenCode skills](<https://opencode.ai/docs/skills/>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-410/reconciliation-and-final-report](https://linear.app/bearmancer/issue/BEA-410/reconciliation-and-final-report)
- Identifier: BEA-410
- Status: Todo
- Priority: Urgent - Assignee: Unassigned
- Labels: SKILLS, Task
- Project: [Skills repo: maximalist live tests and quality audit](https://linear.app/bearmancer/project/skills-repo-maximalist-live-tests-and-quality-audit-03f90fb239d7/overview).
- Created: 2026-11-14T06:36:20.623Z
- Updated: 2026-11-14T06:36:20.623Z

<!-- ===== BEA-328 ===== -->

# plan-rigorously skill: review, merge, install Ledger epic **PLAN** · folder `epics/plan-rigorously-skill` Where: `C:\Users\Lance\Dev\skills\.claude\worktrees\plan-rigorously` (exists). Branch `worktree-plan-rigorously`. Depends on: none Claimed by claude-code at 2026-11-13T02:42:51.891Z (frozen ledger state at export) Open at export: 17 tasks · 54 questions Source: `C:/Users/Lance/.claude/ledger/epics/plan-rigorously-skill/` (frozen archive) Topic sub-issues: 13. Every microscopic question is retained as an individually answerable checkbox section inside its topic; original ledger ids are preserved in each description. Reservation: only Lance writes the `Reserved by` label (agent:claude-code / agent:opencode / agent:muse / agent:omo). Agents read, verify, work, never write the enum.
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-328/plan-rigorously-skill-review-merge-install](https://linear.app/bearmancer/issue/BEA-328/plan-rigorously-skill-review-merge-install)
- Identifier: BEA-328
- Status: Todo
- Priority: Medium - Assignee: Unassigned
- Labels: Epic, PLAN
- Project: [plan-rigorously skill: review, merge, install](https://linear.app/bearmancer/project/plan-rigorously-skill-review-merge-install-190904d79fd9/overview).
- Blocking: BEA-323
- Created: 2026-11-14T06:33:58.584Z
- Updated: 2026-11-14T10:31:33.673Z
## Sub-issues
- [BEA-381 Uncommitted skill edits (check = leave out of commit)](https://linear.app/bearmancer/issue/BEA-381/uncommitted-skill-edits-check-leave-out-of-commit)
- [BEA-382 Engine rules: .env, .gitignore, self-approval, .git boundary, shell edits](https://linear.app/bearmancer/issue/BEA-382/engine-rules-env-gitignore-self-approval-git-boundary-shell-edits)
- [BEA-383 Retro improvements (check = adopt)](https://linear.app/bearmancer/issue/BEA-383/retro-improvements-check-adopt)
- [BEA-384 Old planning skills (check = disable after live run)](https://linear.app/bearmancer/issue/BEA-384/old-planning-skills-check-disable-after-live-run)
- [BEA-385 Rollout: merge, copy/link, push, post-purge review](https://linear.app/bearmancer/issue/BEA-385/rollout-merge-copylink-push-post-purge-review)
- [BEA-386 Hook evidence: capture payloads, proof rule, text fallback](https://linear.app/bearmancer/issue/BEA-386/hook-evidence-capture-payloads-proof-rule-text-fallback)
- [BEA-387 Live test & install gates: scratch run, dry-run, real install, hook path](https://linear.app/bearmancer/issue/BEA-387/live-test-and-install-gates-scratch-run-dry-run-real-install-hook-path)
- [BEA-388 Guard & format: .rigor blocking, anchor test, MultiEdit, checkpoints, worktree-root test](https://linear.app/bearmancer/issue/BEA-388/guard-and-format-rigor-blocking-anchor-test-multiedit-checkpoints)
- [BEA-389 Parked stages & Ctrl-key check](https://linear.app/bearmancer/issue/BEA-389/parked-stages-and-ctrl-key-check)
- [BEA-390 Review & install: round-2 review, reference reads, install location, live run, hook shapes](https://linear.app/bearmancer/issue/BEA-390/review-and-install-round-2-review-reference-reads-install-location)
- [BEA-391 Docs & scope: examples read, POSIX, memory note, handoffs](https://linear.app/bearmancer/issue/BEA-391/docs-and-scope-examples-read-posix-memory-note-handoffs)
- [BEA-392 Engine fixes: sha256, replace, writeLf, review-2 blockers, purge leftovers](https://linear.app/bearmancer/issue/BEA-392/engine-fixes-sha256-replace-writelf-review-2-blockers-purge-leftovers)
- [BEA-393 Docs & adapters: examples, POSIX, memory, handoffs, opencode adapter, Ctrl keys](https://linear.app/bearmancer/issue/BEA-393/docs-and-adapters-examples-posix-memory-handoffs-opencode-adapter-ctrl)
- [BEA-476 PLAN-52 · Source skills never read in full; OMO and opencode-slim never located](https://linear.app/bearmancer/issue/BEA-476/plan-52-source-skills-never-read-in-full-omo-and-opencode-slim-never)

<!-- ===== BEA-381 ===== -->

# Uncommitted skill edits (check = leave out of commit)
> Consolidated from the frozen local ledger · original ids: PLAN-34.01, PLAN-34.02, PLAN-34.03, PLAN-34.04.
>
**Row semantics:** Check = LEAVE OUT of the commit (recommended). Leave unchecked = decide by comment (revert or commit separately).
## Items
- [ ] **PLAN-34.01** · arr-api-reference/SKILL.md has an edit no agent here made (drops "General HTTP/API debugging and"); keep it uncommitted?
- [ ] **1. Leave out of commit (Recommended)** — Not plan-rigorously work; stays as an uncommitted change in the worktree.
``` one line changed: - "General HTTP/API debugging and PowerShell pitfalls go to shell-gotchas" + "PowerShell pitfalls go to shell-gotchas" No link to this task.
```
- [ ] **2. Revert it** — git restore the file to the committed text
``` Loses the edit for good.
```
- [ ] **3. Commit it** — Include it in a separate commit
``` It will ship with this branch.
```
- [ ] **PLAN-34.02** · ps-wizard/SKILL.md has an edit no agent here made (adds a shell-gotchas pointer line); keep it uncommitted?
- [ ] **1. Leave out of commit (Recommended)** — Not plan-rigorously work; stays as an uncommitted change in the worktree.
``` added after the title: "Shell commands failing, hanging, or quoting wrong ... see the shell-gotchas skill before debugging from scratch."
```
- [ ] **2. Revert it** — git restore the file to the committed text
``` Loses the edit for good.
```
- [ ] **3. Commit it** — Include it in a separate commit
``` It will ship with this branch.
```
- [ ] **PLAN-34.03** · shell-gotchas/SKILL.md has a big edit no agent here made (85 lines changed, new description); keep it uncommitted?
- [ ] **1. Leave out of commit (Recommended)** — Large rewrite from another session; not for this branch.
``` 43 lines added, 48 removed. New "Shell working patterns" section, new description, "[This shell tool only]" tags, dated notes trimmed. Looks like deliberate work by you or another agent.
```
- [ ] **2. Revert it** — git restore the file to the committed text
``` Loses the rewrite for good.
```
- [ ] **3. Commit it** — Include it in a separate commit
``` It will ship with this branch.
```
- [ ] **PLAN-34.04** · work-audit/SKILL.md has an edit no agent here made (2 lines added); keep it uncommitted?
- [ ] **1. Leave out of commit (Recommended)** — Not plan-rigorously work; stays as an uncommitted change in the worktree.
``` 2 lines added, none removed. No link to this task.
```
- [ ] **2. Revert it** — git restore the file to the committed text
``` Loses the edit for good.
```
- [ ] **3. Commit it** — Include it in a separate commit
``` It will ship with this branch.
```
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [Linear docs](<https://linear.app/docs>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-381/uncommitted-skill-edits-check-leave-out-of-commit](https://linear.app/bearmancer/issue/BEA-381/uncommitted-skill-edits-check-leave-out-of-commit)
- Identifier: BEA-381
- Status: Todo
- Priority: Medium - Assignee: Unassigned
- Labels: PLAN, Question
- Project: [plan-rigorously skill: review, merge, install](https://linear.app/bearmancer/project/plan-rigorously-skill-review-merge-install-190904d79fd9/overview).
- Created: 2026-11-14T06:35:44.703Z
- Updated: 2026-11-14T06:35:44.703Z

<!-- ===== BEA-382 ===== -->

# Engine rules: .env, .gitignore, self-approval, .git boundary, shell edits
> Consolidated from the frozen local ledger · original ids: PLAN-38.01, PLAN-38.02, PLAN-39, PLAN-40, PLAN-41.
> Answer each section: check exactly one option (or every applicable one when marked multi-select). Comment for anything else.
## PLAN-38.01 · Should a full plan be blocked from listing the exact file .env under Creates (wildcards are already refused)? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Block it (Recommended)** — .env is secrets; the light path already refuses it. Same rule for full plans.
``` T-3 - Creates: .env <- today: allowed After: refused with a message naming the risk pattern. config.json riskPatterns already matches .env; this applies it to exact Creates.
```
- [ ] **2. Allow it** — The user approves the whole plan anyway
``` An approved plan that names .env is an informed choice.
```
## PLAN-38.02 · Should a full plan be blocked from listing the exact file .gitignore under Creates? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Allow it (Recommended)** — Harmless and common; not in the risk patterns (only the .git folder is).
``` T-1 - Creates: .gitignore <- allowed today Adding .rigor/ to .gitignore is what the skill itself suggests in some projects.
```
- [ ] **2. Block it** — Treat like .env: refuse the exact name
``` Would also need a new risk pattern; blocks a normal task.
```
## PLAN-39 · Accept that a self-written "-> user: fine" line in
## Review satisfies the post-round-3 approval check? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Accept it (Recommended)** — Purge removed the answer-backing check; the threat model is accidents, not forgery.
``` F-9 [minor] "B-2 ..." -> user: fine Typed by the planner, passes check3 after round 3 with no question asked. Fix would be: require a recorded answer newer than the last review (~15 lines + tests), the code you told us to purge.
```
- [ ] **2. Restore the check** — Require a recorded non-reserved answer newer than the last review
``` Closes the hole; brings back one of the deleted engine parts.
```
## PLAN-40 · Keep the rule that only a .git FILE (worktree, submodule) is a boundary, and a nested .git folder is not? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Keep it (Recommended)** — Everything under the plan root needs the plan; worktrees stay independent.
``` project/ .rigor/ sub/.git/ folder -> inside the plan wt/.git file -> independent Write sub/x.ts in drafting: blocked. Write wt/x.ts: allowed.
```
- [ ] **2. Folder is a boundary too** — Any nested repo is independent
``` git init sub then lets every write in sub bypass the plan.
```
## PLAN-41 · Keep "no shell edits of project files during planning" as a text rule only, with no enforcement? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Text rule only (Recommended)** — Shell filters were bypassed in every review round; you ordered the purge.
``` echo x
> src/theme.ts in drafting Write/Edit tools: blocked. Shell redirect: allowed (text asks you not to). Enforcing needs a command parser that reviewers broke 4 times.
```
- [ ] **2. Block shell in planning** — Deny every Bash/PowerShell command until the build starts
``` Real enforcement, but reading commands (git, ls, tests) is needed for evidence.
```
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [Linear docs](<https://linear.app/docs>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-382/engine-rules-env-gitignore-self-approval-git-boundary-shell-edits](https://linear.app/bearmancer/issue/BEA-382/engine-rules-env-gitignore-self-approval-git-boundary-shell-edits)
- Identifier: BEA-382
- Status: Todo
- Priority: Medium - Assignee: Unassigned
- Labels: PLAN, Question
- Project: [plan-rigorously skill: review, merge, install](https://linear.app/bearmancer/project/plan-rigorously-skill-review-merge-install-190904d79fd9/overview).
- Created: 2026-11-14T06:35:44.900Z
- Updated: 2026-11-14T06:35:44.900Z

<!-- ===== BEA-383 ===== -->

# Retro improvements (check = adopt)
> Consolidated from the frozen local ledger · original ids: PLAN-37.01, PLAN-37.02, PLAN-37.03, PLAN-37.04, PLAN-37.05, PLAN-37.06, PLAN-37.07, PLAN-37.08, PLAN-37.09, PLAN-37.10, PLAN-37.11, PLAN-37.12, PLAN-37.13, PLAN-37.14.
>
**Row semantics:** Check = ADOPT the improvement. Leave unchecked = drop. Recommended defaults noted per row.
## Items
- [ ] **PLAN-37.01** · Retro 1: add the guard threat-model sentence to the design handoff too (it is already in plan-format.md)?
- [ ] **1. Skip, already there (Recommended)** — plan-format.md "The guard" states it, and the reviewers read that file.
``` plan-format.md line 143: "The guard stops accidental edits of .rigor. Deliberate evasion through the shell is out of scope." Done in the skill. Only the old handoff doc lacks it.
```
- [ ] **2. Add to handoff** — Copy the sentence into plan-rigorously-super-skill.md
``` Keeps the design record and the skill in step.
```
- [ ] **PLAN-37.02** · Retro 2: add a drift test that checks the risk-pattern lists in the text against config.json?
- [ ] **1. Yes, do it** — One test compares SKILL.md, plan-format.md and the denial text to config.json.
``` Risk list lives in 4 places: config.json, checks.mjs message, SKILL.md line 44, plan-format.md line 102 A test fails when one is edited alone.
```
- [ ] **2. No, drop it** — The guard examples that caused most drift are gone after the purge.
``` Before the purge ~30 findings were text vs engine mismatches, mostly guard examples. Those examples are deleted.
```
- [ ] **PLAN-37.03** · Retro 3: add a pre-commit hook in Dev/skills that runs the plan-rigorously tests before each commit?
- [ ] **1. Yes, do it** — Runs node --test plan-rigorously/tests/ (about 5 seconds) on every commit.
``` Repo has no package.json, no CI, no hook. The hook would run on commits for ALL skills in the repo, even unrelated ones, unless limited to staged plan-rigorously/ files.
```
- [ ] **2. No, drop it** — Tests stay a thing an agent must remember to run.
``` 183 tests, 5 seconds, run by hand.
```
- [ ] **PLAN-37.04** · Retro 4: probe whether execute-rigorously still works when a plan is live, since it keeps files under .rigor/?
- [ ] **1. Yes, do it (Recommended)** — Check .rigor/exec/wt and .rigor/plans against the new guard and plan layout.
``` plan-rigorously: one plan at .rigor/plan.md execute-rigorously (old): .rigor/plans/, worktree .rigor/exec/wt, run.yaml New guard blocks any shell command naming .rigor while a plan is live. Likely clash.
```
- [ ] **2. No, drop it** — Leave the clash unfound until it bites.
``` Both skills claim .rigor; nobody has checked them together.
```
- [ ] **PLAN-37.05** · Retro 5: make "report blocker and major only; a round with none ends the loop" the standing rule for review briefs?
- [ ] **1. Yes, do it (Recommended)** — Stops review loops chasing minors forever; saved as a feedback note.
``` Before: "try to BREAK each fix" -> reviewers always found something -> 4 loops. After: floor at major, stop when a round has none. Loop 3 text review: 5 minors + APPROVE = finished under this rule.
```
- [ ] **2. No, drop it** — Each brief sets its own bar.
``` Reviewers keep reporting minors and the loop only ends when you stop it.
```
- [ ] **PLAN-37.06** · Retro 6: resume the same two reviewers for later rounds ("verify these fixes, then look for new issues") instead of fresh ones?
- [ ] **1. Yes, do it** — Cuts the cost of a round roughly in half, but the reviewers are no longer fresh.
``` Cold start: 6 reviews x 170-210k tokens. Resumed: they already know the plan. Cost: a resumed reviewer remembers its own earlier verdict, so it is less independent.
```
- [ ] **2. No, drop it** — Every round uses new reviewers.
``` Full cost each round; maximum independence.
```
- [ ] **PLAN-37.07** · Retro 7: commit after every fix pass on the worktree branch, so reviewers can read a diff?
- [ ] **1. Yes, do it (Recommended)** — Small work-in-progress commits on worktree-plan-rigorously; squash later if wanted.
``` Before: skill stayed untracked for 5 review rounds; each reviewer re-read everything (~180k tokens). After: git diff <last-reviewed>..HEAD.
```
- [ ] **2. No, drop it** — Commits only when the work is done.
``` Reviewers re-read the whole skill.
```
- [ ] **PLAN-37.08** · Retro 8: make subagents write their reports to a file (for example .omc/research/) as well as handing back?
- [ ] **1. Yes, do it (Recommended)** — A restart finds the report with one ls; the hand-back filter cannot truncate it.
``` Seen: two reports lost for 6 hours with the session, and hand-backs replaced by "[harness: subagent output matched instruction-shaped pattern]".
```
- [ ] **2. No, drop it** — Reports live only in the hand-back.
``` A dead session loses the report.
```
- [ ] **PLAN-37.09** · Retro 9: spawn reviewers in-process, and check after 2 minutes that each made a first tool call?
- [ ] **1. Yes, do it (Recommended)** — Avoids tmux panes stuck on "Do you trust this folder?" (lost 4 hours once).
``` Before: reviewers sat on a trust prompt for 4 hours until you asked. After: in-process by default; a 2 minute check lists agents with no tool call.
```
- [ ] **2. No, drop it** — Keep tmux panes and manual checks.
``` A stuck pane stays invisible until you ask "Are you finished?".
```
- [ ] **PLAN-37.10** · Retro 10: when a 5-hour rate limit kills an agent, schedule a wakeup at the reset time and resume it?
- [ ] **1. Yes, do it (Recommended)** — The failure notice carries the reset time, so the resume can be automatic.
``` Seen 3 times: reviewers died at 05:48 and the session idled until you typed "Continue" at 17:18 (11+ hours).
```
- [ ] **2. No, drop it** — You type Continue yourself.
``` Work waits for you after every limit.
```
- [ ] **PLAN-37.11** · Retro 11: after spawning agents, always schedule one fallback wakeup that lists agents and reports any not running?
- [ ] **1. Yes, do it (Recommended)** — Covers silent stalls even when no error notice arrives.
``` Seen: nothing happened from 17:19 to 21:58 while the session said "waiting on reports". Fallback: one wakeup, list agents, report.
```
- [ ] **2. No, drop it** — No fallback check.
``` Silent stalls last until you notice.
```
- [ ] **PLAN-37.12** · Retro 12: split big jobs into three sessions (design, build, review) joined by handoff files?
- [ ] **1. Yes, do it** — Avoids the two context compactions this job hit; handoffs were good enough to restart.
``` One session did design, build and review: compacted twice, 30 question calls before any code. Split: design -> handoff -> build -> handoff -> review.
```
- [ ] **2. No, drop it** — Keep one long session.
``` Compaction can lose detail mid-job.
```
- [ ] **PLAN-37.13** · Retro 13: add a small tail-transcript script in \~/.local/bin and a pointer to it in your global CLAUDE.md?
- [ ] **1. Yes, do it** — Saves \~3 failed calls per transcript check; edits your CLAUDE.md pointer list.
``` Seen: python missing, then a one-off Node script to read a transcript tail. New: tail-transcript <session-id
> [n].
```
- [ ] **2. No, drop it** — Keep writing one-off scripts.
``` Each session rediscovers the same trick.
```
- [ ] **PLAN-37.14** · Retro 14: remove the injected hook lines "Use parallel execution" and "Verify changes work", which fire on nearly every call?
- [ ] **1. Yes, do it** — They changed nothing the agent did and cost tokens on every tool call.
``` Seen as hook context on almost every call: "Use parallel execution for independent tasks." "Verify changes work." They come from OMC hooks, not CLAUDE.md.
```
- [ ] **2. No, drop it** — Keep the reminders.
``` Small constant noise; may still help weaker models.
```
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [Linear docs](<https://linear.app/docs>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-383/retro-improvements-check-adopt](https://linear.app/bearmancer/issue/BEA-383/retro-improvements-check-adopt)
- Identifier: BEA-383
- Status: Todo
- Priority: Medium - Assignee: Unassigned
- Labels: PLAN, Question
- Project: [plan-rigorously skill: review, merge, install](https://linear.app/bearmancer/project/plan-rigorously-skill-review-merge-install-190904d79fd9/overview).
- Blocked by: BEA-385
- Created: 2026-11-14T06:35:45.140Z
- Updated: 2026-11-14T06:37:38.808Z

<!-- ===== BEA-384 ===== -->

# Old planning skills (check = disable after live run)
> Consolidated from the frozen local ledger · original ids: PLAN-44.01, PLAN-44.02, PLAN-44.03, PLAN-44.04, PLAN-44.05, PLAN-44.06.
>
**Row semantics:** Check = DISABLE once plan-rigorously passes its live run. Leave unchecked = keep for now. Comment 'forever' to keep permanently.
## Items
- [ ] **PLAN-44.01** · Disable the original wayfinder skill once plan-rigorously replaces it?
- [ ] **1. Keep for now (Recommended)** — Your rule: disable only after the new skill passes its checks.
``` wayfinder skill (in ~/.claude/skills and ~/.agents/skills) It stays active until the live run (PLAN-16.01) works.
```
- [ ] **2. Disable it** — Remove it from both skill folders once plan-rigorously is installed
``` wayfinder would no longer load; its job moves to plan-rigorously.
```
- [ ] **3. Keep it forever** — It does something plan-rigorously does not
``` Drop it from the replace list.
```
- [ ] **PLAN-44.02** · Disable the original grill-with-docs skill once plan-rigorously replaces it?
- [ ] **1. Keep for now (Recommended)** — Your rule: disable only after the new skill passes its checks.
``` grill-with-docs skill (in both skill folders) It stays active until the live run (PLAN-16.01) works.
```
- [ ] **2. Disable it** — Remove it from both skill folders once plan-rigorously is installed
``` grill-with-docs would no longer load; its job moves to plan-rigorously.
```
- [ ] **3. Keep it forever** — It does something plan-rigorously does not
``` Drop it from the replace list.
```
- [ ] **PLAN-44.03** · Disable the original to-spec skill once plan-rigorously replaces it?
- [ ] **1. Keep for now (Recommended)** — Your rule: disable only after the new skill passes its checks.
``` to-spec skill (in both skill folders) It stays active until the live run (PLAN-16.01) works.
```
- [ ] **2. Disable it** — Remove it from both skill folders once plan-rigorously is installed
``` to-spec would no longer load; its job moves to plan-rigorously.
```
- [ ] **3. Keep it forever** — It does something plan-rigorously does not
``` Drop it from the replace list.
```
- [ ] **PLAN-44.04** · Disable the original to-tickets skill once plan-rigorously replaces it?
- [ ] **1. Keep for now (Recommended)** — Your rule: disable only after the new skill passes its checks.
``` to-tickets skill (in both skill folders) It stays active until the live run (PLAN-16.01) works.
```
- [ ] **2. Disable it** — Remove it from both skill folders once plan-rigorously is installed
``` to-tickets would no longer load; its job moves to plan-rigorously.
```
- [ ] **3. Keep it forever** — It does something plan-rigorously does not
``` Drop it from the replace list.
```
- [ ] **PLAN-44.05** · Disable the OMC plan skill (oh-my-claudecode:plan) once plan-rigorously replaces it?
- [ ] **1. Keep for now (Recommended)** — Your rule: disable only after the new skill passes its checks.
``` Plugin skill; disabled through the plugin settings, not by deleting files.
```
- [ ] **2. Disable it** — Turn it off in the OMC plugin settings once plan-rigorously is installed
``` OMC autopilot may call plan; check that nothing depends on it first.
```
- [ ] **3. Keep it forever** — It does something plan-rigorously does not
``` Drop it from the replace list.
```
- [ ] **PLAN-44.06** · Disable the OMC ralplan skill (oh-my-claudecode:ralplan) once plan-rigorously replaces it?
- [ ] **1. Keep for now (Recommended)** — Your rule: disable only after the new skill passes its checks.
``` Plugin skill; disabled through the plugin settings, not by deleting files.
```
- [ ] **2. Disable it** — Turn it off in the OMC plugin settings once plan-rigorously is installed
``` ralplan is a keyword trigger in your CLAUDE.md; that line would need to go.
```
- [ ] **3. Keep it forever** — It does something plan-rigorously does not
``` Drop it from the replace list.
```
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [Linear docs](<https://linear.app/docs>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-384/old-planning-skills-check-disable-after-live-run](https://linear.app/bearmancer/issue/BEA-384/old-planning-skills-check-disable-after-live-run)
- Identifier: BEA-384
- Status: Todo
- Priority: Medium - Assignee: Unassigned
- Labels: PLAN, Question
- Project: [plan-rigorously skill: review, merge, install](https://linear.app/bearmancer/project/plan-rigorously-skill-review-merge-install-190904d79fd9/overview).
- Blocked by: BEA-387
- Created: 2026-11-14T06:35:45.452Z
- Updated: 2026-11-14T06:37:38.730Z

<!-- ===== BEA-385 ===== -->

# Rollout: merge, copy/link, push, post-purge review
> Consolidated from the frozen local ledger · original ids: PLAN-31.01, PLAN-31.02, PLAN-32, PLAN-90.
> Answer each section: check exactly one option (or every applicable one when marked multi-select). Comment for anything else.
## PLAN-31.01 · Merge branch worktree-plan-rigorously (1 commit, ab5f897) into main of Dev/skills? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Not yet (Recommended)** — Wait for the live run (PLAN-16.01) and the post-purge review (PLAN-90) first.
``` main e7cbc23
--------------- \ branch ab5f897 (skill, 35 files) Nothing has run live. Merging first means fixes land as extra commits on main.
```
- [ ] **2. Merge now** — Merge locally; no push
``` Skill appears on main in Dev/skills, still not installed anywhere.
```
- [ ] **3. Open a PR instead** — Draft pull request on GitHub, no direct merge
``` Public repo Bearmancer/skills; PR shows the diff to review first.
```
## PLAN-31.02 · Copy plan-rigorously/ to \~/.agents/skills and link it from \~/.claude/skills so Claude can load it? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Not yet (Recommended)** — Hooks are not installed, and the old planning skills are still active.
``` Today neither folder has plan-rigorously. Copying makes it appear in the skill list with no hooks behind it: the text says the system checks things it does not.
```
- [ ] **2. Yes, copy and link** — Copy to .agents/skills, link into .claude/skills
``` Other skills sit as real folders in both places; a link from .claude keeps one copy.
```
- [ ] **3. Copy to both** — Two real copies, no link
``` Matches how most skills are stored; two copies can drift apart.
```
## PLAN-32 · Push branch worktree-plan-rigorously to the public repo Bearmancer/skills? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Not yet (Recommended)** — Public and not live-tested; a pushed commit cannot be quietly taken back.
``` origin = github.com/Bearmancer/skills Public. Branch has no upstream yet. Push after the live run and the post-purge review pass.
```
- [ ] **2. Push the branch** — Push worktree-plan-rigorously only, not main
``` Visible to anyone; main untouched.
```
- [ ] **3. Never push** — Keep the skill local only
``` You said local only for state; this would keep the code local too.
```
## PLAN-90 · Run one independent review of the purged engine and text, reporting blocker and major findings only? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Yes, Sonnet reviewers (Recommended)** — Nobody has reviewed the code since the purge; two fresh Sonnet reviewers, one round, no minors.
``` Scope: scripts/lib (1,844 lines) + SKILL.md + references. 183 tests green. Report: blocker and major only. A round with none ends it. No Fable agents.
```
- [ ] **2. Skip** — Merge on the current state
``` Last review round was before the purge; the purge deleted ~420 lines unreviewed.
```
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [Linear docs](<https://linear.app/docs>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-385/rollout-merge-copylink-push-post-purge-review](https://linear.app/bearmancer/issue/BEA-385/rollout-merge-copylink-push-post-purge-review)
- Identifier: BEA-385
- Status: Todo
- Priority: Medium - Assignee: Unassigned
- Labels: PLAN, Question
- Project: [plan-rigorously skill: review, merge, install](https://linear.app/bearmancer/project/plan-rigorously-skill-review-merge-install-190904d79fd9/overview).
- Blocking: BEA-383
- Created: 2026-11-14T06:35:48.875Z
- Updated: 2026-11-14T06:35:48.875Z

<!-- ===== BEA-386 ===== -->

# Hook evidence: capture payloads, proof rule, text fallback
> Consolidated from the frozen local ledger · original ids: PLAN-14.01, PLAN-15, PLAN-10.07.
> Answer each section: check exactly one option (or every applicable one when marked multi-select). Comment for anything else.
## PLAN-14.01 · Capture real hook payloads (AskUserQuestion, Bash, PowerShell, PostToolUse) with a temporary logger in a scratch project? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Yes, scratch project (Recommended)** — A logger in that project only; your real settings.json is not touched.
``` scratch-project/.claude/settings.local.json hooks: PreToolUse + PostToolUse -> log.mjs log.mjs appends stdin to a temp file Then run one question, one Bash, one PowerShell, one WebFetch there and read the file. Settles four unknown shapes. Delete the scratch folder afterwards.
```
- [ ] **2. Use real settings** — Log in \~/.claude/settings.json for one session
``` Logs every tool call of every project until removed. Wider than needed.
```
- [ ] **3. Skip** — Keep guessing from docs
``` Docs do not give the AskUserQuestion response shape at all.
```
## PLAN-15 · Should proof.md say that a doc: or cmd: claim only counts if the main agent itself fetched or ran it? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Yes, add one line (Recommended)** — Unknown whether hooks see subagent calls; the line makes the rule safe either way.
``` proof.md line 22 today lets a lookup agent fetch the page. If hooks do not see subagent WebFetch, that claim can never pass and the planner loops. Add: "Fetch or run it yourself, not via a subagent."
```
- [ ] **2. Live test first** — Check with the captured payloads before touching the text
``` Same facts as PLAN-14.01 will answer it. Text stays unchanged until then.
```
- [ ] **3. Leave as is** — Accept the risk
``` A subagent-found citation may be refused with no clear reason.
```
## PLAN-10.07 · Keep the text-scraping fallback that reads answers from AskUserQuestion output (claude-code.mjs line 550)? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Keep for now (Recommended)** — The real response shape is unverified, so the fallback may be the only reader.
``` extractAnswers reads two ways: 1. resp.answers object (structured) 2. text "question"="answer" (fallback) If the real tool only sends text, removing (2) means no answer is ever recorded and Sign intent is blocked forever.
```
- [ ] **2. Remove it** — Only structured answers count; text answers are ignored
``` Safer against forged answers, but breaks everything if the real shape is text only. Verify the shape first.
```
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [Linear docs](<https://linear.app/docs>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-386/hook-evidence-capture-payloads-proof-rule-text-fallback](https://linear.app/bearmancer/issue/BEA-386/hook-evidence-capture-payloads-proof-rule-text-fallback)
- Identifier: BEA-386
- Status: Todo
- Priority: Medium - Assignee: Unassigned
- Labels: PLAN, Question
- Project: [plan-rigorously skill: review, merge, install](https://linear.app/bearmancer/project/plan-rigorously-skill-review-merge-install-190904d79fd9/overview).
- Blocking: BEA-390
- Created: 2026-11-14T06:35:49.003Z
- Updated: 2026-11-17T02:29:32.455Z
## Comments - Lance: Recorded 2026-11-17 — real hook payloads captured live (scratch project, real settings untouched, logger hook on all events, one claude -p session):
* PreToolUse: session_id, transcript_path, cwd, prompt_id, permission_mode, effort, hook_event_name, tool_name, tool_input, tool_use_id.
* PostToolUse adds tool_response, duration_ms.
* UserPromptSubmit: prompt_id, permission_mode, prompt.
* SessionStart: source. Stop: stop_hook_active, last_assistant_message, background_tasks, session_crons.
* Shell tool fires as BOTH names on this host: echo via Bash, Get-Content via PowerShell (tool_name literally PowerShell) — dual matcher required and validated.
* Hook env does NOT inherit arbitrary parent env vars; discriminate events via hook_event_name in the payload, not custom env tags. Evidence: events.jsonl + scratch at AppData\\Local\\Temp\\opencode\\hook-capture. AskUserQuestion not yet triggered (-p mode is non-interactive); left open.

<!-- ===== BEA-387 ===== -->

# Live test & install gates: scratch run, dry-run, real install, hook path
> Consolidated from the frozen local ledger · original ids: PLAN-16.01, PLAN-16.02, PLAN-33, PLAN-94.
> Answer each section: check exactly one option (or every applicable one when marked multi-select). Comment for anything else.
## PLAN-16.01 · Run the skill once in a scratch git repo with its hooks enabled, to see it work for real? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Yes, scratch repo (Recommended)** — Hooks go in that repo's settings.local.json via install.mjs --settings; nothing global changes.
``` node install.mjs --settings <scratch>/.claude/ settings.local.json Then: /plan-rigorously on a toy ask. Check: plan file, Sign intent block, status notes, reviewer gate. The skill has never run live yet.
```
- [ ] **2. Not yet** — Merge and install without a live run
``` Risk: first real use finds the problems in your real projects.
```
## PLAN-16.02 · Run install.mjs --dry-run against your real \~/.claude/settings.json to preview the hook entries? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Yes, dry run (Recommended)** — Prints the resulting file and writes nothing.
``` node install.mjs --dry-run Shows the exact JSON that would be added for PreToolUse, PostToolUse, UserPromptSubmit, SessionStart. No file is changed, no .bak made.
```
- [ ] **2. No** — Do not even preview
``` Install stays unseen until you decide.
```
## PLAN-33 · Install the plan-rigorously hooks into your real \~/.claude/settings.json (writes the file, keeps one .bak)? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Not yet (Recommended)** — Preview with PLAN-16.02 and live-test in a scratch repo first.
``` Once installed, EVERY project you open gets these hooks: a shell command naming .rigor is blocked while a plan is live. install.mjs --uninstall removes them.
```
- [ ] **2. Yes, install now** — Add hooks for all projects
``` Skill gets enforced everywhere; first live run happens in a real project.
```
- [ ] **3. Per project only** — Never global; use each project settings.local.json
``` Safer blast radius; one install step per project.
```
## PLAN-94 · Where should the plan-rigorously hook path in settings.json point, given the worktree folder is removed later? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. \~/.agents/skills copy (Recommended)** — Stable path. Needs the copy step (PLAN-31.02) first. It was the first option in the cut-off prompt.
``` settings.json hook command -> ~/.agents/skills/plan-rigorously/... survives: worktree removal, repo moves needs: PLAN-31.02 (copy the skill there)
```
- [ ] **2. Dev/skills main checkout** — Stable once the branch is merged (PLAN-31.01). Breaks if the repo folder moves.
``` settings.json hook command -> ~/Dev/skills/plan-rigorously/... survives: worktree removal needs: PLAN-31.01 (merge to main)
```
- [ ] **3. Worktree folder** — Works today. The hook fails silently once the worktree is removed.
``` settings.json hook command -> Dev/skills/.claude/worktrees/ plan-rigorously/... dead path after worktree removal; a missing hook fails open
```
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [Linear docs](<https://linear.app/docs>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-387/live-test-and-install-gates-scratch-run-dry-run-real-install-hook-path](https://linear.app/bearmancer/issue/BEA-387/live-test-and-install-gates-scratch-run-dry-run-real-install-hook-path)
- Identifier: BEA-387
- Status: Todo
- Priority: Medium - Assignee: Unassigned
- Labels: PLAN, Question
- Project: [plan-rigorously skill: review, merge, install](https://linear.app/bearmancer/project/plan-rigorously-skill-review-merge-install-190904d79fd9/overview).
- Blocking: BEA-384
- Created: 2026-11-14T06:35:49.247Z
- Updated: 2026-11-17T02:29:33.820Z
## Comments - Lance: Recorded 2026-11-17 — live scratch test + install preview, both green: 1. install.mjs --dry-run: prints 'Would change C:\\Users\\Lance.claude\\settings.json; resulting file' and writes nothing; existing hooks (question-gate, question-shape, prefs-inject) preserved, not replaced. PLAN-49 confirmed live: registered hook path points at the extraction dir — install must run from the final merged location. New observation: plan-rigorously hooks run via bare 'node' while every existing hook uses absolute C:/Users/Lance/.bun/bin/bun.exe — PATH dependency risk. 2. Engine live (hooks wired into scratch .claude/settings.json only): bare 'path: light' plan write → blocked with the format template (invalid stage); valid light plan → accepted with status note; shell command naming .rigor → PreToolUse deny with the guard message; Read of .rigor/plan.md via file tools → allowed; innocent command → unaffected. Cross-session guard works (second claude -p session was also blocked). Evidence: AppData\\Local\\Temp\\opencode\\hook-capture.

<!-- ===== BEA-388 ===== -->

# Guard & format: .rigor blocking, anchor test, MultiEdit, checkpoints, worktree-root test
> Consolidated from the frozen local ledger · original ids: PLAN-93, PLAN-91, PLAN-92, PLAN-43, PLAN-12.02.
> Answer each section: check exactly one option (or every applicable one when marked multi-select). Comment for anything else.
## PLAN-93 · Keep blocking every shell command that names .rigor during a live plan, even ls .rigor or a git commit message? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Keep blocking (Recommended)** — Simple, matches the purge; the block message says to use file tools.
``` Live plan, checked today: cat .rigor/plan.md -> denied ls .rigor -> denied git commit -m "fix .rigor/x" -> denied Set-Content */state/x -> allowed A false stop costs one retry with a Read or a reworded message.
```
- [ ] **2. Only block writes** — Allow read-looking commands such as ls and cat
``` Needs a command parser to tell read from write: the machinery reviewers broke 4 times and you ordered purged.
```
## PLAN-91 · Keep the anchor test (destination sentence, first three decisions, one anchor) as text guidance only? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Text only (Recommended)** — It is judgement, and checks on wording are easy to game.
``` interview.md line 7 already says: "this test is your own judgement: the system does not check it". Same for lines 5-21. The engine cannot tell a good destination sentence from a bad one. Not in the plan-format.md list; labelled inline instead.
```
- [ ] **2. Check that it exists** — Engine requires the three items to be non-empty before Sign intent
``` Cheap check, but only tests presence, not quality.
```
## PLAN-92 · Add MultiEdit to the tools the write guard watches (today only Write, Edit, NotebookEdit; its input shape is undocumented)? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Yes, add it (Recommended)** — Else MultiEdit can write project files during planning with no check.
``` WRITE_TOOLS = Write, Edit, NotebookEdit + MultiEdit Guard would read file_path like Edit. Docs call MultiEdit "legacy"; the shape stays unverified until PLAN-14.01.
```
- [ ] **2. No** — Treat it as legacy and unsupported
``` Current Claude Code may not even offer the tool.
```
## PLAN-43 · The plan format has no checkpoint field; keep
## Checkpoints as a free-text section the checker ignores? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Keep free text (Recommended)** — Simplest. Task text already says to read
## Checkpoints and report at them.
```
## Checkpoints - After T-2: run the full test suite Not parsed, not enforced. after-approval.md step 7 tells the agent to report there.
```
- [ ] **2. Add a task field** — Checkpoint: line per task, checked by the engine
``` More structure; one more field for the parser and tests.
```
- [ ] **3. Remove the idea** — Delete mentions of checkpoints from the text
``` Fewer concepts; no report points.
```
## PLAN-12.02 · Add a test that a plan whose root is itself a linked worktree (its .git is a file) still governs writes in that root? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Yes, add test (Recommended)** — Code looks right, but no test has a root whose .git is a file; this repo is such a root.
``` findRoot (state.mjs:116) walks up from a path. At a folder holding .rigor AND a .git FILE it must stop there and return that folder. tests today: makeRepo uses a .git FOLDER; only a nested wt/.git file is tested. A change to the file-vs-folder check would keep all 183 green.
```
- [ ] **2. No** — Leave it untested
``` Works today by reading the code; plan roots in worktrees (like this one) stay unproven.
```
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [Linear docs](<https://linear.app/docs>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-388/guard-and-format-rigor-blocking-anchor-test-multiedit-checkpoints](https://linear.app/bearmancer/issue/BEA-388/guard-and-format-rigor-blocking-anchor-test-multiedit-checkpoints)
- Identifier: BEA-388
- Status: Todo
- Priority: Medium - Assignee: Unassigned
- Labels: PLAN, Question
- Project: [plan-rigorously skill: review, merge, install](https://linear.app/bearmancer/project/plan-rigorously-skill-review-merge-install-190904d79fd9/overview).
- Created: 2026-11-14T06:35:49.799Z
- Updated: 2026-11-16T17:13:32.579Z
## Comments - Lance: Recorded: worktree-root test (PLAN-12.02) — forgo tests (Lance, interview 2026-11-16). The N1 junction and 8.3 short-name roots are already covered by the round2-fixes tests; a plan root that is itself a linked worktree is not a real shape on this rig.

<!-- ===== BEA-389 ===== -->

# Parked stages & Ctrl-key check
> Consolidated from the frozen local ledger · original ids: PLAN-21.01, PLAN-21.02, PLAN-21.03, PLAN-22.
> Answer each section: check exactly one option (or every applicable one when marked multi-select). Comment for anything else.
## PLAN-21.01 · Keep the opencode adapter parked (not started; plugin event names unverified)? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Keep parked (Recommended)** — Claude adapter is not live-tested yet; a second adapter doubles what is unproven.
``` Order: Claude adapter live test -> merge -> then opencode.
```
- [ ] **2. Drop it** — Remove opencode from the plan entirely
``` Design record would lose its second adapter goal.
```
- [ ] **3. Start it next** — Verify opencode event names, then build
``` Needs ~/.config/opencode inspected (never done) and docs read.
```
## PLAN-21.02 · Keep the execute stage inside plan-rigorously parked (the separate execute-rigorously skill exists)? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Keep parked (Recommended)** — You said "do not add execution stuff into planning".
``` plan-rigorously: plan only (+ ticks). execute-rigorously: carries it out. Two skills, no overlap built.
```
- [ ] **2. Drop it** — Remove the execute stage from the design
``` Leaves execution fully to execute-rigorously.
```
## PLAN-21.03 · Keep a separate post-build review stage parked (not started)? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Keep parked (Recommended)** — Plan-time review is built; a post-build one adds more engine to prove.
``` Built: two reviewers on the plan. Parked: review of the finished code.
```
- [ ] **2. Drop it** — Remove it from the design
``` Use code-review skills afterwards.
```
## PLAN-22 · Which of Ctrl+A, Ctrl+E, Ctrl+K fail in a foreground claude tab (not the background session)? *(multi-select: check every option that applies)*
## Options
- [ ] **1. Ctrl+A** — Line start does not work
- [ ] **2. Ctrl+E** — Line end does not work
- [ ] **3. Ctrl+K** — Kill to end of line does not work
- [ ] **4. All three work** — None fail in a foreground tab
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [Linear docs](<https://linear.app/docs>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-389/parked-stages-and-ctrl-key-check](https://linear.app/bearmancer/issue/BEA-389/parked-stages-and-ctrl-key-check)
- Identifier: BEA-389
- Status: Todo
- Priority: Medium - Assignee: Unassigned
- Labels: PLAN, Question
- Project: [plan-rigorously skill: review, merge, install](https://linear.app/bearmancer/project/plan-rigorously-skill-review-merge-install-190904d79fd9/overview).
- Created: 2026-11-14T06:35:53.064Z
- Updated: 2026-11-14T06:35:53.064Z

<!-- ===== BEA-390 ===== -->

# Review & install: round-2 review, reference reads, install location, live run, hook shapes
> Consolidated from the frozen local ledger · original ids: PLAN-50, PLAN-48, PLAN-49, PLAN-16, PLAN-14, PLAN-15.
> Tasks: check each box when its real effect is verified; comment the result. Issue Done when all boxes are checked.
## Tasks
- [ ] **PLAN-50** · Round-2 review of plan-rigorously never completed (killed three times: usage limit, trust prompt, restart). Rerun the engine review and the skill-text review with 2 Sonnet agents; build is in the worktree, 154 of 154 tests passed on 2026-11-10 (from chat d8eb0d62 before deletion) · added 2026-11-12 by claude-code
- [ ] **PLAN-48** · Read interview, map, spec, proof, design and tasks reference files end to end; the final review only grepped them · added 2026-11-12 by claude-code
- [ ] **PLAN-49** · Run install.mjs from the final merged location, never from the worktree, because the hook path comes from the script path · added 2026-11-12 by claude-code
- [ ] **PLAN-16** · Skill has never run in a live session; `install.mjs` never run on real settings
- [ ] **PLAN-14** · Real shapes of PostToolUse, AskUserQuestion, Bash, NotebookEdit, MultiEdit hook payloads
- [ ] **PLAN-15** · Whether PostToolUse records subagent WebFetch and shell calls
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [Linear docs](<https://linear.app/docs>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-390/review-and-install-round-2-review-reference-reads-install-location](https://linear.app/bearmancer/issue/BEA-390/review-and-install-round-2-review-reference-reads-install-location)
- Identifier: BEA-390
- Status: Todo
- Priority: Medium - Assignee: Unassigned
- Labels: PLAN, Task
- Project: [plan-rigorously skill: review, merge, install](https://linear.app/bearmancer/project/plan-rigorously-skill-review-merge-install-190904d79fd9/overview).
- Blocked by: BEA-386
- Created: 2026-11-14T06:35:53.284Z
- Updated: 2026-11-17T03:15:06.429Z
## Comments
- Lance: Round-2 skill-text review (PLAN-50) done 2026-11-17, reviewer read frozen branch worktree-plan-rigorously @ ab5f897. Verdict: MERGEABLE-WITH-FIXES. Blocker: 1. A one-file job in a risky area skips the whole skill. [SKILL.md:43](<http://SKILL.md:43>) says one-file jobs need no plan; [SKILL.md:44](<http://SKILL.md:44>) says risky areas force the full path (also [plan-format.md:98](<http://plan-format.md:98>)). Fix: exempt one-file jobs only when they are outside a risky area. Major: 2\. The double-quote ban clashes with findings and claims that must quote text in previews ([review.md:80/89/101](<http://review.md:80/89/101>)), so approval answers can't be recorded. 3\. 'Round' means two different things ([review.md:82](<http://review.md:82>) vs 83/86). 4\. 'You never record an answer' ([SKILL.md:24/83](<http://SKILL.md:24/83>)) vs 'write the answers into the plan' ([interview.md:35](<http://interview.md:35>)). 5\. The project root is undefined when .git is a file (linked worktree). 6\. Risk patterns don't match the text: only auth-shaped paths are caught (login/signin/permissions/rbac are not), uv.lock is missing, and three risk lists differ. 7\. Nothing makes reviewers read-only: no prompt says 'do not edit'. 8\. A plan file deleted by hand mid-build has no recovery path. 9\. Nothing stops two sessions building the same plan. Minor (10-17): task-less closes log done; map.md asks a question before writing the skeleton; the no-shell-edit rule covers planning only; Batch: wide-refactor is self-declared and missing from the unchecked list; full→light downgrade undefined; transitive Creates: undefined; the stop-and-ask rule needs two different approaches; round-2 independence can't be met as worded. Note: the [review.md:16](<http://review.md:16>) '(Not checked by the system.)' edit is NOT in the branch. It was an uncommitted worktree edit and was lost when the worktree was pruned. Engine review still running.
- Lance: Round-2 engine review (PLAN-50) done 2026-11-17 on the frozen branch at ab5f897. Verdict: MERGEABLE-WITH-FIXES. Blocker:
* F1, install.mjs:11: HOOK_PATH comes from the script's own location. Installing from a worktree or temp copy registers a dead path. A hook that can't start is a non-blocking error, so every gate fails open without warning. Fix: refuse to install from tmpdir or a worktree, add a --hook-path option, and set onFailure: block on PreToolUse. Major:
* F2, claude-code.mjs:328: the shell guard keys on state.json, not plan.md. A plan created through the shell leaves the guard off until the first answer. Fix: gate on the plan file instead.
* F3, claude-code.mjs:601: approval and sign-off are recorded in postAsk without re-running check1/2/3, so another session can swap the plan in between. Also, withLock runs unlocked after 4 s (state.mjs:187). Fix: re-run the checks before recording.
* F4, checks.mjs:157: cmd: proofs ignore the exit code, so a failed command satisfies a claim. Fix: exclude entries with a non-zero exitCode. Minor:
* F5: the shell matcher misses .rigor after an opening paren and the RIGOR\~1 short name.
* F6: the quote ban only exists in the skill text. One stray double quote silently drops every text-fallback answer. Fix: deny reserved-header questions containing quotes in preAsk.
* F7: yes() is a prefix match, so 'yes, but…' and 'yesterday' approve.
* F8: the shell guard only covers the cwd root.
* F9: Monitor is missing from SHELL_TOOLS (version-dependent).
* F10: a corrupted state.json reviews field fails the review gate open (self-corrects later). Leftovers: writeLf is present and cosmetic. The unused test exports are now all used. Verified sound: path normalization (junction, 8.3, case, dots), payload shapes, node+args exec form, idempotent install and dry-run, and the state machine. - Lance: Ruling 2026-11-17 (Lance, ticked item by item): all 31 round-2 items kept. Engine: F1-F10, the writeLf cleanup, and a new item adding REPL to the PreToolUse matcher for Code Mode. Skill text: findings 1-17, the restored [review.md:16](<http://review.md:16>) '(Not checked by the system.)' note, and documentation of the install guard. Note: the real finding count is 27 (10 engine + 17 text), not 34 as I said earlier. The fixer lanes are implementing them in worktree-plan-rigorously. REPL will be added after the engine lane reports. Nothing is committed yet. - Lance: Round-2 fixes landed 2026-11-17: commit e650b2d on branch worktree-plan-rigorously, pushed. Engine F1-F10 and writeLf done. Skill text 1-17 done, plus the [review.md:16](<http://review.md:16>) note. Tests: node --test plan-rigorously/tests/ gives 183/183 before and after. No new tests were added; 5 existing test files were adjusted where the behaviour changed (F1, F3, F7, F9). Not done, waiting on the owner: the REPL matcher (it would block Code Mode reads of plan.md), and documenting the install guard (no install section exists in the skill text). Two engine-lane interpretations to ratify: (1) F1 accepts an explicit --hook-path without validating it; (2) under F7, free-text Yes answers count only when they match an offered label. PLAN is parked; merge to main and install are not done.

<!-- ===== BEA-391 ===== -->

# Docs & scope: examples read, POSIX, memory note, handoffs
> Consolidated from the frozen local ledger · original ids: PLAN-17, PLAN-18, PLAN-19, PLAN-20.01, PLAN-20.02.
> Answer each section: check exactly one option (or every applicable one when marked multi-select). Comment for anything else.
## PLAN-17 · Have idea-refine/examples.md read in full and compared with plan-rigorously text (only \~50 of 400 lines were read)? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Yes, read it all (Recommended)** — Your rule is full reads; this file was only skimmed when interview.md was written.
``` Today: first example only. A full read checks that interview.md did not miss a technique from the other 350 lines, then reports gaps as small items.
```
- [ ] **2. No** — Accept the partial read
``` Gaps in interview.md would stay unknown.
```
## PLAN-18 · Should POSIX/Linux behaviour of the engine be tested now, or declared Windows-only? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Declare Windows-only (Recommended)** — All paths run on Windows; 8.3 and junction tests skip elsewhere. Say so in SKILL.md.
``` Today: foldCase and 8.3 handling are win32 only; nothing was ever run on POSIX. One sentence in SKILL.md: "Tested on Windows only."
```
- [ ] **2. Test on POSIX** — Run the 183 tests under WSL or Git Bash on Linux
``` Finds real POSIX failures but costs a setup and a fix pass.
```
- [ ] **3. Neither** — Leave unstated
``` A Mac or Linux user finds out by failure.
```
## PLAN-19 · Update memory note plan-rigorously-handoff.md, which still says "nothing built"? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Rewrite it (Recommended)** — State: built, 183 tests green, committed on worktree-plan-rigorously, not merged or installed.
``` Now: "design complete ... nothing built" After: "built and committed (ab5f897) on branch worktree-plan-rigorously; 183 tests; not merged, not installed" The MEMORY.md index line is updated to match.
```
- [ ] **2. Delete it** — Remove the note and its index line
``` Facts live in the repo and git log.
```
- [ ] **3. Leave stale** — Do nothing
``` Next session believes nothing exists.
```
## PLAN-20.01 · Mark handoff plan-rigorously-super-skill.md (says "nothing built", step 7 stale) as superseded? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Add header note (Recommended)** — One line at the top: built; see the repo. File kept as the design record.
``` Top of file gets: SUPERSEDED: built 2026-11-11, see Dev/skills worktree plan-rigorously. Design record only; section 7 is stale.
```
- [ ] **2. Delete file** — Remove the handoff
``` Loses the confirmed design decisions (section 4a).
```
- [ ] **3. Leave** — Do nothing
``` A future session may restart the build.
```
## PLAN-20.02 · Mark handoff plan-rigorously-build-spec.md (build steps all done) as superseded? *(click exactly one option; comment for anything else)*
## Options
- [ ] **1. Add header note (Recommended)** — One line at the top: engine built, 183 tests. Hook facts appendix stays useful.
``` Top of file gets: SUPERSEDED: engine and planning stage built; appendix (hook facts) still valid.
```
- [ ] **2. Delete file** — Remove the build spec
``` Loses the hook-facts appendix.
```
- [ ] **3. Leave** — Do nothing
``` The spec still reads as a to-do list.
```
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [Linear docs](<https://linear.app/docs>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-391/docs-and-scope-examples-read-posix-memory-note-handoffs](https://linear.app/bearmancer/issue/BEA-391/docs-and-scope-examples-read-posix-memory-note-handoffs)
- Identifier: BEA-391
- Status: Todo
- Priority: Medium - Assignee: Unassigned
- Labels: PLAN, Question
- Project: [plan-rigorously skill: review, merge, install](https://linear.app/bearmancer/project/plan-rigorously-skill-review-merge-install-190904d79fd9/overview).
- Created: 2026-11-14T06:35:53.469Z
- Updated: 2026-11-14T06:35:53.469Z

<!-- ===== BEA-392 ===== -->

# Engine fixes: sha256, replace, writeLf, review-2 blockers, purge leftovers
> Consolidated from the frozen local ledger · original ids: PLAN-45, PLAN-46, PLAN-47, PLAN-10, PLAN-12.
> Tasks: check each box when its real effect is verified; comment the result. Issue Done when all boxes are checked.
## Tasks
- [ ] **PLAN-45** · Remove unused sha256 export and its createHash import in scripts/lib/state.mjs (lines 68 and 7), then re-run the 183 tests · added 2026-11-12 by claude-code
- [ ] **PLAN-46** · Remove the redundant .replace(/\\/g,"/") at scripts/lib/claude-code.mjs:324 · added 2026-11-12 by claude-code
- [ ] **PLAN-47** · writeLf at scripts/lib/state.mjs:198 is cosmetic-only; tidy or leave · added 2026-11-12 by claude-code
- [ ] **PLAN-10** · Engine review 2 from first chat (`cc-d8eb0d62-sub-aengine-review-2-236043b933c`): N1 blocker 8.3 short name `RIGOR~1`, N2, N3, N6, N7
- [ ] **PLAN-12** · Fixer deliberately left unfixed in purge: F1, F4, F6, N1 to N3, N4 test, F3/N5, F5, Edge
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [Linear docs](<https://linear.app/docs>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-392/engine-fixes-sha256-replace-writelf-review-2-blockers-purge-leftovers](https://linear.app/bearmancer/issue/BEA-392/engine-fixes-sha256-replace-writelf-review-2-blockers-purge-leftovers)
- Identifier: BEA-392
- Status: Todo
- Priority: Medium - Assignee: Unassigned
- Labels: PLAN, Task
- Project: [plan-rigorously skill: review, merge, install](https://linear.app/bearmancer/project/plan-rigorously-skill-review-merge-install-190904d79fd9/overview).
- Created: 2026-11-14T06:35:53.834Z
- Updated: 2026-11-14T06:35:53.834Z

<!-- ===== BEA-393 ===== -->

# Docs & adapters: examples, POSIX, memory, handoffs, opencode adapter, Ctrl keys
> Consolidated from the frozen local ledger · original ids: PLAN-17, PLAN-18, PLAN-19, PLAN-20, PLAN-21, PLAN-22.
> Tasks: check each box when its real effect is verified; comment the result. Issue Done when all boxes are checked.
## Tasks
- [ ] **PLAN-17** · `idea-refine/examples.md`: about 50 of 400 lines read by the text writer
- [ ] **PLAN-18** · Non-Windows behaviour (POSIX, 8.3 names, junctions)
- [ ] **PLAN-19** · Memory note `plan-rigorously-handoff.md` still says "nothing built"
- [ ] **PLAN-20** · Two handoff docs (`handoff-build-spec.md`, `handoff-super-skill.md` in this folder) are stale against the worktree
- [ ] **PLAN-21** · Opencode adapter, execute stage, review stage: parked, not started
- [ ] **PLAN-22** · Ctrl-key lookup: one docs agent interrupted, one answer cut off. Test Ctrl+A, Ctrl+E, Ctrl+K in a foreground tab
## References Provenance: `C:/Users/Lance/.claude/ledger/epics/` (frozen archive); original ids above. [Linear docs](<https://linear.app/docs>)
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-393/docs-and-adapters-examples-posix-memory-handoffs-opencode-adapter-ctrl](https://linear.app/bearmancer/issue/BEA-393/docs-and-adapters-examples-posix-memory-handoffs-opencode-adapter-ctrl)
- Identifier: BEA-393
- Status: Todo
- Priority: Medium - Assignee: Unassigned
- Labels: PLAN, Task
- Project: [plan-rigorously skill: review, merge, install](https://linear.app/bearmancer/project/plan-rigorously-skill-review-merge-install-190904d79fd9/overview).
- Created: 2026-11-14T06:35:56.955Z
- Updated: 2026-11-14T10:31:35.878Z
## Comments - Lance: PLAN-20 fact for the next worker (claude-code, 2026-11-14): both handoff docs were read in full and their work done / work left is now in the "PLAN · Done archive" document, section "Handoffs 2026-11-10". What is stale in them: the "nothing built" status, the "create the worktree" step, section 7 step 1 of the design record ("ask the section 4 questions": all answered in 4a), and the 154/183/184 test counts (the suite is 22 tests since 2026-11-13). What is still the only full copy: the build contract itself (plan.md parser rules, state hashes, stage table, per-hook behaviour, hook facts appendix) and the source-skill table of the design record. Those live only in the frozen archive at `epics/plan-rigorously-skill/`. They were not copied into Linear verbatim; decide that before the archive folder is deleted. The `chats/handoff-plan-rigorously-*.md` pair are digests of these two files, not copies.

<!-- ===== BEA-476 ===== -->

# PLAN-52 · Source skills never read in full; OMO and opencode-slim never located The design handoff of 2026-11-10 lists source skills that were judged from their descriptions only. Lance's rule is that a skill is judged only after its full directory is read. No existing issue covers this (PLAN-17 covers `idea-refine/examples.md` only; PLAN-48 covers the skill's own reference files).
## Tasks
- [ ] Read in full (SKILL.md and every attached file), then note what each adds to the planning stage, or "nothing": OMC `sharpen`, `in-your-own-words`, `loft`, `arena`, `launch`
- [ ] Same for the user-level skills: `research`, `code-review`, `setup-matt-pocock-skills`, `context-engineering`, `code-review-and-quality`, `debugging-and-error-recovery`
- [ ] Locate OMO and opencode-slim planning skills on this machine (`~/.config/opencode` was never inspected), or record that they do not exist
## Acceptance criteria
- [ ] Each skill above has a one-line verdict recorded as a comment here
- [ ] Any doctrine worth taking is listed as a proposed edit to the plan-rigorously text, not applied
## References
* Source: `epics/plan-rigorously-skill/handoff-super-skill.md` section 5, last paragraph, and section 3 of its digest `chats/handoff-plan-rigorously-super-skill.md` (frozen archive). Added 2026-11-14 by claude-code while assimilating the handoffs.
* Skill paths at the time: `C:\Users\Lance\.agents\skills\`, `C:\Users\Lance\.claude\plugins\cache\omc\oh-my-claudecode\5.8.3\skills\`.
## Metadata
- URL: [https://linear.app/bearmancer/issue/BEA-476/plan-52-source-skills-never-read-in-full-omo-and-opencode-slim-never](https://linear.app/bearmancer/issue/BEA-476/plan-52-source-skills-never-read-in-full-omo-and-opencode-slim-never)
- Identifier: BEA-476
- Status: Todo
- Priority: Low - Assignee: Unassigned
- Labels: PLAN, Task
- Project: [plan-rigorously skill: review, merge, install](https://linear.app/bearmancer/project/plan-rigorously-skill-review-merge-install-190904d79fd9/overview).
- Created: 2026-11-14T10:31:33.673Z
- Updated: 2026-11-14T10:31:33.673Z

