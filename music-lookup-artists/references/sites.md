# Sites: facts, page patterns, traps

## MusicBrainz (open API — no credentials)

Base `https://musicbrainz.org/ws/2`, `fmt=json`, User-Agent `music-lookup-artists/1.0` (never a personal address). Pace at 1 request/s; on 500/502/503 wait and retry with growing delay (up to 8 tries). A busy reply is never read as a result. Never fire MB calls in parallel.

| Need | Endpoint |
| --- | --- |
| Search releases | `/release?query=<lucene>&limit=25` |
| Release, media, credits, labels | `/release/<mbid>?inc=recordings+artist-credits+labels` |
| Recording dates and venues | `/release/<mbid>?inc=recordings+recording-level-rels+artist-rels+place-rels` |
| Huge boxes without embedded relations | `/recording?release=<mbid>&inc=artist-rels+place-rels&limit=100&offset=N` (browse; not position-ordered — join by recording MBID) |
| Cover | `https://coverartarchive.org/release/<mbid>` (404 for many new releases) |

- Lucene: `barcode:`, `catno:`, `release:` (title only, no wildcards), `artist:`. A disc titled `Symphony no. 5` is missed by `release:Mahler` — search `artist:"<conductor>" AND release:"<work title>"`. Quote handling varies by fetch tool; when a quoted query gets mangled, send the query string as a file or a request body, not through a shell.
- JSON shape: `media[].tracks[]`; a track's `title` is omitted when it equals the recording title (106 of 152 tracks on the Végh box) — fall back to `recording.title`. Artist credits are arrays of `{name, artist, joinphrase}`; the credited name is `name` (it can differ from `artist.name`).
- Release convention: the track-level artist-credit is the composer; recording-level credits mix soloists and ensembles (split by artist type). A second conductor credited only on some discs can leak into Soloists — review Soloists against the release page.
- Dual credit: MB co-credited Maazel as composer on twelve Serge Lama chansons (the Cleveland CBS box), which moved him out of the Conductor row. When the set's named conductor picks up a composer credit on a subset, keep him as Conductor once the subset is verified against retailer contents. Flag such names in `dual_credit_review` / `conductor_review` (`extract.md`). Pass an explicit conductor when soloists also conduct (Ashkenazy, Perlman, Zukerman).
- Several MB editions of one box: pick the one a retailer corroborates. The RSO Berlin set has two 14-disc entries, and only barcode ELQ4844904 matches Presto. Record which edition you used.
- Recording relations: relation dates are `begin`/`end`, never `begin-date`. `recording-level-rels` is a 400 on the recording resource — it belongs on the release GET. Dated `recorded at` example: Kleiber DG `fc7085ae-721c-4d39-a124-8a07a9c924da` (1974-03..04, Musikverein). Huge boxes (240/330-CD) embed recordings without relations; page the recording browse instead.
- No MB row (archival and radio boxes often have none): run several query variants and record their counts, so that "no MB row" is a measured claim. Then build rows from Discogs and retailer contents.
- MB track-level composer credits contain real errors. Cross-check composers against a retailer contents listing before posting.
- MB search through a plain web-fetch tool returns 503 (measured). Use a direct API fetch with pacing; when that stays blocked, read the human page `musicbrainz.org/release/<mbid>` through Firecrawl or Tavily extract.

## Discogs (via Exa / Tavily / Firecrawl — no token, ever)

- Find the release: Exa or Tavily search scoped to `discogs.com` (`<artist> <title> <label> <catalogue>`), or a barcode/catno query. Read the returned titles before calling a hit or a miss: search never reports "no results" — an unmatched query returns fuzzy rows (a Végh box query returned Händel and DJ Smallcock).
- Read the release: scrape `https://www.discogs.com/release/<id>` — Firecrawl first (proven 2026-11-25: full tracklist + credits); Tavily extract fails on release pages ("Failed to fetch url", measured). Page anatomy: title and main artists; tracklist with per-track credits; a Credits section listing every credited name with free-text roles; label, catalogue, barcode, country, release date; `og:image` cover.
- Credits are free-text roles ("Conductor", "Composed By", "Piano", "Orchestra"). Main artists carry no role, so ensembles are detected by name. Classification rules: `extract.md`.
- Discogs under-credits box sets: the Bernstein Live box lists 12 of 19 soloists. Use it as the tracklist spine and the per-disc split, not as complete credits.
- Brand-new boxes are often missing from Discogs search. Use Presto as the fallback for an absent row only.
- Discogs has no recording dates beyond release notes / `Recorded At` credits.
- Proven box releases (`discogs.com/release/<id>`):
  - Mehta: Complete Warner 21069511; NYP/IPO/VPO/BPO 14177922
  - Klemperer: Warner Remastered 27439110
  - Ormandy: RCA Minneapolis 24369059; Columbia Legacy 19270408; Columbia Stereo 1964-83 33440513 and 1958-63 29420596
  - Salonen: Complete Sony 13662886
  - van Beinum: Decca/Philips 27459036
  - Mitropoulos: RCA/Columbia 23211068
  - Bruno Walter: Columbia 15554753
  - Previn: Warner HMV/Teldec 20817913; RCA/Columbia 13658873
