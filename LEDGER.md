# Ledger - Dev\Skills

## ledger/epic split, rigorous-research CLI-only, review fixes (2026-11-20T09:40+05:30)
Goal: one diagnostic event-log skill (`ledger`) and one plan skill (`epic`); rigorous-research routes through CLIs and env-var keys only; fix every finding of the two-axis + bug review.
Concern: skills
Purpose: build
Started: 2026-11-20T09:40+05:30
Status: done

### Established facts
- [F1] `.agents\skills\{ledger,epic}` and `.claude\skills\{ledger,epic}` are junctions to this repo - source: `Get-Item -Force` LinkType Junction - 2026-11-20
- [F2] Key pools come from `## <Service>` sections of `~/.secrets/.env`, which mirror Bitwarden Secrets Manager names `<SERVICE>_<ACCOUNT>`; zenrows and tinyfish have no pool - source: `switch_api_key.py --service all --list`, `bws secret list` (names only) - 2026-11-20
- [F3] CLI key precedence: firecrawl, tinyfish, tavily, brightdata take the env var over a stored login; zenrows takes `~/.zenrows/secrets.json` over `ZENROWS_API_KEY` (`@zenrows/cli/dist/src/core/auth.js:4`); apify reports "token source: APIFY_TOKEN environment variable" with no `~/.apify/auth.json` - source: CLI sources + `apify info` - 2026-11-20
- [F4] just-scrape reads `SGAI_API_KEY`, not `SCRAPEGRAPH_API_KEY` - source: `rg process.env` over the just-scrape package - 2026-11-20
- [F5] The installed `browse` (`~/.local/bin/browse.exe`) is a Chrome-extension relay with no `open` command - source: review bug hunt probe - 2026-11-20

### Attempts
- [A1] 2026-11-20 executed: `muse skills validate ledger|epic --json` after each rewrite - outcome: success, valid, 0 diagnostics.
- [A2] 2026-11-20 executed: `uv run scripts/gen_routing_table.py` then `--check` - outcome: success, exit 0 - why: routing.md/fleet.md are generated, never hand-edited (rigorous-research/AGENTS.md).
- [A3] 2026-11-20 hypothesis: an empty key pool suspends a run - executed: probe `KeyManager.on_failure("brightdata", code="No API key found")` with an empty fingerprint list - outcome: before the fix `_rotate` raised `PoolExhausted("no available key")` (driver suspends); after adding `if not self.fingerprints(pool): return NEXT_SURFACE` to `_rotation_decision` the probe returned `next_surface` - next: keep zenrows/tinyfish on the ladder without pools.
- [A4] 2026-11-20 executed: removed `~/.zenrows/secrets.json` (key already in `ZENROWS_API_KEY`, length-verified) - outcome: `zenrows status --json` auth `source: env` - why: the stored file would win over a rotated env var.
- [A5] 2026-11-20 executed: PowerShell helper named `H` to hash keys - outcome: fail - evidence: `H` is the built-in alias for `Get-History`; the bind error printed three key values into the session output - why: alias collision (same class as an earlier `R` = `Invoke-History` failure) - QUARANTINED: never name helpers with one letter; use script files and Verb-Noun names - next: owner to rotate the zenrows, tinyfish and firecrawl keys.

### Decisions
- [D1] 2026-11-20 decided (owner): event logs are a committed root `LEDGER.md` per repo, or `~/.agents/ledgers/<concern>/` with no repo; plans only in `~/.agents/EPICs/<concern>/EPIC.md` - SETTLED.
- [D2] 2026-11-20 decided (owner): the public Pages repo keeps `LEDGER.md` local (excluded, never committed) - SETTLED.
- [D3] 2026-11-20 decided (owner): purge finished items from plan docs automatically - SETTLED; the epic skill now purges on every open/serve and when a ledger section closes.
- [D4] 2026-11-20 decided (owner): rigorous-research routes are CLIs alone, bun CLIs as the reference set; MCP routes rejected by the validator (ADR 0035) - SETTLED.
- [D5] 2026-11-20 decided (owner): fix every review finding, including lows and judgement calls - SETTLED.
- [D6] 2026-11-20 decided: the ledger write lock is held only while appending (concurrent sections take turns); the EPIC lock is a session-ownership lock with a heartbeat. Different purposes, so two definitions, each in its own skill - rationale: review bug 9 (one lock per file blocked concurrent work) - re-open if: a harness enforces locks mechanically.

### Spec change log
- [C1] 2026-11-20 spec: single location `~/.agents/EPICs/<concern>/LEDGER.md` for everything -> split: logs in repo roots or `~/.agents/ledgers/`, plans in `EPICs/<concern>/EPIC.md` - reason: owner separated event logs from plans.
- [C2] 2026-11-20 spec: in-repo log git-excluded -> committed - reason: owner ruling (question tool).

### Resume point
- next: none for this repo; open follow-ups live in `~/.agents/EPICs/skills/EPIC.md`.

### Artifacts to revert
- [x] `%TEMP%\ledger-split\*` scratch scripts - revert: `Remove-Item $env:TEMP\ledger-split -Recurse`

## ps-wizard ground-up rebuild (2026-11-20T13:45+05:30)
Goal: one shared toolbox module instead of a 1,030-line copy per wizard; unattended-first runs with human-only pauses; failure rules as verifier checks; lean skill loading.
Concern: skills
Purpose: build
Started: 2026-11-20T13:45+05:30
Status: closed 2026-11-20

