---
name: work-audit
description: "Use when a task ends, before reporting done, committing or pushing, or on 'status' and 'what is left'. Always, even for small edits: scans touched repos for 21 indices and writes the final report."
---

# Work audit

Shell commands failing, hanging, or quoting wrong (PowerShell, git-bash, Bun.$): see the `shell-gotchas` skill before debugging from scratch.

End-of-task audit. Resolve every finding in the same turn: fix the mechanical ones, ask the decisions. Decisions go ONLY through the question tool (`AskUserQuestion`), never prose: 2-4 options, recommended first, each naming the goal, problem, and trade-offs. Before proposing any deletion, state the folder's `safety` facts (the purge indices in the canonical index table; index 11 `counts` for a whole repo); describe it from those facts.

`$SKILL_DIR` is the directory holding this SKILL.md. Scripts in `$SKILL_DIR/scripts/` run only through `uv run`, enforced by `scripts\uv-guard.py` (register `uv run <skill dir>\scripts\uv-guard.py` as a PreToolUse hook). They need Python 3.12+, git and nothing else; `gh` is used only when present and authenticated (`WORK_AUDIT_NO_GH` turns it off).

## Scope

The repos the session touched, derived structurally:

- the working directory's repo;
- every git repo root named by paths in the session transcript's tool inputs (`file_path`, `path`, `cwd`, `workdir`, `notebook_path`, `-C <dir>` and `cd <dir>` in shell commands, the cwd on entries);
- `--roots` / repo arguments passed explicitly, and the env var `WORK_AUDIT_ROOTS` (`os.pathsep`-separated); a folder that is not a repo is searched for repos;
- a linked worktree counts as its own repo plus its main repo.

`uv run $SKILL_DIR/scripts/state-report.py` without `--roots` audits the cwd repo. Pass `--transcript <file.jsonl>` (state-report.py or record.py) to add the repos the session touched; the Stop hook reads the transcript itself. A session that touched several repos from a neutral cwd passes `--roots repo-a repo-b`. Other repos under `WORK_AUDIT_ROOTS` (default `~/Dev`) are only listed (1) and duplicate-origin checked (2).

Hook: `uv run $SKILL_DIR/scripts/stop-guard.py` as a Stop hook. It acts only when the final message starts a line with `Result:` or `Remaining items:`, and passes when `stop_hook_active` is set or the turn used no tools. Otherwise it blocks when touched repos changed since the last audit and the turn did not run `state-report.py`. A third block on the same state is let through and logged under `unresolved` in `audited.json`. It does not check records: `uv run $SKILL_DIR/scripts/record.py check` verifies they exist and pass. Without the hook, the agent runs this skill itself at task end.

## Steps

