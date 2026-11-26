# Routing matrix

Find the row for the metadata need. Query its sources in rank order, and move down a rank only when the current source has no row, is blocked, or lacks the field. Say which source failed, and append it to the failure ledger. Bans: `exclusions.md`. Per-site traps and page patterns: `sites.md`. How to drive the search MCPs: `mcp-playbook.md`.

## Stop rule (every row)

- **Stop** when the row's stop condition holds. Report the value with its citation. Do not cross-check a lower rank unless the owner asks for a cross-check.
- **Conflict**: if two sources at the same rank disagree, report both values with their citations in one line. Never pick one silently. A lower rank consulted anyway is reported the same way, in one line.
- **Exhausted**: if every rank has been tried, report `<field>: not found` and list the sources tried. Never guess a value.
- **Fact versus write**: a fact question ends at the stop condition. A tag write follows `tagging.md` (OpenCode only), and DATE stays as Toolbox writes it, even when a higher rank here disagrees.

## Matrix

| Need | 1 | 2 | 3 | 4 | 5 | Stop when |
| --- | --- | --- | --- | --- | --- | --- |
| Release identification (MBID, Discogs id, edition) | MusicBrainz search API (`barcode:`, `catno:`, `release:` + `artist:`; endpoints in `sites.md`) | Discogs release search via Exa/Tavily scoped to `discogs.com`, then scrape the release page | Presto (newest boxes appear here first) | Europadisc / Horizons | - | One release whose disc and track layout matches the files or the asked box. When several editions exist, record which edition you chose and why. |
| Credits / cast sheet | MusicBrainz release credits (API or release page) | Discogs release page credits via MCP scrape (under-credits boxes) | AllMusic credits tab via Firecrawl (never lists composers) | Retailer contents (Presto, Europadisc, Horizons) | MusicWeb review | Every name traces to a credit line. When a second source was used, it is reconciled. |
| Recording date and venue | MusicWeb contents list or review `rec.` lines | Retailer contents (Presto, Europadisc), booklet notes | Allowed label catalogue page (Naxos, Orfeo, Hänssler, CPO, Hyperion, Chandos, BIS) | MusicBrainz recording relations (`begin`/`end`, `recorded at` place; `sites.md`) | Discogs release notes / `Recorded At` credits | Date and venue for the asked work, both from one source. |
| Track list / contents | MusicBrainz media + tracks (API) | Discogs tracklist via MCP scrape | Europadisc / Horizons | MusicWeb contents page | Presto, then AllMusic | Every disc's contents listed, with the per-disc split confirmed. |
| Label and catalogue number | MusicBrainz search / release facts | Discogs | Presto | Allowed label catalogue | - | Label and catalogue number from a database or a retailer, never from a blog post. |
| Cover image | Cover Art Archive (`coverartarchive.org/release/<mbid>`) | Discogs `og:image` | Presto (resize trick in `sites.md`) | Europadisc / Horizons | - | HTTPS 200 with an image content-type. OPS needs a rehosted copy of any Discogs image. |
| DVD / concert-video chapter data | The disc folder's `tags.json` and its scans (`Scans\`) | Allowed video-label catalogue (Arthaus, Unitel, C Major), medici.tv | Venue archives (Southbank, Concertgebouw, RFH) | Reviews (MusicWeb, NRC) | Retailer track lists (CDJapan, Oricon), then duration matching | Every chapter has a value with `confidence` and `evidence`, or a flag for the owner (`dvd-tags-json.md`). |

A need not in the matrix: use the release-identification order and propose the new row in the reply.

## Failure ledger

- Every failed source is appended with its route and reason: `<site> via <tool/route>: <reason>`.
- The whole ledger travels with every Exa/Tavily/Firecrawl delegation, together with the banned list and the next candidates (`mcp-playbook.md` template, seed in `failures.md`).
- A failed route is never retried. The same URL through a different route (Tavily extract → Firecrawl scrape) is a new route, allowed once.

## Finding and fetching pages

MCPs first: Exa, Tavily and Firecrawl before the built-in web search/fetch. The built-ins are the fallback when an MCP is not connected or its route failed.

- Discovery: Exa or Tavily search for `"<work> <performer> <label> <catalogue>"`, with the streaming and label domains in `exclusions.md` excluded. Scope to the rank-1 site with the tool's include-domains filter: a long unrestricted phrase returns MapQuest and LinkedIn noise (measured 2026-11-22). A MusicWeb hit's search snippet often already holds the `rec.` line; a Presto snippet often holds the `Recorded:` line. Read snippets before fetching.
- Static pages: Tavily extract first; built-in fetch as fallback. Exceptions — Discogs release pages: Firecrawl first (Tavily extract measured dead, `failures.md`); old table-layout pages (MusicWeb): Tavily extract returns only the site's navigation menus and sidebars there (measured 2026-11-20), so use the built-in fetch in text mode or Firecrawl scrape.
- JS-rendered pages (orfeomusic.de and other label shops): Firecrawl scrape renders them; retry once before calling the page empty — a cold scrape returns a shell.
- Bot-blocked (401/403/429/503, a challenge page, an empty body): walk the fetch ladder in `mcp-playbook.md` and stop at the first fetch that holds the content.
- MusicBrainz: direct API fetch, paced at 1 request/s, retrying 503 with growing delay; a busy reply is never read as a result. When the API stays blocked, read the human release page (`musicbrainz.org/release/<mbid>`) through Firecrawl or Tavily extract instead. Endpoints and traps: `sites.md`.
