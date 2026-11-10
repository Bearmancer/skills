# Routing table (generated)

Generated from `registry/registry.yaml` by `scripts/gen_routing_table.py`. Do not edit by hand.

## Rounds

| Round | Paradigms                   |
| ----- | --------------------------- |
| R1    | keyword                     |
| R2    | semantic                    |
| R3    | answer-agent                |
| R4    | scholarly-archive           |
| R5    | crawl-map, browser-unlocker |

## Fetch ladder

1. `direct.fetch`
2. `tavily.extract`
3. `firecrawl.scrape`
4. `exa.fetch`
5. `wayback.fetch`
6. `scrapegraph.scrape`
7. `apify.rag-web-browser`
8. `agentql.extract`
9. `browserbase.session`

## Surfaces

| Surface                     | Paradigm              | Ladder    | Cost | Wired | MCP                                                                   | CLI                                          | POST/HTTP/local                                                                         |
| --------------------------- | --------------------- | --------- | ---- | ----- | --------------------------------------------------------------------- | -------------------------------------------- | --------------------------------------------------------------------------------------- |
| `direct.fetch`              | crawl-map             | fetch     | low  | yes   | -                                                                     | -                                            | http: `GET <url>`                                                                       |
| `tavily.search`             | keyword               | discovery | low  | yes   | `tavily_search`                                                       | `tvly search`                                | -                                                                                       |
| `tavily.extract`            | crawl-map             | fetch     | low  | yes   | `tavily_extract`                                                      | `tvly extract`                               | -                                                                                       |
| `tavily.crawl`              | crawl-map             | discovery | med  | yes   | `tavily_crawl`<br>`tavily_map`                                        | `tvly crawl`<br>`tvly map`                   | -                                                                                       |
| `tavily.research`           | answer-agent          | discovery | high | yes   | `tavily_research`                                                     | `tvly research`                              | -                                                                                       |
| `exa.search`                | semantic              | discovery | low  | yes   | `web_search_exa`<br>`web_search_advanced_exa`                         | -                                            | -                                                                                       |
| `exa.fetch`                 | crawl-map             | fetch     | low  | yes   | `web_fetch_exa`                                                       | -                                            | -                                                                                       |
| `exa.answer`                | answer-agent          | discovery | med  | yes   | -                                                                     | -                                            | post: `uv run <skill dir>/scripts/post/vendor_request.py exa POST /answer --body <json  | @file>`                                                                         |
| `exa.agent`                 | answer-agent          | discovery | high | yes   | `agent_run`                                                           | -                                            | post: `uv run <skill dir>/scripts/post/exa_agent_run.py stop                            | cancel <run_id>`<br>post: `uv run <skill dir>/scripts/post/exa_batches.py start | status | cancel` |
| `firecrawl.search`          | keyword               | discovery | low  | yes   | `firecrawl_search`                                                    | `firecrawl search`                           | -                                                                                       |
| `firecrawl.scrape`          | crawl-map             | fetch     | low  | yes   | `firecrawl_scrape`                                                    | `firecrawl scrape`                           | -                                                                                       |
| `firecrawl.crawl`           | crawl-map             | discovery | med  | yes   | `firecrawl_crawl`<br>`firecrawl_map`                                  | `firecrawl crawl`<br>`firecrawl map`         | -                                                                                       |
| `firecrawl.batch-scrape`    | crawl-map             | fetch     | med  | yes   | -                                                                     | -                                            | post: `uv run <skill dir>/scripts/post/firecrawl_batch_scrape.py start                  | status                                                                          | cancel | errors` |
| `firecrawl.agent`           | answer-agent          | discovery | high | yes   | `firecrawl_agent`                                                     | `firecrawl agent`                            | -                                                                                       |
| `firecrawl.research`        | scholarly-archive     | discovery | low  | yes   | `firecrawl_research_search_papers`<br>`firecrawl_research_read_paper` | `firecrawl research`                         | -                                                                                       |
| `scrapegraph.search`        | keyword               | discovery | med  | yes   | `search`                                                              | `just-scrape search`                         | -                                                                                       |
| `scrapegraph.scrape`        | structured-extraction | fetch     | med  | yes   | `scrape`<br>`extract`                                                 | `just-scrape scrape`                         | -                                                                                       |
| `scrapegraph.crawl`         | crawl-map             | discovery | high | yes   | `crawl_start`<br>`crawl_get`<br>`crawl_pages`                         | `just-scrape crawl`                          | post: `uv run <skill dir>/scripts/post/scrapegraph_crawl.py start                       | status                                                                          | stop   | resume  | delete | pages` |
| `apify.rag-web-browser`     | browser-unlocker      | fetch     | med  | yes   | `apify--rag-web-browser`                                              | `apify actors call`                          | -                                                                                       |
| `apify.actor`               | structured-extraction | fetch     | high | yes   | `search-actors`<br>`call-actor`                                       | `apify actors search`<br>`apify actors call` | -                                                                                       |
| `agentql.extract`           | structured-extraction | fetch     | med  | yes   | `extract-web-data`                                                    | -                                            | -                                                                                       |
| `browserbase.session`       | browser-unlocker      | fetch     | high | yes   | `start`<br>`navigate`<br>`act`<br>`observe`<br>`extract`<br>`end`     | `browse open`                                | -                                                                                       |
| `browserbase.agent-run`     | browser-unlocker      | fetch     | high | yes   | -                                                                     | -                                            | post: `uv run <skill dir>/scripts/post/browserbase_agent_run.py start                   | status`                                                                         |
| `microsoft-learn.docs`      | keyword               | discovery | low  | yes   | `microsoft_docs_search`<br>`microsoft_docs_fetch`                     | -                                            | -                                                                                       |
| `dappier.search`            | semantic              | discovery | low  | yes   | `dappier_real_time_search`                                            | -                                            | -                                                                                       |
| `openalex.search`           | scholarly-archive     | discovery | low  | yes   | -                                                                     | -                                            | http: `GET api.openalex.org/works`                                                      |
| `crossref.search`           | scholarly-archive     | discovery | low  | yes   | -                                                                     | -                                            | http: `GET api.crossref.org/works`                                                      |
| `semantic-scholar.search`   | scholarly-archive     | discovery | low  | yes   | -                                                                     | -                                            | http: `GET api.semanticscholar.org/graph/v1/paper/search`                               |
| `arxiv.search`              | scholarly-archive     | discovery | low  | yes   | -                                                                     | -                                            | http: `GET export.arxiv.org/api/query`                                                  |
| `unpaywall.lookup`          | scholarly-archive     | discovery | low  | yes   | -                                                                     | -                                            | http: `GET api.unpaywall.org/v2/<doi>`                                                  |
| `wayback.fetch`             | scholarly-archive     | fetch     | low  | yes   | -                                                                     | -                                            | http: `GET archive.org/wayback/available`<br>http: `GET web.archive.org/cdx/search/cdx` |
| `internet-archive.fulltext` | scholarly-archive     | discovery | low  | yes   | -                                                                     | -                                            | http: `GET archive.org/advancedsearch.php`                                              |
| `wikisource.search`         | scholarly-archive     | discovery | low  | yes   | -                                                                     | -                                            | http: `GET wikisource.org/w/api.php`                                                    |
| `wikipedia.search`          | keyword               | discovery | low  | yes   | -                                                                     | -                                            | http: `GET wikipedia.org/w/api.php`                                                     |
| `wikidata.query`            | semantic              | discovery | low  | yes   | -                                                                     | -                                            | http: `GET wikidata.org/w/api.php`                                                      |
| `bgg.xmlapi`                | scholarly-archive     | discovery | low  | yes   | -                                                                     | -                                            | http: `GET boardgamegeek.com/xmlapi2/thing`                                             |
| `ytdlp.transcript`          | structured-extraction | fetch     | low  | yes   | -                                                                     | -                                            | local: `yt-dlp --write-subs`                                                            |
| `pdftotext.extract`         | structured-extraction | fetch     | low  | yes   | -                                                                     | -                                            | local: `pdftotext`                                                                      |
| `ocr.read`                  | structured-extraction | fetch     | low  | yes   | -                                                                     | `toolbox azure docintel`                     | -                                                                                       |
| `playwright.render`         | browser-unlocker      | fetch     | med  | yes   | -                                                                     | -                                            | local: `playwright`                                                                     |

