# Research sources — where to start

Allowed starting points for release facts (title, year, label, catalogue, barcode,
contents, cover image, credits). Work down this order — it is the owner's mandated
ranking (owner ruling 2026-11-18), not a suggestion; move to the next only when the
current source has no row or is blocked, and say which failed:

| # | Source | URL | What it gives |
| --- | --- | --- | --- |
| 1 | MusicBrainz | `https://musicbrainz.org/ws/2/release/<mbid>?inc=recordings+artist-credits+labels&fmt=json` | The extraction feed: track-level composer credits + recording-level performer credits, media titles, label/catalogue, release events. Cover art via `https://coverartarchive.org/release/<mbid>` (404 on many new releases). |
| 2 | Discogs | `https://www.discogs.com` | Release page: barcode, label code, SPARS, per-disc timings, full performer credits, images (`og:image`). Search `discogs.com/release/<id>` or the site search. |
| 3 | Europadisc | `https://www.europadisc.co.uk` | Full retailer contents listing per disc, catalogue, release date, cover image. Often Cloudflare-challenged — if blocked, move on. |
| 4 | Horizons Music | `https://www.horizonsmusic.co.uk` | Retailer listing, contents, cover image. |
| 5 | MusicWeb International | `https://www.musicweb-international.com` | Reviews with detailed contents and recording-date context; box contents pages live under `/classrev/<year>/<Mon>/`. |
| 6 | AllMusic | `https://www.allmusic.com` | Release metadata, credits, review. |
| 7 | Presto Classical | `https://www.prestomusic.com/classical` | Catalogue number, release date, full per-disc contents and tracklist, blurb. |

## Page patterns that carry full box contents (proven examples)

Strip `#:~:text=` fragments and truncated slugs; the id alone resolves.

- **Discogs** — `https://www.discogs.com/release/<id>`: tracklist per disc, credits,
  barcode, `og:image`. Known boxes: Mehta Complete Warner Recordings `21069511`;
  Mehta NYP/IPO/VPO/BPO set `14177922`; Klemperer Warner Classics Remastered
  `27439110`; Ormandy RCA Minneapolis `24369059`, Columbia Legacy `19270408`,
  Columbia Stereo 1964–83 `33440513` and 1958–63 `29420596`; Salonen Complete Sony
  `13662886`; van Beinum Decca/Philips `27459036`; Mitropoulos RCA/Columbia
  `23211068`; Bruno Walter Columbia `15554753`; Previn Warner HMV/Teldec `20817913`
  and RCA/Columbia `13658873`.
- **Europadisc** — `https://www.europadisc.co.uk/classical/<id>/<Slug>.htm`, e.g.
  `/classical/123283/Igor_Markevitch:_The_Complete_HMV_Recordings.htm`.
- **Horizons Music** — `https://www.horizonsmusic.co.uk/products/<slug>`: the product
  page lists every disc as `CD n <timing>` followed by composer and work. Examples:
  `riccardo-muti-riccardo-muti-the-complete-warner-symphonic-recordings-91cd-lift-off-lid-box-with-neck`,
  `mariss-jansons-the-oslo-years-boxed-set`.
- **MusicWeb International** — a dedicated contents page per box, e.g.
  `https://www.musicweb-international.com/classrev/2020/Nov/Barbirolli-box-9029538608-contents.htm`.

## Not part of the routine

Do **not** automatically search or fetch:

- Wikipedia
- Amazon
- The Guardian
- UMG label storefronts and their sites (Decca Classics `store.deccaclassics.com`,
  Deutsche Grammophon `store.deutschegrammophon.com`, and siblings)

The user may explicitly point at one of these; that overrides the ban for that one
fetch. Otherwise stay in the list above.

## Known access traps

- Europadisc and Gramophone sit behind Cloudflare browser challenges — a plain fetch
  returns 403 and retrying does not help. Use Presto or Discogs instead, or drive the
  page through the browser MCP if it is already open.
- WorldCat (`search.worldcat.org`) is JS-rendered and gated by a Terms-of-Service /
  sign-in wall; the OCLC field on RED is optional — leave it blank rather than guess.
- Cover Art Archive returns 404 for releases without uploaded art; fall back to a
  Discogs or retailer image and verify HTTPS 200 + image content-type.
- A blog post's `Label :` line can be wrong. The Järvi Cincinnati Telarc box is labelled
  Decca on the blog but was issued on **New Classical Adventure** after the Telarc
  catalogue passed to Concord. Take the label from MusicBrainz or a retailer, not the post.
- The catalogue-number torrent search is decisive but not sufficient: OPS returned 0 for
  `cataloguenumber=234381` while its own group page for that box displays 234381. Run the
  title search as well — that is what found the existing rip on OPS.
- Discogs search never reports "no results" — an unmatched query returns unrelated
  fuzzy rows (a Végh box query returned Händel and DJ Smallcock). Read the returned
  titles before calling anything a hit or a miss.
- Retailer search endpoints fall back to generic listings when the query misses:
  Presto redirected `/classical/search?search=` to the section front page, Horizons
  returned 220 unrelated products. A page full of products is not a search result.
- The label's own site can be JS-only: `orfeomusic.de` returned an error page to a
  plain fetch and a pre-hydration shell to the first scrape. **Retry before calling it
  empty** — measured 2026-11-18: the identical firecrawl call (`onlyMainContent: true,
  waitFor: 5000`) returned 5,953 chars with zero catalogue links on the first attempt
  and 5,202 chars with all 6 links on a later one. A cold fetch of a JS page is a
  timing artefact, not an absent source. Naxos distributes Orfeo and publishes its
  catalogue at `naxos.com/individuallabel?labelid=OFO`; `tvly extract` reads both that
  and `orfeomusic.de/CatalogueDetail/?id=<cat>` cleanly.
- Scrapegraph MCP was down at the transport layer, not the target site: `smartscraper`
  given inline `website_html` and no URL failed with the same
  `SSLV3_ALERT_HANDSHAKE_FAILURE` as a URL fetch. When a scraper errors, test it with
  inline HTML to tell "the site refused" from "the tool cannot reach its own API".
- Brand-new boxes are often missing from Discogs search. When ranks 1–6 have no row,
  jump to Presto (rank 7) as the fallback — it carries the catalogue number, release
  date and cover earliest. This is a fallback for an absent row, not a licence to
  start there. jpc answers 451 to fetches; MusicBrainz search through `webfetch`
  returned 503 — query it from Python with a User-Agent.
- Presto `og:image` is a 200 px CloudFront thumbnail whose path is base64 JSON
  (`{"bucket":"presto-cover-images","key":"<id>.1.jpg","edits":{"resize":{"width":200},…}}`);
  re-encode with `width: 800` for a usable cover, then rehost.
- MB release JSON for huge boxes embeds recordings without relations; performer
  credits are on the recording entities. Browse JSON serializes relation dates as
  `begin`/`end`, not `begin-date`.
