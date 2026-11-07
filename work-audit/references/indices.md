# Indices, records and known false positives

Loaded from SKILL.md when resolving findings; the steps there are the workflow.

## Resolving the extended indices

- Own repos end with nothing dirty, untracked, unpushed, stashed or merged but undeleted (1, 2, 11).
- `third_party` (index 2) means the origin owner is not in `WORK_AUDIT_OWNERS` (`;` or `:` separated) or the `gh api user` login. Third-party clones and `duplicate_origin` groups are reported; touching them is a question-tool decision.
- `open_issues` and `open_prs` are counts; with `gh_errors` set, that repo's counts are missing.
- Plans (3): `executed` (`Remaining items: 0`, all boxes checked, or `status: done`), `open` (unchecked boxes or pending/blocked status, counted in 17), `unknown`.
- Index 4 also lists top-level entries of home folders in `config_roots` of `scripts/work-audit.toml`, minus `allow` (override: `WORK_AUDIT_CONFIG_FILE`).

## The 21 indices

Grouped by the phase `state-report.py` prints them under (`PHASES`). The number is the record key; the short name is the script's own (`INDICES`). Full definitions follow under Definitions.

Tags: `[judgment]` the script counts and the `verify` record decides (finished = files with evidence, not verified = the rest, skipped = tests identified but not run, left = not verified plus open questions); `[hint]` the line starts `proxy:` and ends `-> record <index> required`, and the record decides (tracked secrets in 21 stay a hard defect); `[purge]` the findings go to the deletion pass; `[purge, owner]` they go only as OWNER rows the owner releases. Untagged checks are mechanical: the script's count is the answer.

Purge routing is the only deletion path: hand the report to `purge-safety`'s adapter. The routing, 4 -> 15 -> 16 order, flags and engine are defined once in `purge-safety/SKILL.md` §6.

### Phase 1: repo state

1. git status
2. branches/worktrees/stashes
3. tool state

### Phase 2: clutter

4. stale artifacts `[purge]`
5. handoffs and wizards
6. empty dirs `[purge]`
7. duplicates `[purge, owner]`

### Phase 3: tests

7. tests present
8. tests run
9. tests deleted
10. skipped `[judgment]`

### Phase 4: work status

3. plan files
4. other files deleted
5. left `[judgment]`
6. finished `[judgment]`
7. unfinished

### Phase 5: verification

14. not verified `[judgment]`
15. small commits to squash

### Phase 6: docs and sprawl

19. doc mismatches `[hint]`
20. doc sprawl `[hint]`
21. repo sprawl vs style `[hint]`

## Definitions

1. git status: `dirty`, `untracked` per repo.
2. branches/worktrees/stashes, unpushed, merged-undeleted; `third_party` flag, duplicate-origin groups.
3. plan files, classified `executed`, `open`, `unknown`.
4. stale artifacts: zero-byte files (except `__init__.py`, `.gitkeep`, `.keep`, `py.typed`), `*.tmp`/`*.bak`/`*.orig`, `__pycache__`, gitignored untracked entries older than 24h (not `node_modules`, never secret-named files), each with `safety` facts; plus home config roots. Purge: hand to purge-safety (rules in `SKILL.md` §6).
5. handoffs and wizards: files named `handoff*`, `wizard*`, `runbook*`.
6. tool state: versions found on PATH (git, gh, uv, node, python via uv, dotnet, cargo, go, npm), manifests (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`) without a lockfile.
7. tests present.
8. tests run: pytest cache records only, no test is run.
9. tests deleted.
10. other files deleted.
11. left: `unpushed`, `dirty`, `untracked`, `open_issues`, `open_prs` (`gh_status`; `gh unavailable` when gh is absent or unauthenticated).
12. skipped: `skip`/`xfail`/`pytest.skip` and `.skip`/`.only` markers in changed test files.
13. finished.
14. not verified.
15. empty dirs, with `safety` facts. Purge: hand to purge-safety (rules in `SKILL.md` §6).
16. duplicates: identical files and identical same-name dirs, with `safety` facts. Purge: purge-safety adapter OWNER rows via `--include-duplicates`; keeper is a question-tool decision (rules in `SKILL.md` §6).
17. unfinished.
18. small commits to squash.
19. doc mismatches.
20. doc sprawl.
21. repo sprawl vs style: reviewers check the repo's own style docs (CLAUDE.md, AGENTS.md, CONTEXT.md, README, CONTRIBUTING, `docs/standards*`, `.claude/plans/specs/*`), flag rules that conflict and apply the newest, asking through the question tool only when truly ambiguous.

## Records

`<state>/records/<repo>-<shorthash>/<tree>/<index>.json` (index `19`, `20`, `21` or `verify`), shape `{index, repo, tree, head, files_read[], findings[{path, claim, evidence, severity, fixed}], samples[{id, status, evidence}], verdict, checked_at}`. `tree`, `head` and `checked_at` are stamped by `uv run $SKILL_DIR/scripts/record.py write`. Verdicts: `pass`, `fail`, `unverifiable`.

- Any `fixed: false` finding forces `fail`.
- `unverifiable` needs a sample marked unverifiable with a reason; it goes to the question tool.
- A pass with no findings still needs `files_read` holding every required file and every sampled id with a status and path:line evidence on a line with the sampled token.
- `fixed: true` is accepted only when the previous record for the same index and repo held the same path and claim as `fixed: false` and the finding carries `rechecked: true`.
- `verify` evidence per file is `{kind: test, cmd, exit}` (`write` re-runs `cmd` and compares the exit code) or `{kind: review, record}`.
- A failed external call (gh, git, network, a missing agent) is a finding quoting the exact error text, never 'no results' or '0 open PRs' (index 11 `gh_errors`, timeout findings).

Line-checked samples are the only proof a reviewer read the files.

## Known false positives

- Index 19 path refs resolve against the doc's repo, the skill dir holding it, `~/` and absolute paths. Placeholders, runtime-created files, paths relative to another tool's root and files in other repos get flagged; the 19 reviewer classifies each, and a doc changes only for a truly wrong reference.
- Index 9, 10 count tracked deletions in the window, including intended refactors.
- Index 15: a dir a tool recreates at startup returns after removal, so leave it.
- Index 16 duplicates include vendored or mirrored copies; a mirror is intended, a stray copy is not.
- Index 17 matches the words TODO/skip in docs that describe rules; read the hit before acting.
