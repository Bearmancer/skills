---
name: web-cli-research
description: Route any web research, search, scrape, extract, crawl, map, or monitoring task to the right PATH CLI — firecrawl, tvly (Tavily), just-scrape, brightdata, apify, agentql, or browse. Use this whenever the user needs current web facts, sources, page content, structured records, code issues, US law, papers, or repeated site checks, even if they do not name a tool.
allowed-tools:
  - Bash(firecrawl *)
  - Bash(tvly *)
  - Bash(just-scrape *)
  - Bash(brightdata *)
  - Bash(bdata *)
  - Bash(apify *)
  - Bash(agentql *)
  - Bash(browse *)
---

# Web CLI research

All tools are already on PATH (bun shims plus `tvly`). Call the binary directly. Do not use `bunx`, `npx`, or reinstall.

## Routing first: read --help before you run

Flag shapes differ per tool. Before first use in a task, run top-level and subcommand help and follow what it says:

```bash
firecrawl --help; firecrawl search --help; firecrawl scrape --help
tvly --help; tvly search --help; tvly extract --help
just-scrape --help; just-scrape scrape --help
brightdata --help; brightdata search --help; brightdata scrape --help
apify --help; agentql --help; browse --help
```

Pick one tool per need. Do not stack two scrapers for the same page unless the first fails.

## Unique job per tool

- `firecrawl search '<query>'`: web/news/images search with highlights plus Alexandria tool matches. `search alexandria '<need>'`, `find-tools <url>`, and `list <provider> <capability> --pretty` discover structured workflows first for records, listings, datasets. Then `scrape <provider/capability> --options '<JSON>'`.
- `firecrawl scrape/crawl/map`: known URL (`scrape`), whole site (`crawl --wait`, `map --wait`). `parse <file>` is only for local HTML/PDF/DOCX/XLSX. `monitor` is for repeat checks.
- `firecrawl developer/gov/research`: dedicated indexes. `developer` for repos, issues, merged PRs, READMEs, docs. `gov` for US statutes, regulations, court opinions (filter `--jurisdiction us-ca`, `--court ca9`). `research search-papers/inspect-paper/related-papers/read-paper` for ~43M papers (mostly biomedical + arXiv). Never web-search PubMed or Google Scholar by hand when this fits.
- `tvly search`: fast general/finance/news search. Use `--depth advanced --max-results 10 --json`; up to 5 queries per call. `extract` reads up to 20 URLs (`--query` only to isolate one fact, `--extract-depth advanced` for JS/tables). `map` lists URLs only, `crawl` returns content, `research "query"` runs deep async jobs (`run/status/poll`).
- `just-scrape scrape/extract/search/crawl`: single-page scrape (`-f markdown --json`), AI `extract <URL> -p '<prompt>' [--schema '<json>']`, AI `search '<query>' -p '<prompt>'`, bounded `crawl`. Use `--mode js --stealth` for JS-heavy pages. `monitor/history/credits` manage repeats.
- `brightdata` (`bdata` alias): `search` for SERP with engine/type control (`--engine google|bing|yandex --type web|news|images|shopping`), `scrape` via Web Unlocker for blocked pages, `discover` for AI intent-ranked results, `pipelines/zones/browser` for prebuilt scrapers and sessions.
- `apify`: Actor platform. `apify call <actorId> --input '<JSON>' --output-dataset --json` runs a remote actor; `apify run --input '<JSON>'` runs locally. Use when a site needs a dedicated actor the scrapers above lack.
- `agentql`: selector scripts. `agentql init` scaffolds a project, `agentql new-script` fetches an example script. Use when extraction needs stable selectors rather than AI prompts.
- `browse`: live Browserbase session. Always start with `browse skills show`, then `browse tab list|new|switch|close` and cloud/network/functions subcommands. Use for interactive or login-gated pages.
- `firecrawl agent '<prompt>' --urls '<csv>' [--schema '<json>'] [--wait]`: agentic extraction job when crawl+extract is not enough. Poll by job ID with `--status`.

## Output rules

- Add `--json -o <dir>/<name>.json` for large results. Never dump full JSON into context; read the needed slice with the file tool or `jq`.
- Save under `.firecrawl/`, `.tavily/`, or matching names such as `.just-scrape/<query>.json`.
- After `firecrawl search`, send one `search-feedback` in the background within ~2 minutes when results were inspected.
- Stop when two independent sources agree, or the official domain confirms releases, ownership, figures, or named-body decisions.
