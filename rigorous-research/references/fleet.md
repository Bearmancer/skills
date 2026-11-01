# Fleet: route a web call (generated)

Generated from `registry/registry.yaml` by `scripts/gen_routing_table.py`. Do not edit by hand. Full tables: `routing.md`.

Per surface the route order is: MCP tool the host carries, then vendor CLI, then POST script. A server's key pool rotates
inside the server (SKILL.md, "Key rotation: single home"); a fallback inside a server is never a new surface.

## Pick by capability

| Capability      | Surfaces, cheapest first                                                                                                                                                                                                                                                              |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| actor           | `apify.actor` (high)                                                                                                                                                                                                                                                                  |
| agent           | `exa.agent` (high), `firecrawl.agent` (high)                                                                                                                                                                                                                                          |
| agent-run       | `browserbase.agent-run` (high)                                                                                                                                                                                                                                                        |
| answer          | `exa.answer` (med)                                                                                                                                                                                                                                                                    |
| batch-scrape    | `firecrawl.batch-scrape` (med)                                                                                                                                                                                                                                                        |
| crawl           | `firecrawl.crawl` (med), `tavily.crawl` (med), `scrapegraph.crawl` (high)                                                                                                                                                                                                             |
| docs            | `microsoft-learn.docs` (low)                                                                                                                                                                                                                                                          |
| extract         | `pdftotext.extract` (low), `tavily.extract` (low), `agentql.extract` (med)                                                                                                                                                                                                            |
| fetch           | `direct.fetch` (low), `exa.fetch` (low), `wayback.fetch` (low)                                                                                                                                                                                                                        |
| fulltext        | `internet-archive.fulltext` (low)                                                                                                                                                                                                                                                     |
| lookup          | `unpaywall.lookup` (low)                                                                                                                                                                                                                                                              |
| query           | `wikidata.query` (low)                                                                                                                                                                                                                                                                |
| rag-web-browser | `apify.rag-web-browser` (med)                                                                                                                                                                                                                                                         |
| read            | `ocr.read` (low)                                                                                                                                                                                                                                                                      |
| render          | `playwright.render` (med)                                                                                                                                                                                                                                                             |
| research        | `firecrawl.research` (low), `tavily.research` (high)                                                                                                                                                                                                                                  |
| scrape          | `firecrawl.scrape` (low), `scrapegraph.scrape` (med)                                                                                                                                                                                                                                  |
| search          | `arxiv.search` (low), `crossref.search` (low), `dappier.search` (low), `exa.search` (low), `firecrawl.search` (low), `openalex.search` (low), `semantic-scholar.search` (low), `tavily.search` (low), `wikipedia.search` (low), `wikisource.search` (low), `scrapegraph.search` (med) |
| session         | `browserbase.session` (high)                                                                                                                                                                                                                                                          |
| transcript      | `ytdlp.transcript` (low)                                                                                                                                                                                                                                                              |
| xmlapi          | `bgg.xmlapi` (low)                                                                                                                                                                                                                                                                    |

## Bot-block chain

Walk in order per URL; the first step that returns the target content wins. Bot-blocked means 401, 403, 429, 503, a
challenge page or an empty body. A credit or auth failure rotates that server's key first, then the walk moves on.
Every step exhausted: the URL is blocked; never guess its content.

1. `direct.fetch` - http: `GET <url>`
2. `tavily.extract` - mcp: `tavily_extract`; cli: `tvly extract`
3. `firecrawl.scrape` - mcp: `firecrawl_scrape`; cli: `firecrawl scrape`
4. `exa.fetch` - mcp: `web_fetch_exa`
5. `wayback.fetch` - http: `GET archive.org/wayback/available`, `GET web.archive.org/cdx/search/cdx`
6. `scrapegraph.scrape` - mcp: `scrape`, `extract`; cli: `just-scrape scrape`
7. `apify.rag-web-browser` - mcp: `apify--rag-web-browser`; cli: `apify actors call`
8. `agentql.extract` - mcp: `extract-web-data`
9. `browserbase.session` - mcp: `start`, `navigate`, `act`, `observe`, `extract`, `end`; cli: `browse open`

## POST scripts

JSON to stdout, HTTP errors exit 1 with `{status, code, message}` on stderr.

- `exa.answer`: `uv run <skill dir>/scripts/post/vendor_request.py exa POST /answer --body <json|@file>`
- `exa.agent`: `uv run <skill dir>/scripts/post/exa_agent_run.py stop|cancel <run_id>`
- `exa.agent`: `uv run <skill dir>/scripts/post/exa_batches.py start|status|cancel`
- `firecrawl.batch-scrape`: `uv run <skill dir>/scripts/post/firecrawl_batch_scrape.py start|status|cancel|errors`
- `scrapegraph.crawl`: `uv run <skill dir>/scripts/post/scrapegraph_crawl.py start|status|stop|resume|delete|pages`
- `browserbase.agent-run`: `uv run <skill dir>/scripts/post/browserbase_agent_run.py start|status`
