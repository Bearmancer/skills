# Failure ledger: seed and format

Every delegation to Exa, Tavily or Firecrawl enumerates **all sources that have failed so far** and **the new ones to try**. This file is the static seed: routes measured dead on this project. Copy the relevant rows into every briefing, then append this lookup's own failures as they happen. The full briefing template is in `mcp-playbook.md`.

## Seed: measured dead routes

| Site | Route | Failure | What to do instead |
| --- | --- | --- | --- |
| musicbrainz.org | `ws/2` search via a plain web-fetch tool | 503 (measured) | Direct API fetch with pacing and 503 retry; else Firecrawl/Tavily on `musicbrainz.org/release/<mbid>` |
| allmusic.com | plain fetch | 403 bot block | Firecrawl scrape (OpenCode: just-scrape) |
| prestomusic.com (formerly prestoclassical.co.uk) | product page via plain fetch | 403 Cloudflare challenge | Read `Recorded:` lines from the search snippet; else Firecrawl scrape (proven 2026-11-25) |
| europadisc.co.uk | any fetch | Cloudflare challenge; retrying does not help | Move to the next rank |
| jpc.de | any fetch | 451 | Move to the next rank |
| gramophone.co.uk | any fetch | Cloudflare | Move to the next rank |
| musicwebinternational.com | Tavily extract | Returns navigation menus and sidebars only (measured 2026-11-20) | Built-in fetch in text mode, or Firecrawl scrape |
| orfeomusic.de | cold scrape | JS shell, zero catalogue links (measured 2026-11-18: same fetch empty once, full later) | Firecrawl scrape, retry once before calling it empty |
| worldcat.org | any fetch | JS-rendered + sign-in wall | Leave OCLC blank; never guess |
| coverartarchive.org | `/release/<mbid>` | 404 for many new releases | Next cover rank |
| discogs.com | API search | Needs a user token — none in this skill, ever | Exa/Tavily scoped search + page scrape |
| discogs.com | release page via Tavily extract | "Failed to fetch url" (measured 2026-11-25) | Firecrawl scrape (proven same day: full tracklist + credits) |
| Exa search | `includeDomains` scope | Returned out-of-scope and banned domains anyway (measured 2026-11-25) | Check every hit's domain client-side; discard banned hits unread |
| Unscoped long search phrases | Exa/Tavily without include-domains | MapQuest / LinkedIn noise (measured 2026-11-22) | Scope to the rank-1 site |

Banned domains (streaming + label sites) are not failures — they are never tried at all. List them separately in the briefing (`exclusions.md`).

## Dynamic ledger format

One line per failure, appended in order:

```
<site> via <tool + route>: <reason> (<date or "this run">)
```

Example mid-lookup ledger:

```
FAILED SO FAR (do not retry these routes):
- musicbrainz.org ws/2 search via built-in fetch: 503 (this run)
- discogs.com/release/21069511 via tavily extract: empty body (this run)
- europadisc.co.uk via firecrawl scrape: Cloudflare challenge (seed; retry does not help)
- jpc.de: 451 (seed)
- gramophone.co.uk: Cloudflare (seed)
```

Rules:

- The ledger only grows within a lookup. Carry it whole into every subsequent MCP call.
- A failed route is never re-delegated. The same URL through a different route is a new route, allowed once.
- When every rank is exhausted, report `<field>: not found` with the full ledger. Never guess.
