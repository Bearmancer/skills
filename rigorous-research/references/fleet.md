# Fleet: route a web call (generated)

Generated from `registry/registry.yaml` by `scripts/gen_routing_table.py`. Do not edit by hand. Full tables: `routing.md`.

Per surface the route order is: vendor CLI, then POST script, then HTTP or a local tool. No MCP. A server's key pool rotates
inside the server (SKILL.md, "Key rotation: single home"); a fallback inside a server is never a new surface.

## Pick by capability

| Capability | Surfaces, cheapest first |
|---|---|
| actor | `apify.actor` (high) |
| agent | `exa.agent` (high), `firecrawl.agent` (high) |
| agent-run | `browserbase.agent-run` (high) |
| answer | `exa.answer` (med) |
| batch-scrape | `firecrawl.batch-scrape` (med) |
| crawl | `firecrawl.crawl` (med), `tavily.crawl` (med), `scrapegraph.crawl` (high) |
| docs | `microsoft-learn.docs` (low) |
| extract | `pdftotext.extract` (low), `tavily.extract` (low) |
| fetch | `direct.fetch` (low), `exa.fetch` (low), `wayback.fetch` (low), `tinyfish.fetch` (med), `zenrows.fetch` (med) |
| fulltext | `internet-archive.fulltext` (low) |
| lookup | `unpaywall.lookup` (low) |
| query | `wikidata.query` (low) |
| rag-web-browser | `apify.rag-web-browser` (med) |
| read | `ocr.read` (low) |
| render | `playwright.render` (med) |
| research | `firecrawl.research` (low), `tavily.research` (high) |
| scrape | `firecrawl.scrape` (low), `scrapegraph.scrape` (med), `brightdata.scrape` (high) |
| search | `arxiv.search` (low), `crossref.search` (low), `exa.search` (low), `firecrawl.search` (low), `openalex.search` (low), `semantic-scholar.search` (low), `tavily.search` (low), `wikipedia.search` (low), `wikisource.search` (low), `scrapegraph.search` (med) |
| transcript | `ytdlp.transcript` (low) |
| xmlapi | `bgg.xmlapi` (low) |

## Bot-block chain

Walk in order per URL; the first step that returns the target content wins. Bot-blocked means 401, 403, 429, 503, a
challenge page or an empty body. A credit or auth failure rotates that server's key first, then the walk moves on.
Every step exhausted: the URL is blocked; never guess its content.

1. `direct.fetch` - http: `GET <url>`
2. `tavily.extract` - cli: `tvly extract <url...(max 20)> --json -o <file>`
3. `firecrawl.scrape` - cli: `firecrawl scrape <url>`
4. `exa.fetch` - post: `uv run <skill dir>/scripts/post/vendor_request.py exa POST /contents --body <json|@file>`
5. `wayback.fetch` - http: `GET archive.org/wayback/available`, `GET web.archive.org/cdx/search/cdx`
6. `scrapegraph.scrape` - cli: `just-scrape scrape <url>`
7. `zenrows.fetch` - cli: `zenrows fetch <url>`
8. `tinyfish.fetch` - cli: `tinyfish fetch content get <url>`
9. `brightdata.scrape` - cli: `brightdata scrape <url> --zone cli_unlocker`
10. `apify.rag-web-browser` - cli: `apify actors call apify/rag-web-browser`

## POST scripts

JSON to stdout, HTTP errors exit 1 with `{status, code, message}` on stderr.

- `exa.search`: `uv run <skill dir>/scripts/post/vendor_request.py exa POST /search --body <json|@file>`
- `exa.fetch`: `uv run <skill dir>/scripts/post/vendor_request.py exa POST /contents --body <json|@file>`
- `exa.answer`: `uv run <skill dir>/scripts/post/vendor_request.py exa POST /answer --body <json|@file>`
- `exa.agent`: `uv run <skill dir>/scripts/post/vendor_request.py exa POST /agent/runs --body <json|@file>`
- `exa.agent`: `uv run <skill dir>/scripts/post/vendor_request.py exa GET /agent/runs/<run_id>`
- `exa.agent`: `uv run <skill dir>/scripts/post/exa_agent_run.py stop|cancel <run_id>`
- `exa.agent`: `uv run <skill dir>/scripts/post/exa_batches.py start|status|cancel`
- `firecrawl.batch-scrape`: `uv run <skill dir>/scripts/post/firecrawl_batch_scrape.py start|status|cancel|errors`
- `scrapegraph.crawl`: `uv run <skill dir>/scripts/post/scrapegraph_crawl.py start|status|stop|resume|delete|pages`
- `browserbase.agent-run`: `uv run <skill dir>/scripts/post/browserbase_agent_run.py start|status`