1. Report: `uv run $SKILL_DIR/scripts/state-report.py --json`. It prints the 21 indices and writes every finding unsampled to `<state>/records/<repo>-<shorthash>/<tree>/report.json`; `<state>` is `.work-audit-state` under `WORK_AUDIT_STATE_DIR` (default home). Flags: `--roots <dirs>`, `--transcript <file>`, `--since 24h|7d|2w`, `--brief` (summary lines only), `--quiet-if-unchanged` (same tree hash and findings as the previous run: prints `unchanged since <time>` instead of the report). Exit 1 means a hard defect (tracked secret, index 21) or unfinished work (17, 18). Exit 2 means bad usage or an unreadable report or record.
2. Bounds: git and `gh` calls time out at 30s (`WORK_AUDIT_SUBPROCESS_TIMEOUT`), test re-runs in `record.py write` at 900s (`WORK_AUDIT_TEST_TIMEOUT`), each index at 20s plus 1s per repo (`WORK_AUDIT_INDEX_TIMEOUT` sets it flat), file listing at 20000 files or 4000 per repo, whichever is larger (`WORK_AUDIT_MAX_FILES` sets it flat); files over 1 MB are not read. Per-repo git and `gh` calls, file reads and hashing run on 16 threads (`WORK_AUDIT_WORKERS`). The first cap hit stops the scan: exit 3, the stop reason and a narrowing `--roots` command on stderr, and the partial report marked `truncated` and incomplete, which `record.py` refuses. Fix the cause, narrow the roots or raise the cap, then rerun. `subprocess_timeouts` (index 6) lists spawns that timed out; `ERROR` means that index failed. Scope: discovery never walks the system temp dir below a root (purge-safety's `purge.py` clears it by age) and names it as `not scanned` in index 1; a root inside temp is still scanned. The gh list calls start when the report begins and run beside the git indices. Expected runtimes on this host: cwd repo about 6s (accepted target: median 6 s over 3 runs, #131), `~/Dev` (5 repos) about 14s, the whole home folder (about 15 repos) about 1 min.
3. Brief: `uv run $SKILL_DIR/scripts/record.py brief [repo...]` prints a JSON array with one brief per repo: required record indices, `required_files`, seeded samples (claims, flagged refs, doc pairs, files) and the previous run's open findings. The seed is the repo's tree hash, so samples cannot be re-rolled.
4. Review: spawn one reviewer subagent per changed repo, prompt from [references/review-briefs.md](references/review-briefs.md) (load it only now). Reviewers only read; fixes go to executors; each writes one JSON per required index and runs `uv run $SKILL_DIR/scripts/record.py write <json> <repo path>` until it accepts.
5. Fix: every finding with `fixed: false` goes to an executor subagent; mechanical defects are fixed directly. Small unpushed commits (index 18) with no issue reference are squashed (`git reset --soft <upstream>`, one commit) before pushing; pushed history stays as is.
6. Re-check: rerun it (`--quiet-if-unchanged` is fine), then reviewers only for pairs whose repo tree changed (the previous record carries over, so a finding becomes `fixed: true` only after a reviewer re-checked it). Then `uv run $SKILL_DIR/scripts/record.py check [repo...]`: when every required pair of a repo passes, its baseline moves to the current tree and older tree folders are deleted.
7. Round cap: two fix rounds per (index, repo) pair; what is still failing goes to the owner through the question tool.
8. **Purge, the deletion pass, last and in one place:** indices 4 (stale artifacts), 15 (empty dirs) and optionally 16 (duplicates) are resolved only by handing `report.json` to `purge-safety`'s adapter and engine; never an ad-hoc delete. Routing, flags, age gates, owner rows and the 4 -> 15 -> 16 order are defined once in `purge-safety/SKILL.md` §6. Hand it the report and the repo; it returns the manifest and the plan/apply result. The report stays the finding source.
9. Final report.

Tiers: every spawn names a tier (not a vendor id) (`medium` reviewers, `light` fixes, `heavy` whole-diff/final review); unmapped is a loud failure.

Skill tests: `uv run --no-project --with pytest --with pytest-xdist python -W error -m pytest -q -n auto -p no:cacheprovider` in the skill folder. Slow suite? `uv run $SKILL_DIR/scripts/bench.py [suite]` ranks per-file/per-test costs with bottleneck causes.

Offline audit: `uv run $SKILL_DIR/scripts/offline-audit.py [--owners owners.json] [--json]` walks the home folder's agent and dev folders read-only and ranks every repo with local-only state (dirty entries, stashes, local-only branches, unpushed commits) and every untracked plan, draft, scratch or notes folder; `--owners` maps path prefixes to tickets, and an UNOWNED item exits 1.

Test-authoring audit: `uv run $SKILL_DIR/scripts/test-audit.py [repo]` flags per-test setup, unmocked tool probes, timeout/sleep simulation, duplicated helpers, slow tests without `# bench:` evidence, weak asserts, count drift and shared state; details in [references/test-audit.md](references/test-audit.md). Resolve each finding in the same turn.

Commit, push and squash do not change the tree; a fix in repo A does not invalidate repo B. The first run has no baseline: the changed set is the last 24 hours plus porcelain status.

## Detail

[references/indices.md](references/indices.md) holds how to resolve each extended index, the 21 indices grouped by the phase `state-report.py` prints them under (with judgment, hint and purge tags) and their definitions, the record shape and rules, and the known false positives. Read it when a finding needs resolving or a record is written.

## Final report

First line `Remaining items: N`: N is 0, or the count of open decisions, which then goes to the question tool. Then one line per index, numbered 1 to 21, each with a count and a pointer; skip lines already reported unchanged. Lines 11-14, 19, 20 and 21 take counts from the records. Index 17 must read none: unfinished work is finished or open; say "finished" only at N = 0.

Empty-catch gate: [references/empty-catch-gate.md](references/empty-catch-gate.md) (run when auditing eval/scratch code)

Sprawl gate: [references/sprawl-gate.md](references/sprawl-gate.md) (rules, both exemption mechanisms with their reasons, verdict table; read before changing `scripts/sprawl-gate.py` or `scripts/sprawl-gate.toml`)
