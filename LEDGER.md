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
