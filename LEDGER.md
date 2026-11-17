# Ledger — Dev\Skills

Assimilated 2026-11-17 from the frozen archive `C:\Users\Lance\.claude\ledger\epics\`. Settled decisions and durable facts only; open questions stayed in the archive.

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