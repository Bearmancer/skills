# Reviewer briefs

One reviewer subagent per changed repo, spawned at tier `medium` (a whole-diff or final review is `heavy`, mechanical fixes `light`; never a vendor model id, and an unmapped tier is a failure to report, not a default). Give the reviewer that repo's entry from the `uv run $SKILL_DIR/scripts/record.py brief` output plus the brief text for each index in `required`. Reviewers never edit repo files. Each writes one JSON file per required index, then runs `uv run $SKILL_DIR/scripts/record.py write <json> <repo path>` (`$SKILL_DIR` is the directory holding SKILL.md; `path` is in the brief) and fixes the record until `write` accepts it. Do not fill `tree`, `head` or `checked_at`; `write` stamps them.

## Common rules

- Record shape: `{index, repo, files_read[], findings[{path, claim, evidence, severity, fixed}], samples[{id, status, evidence}], verdict}`. `verdict` is `pass`, `fail` or `unverifiable`. `severity` is `low`, `medium` or `high`. Evidence is `path:line` relative to the repo (or absolute).
- `files_read` must contain every file in `required_files`.
- Every sampled id from the brief gets one entry in `samples` with a status and evidence. The line at the evidence must contain the sampled token; a PowerShell parameter `-Name` also matches its `$Name` declaration. A claim whose name the code builds rather than spells (`f"{P}_{n}_{d}.ris"` writes `TA_2_unclear.ris`) is `traced`: evidence is the non-doc line that builds it, plus a `reason` saying how; it counts as finished. `unverifiable` needs a `reason` field and sends the item to the question tool.
- Any finding with `fixed: false` means verdict `fail`. A finding is `fixed: true` only when the previous record (`previous_findings` in the brief) held the same `path` and `claim` as `fixed: false`, you re-checked it in the current files, and you set `rechecked: true`. Keep every previous open finding in the new record.
- Read `report` (the `report.json` path in the brief) for the unsampled mechanical findings instead of scanning again.
- Before a finding proposes deleting anything, state what the folder actually holds: `files`, `uncommitted` and `unpushed` from its `safety` entry in `report` (indices 4, 15, 16), or `dirty`, `untracked` and `unpushed` from index 11 `counts` for a whole repo. Never describe it from its name.
- A failed external call is a finding quoting the exact error text, never 'no results' or '0 open PRs'.
- A decision for the owner goes only through the question tool, in plain terms: the goal, the problem, and what each option changes.

## Brief 19: doc mismatches

You are reviewing documentation accuracy in repo `<repo>`. Inputs: the brief's index 19 `required_files`, `samples` (kind `ref` and kind `claim`) and `inputs.report_19`.

1. For each `ref` sample (a path or ADR reference the mechanical check flagged), open the doc line and decide the status: `broken` (the reference is wrong and the doc needs a fix), `placeholder` (an example name, not meant to exist), `runtime-created` (a file created when the tool runs), or `other-repo` (exists in another repo or root). Evidence is the `doc:line` that contains the reference. Every `broken` ref also gets a finding with `fixed: false`.
2. For each `claim` sample (a backticked identifier, flag, environment variable or config key from a changed doc), check that it exists in code or config with the same meaning. Status `ok` needs evidence in a file other than the doc, on a line containing the token. Status `missing` or `mismatch` needs evidence at the doc line and a finding with `fixed: false`.
3. Read the changed docs and check them for contradictions with other docs in the repo. Each contradiction is a finding with both locations in the claim.
4. List every file you opened in `files_read`.

## Brief 20: doc sprawl

You are reviewing documentation sprawl in repo `<repo>`. Inputs: `inputs.report_20` (markdown files outside allowed homes, files over 300 lines, duplicate H1 titles), the `changed_md` list in `inputs`, and `samples` of kind `pair` (the markdown pairs with the highest H2-heading overlap).

1. Is each concept in exactly one place? A concept in two docs is a finding.
2. Is any stub, superseded doc or handoff outside a plan folder? Each is a finding.
3. For each `pair` sample decide `duplicate` (the same content in two places) or `distinct` (different content under the same heading). Evidence is two refs separated by a semicolon, `a:line; b:line`, each line containing the sampled heading. Every `duplicate` pair also gets a finding with `fixed: false`. Ignore text inside `SHARED:START`/`SHARED:END` markers in generated mirrors.
4. List every file you opened in `files_read`.

## Brief 21: repo sprawl vs style

You are reviewing the changes in repo `<repo>` against the repo's own rules, whatever they are: read the repo's own docs and apply what they say (language and tooling bans, layout, naming, banned commands, file-placement rules). Inputs: `style_docs` (the repo's CLAUDE.md, AGENTS.md, CONTEXT.md, README, CONTRIBUTING, docs/standards* and .claude/plans/specs/* that exist), the changed files in `inputs.changed_files`, and `samples` of kind `file`.

1. Read every style doc. List the checkable rules in the record's `rules` array as `<verbatim quote>@<doc path>:<line>`, at least one per style doc that exists (for a README, any line that states a usage or contribution rule). The quote must appear on that line.
2. Check every changed file against every rule. Each violation is a finding with `fixed: false`.
3. Is any changed file a near-copy of a sibling file (same extraction shape, same table)? Is any changed file outside the repo's documented layout? Each is a finding.
   Where owner rules conflict (two docs, or a doc and a later instruction), record a finding quoting both and apply the newest. Ask through the question tool only when truly ambiguous, and then mark the sample `unverifiable`.
4. For each `file` sample set `conforms` or `violates` with evidence `path:line` in that file.
5. List every file you opened in `files_read`.

## Brief verify: judgment parts of indices 11-14

You are establishing what was finished and verified in repo `<repo>`. Inputs: `required_files` (the changed non-doc files).

1. For each changed file give one evidence entry in `evidence[]`: `{file, kind: "test", cmd, exit}` for a test command you ran (the command runs with the repo as working directory; `write` re-runs it and compares the exit code), `{file, kind: "review", record}` where `record` is `19`, `20` or `21` and that record's `files_read` holds the file, or `{file, kind: "unverifiable", reason}`.
2. `tests_identified[]` lists every test command that exists for these files, run or not.
3. `open_questions` is the number of decisions still open.
4. Counts are derived by `write`: finished = files with evidence, not verified = the rest, skipped = tests identified but not run, left = not verified + open questions. Verdict `pass` needs not verified, skipped and left all at 0; otherwise record the gap as a finding with `fixed: false` and verdict `fail`.
5. List every file you opened in `files_read`.

## Valid example (index 21)

```json
{
	"index": "21",
	"repo": "demo",
	"files_read": ["CLAUDE.md", "app.py"],
	"rules": ["Keep one module per concept@CLAUDE.md:4"],
	"findings": [],
	"samples": [{ "id": "f1", "status": "conforms", "evidence": "app.py:1" }],
	"verdict": "pass"
}
```