## Key policy

Key goes only into the vendor auth header; source order: `~/.config/opencode/secrets/<pool>`, then the env var.

| Server      | Env var               | Pool          | Auth header                   | Wired |
| ----------- | --------------------- | ------------- | ----------------------------- | ----- |
| tavily      | `TAVILY_API_KEY`      | `tavily`      | `Authorization: Bearer <key>` | yes   |
| exa         | `EXA_API_KEY`         | `exa`         | `x-api-key: <key>`            | yes   |
| firecrawl   | `FIRECRAWL_API_KEY`   | `firecrawl`   | `Authorization: Bearer <key>` | yes   |
| scrapegraph | `SCRAPEGRAPH_API_KEY` | `scrapegraph` | `SGAI-APIKEY: <key>`          | yes   |
| apify       | `APIFY_TOKEN`         | `apify`       | `Authorization: Bearer <key>` | yes   |
| agentql     | `AGENTQL_API_KEY`     | `agentql`     | `X-API-Key: <key>`            | yes   |
| browserbase | `BROWSERBASE_API_KEY` | `browserbase` | `X-BB-API-Key: <key>`         | yes   |
| dappier     | `DAPPIER_API_KEY`     | `dappier`     | -                             | yes   |

## POST scripts

JSON to stdout; HTTP error: exit 1 with `{status, code, message}` on stderr; redirects refused.

