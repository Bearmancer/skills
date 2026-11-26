# Routing table (generated)

Generated from `registry/registry.yaml` by `rr gen-routing`. Do not edit by hand.

Per surface the route order is: MCP tool the host carries, then vendor CLI, then POST script, then HTTP or a local tool. A server's key pool rotates
inside the server (SKILL.md, "Key rotation: single home"); a fallback inside a server is never a new surface. Only agent-answered surfaces carry MCP routes: the agent calls `tools.<server>.<tool>`; Python never does.

## Rounds

| Round | Paradigms |
|---|---|
| R1 | keyword |
| R2 | semantic, answer-agent |
| R3 | scholarly-archive, crawl-map, browser-unlocker, structured-extraction |

## Pick by capability

| Capability | Surfaces, cheapest first |
|---|---|
| actor | `apify.actor` (high) |
| agent | `exa.agent` (high) |
| answer | `exa.answer` (med) |
| crawl | `tavily.crawl` (med), `scrapegraph.crawl` (high) |
| docs | `microsoft-learn.docs` (low) |
| extract | `tavily.extract` (low) |
| fetch | `direct.fetch` (low), `exa.fetch` (low), `wayback.fetch` (low), `tinyfish.fetch` (med), `zenrows.fetch` (med) |
| fulltext | `internet-archive.fulltext` (low) |
| lookup | `unpaywall.lookup` (low) |
| query | `wikidata.query` (low) |
| rag-web-browser | `apify.rag-web-browser` (med) |
| read | `ocr.read` (low) |
| research | `tavily.research` (high) |
| scrape | `scrapegraph.scrape` (med), `brightdata.scrape` (high) |
| search | `arxiv.search` (low), `crossref.search` (low), `exa.search` (low), `openalex.search` (low), `semantic-scholar.search` (low), `tavily.search` (low), `wikisource.search` (low), `scrapegraph.search` (med) |
| transcript | `ytdlp.transcript` (low) |
| xmlapi | `bgg.xmlapi` (low) |

## Bot-block chain

Walk in order per URL; the first step that returns the target content wins. Bot-blocked means 401, 403, 429, 503, a
challenge page or an empty body. A credit or auth failure rotates that server's key first, then the walk moves on.
Every step exhausted: the URL is blocked; never guess its content.

1. `direct.fetch` - http: `GET <url>`
2. `tavily.extract` - mcp: `tools.tavily.tavily_extract`; cli: `tvly extract <url...(max 20)> --json -o <file>`
3. `exa.fetch` - mcp: `tools.exa.web_fetch_exa`; post: `uv run <skill dir>/rr.py vendor exa POST /contents --body <json|@file>`
4. `wayback.fetch` - mcp: `tools.fetch.fetch`; http: `GET archive.org/wayback/available`, `GET web.archive.org/cdx/search/cdx`
5. `scrapegraph.scrape` - mcp: `tools.scrapegraph.scrape`, `tools.scrapegraph.extract`; cli: `just-scrape scrape <url>`
6. `zenrows.fetch` - mcp: `tools.zenrows.scrape`; cli: `zenrows fetch <url>`
7. `tinyfish.fetch` - mcp: `tools.tinyfish.fetch_content`; cli: `tinyfish fetch content get <url>`
8. `brightdata.scrape` - mcp: `tools.brightdata.web_fetch`; cli: `brightdata scrape <url> --zone cli_unlocker`
9. `apify.rag-web-browser` - mcp: `tools.apify.apify--rag-web-browser`; cli: `apify actors call apify/rag-web-browser`

## Key policy

The active key is the User-scope env var; `rr keys` rotates it. A running shell keeps the old value, so run
every CLI route with its key refreshed: `$env:<VAR> = [Environment]::GetEnvironmentVariable('<VAR>', 'User'); <cli ...>`.
POST scripts read HKCU themselves and send the key only in the vendor auth header. An MCP route follows rotation only
when the host config reads the key as `{env:<VAR>}`; a literal key in that config is out of `rr keys`'s reach.

