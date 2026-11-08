# Assimilation method

How the five source packs (omo, omc, matt-pocock, addyosmani, superpowers) get replaced by the `<verb>-rigorously` skills without guessing.

## What "done" means

Every piece of every source skill has exactly one recorded answer, and a script has checked that. Not "I read them and they look covered".

A **unit** is the smallest structural piece of a source file: a frontmatter field, a heading, a paragraph, one list item, one table row, a code block, or a whole bundled script. The pieces are cut so that putting them back together gives the original file, byte for byte. Unit ids are `<source>:<skill>/<file>#<seq>`, so they stay unique across packs.

## The procedure, per source pack

1. **Claim the skills.** `sources.json` lists which skill folders belong to each pack and which installed skills are out of scope. `node assimilation/enumerate.mjs claims` fails if any installed skill folder is unclaimed or claimed twice.
2. **Enumerate.** `node assimilation/enumerate.mjs build <source>` writes `assimilation/units/<source>.jsonl` (regenerated on demand, git-ignored).
3. **Verify the cut.** `node assimilation/enumerate.mjs verify <source>` re-reads the disk and proves: units are contiguous (no gap, no overlap), they reassemble to the exact bytes, and no file was added or removed since the build.
4. **Answer every unit.** One file per skill, `assimilation/answers/<source>/<skill>.jsonl`. A `range` lets one answer cover a run of consecutive units; the checker still counts each unit.
5. **Check.** `node assimilation/check.mjs [sources] [--skill a,b]` fails until every unit of the selected skills has exactly one answer from the closed vocabulary below, and every reference (across all packs) resolves.
6. **Build, then check again.** Once the target skills exist, `check.mjs --build <skills-dir>` also requires each absorbed section to exist as a heading in the built skill.
7. **Cluster.** When every pack passes step 5, group the absorbed units by target. Where a group has no home in `lanes.json`, add a lane.

## The answer vocabulary

| Answer | Meaning | Extra fields |
| --- | --- | --- |
| `absorbed` | The idea lives in a rigorous skill | `to: {skill, section}`; skill must be in `lanes.json` |
| `duplicate` | Same text as a unit that is absorbed | `of: <unit id>` (single unit only) |
| `dropped` | Deliberately not carried over | `why`: `noise`, `runtime`, `boilerplate`, `example-only`, `superseded`, `out-of-scope`; `note` required except for `boilerplate`; `ref` (single unit, must be absorbed) required for `superseded`, optional for `example-only`, forbidden otherwise |

## Standing decisions (from the user)

- Questions are always asked as a whole round, up front, through the question tool; never one at a time.
- Examples and noise are enumerated first, then dropped. Noise means plugin-specific admin or display skills (hud, omc-setup, configure-notifications).
- The stop-hook adapter counts each refusal to let the agent stop as a failure and lets it stop on the 3rd.
- The old `rigorous-*` skills are deleted once their replacements exist and pass; nothing is deleted before then.
- No upstream-change tracking. Execution is last in the sequence.
- Lanes: planning, research, review, debugging, execute, visualize, version-control, sweep, init, core (all named `<verb>-rigorously`, except core, the shared driver). No build, design, ship, frontend, browsing, API or release lane. init-rigorously (preparing a project for agents: the AGENTS.md hierarchy, repo conventions) is the last skill to be built, after execute-rigorously.
- visualize-rigorously covers diagrams, HTML pages and other visuals, not frontend frameworks.
- version-control-rigorously collects the git-centered skills (git-workflow-and-versioning, using-git-worktrees, finishing-a-development-branch, git-master, project-session-manager); plan and execute point to it at commit and branch steps.
- sweep-rigorously covers all GitHub work: sweeping, PR creation, PR review, issue creation. Inputs: the user's github-sweep and github-create, omc harbor, pr and project-session-manager, matt triage and pr. It is built in Node and asks everything up front like the rest.
- TDD is on by default in planning, with a flag to turn it off.
- All work, including incremental work, lives in planning and execute only.
- Design is part of planning: by task scope, planning routes into an architecture flow.
- Dropped for now: frontend, browsing, API, release.
- CI and tests in the skills repo were purged on 2026-11-08 (user decision). Verification is the `verify` and `check` commands above.

## What the scripts prove, and what they cannot

Proved: nothing was skipped (coverage), nothing was lost in the cut (reassembly), no installed skill is unclaimed, answers use only allowed words, and every reference points at a real unit that is itself absorbed.

Not proved: that an answer is wise. Whether two differently worded rules mean the same thing is a judgement. The scripts force that judgement to be written down per unit and checked for consistency. Only exact repeats inside one pack are auto-detected (`dupOf` in the unit list); repeats across packs are found by whoever answers.

## Where it stands

| Pack | Skills | Units | Answered | Skills fully answered |
| --- | --- | --- | --- | --- |
| addyosmani | 25 | 3,416 | 599 | 5 |
| mattpocock | 30 | 1,638 | 0 | 0 |
| omc | 48 | 5,236 | 1,399 | 7 |
| omo | 27 | 37,378 | 27,061 | 6 |
| personal (inputs to sweep-rigorously) | 2 | 561 | 0 | 0 |
| superpowers | 14 | 3,162 | 0 | 0 |
| **total** | | **51,391** | **29,059** | |

All packs reassemble exactly. All 118 installed skill folders are claimed once (43 out of scope: vendor and personal skills; 4 old rigorous skills; github-create and github-sweep are inputs).

Dropped so far by user decision: omo frontend (entirely, pending an assessment of its visuals content), browser, ultimate-browsing; addyosmani frontend-ui-engineering, browser-testing-with-devtools, api-and-interface-design (for now), shipping-and-launch; omc release. Dropped as noise: omc hud, omc-setup, configure-notifications, omc-doctor, skill, cancel; omo onboarding, give-me-tips, lsp-setup.

## Findings

- `test-driven-development` exists in both addyosmani and superpowers; only one folder is installed (addyosmani's), so it is claimed once. Superpowers' own copy is not on disk.
- omo `frontend` is 24,968 of 50,830 units (brand design-system reference files); how to treat it is a user decision.
- Unit counts are dominated by list items and table rows; ranges keep the answer files small.

## Not covered yet

Cross-pack exact-duplicate detection does not exist. There are no tests for these scripts (purged by user decision).