### Established facts
- [F1] Old template.ps1: 1,031 lines = 717 code + 266 comment/help + 48 blank; 36 functions - source: AST audit `%TEMP%\ps-wizard-audit\audit-template.ps1` - 2026-11-20
- [F2] `~/.agents/skills/ps-wizard` was a stale REAL directory (not a junction); content matched repo HEAD apart from whitespace - source: Compare-Object line diffs - 2026-11-20; replaced with junction into this repo (old copy to Recycle Bin).
- [F3] `#Requires` lines tokenize as Comment kinds - source: Parser.ParseFile token dump - 2026-11-20; the no-comments check must exempt them.
- [F4] Get-PSCallStack in a parameter DEFAULT sees only the current frame - source: runtime harness crash "Index was outside the bounds" - 2026-11-20; caller detection moved into the function body.

### Attempts
- [A1] 2026-11-20 executed: wrote PsWizard.psm1 (21 exported functions, comment-based help per owner override) - outcome: imports clean, 0 analyzer findings after folding New-RunState into Start-WizardRun and adding SupportsShouldProcess to Start/Stop.
- [A2] 2026-11-20 executed: rewrote SKILL.md (131 -> 74 lines, skeleton inside) and verify-wizard.ps1 (new-shape checks); `git rm` template.ps1 - outcome: done.
- [A3] 2026-11-20 executed: 23 verifier fixtures (1 valid + 22 rule-violating) - outcome: first pass 19/23; fixed no-comments #Requires exemption, relative-launch regex (^'(?![A-Za-z]:)), fixture escaping - final 23/23.
- [A4] 2026-11-20 executed: runtime harness, 14 checks in real pwsh (exit codes, layout, backup, rollback, failed-check-keeps-install, synthetic-secret no-trace) - outcome: first runs exposed F4 and a same-second stamp collision (two runs shared one folder); fixed with body-side caller detection and millisecond stamps - final 14/14.
- [A5] 2026-11-20 executed: secret-test wizard at Desktop\ps-wizard\secret-test\secret-test.ps1, verifier all PASS; opened for owner via `ii` - outcome: awaiting owner's typed-secret run.
- [A6] 2026-11-20 executed: resumed; secret-test folder found deleted, no PSWIZARD_SECRET_TEST env var (typed test never ran). Re-ran fixtures 23/23 and harness 14/14; rebuilt secret-test.ps1 (verifier all PASS); launched visible for owner - outcome: awaiting owner's typed-secret run.
- [A7] 2026-11-20 executed: owner typed a 10-char dummy; rg -F for it in run wizard.log, transcript.log, whole run folder and PSReadLine ConsoleHost_history.txt -> 0 hits; env var PSWIZARD_SECRET_TEST holds it - outcome: NO-TRACE TEST PASSED.
- [A8] 2026-11-20 failed->fixed: same run showed `Copy-Item: Source and destination path did not resolve to the same provider` for `Invoke-QuickBackup HKCU:\Environment`; error was non-terminating, backup folder empty, run still reported success. Fix: Registry provider sources exported via `reg.exe export <key> <file>.reg /y` (output captured), Copy-Item -ErrorAction Stop, throw on export failure. Added harness check backup-registry-exported. Also [OutputType([string])] on Read-PlainValue. - outcome: harness 15/15, fixtures 23/23, analyzer 0 findings.
- [F5] Stop-WizardRun holds the window with `Read-Host 'Press ENTER to close this window'` when interactive (PsWizard.psm1:139); ~/.agents/AGENTS.md said "no closing hold" - settled by D5.
- [A9] 2026-11-20 executed: AGENTS.md + SKILL.md reworded per D5; removed PSWIZARD_SECRET_TEST env var, %TEMP%\ps-wizard-audit, Desktop\ps-wizard\{secret-test,smoke-wizard} (runtime-harness already absent) - outcome: Test-Path False for all four, env var empty.

### Decisions
- [D1] 2026-11-20 decided (owner): shared module WITH comment-based help (overrides the earlier never-comments answer for the module only); wizards comment-free - SETTLED.
- [D2] 2026-11-20 decided (owner): unattended-first but owner-runnable; human-only input (secrets, typed values, hands-on steps) always pauses; Confirm-Choice dropped; Close-BlockingProcess needs prior consent - SETTLED.
- [D3] 2026-11-20 decided (owner): lean skill shape - ~60-line SKILL.md with skeleton, failure rules as verifier checks, template deleted, toolbox via Get-Help only - SETTLED.
- [D4] 2026-11-20 decided (owner): existing wizards rewritten in a follow-up pass; spec at ~/.agents/EPICs/skills/ps-wizard-rebuild-spec.md; test seams = verifier fixtures + module runtime harness - SETTLED.
- [D5] 2026-11-20 decided (owner): keep the final ENTER on interactive runs; rewrite docs to match ("Rewrite docs to keep / retain enter as last step") - SETTLED.
- [D6] 2026-11-20 decided (owner): commit + push; clean up all dirty files under ~; move on to the next easiest EPIC - SETTLED.

### Resume point
- next: closed. Follow-up pass (rewrite existing wizards) is moot: `fd "(-setup|wizard).*\.ps1$"` over Dev, Desktop, .agents, Documents\PowerShell, .local -> only verify-wizard.ps1 copies; `rg -l "Confirm-Choice|Invoke-SelfElevation|Show-WizardBanner"` *.ps1 under ~ -> only the verifier (2026-11-20). No old-template wizards remain.

### Artifacts to revert
- [x] `%TEMP%\ps-wizard-audit\*` - removed 2026-11-20 (A9)
- [x] `Desktop\ps-wizard\secret-test\` - removed 2026-11-20 (A9)