- OPS rejects Discogs image URLs server-side. Rehost them.

## AllMusic (via Firecrawl; OpenCode: just-scrape)

- AllMusic has no API and blocks plain fetchers (403). Render the album page through Firecrawl (OpenCode host: just-scrape, since Firecrawl is disabled there).
- The Credits tab HTML is in the page: each row is an artist anchor plus a credit-role span. Multi-role credits are comma-stacked ("Interviewee, Piano"), so judge every part.
- AllMusic never lists composers, so fill Composers from the tracklist or another source. "Director" (conductor) rows are dropped, so a conductor who plays (Bernstein at the piano) lands in Soloists correctly.

## Retailers and reviews

- **MusicWeb International**: reviews carry per-work `rec.` lines (date and venue). Box contents pages live under `/classrev/<year>/<Mon>/`, for example `classrev/2020/Nov/Barbirolli-box-9029538608-contents.htm`. These are old http pages whose direct SSL fetch fails, and Tavily extract returns only navigation there — use an http-tolerant fetch (built-in fetch text mode) or Firecrawl scrape. Example: HC16001 (Fey London Symphonies) gives "Symphony No. 102 rec. May 2012 Gesellschaftshaus Pfaffengrund".
- **Presto Classical** (`prestomusic.com`, formerly prestoclassical.co.uk; product pages `prestomusic.com/classical/products/<id>--<slug>`): catalogue number, release date and per-disc tracklist, with the earliest listing for new boxes. A product page's per-work metadata carries `Recorded: YYYY-MM-DD` and `Recording Venue:`, the quickest date and venue answer. Plain fetch gets a 403 Cloudflare challenge: read the `Recorded:` lines from the search snippet, or render through Firecrawl (scrape proven 2026-11-25: full page with Label and Catalogue number lines). `og:image` is a 200 px CloudFront thumbnail whose path is base64 JSON (`{"bucket":"presto-cover-images","key":"<id>.1.jpg","edits":{"resize":{"width":200}}}`). Re-encode it with `width: 800`, then rehost. The search falls back to the section front page when a query misses, so a page full of products is not a search result.
- **Europadisc** (`europadisc.co.uk/classical/<id>/<Slug>.htm`): full per-disc contents. It is often behind a Cloudflare challenge (403), and retrying does not help, so move on.
- **Horizons Music** (`horizonsmusic.co.uk/products/<slug>`): lists every disc as `CD n <timing>`, followed by composer and work. A missed search returns hundreds of unrelated products.
- **Clicmusique**: gives the recording year and venue in a `Recording :` / `Location :` line.
- **classite.com**: performers, venues and recording dates per work, for archival boxes.
- jpc answers 451 to fetches, and Gramophone sits behind Cloudflare.
- Strip `#:~:text=` fragments, `srsltid` tracking parameters (Firecrawl search results carry them) and truncated slugs from URLs; the id alone resolves.
- Discogs search hits can land on `newreleases.discogs.com` with a different release id for another edition (Mehta box: 131294 CD vs 21069511 box). Match the edition to the files before citing.

## Allowed label catalogues

- Naxos publishes distributed labels' catalogues at `naxos.com/individuallabel?labelid=<code>` (Orfeo: `OFO`). Tavily extract reads it cleanly.
- `orfeomusic.de/CatalogueDetail/?id=<cat>` is JS-only. Measured 2026-11-18: the same rendered fetch returned zero catalogue links once and all 6 links later. Retry before calling it empty.
- `haensslerprofil.de/shop/...` gives the full tracklist with timings per release.

## Blog posts and other leads

- A blog post's `Label :` line can be wrong. The Järvi Cincinnati Telarc box shows Decca on the blog but was issued on New Classical Adventure. Take the label from MB or a retailer.
- Forum posts (TalkClassical, Reddit) are leads only. Back every value with a database, retailer or catalogue citation.
- WorldCat is JS-rendered and sits behind a sign-in wall. Leave OCLC blank rather than guess.