| Surface                  | Command                                                                          |
| ------------------------ | -------------------------------------------------------------------------------- |
| `exa.answer`             | `uv run <skill dir>/scripts/post/vendor_request.py exa POST /answer --body <json | @file>`          |
| `exa.agent`              | `uv run <skill dir>/scripts/post/exa_agent_run.py stop                           | cancel <run_id>` |
| `exa.agent`              | `uv run <skill dir>/scripts/post/exa_batches.py start                            | status           | cancel` |
| `firecrawl.batch-scrape` | `uv run <skill dir>/scripts/post/firecrawl_batch_scrape.py start                 | status           | cancel  | errors` |
| `scrapegraph.crawl`      | `uv run <skill dir>/scripts/post/scrapegraph_crawl.py start                      | status           | stop    | resume  | delete | pages` |
| `browserbase.agent-run`  | `uv run <skill dir>/scripts/post/browserbase_agent_run.py start                  | status`          |

## Error classes

| Server      | Class         | Codes                                                                      | Verified |
| ----------- | ------------- | -------------------------------------------------------------------------- | -------- |
| tavily      | bad_key       | -                                                                          | no       |
| tavily      | out_of_credit | -                                                                          | no       |
| tavily      | blocked       | `failed to fetch url`                                                      | yes      |
| tavily      | rate_limit    | -                                                                          | no       |
| exa         | bad_key       | `401`                                                                      | yes      |
| exa         | out_of_credit | `402`                                                                      | yes      |
| exa         | blocked       | `source_not_available`                                                     | yes      |
| exa         | rate_limit    | `429`                                                                      | yes      |
| firecrawl   | bad_key       | `401`                                                                      | yes      |
| firecrawl   | out_of_credit | `402`                                                                      | yes      |
| firecrawl   | blocked       | `403`                                                                      | yes      |
| firecrawl   | rate_limit    | `429`                                                                      | yes      |
| scrapegraph | bad_key       | `401`, `auth_missing_key`, `403`, `auth_invalid_key`                       | yes      |
| scrapegraph | out_of_credit | `402`, `insufficient_credits`                                              | yes      |
| scrapegraph | blocked       | -                                                                          | no       |
| scrapegraph | rate_limit    | `429`, `rate_limited`                                                      | yes      |
| apify       | bad_key       | `401`, `invalid-token`, `token-not-provided`                               | yes      |
| apify       | out_of_credit | `402`, `not-enough-usage-to-run-paid-actor`, `monthly-usage-limit-too-low` | yes      |
| apify       | blocked       | -                                                                          | no       |
| apify       | rate_limit    | `429`, `rate-limit-exceeded`                                               | yes      |
| agentql     | bad_key       | `401`, `api key required`                                                  | yes      |
| agentql     | out_of_credit | -                                                                          | no       |
| agentql     | blocked       | -                                                                          | no       |
| agentql     | rate_limit    | -                                                                          | no       |
| browserbase | bad_key       | -                                                                          | no       |
| browserbase | out_of_credit | -                                                                          | no       |
| browserbase | blocked       | -                                                                          | no       |
| browserbase | rate_limit    | -                                                                          | no       |
| dappier     | bad_key       | -                                                                          | yes      |
| dappier     | out_of_credit | -                                                                          | yes      |
| dappier     | blocked       | -                                                                          | yes      |
| dappier     | rate_limit    | -                                                                          | yes      |
