# MCP playbook: Exa, Tavily, Firecrawl

Remedial guide. These three replace every credentialed client and are the **first-choice routes** — built-in web search/fetch are fallbacks only. Discogs and AllMusic are read as public pages through them, and MusicBrainz stays a direct open-API fetch. Tool names vary slightly by host (`search` / `web_search_exa`, `tavily_search` / `tavily_extract`, `firecrawl_scrape` / `firecrawl_search`); match by shape, not by exact name. Use whichever are connected.

## What each one is for

### Exa — neural search: find the page when you do not have the URL

- Describe the page you want in plain language; it returns URLs plus text excerpts. Best for discovery: "the Discogs release page for Mehta's Complete Warner Recordings", "a MusicWeb review of the Barbirolli Warner box with recording dates".
- Call shape: **both `query` and `objective` are required** (measured 2026-11-25).
- Scope with `includeDomains: ["discogs.com"]` (or the rank-1 site) and `excludeDomains` from `exclusions.md` — but the scope is not enforced server-side: a discogs.com-scoped search returned warnerclassics.com and prestomusic.com hits (measured 2026-11-25). **Check every hit's domain client-side; discard banned hits unread.** For strict scoping use Tavily search, which honors its domain filter. An unscoped long phrase returns MapQuest/LinkedIn noise (measured 2026-11-22).
- Ask for contents/highlights when the snippet may already answer (a `rec.` or `Recorded:` line). Fetch the full page only when the snippet is not enough.
- Weakness: excerpts of JS-heavy pages can be stale or partial — verify on the scraped page before citing.

### Tavily — search + extract: snippets first, then full text of a known URL

- `search`: ranked snippets. Often the answer is already in the snippet — Presto `Recorded:` lines and MusicWeb `rec.` lines read fine there. Scope with include/exclude domains — **Tavily honors `include_domains` server-side** (measured 2026-11-25, unlike Exa), so prefer Tavily search when strict scoping matters.
- `extract`: full text of a known URL. Good on static pages (Naxos distributed-label catalogues read cleanly).
- Measured failures: on old table-layout pages (MusicWeb) extract returns only navigation menus and sidebars; on Discogs release pages it fails outright ("Failed to fetch url", 2026-11-25) — use Firecrawl there.
- Extract of a JS-only shop returns a shell → Firecrawl.

### Firecrawl — scrape that renders JavaScript and defeats light bot protection

- `scrape`: renders the page (JS shops like orfeomusic.de, Cloudflare-challenged pages like Presto product pages, AllMusic's 403). The render slot of the ladder.
- `search` / `map`: discovery and site-URL enumeration when Exa/Tavily miss. Search proven 2026-11-25 (found the target Discogs release at position 1); its URLs carry `srsltid` tracking parameters — strip them before fetching or citing.
- Costs credits: try Tavily extract or the built-in fetch first; escalate to Firecrawl when they return a shell, a challenge, or nav-only text.
- A cold scrape can return an empty shell once and the full page on retry (orfeomusic, measured 2026-11-18). Retry once before calling a page empty.
- OpenCode host: Firecrawl is disabled (research-rigorously ADR 0036) — `just-scrape` fills this slot. In Claude Chat, Firecrawl is the hosted connector.

## Decision ladder

| Situation | Route |
| --- | --- |
| MusicBrainz data | Direct API fetch, 1 req/s, 503 retry (`sites.md`); if still blocked, Firecrawl/Tavily on the human release page |
| No URL yet | Exa or Tavily search, scoped to the rank-1 site — before any built-in search |
| Know the URL, static page | Tavily extract first; built-in fetch only as fallback |
| Discogs release page | Firecrawl scrape first (Tavily extract measured dead) |
| Know the URL, JS-only or challenged | Firecrawl scrape (retry once on a shell) |
| Old table-layout page (MusicWeb) | Built-in fetch text mode or Firecrawl — never Tavily extract |
| MCP not connected / route failed | Built-in web search/fetch as fallback; append the failure to the ledger |
| Every route blocked | Next rank; append to the ledger; never retry a failed route |

## The delegation briefing (mandatory on every call)

Every Exa/Tavily/Firecrawl call carries this block. It tells the tool's agent **all sources that have failed so far** and **the new ones to try**:

```
GOAL: <exact field(s) needed, e.g. recording date + venue of <work>>
RELEASE: <artist / title / label / catalogue / barcode / MBID or Discogs id, whatever is known>
FAILED SO FAR (do not retry these routes):
- <site> via <tool + route>: <reason>
- ... (every failure this run, plus the relevant seed rows from failures.md)
BANNED (never fetch, cite or link): streaming domains + banned label sites (exclusions.md)
TRY NEXT (in rank order): <new sites/URLs — the ones this call is for>
STOP: first source that answers <row stop condition>. Return the value, its URL, and a
verbatim quote of the supporting line. If none answers, say so and list what you tried.
```

Worked example — date and venue after MB and Discogs failed:

```
GOAL: recording date and venue of Beethoven Symphony No. 9 on the Mehta Complete Warner box
RELEASE: Mehta / Complete Warner Recordings / 21069511 (Discogs), barcode known
FAILED SO FAR (do not retry these routes):
- musicbrainz.org ws/2 via built-in fetch: 503 (this run)
- discogs.com/release/21069511 via tavily extract: empty body (this run)
- europadisc.co.uk: Cloudflare challenge, retry does not help (seed)
- jpc.de: 451 (seed); gramophone.co.uk: Cloudflare (seed)
BANNED: spotify.com, music.apple.com, music.amazon.*, tidal.com, deezer.com, qobuz.com,
idagio.com, naxosmusiclibrary.com, soundcloud.com, pandora.com, youtube.com (facts);
deccaclassics.com, deutschegrammophon.com, sonyclassical.com, warnerclassics.com,
harmoniamundi.com, alpha-classics.com, outhere-music.com, eloquenceclassics.com
TRY NEXT:
1. musicwebinternational.com — search "Mehta Warner box review", read rec. lines in snippets
2. prestomusic.com — product page snippet, Recorded: / Recording Venue: lines
3. warnerclassics.com is BANNED; use a retailer or review that names the label instead
STOP: date and venue for the Ninth from one source; return value + URL + verbatim quote.
```

## Ledger discipline

- Keep the ledger in the conversation as you go: each blocked/empty result appends `<site> via <route>: <reason>`.
- Pass the whole ledger with every next delegation — never let a tool retry a route already listed.
- The same URL through a different route is a new route, allowed once (extract → scrape).
- When every rank is exhausted: `<field>: not found`, full ledger in the reply. Never guess.