| Server | Env var | Pool | POST auth header | CLI auth | MCP key (rr keys rotation) | Wired |
|---|---|---|---|---|---|---|
| tavily | `TAVILY_API_KEY` | `tavily` | `Authorization: Bearer <key>` | MCP tools read TAVILY_API_KEY from the host config; the tvly CLI is broken on this host and stays the fallback | `TAVILY_API_KEY` env reference (a rotation reaches the MCP only after OpenCode restarts; the server reads the var at launch) | yes |
| exa | `EXA_API_KEY` | `exa` | `x-api-key: <key>` | MCP tools read EXA_API_KEY from the host config; the POST scripts are the fallback | `EXA_API_KEY` env reference (a rotation reaches the MCP only after OpenCode restarts; the server reads the var at launch) | yes |
| scrapegraph | `SGAI_API_KEY` | `scrapegraph` | `SGAI-APIKEY: <key>` | SGAI_API_KEY (just-scrape); debug with SGAI_DEBUG=1, history with `just-scrape history scrape --json` | `SGAI_API_KEY` env reference (a rotation reaches the MCP only after OpenCode restarts; the server reads the var at launch) | yes |
| apify | `APIFY_TOKEN` | `apify` | `Authorization: Bearer <key>` | APIFY_TOKEN (`apify info` reports token source env; no ~/.apify/auth.json: never run `apify login`) | `APIFY_TOKEN` env reference (a rotation reaches the MCP only after OpenCode restarts; the server reads the var at launch) | yes |
| zenrows | `ZENROWS_API_KEY` | `zenrows` | - | MCP tools read ZENROWS_API_KEY from the host config; the zenrows CLI is the fallback (no ~/.zenrows/secrets.json: a stored key would win; never run `zenrows login`) | `ZENROWS_API_KEY` env reference (a rotation reaches the MCP only after OpenCode restarts; the server reads the var at launch) | yes |
| tinyfish | `TINYFISH_API_KEY` | `tinyfish` | - | TINYFISH_API_KEY (overrides a key saved with `tinyfish auth set`); check `tinyfish auth status` | `TINYFISH_API_KEY` env reference (a rotation reaches the MCP only after OpenCode restarts; the server reads the var at launch) | yes |
| brightdata | `BRIGHTDATA_API_KEY` | `brightdata` | - | BRIGHTDATA_API_KEY plus a Web Unlocker zone: pass --zone or `brightdata config set default_zone_unlocker cli_unlocker` | `BRIGHTDATA_API_KEY` env reference (a rotation reaches the MCP only after OpenCode restarts; the server reads the var at launch) | yes |
| microsoft-learn | `-` | `-` | - | - | keyless (no rotation) | yes |
| fetch | `-` | `-` | - | - | keyless (no rotation) | yes |

## Error classes

| Server | Class | Codes | Verified |
|---|---|---|---|
| tavily | bad_key | - | no |
| tavily | out_of_credit | - | no |
| tavily | blocked | `failed to fetch url` | yes |
| tavily | rate_limit | - | no |
| exa | bad_key | `401` | yes |
| exa | out_of_credit | `402` | yes |
| exa | blocked | `source_not_available` | yes |
| exa | rate_limit | `429` | yes |
| scrapegraph | bad_key | `401`, `auth_missing_key`, `403`, `auth_invalid_key` | yes |
| scrapegraph | out_of_credit | `402`, `insufficient_credits` | yes |
| scrapegraph | blocked | - | no |
| scrapegraph | rate_limit | `429`, `rate_limited` | yes |
| apify | bad_key | `401`, `invalid-token`, `token-not-provided` | yes |
| apify | out_of_credit | `402`, `not-enough-usage-to-run-paid-actor`, `monthly-usage-limit-too-low` | yes |
| apify | blocked | - | no |
| apify | rate_limit | `429`, `rate-limit-exceeded` | yes |
| zenrows | bad_key | - | no |
| zenrows | out_of_credit | - | no |
| zenrows | blocked | - | no |
| zenrows | rate_limit | - | no |
| tinyfish | bad_key | - | no |
| tinyfish | out_of_credit | - | no |
| tinyfish | blocked | - | no |
| tinyfish | rate_limit | - | no |
| brightdata | bad_key | `401`, `api key required`, `No API key found` | yes |
| brightdata | out_of_credit | - | no |
| brightdata | blocked | - | no |
| brightdata | rate_limit | - | no |
