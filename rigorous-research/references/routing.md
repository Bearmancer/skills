# Routing table (generated)

Generated from `registry/registry.yaml` by `scripts/gen_routing_table.py`. Do not edit by hand.

## Rounds

| Round | Paradigms |
|---|---|
| R1 | keyword |
| R2 | semantic |
| R3 | answer-agent |
| R4 | scholarly-archive |
| R5 | crawl-map, browser-unlocker |

## Fetch ladder

1. `direct.fetch`
2. `tavily.extract`
3. `firecrawl.scrape`
4. `exa.fetch`
5. `wayback.fetch`
6. `scrapegraph.scrape`
7. `zenrows.fetch`
8. `tinyfish.fetch`
9. `brightdata.scrape`
10. `apify.rag-web-browser`

## Surfaces

| Surface | Paradigm | Ladder | Cost | Wired | CLI | POST/HTTP/local |
|---|---|---|---|---|---|---|
| `direct.fetch` | crawl-map | fetch | low | yes | - | http: `GET <url>` |
| `tavily.search` | keyword | discovery | low | yes | `tvly search` | - |
| `tavily.extract` | crawl-map | fetch | low | yes | `tvly extract <url...(max 20)> --json -o <file>` | - |
| `tavily.crawl` | crawl-map | discovery | med | yes | `tvly crawl`<br>`tvly map` | - |
| `tavily.research` | answer-agent | discovery | high | yes | `tvly research` | - |
| `exa.search` | semantic | discovery | low | yes | - | post: `uv run <skill dir>/scripts/post/vendor_request.py exa POST /search --body <json|@file>` |
| `exa.fetch` | crawl-map | fetch | low | yes | - | post: `uv run <skill dir>/scripts/post/vendor_request.py exa POST /contents --body <json|@file>` |
| `exa.answer` | answer-agent | discovery | med | yes | - | post: `uv run <skill dir>/scripts/post/vendor_request.py exa POST /answer --body <json|@file>` |
| `exa.agent` | answer-agent | discovery | high | yes | - | post: `uv run <skill dir>/scripts/post/vendor_request.py exa POST /agent/runs --body <json|@file>`<br>post: `uv run <skill dir>/scripts/post/vendor_request.py exa GET /agent/runs/<run_id>`<br>post: `uv run <skill dir>/scripts/post/exa_agent_run.py stop|cancel <run_id>`<br>post: `uv run <skill dir>/scripts/post/exa_batches.py start|status|cancel` |
| `firecrawl.search` | keyword | discovery | low | yes | `firecrawl search` | - |
| `firecrawl.scrape` | crawl-map | fetch | low | yes | `firecrawl scrape <url>` | - |
| `firecrawl.crawl` | crawl-map | discovery | med | yes | `firecrawl crawl`<br>`firecrawl map` | - |
| `firecrawl.batch-scrape` | crawl-map | fetch | med | yes | - | post: `uv run <skill dir>/scripts/post/firecrawl_batch_scrape.py start|status|cancel|errors` |
| `firecrawl.agent` | answer-agent | discovery | high | yes | `firecrawl agent` | - |
| `firecrawl.research` | scholarly-archive | discovery | low | yes | `firecrawl research` | - |
| `scrapegraph.search` | keyword | discovery | med | yes | `just-scrape search` | - |
| `scrapegraph.scrape` | structured-extraction | fetch | med | yes | `just-scrape scrape <url>` | - |
| `scrapegraph.crawl` | crawl-map | discovery | high | yes | `just-scrape crawl` | post: `uv run <skill dir>/scripts/post/scrapegraph_crawl.py start|status|stop|resume|delete|pages` |
| `apify.rag-web-browser` | browser-unlocker | fetch | med | yes | `apify actors call apify/rag-web-browser` | - |
| `apify.actor` | structured-extraction | fetch | high | yes | `apify actors search`<br>`apify actors call` | - |
| `zenrows.fetch` | browser-unlocker | fetch | med | yes | `zenrows fetch <url>` | - |
| `tinyfish.fetch` | browser-unlocker | fetch | med | yes | `tinyfish fetch content get <url>` | - |
| `brightdata.scrape` | browser-unlocker | fetch | high | yes | `brightdata scrape <url> --zone cli_unlocker` | - |
| `browserbase.agent-run` | browser-unlocker | fetch | high | yes | - | post: `uv run <skill dir>/scripts/post/browserbase_agent_run.py start|status` |
| `microsoft-learn.docs` | keyword | discovery | low | yes | - | http: `GET learn.microsoft.com/api/search?search=<q>`<br>http: `GET <hit url>` |
| `openalex.search` | scholarly-archive | discovery | low | yes | - | http: `GET api.openalex.org/works` |
| `crossref.search` | scholarly-archive | discovery | low | yes | - | http: `GET api.crossref.org/works` |
| `semantic-scholar.search` | scholarly-archive | discovery | low | yes | - | http: `GET api.semanticscholar.org/graph/v1/paper/search` |
| `arxiv.search` | scholarly-archive | discovery | low | yes | - | http: `GET export.arxiv.org/api/query` |
| `unpaywall.lookup` | scholarly-archive | discovery | low | yes | - | http: `GET api.unpaywall.org/v2/<doi>` |
| `wayback.fetch` | scholarly-archive | fetch | low | yes | - | http: `GET archive.org/wayback/available`<br>http: `GET web.archive.org/cdx/search/cdx` |
| `internet-archive.fulltext` | scholarly-archive | discovery | low | yes | - | http: `GET archive.org/advancedsearch.php` |
| `wikisource.search` | scholarly-archive | discovery | low | yes | - | http: `GET wikisource.org/w/api.php` |
| `wikipedia.search` | keyword | discovery | low | yes | - | http: `GET wikipedia.org/w/api.php` |
| `wikidata.query` | semantic | discovery | low | yes | - | http: `GET wikidata.org/w/api.php` |
| `bgg.xmlapi` | scholarly-archive | discovery | low | yes | - | http: `GET boardgamegeek.com/xmlapi2/thing` |
| `ytdlp.transcript` | structured-extraction | fetch | low | yes | - | local: `yt-dlp --write-subs` |
| `pdftotext.extract` | structured-extraction | fetch | low | yes | - | local: `pdftotext` |
| `ocr.read` | structured-extraction | fetch | low | yes | `toolbox azure docintel` | - |
| `playwright.render` | browser-unlocker | fetch | med | yes | - | local: `playwright` |

