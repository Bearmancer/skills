# Body layouts

The repo's template or issue form decides headings and fields, verbatim. These layouts apply only when it has none. Depth bar: https://github.com/code-yeongyu/oh-my-openagent/issues/6167 (prerequisites, mechanism, numbered repro, expected vs actual, doctor output, raw logs, config, root cause with suggested fix, OS and version).

Code is cited as a permalink pinned to the indexed SHA (`https://github.com/<o>/<r>/blob/<sha>/<path>#L<a>-L<b>`) with the quoted lines beside it; describe behavior by type, function and contract so the text survives renames.

Every shape carries a **Counterfactual ledger** and an **Environment** block:

| hypothesis | prediction | control run | outcome |
| ---------- | ---------- | ----------- | ------- |

## Issue

- Observed failure: what was run, what happened, what was expected (separate lines).
- Mechanism: responsible code quoted at the permalink, what it does, why that is wrong for this input, the divergent value.
- Repro: numbered, minimal, replayable.
- Evidence: verbatim command output, side-by-side values, never a log summary.
- Fix direction: the function and what a correct fix needs.
- Linked PR: `Linked PR #<n>` on its own line for every existing PR covering the mechanism — required whenever one exists, even when this run files nothing; an issue body that hides its PR is a defect.

## Feature issue

Problem (who is blocked, which job fails), Current behavior (permalink plus verbatim demo), Desired behavior (edge cases and errors), Proposal, Out of scope, Acceptance criteria (`- [ ]`, each independently verifiable and failing at base), Prior art (2+ primary links, one line each), the workaround tried and why it fails, **PR status** (`planned in this pass` until the PR exists, then `#<n>`; `blocked by <reason>` only for: no push or fork rights, private code, maintainer wants proposals only, diff cannot narrow to reviewable scope).

## PR

When the repo's PR template has no fitting heading, use these three sections, skipping preambles and keeping prose brief:

- **Summary:** the smallest view that makes the key point clear: pseudocode for logic, a call tree for runtime flow, a component or file tree for structure, a Mermaid diagram for interaction, or a `diff` block when the point is what changes.
- **Evidence:** a before and after. A screenshot is best for visual changes; otherwise the verbatim output or the exact test that now fails and then passes.
- **Merge Danger:** the door (one-way if the change is destructive or hard to reverse, else two-way) and the blast radius in one word, with the ramifications that matter (layout shift, consumer breakage, mobile).

Every PR body also carries:

- `Fixes #<n>` or `Related #<n>` on its own line (`Closes` only when every acceptance item is met);
- Scope: each file, why it is in, what is left out;
- Test evidence: command, verbatim output, the fail-before and pass-after pair, and the live run of the fix against the reported scenario (SKILL.md step 8);
- the base SHA, short.

## Update

Append; never rewrite the reporter's words. Add the missing material under the template's own heading — minimal repro, mechanism with a SHA-pinned permalink, verbatim evidence, environment. No matching heading → append `## Update (<date>)` with the new material, keeping the original body intact. For a PR, add commits and update Evidence and Test evidence to the new head; keep `Fixes #<n>`. Where an issue covers the same mechanism and a PR exists either way, the issue body gains or keeps `Linked PR #<n>` in the same pass — existing issues always link existing PRs. Re-run `preflight.py check` on the edited body before `gh issue edit`/`gh pr edit`.

## Environment

Software facts only, never hardware, hostname, username or token.

- OS: caption, version, build, architecture, verified. Windows: `Get-CimInstance Win32_OperatingSystem` (`19045` is Win10 22H2, `22000+` is Win11). Linux: `uname -srm` and `/etc/os-release`.
- App version, plugin names and versions, runtimes the repro touches, every binary the repro names with its version, `gh --version`, `git --version`.
- Config excerpt, relevant keys verbatim.
- Logs: at least one verbatim repro line showing the divergent value, with its path.

## URL audit

The procedure has one home: the rigorous-research `SKILL.md`, section "URL audit: single home for all skills" — `uv run <rigorous-research dir>/scripts/urlaudit.py <url>... | -f <body file>` over every drafted body and comment, only a final `200 OK` passes, and the exemptions, the BLOCKED and JS? re-check and the repair-or-drop with `[link unverified]` are stated there. This skill adds three things to it:

- A GitHub URL that comes back `BLOCKED` is re-checked authenticated — `gh api repos/<owner>/<repo>/...` for the resource, or `gh pr|issue view` for one of your own — before it counts as broken, because a plain fetch is rate-limited on GitHub, not dead there. `gh api` proves the resource exists; the body still cites the `github.com/...` link.
- A code permalink carries the full 40-hex SHA (line 5): `preflight check` warns when a markdown-template body has no permalink, fails the fallback layout when it has none, and counts neither a short SHA nor a `commit/` link.
- The audit is a stop, not a note: SKILL.md steps 5 and 10 file only when every URL passed, and an edited body (Update above) re-runs it before `gh issue edit` or `gh pr edit`.
