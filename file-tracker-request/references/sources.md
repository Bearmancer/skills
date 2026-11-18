# Research sources — where to start

Allowed starting points for release facts (title, year, label, catalogue, barcode,
contents, cover image, credits), in rough order of usefulness for classical box sets:

| Source | URL | What it gives |
| --- | --- | --- |
| Europadisc | `https://www.europadisc.co.uk` | Full retailer contents listing per disc, catalogue, release date, cover image. Often Cloudflare-challenged — if blocked, move on. |
| Discogs | `https://www.discogs.com` | Release page: barcode, label code, SPARS, per-disc timings, full performer credits, images (`og:image`). Search `discogs.com/release/<id>` or the site search. |
| MusicBrainz | `https://musicbrainz.org/ws/2/release/<mbid>?inc=recordings+artist-credits+labels&fmt=json` | The extraction feed: track-level composer credits + recording-level performer credits, media titles, label/catalogue, release events. Cover art via `https://coverartarchive.org/release/<mbid>` (404 on many new releases). |
| MusicWeb International | `https://www.musicwebinternational.com` | Reviews with detailed contents and recording-date context. |
| Presto Classical | `https://www.prestomusic.com/classical` | Catalogue number, release date, full per-disc contents and tracklist, blurb. |
| AllMusic | `https://www.allmusic.com` | Release metadata, credits, review. |
| Horizons Music | `https://www.horizonsmusic.co.uk` | Retailer listing, contents, cover image. |

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
- Brand-new boxes are often missing from Discogs search; Presto has the catalogue
  number, release date and cover first. jpc answers 451 to fetches; MusicBrainz
  search through `webfetch` returned 503 — query it from Python with a User-Agent.
- Presto `og:image` is a 200 px CloudFront thumbnail whose path is base64 JSON
  (`{"bucket":"presto-cover-images","key":"<id>.1.jpg","edits":{"resize":{"width":200},…}}`);
  re-encode with `width: 800` for a usable cover, then rehost.
- MB release JSON for huge boxes embeds recordings without relations; performer
  credits are on the recording entities. Browse JSON serializes relation dates as
  `begin`/`end`, not `begin-date`.