## Key policy

The active key is the User-scope env var; `switch_api_key.py` rotates it. A running shell keeps the old value, so run
every CLI route with its key refreshed: `$env:<VAR> = [Environment]::GetEnvironmentVariable('<VAR>', 'User'); <cli ...>`.
POST scripts read HKCU themselves and send the key only in the vendor auth header.

| Server | Env var | Pool | POST auth header | CLI auth | Wired |
|---|---|---|---|---|---|
| tavily | `TAVILY_API_KEY` | `tavily` | `Authorization: Bearer <key>` | TAVILY_API_KEY (`tvly auth` confirms) | yes |
| exa | `EXA_API_KEY` | `exa` | `x-api-key: <key>` | EXA_API_KEY (POST scripts only; exa has no CLI) | yes |
| firecrawl | `FIRECRAWL_API_KEY` | `firecrawl` | `Authorization: Bearer <key>` | FIRECRAWL_API_KEY (wins over the stored login; `firecrawl status` confirms) | yes |
| scrapegraph | `SGAI_API_KEY` | `scrapegraph` | `SGAI-APIKEY: <key>` | SGAI_API_KEY (just-scrape); debug with SGAI_DEBUG=1, history with `just-scrape history scrape --json` | yes |
| apify | `APIFY_TOKEN` | `apify` | `Authorization: Bearer <key>` | APIFY_TOKEN (`apify info` reports token source env; no ~/.apify/auth.json: never run `apify login`) | yes |
| zenrows | `ZENROWS_API_KEY` | `zenrows` | - | ZENROWS_API_KEY (no ~/.zenrows/secrets.json: a stored key would win over the env var; never run `zenrows login`) | yes |
| tinyfish | `TINYFISH_API_KEY` | `tinyfish` | - | TINYFISH_API_KEY (overrides a key saved with `tinyfish auth set`); check `tinyfish auth status` | yes |
| brightdata | `BRIGHTDATA_API_KEY` | `brightdata` | - | BRIGHTDATA_API_KEY plus a Web Unlocker zone: pass --zone or `brightdata config set default_zone_unlocker cli_unlocker` | yes |
| browserbase | `BROWSERBASE_API_KEY` | `browserbase` | `X-BB-API-Key: <key>` | BROWSERBASE_API_KEY (POST scripts only) | yes |

## POST scripts

JSON to stdout; HTTP error: exit 1 with `{status, code, message}` on stderr; redirects refused.

| Surface | Command |
|---|---|
| `exa.search` | `uv run <skill dir>/scripts/post/vendor_request.py exa POST /search --body <json|@file>` |
| `exa.fetch` | `uv run <skill dir>/scripts/post/vendor_request.py exa POST /contents --body <json|@file>` |
| `exa.answer` | `uv run <skill dir>/scripts/post/vendor_request.py exa POST /answer --body <json|@file>` |
| `exa.agent` | `uv run <skill dir>/scripts/post/vendor_request.py exa POST /agent/runs --body <json|@file>` |
| `exa.agent` | `uv run <skill dir>/scripts/post/vendor_request.py exa GET /agent/runs/<run_id>` |
| `exa.agent` | `uv run <skill dir>/scripts/post/exa_agent_run.py stop|cancel <run_id>` |
| `exa.agent` | `uv run <skill dir>/scripts/post/exa_batches.py start|status|cancel` |
| `firecrawl.batch-scrape` | `uv run <skill dir>/scripts/post/firecrawl_batch_scrape.py start|status|cancel|errors` |
| `scrapegraph.crawl` | `uv run <skill dir>/scripts/post/scrapegraph_crawl.py start|status|stop|resume|delete|pages` |
| `browserbase.agent-run` | `uv run <skill dir>/scripts/post/browserbase_agent_run.py start|status` |

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
| firecrawl | bad_key | `401` | yes |
| firecrawl | out_of_credit | `402` | yes |
| firecrawl | blocked | `403` | yes |
| firecrawl | rate_limit | `429` | yes |
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
| browserbase | bad_key | - | no |
| browserbase | out_of_credit | - | no |
| browserbase | blocked | - | no |
| browserbase | rate_limit | - | no |
