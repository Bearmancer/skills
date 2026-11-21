# Sites: facts, page patterns, traps

## MusicBrainz (`scripts/mb.py`)

- `mb.py` runs on musicbrainzngs. It paces requests at 1/s and retries 500/502/503 eight times with a growing delay, so never hand-roll `curl` or urllib against `ws/2`. Raw `curl` skips the pacing and trips a server cooldown that lasts seconds to tens of seconds.
- The library reads the XML API: `medium-list` / `track-list` / `label-info-list`, with join phrases as bare strings inside `artist-credit`. A track's `title` is omitted when it equals the recording title (106 of 152 tracks on the Végh box). `mb.py` falls back to `recording.title`.
- Release convention: the track-level artist-credit is the composer, and the recording-level credits mix soloists and ensembles (split by artist type). A second conductor credited only on some discs can leak into Soloists. The surname filter catches most variants, so review Soloists against the release page.
- Dual credit: MB co-credited Maazel as composer on twelve Serge Lama chansons (the Cleveland CBS box), which moved him out of the Conductor row. When the set's named conductor picks up a composer credit on a subset, keep him as Conductor once the subset is verified against retailer contents. `tracker` lists such names in `dual_credit_review` and `conductor_review`. Pass `--conductor` when soloists also conduct (Ashkenazy, Perlman, Zukerman).
- Several MB editions of one box: pick the one a retailer corroborates. The RSO Berlin set has two 14-disc entries, and only barcode ELQ4844904 matches Presto. Record which edition you used.
- Recording relations: a release GET with `recording-level-rels` + `artist-rels` + `place-rels` returns the dated `recorded at` relations (Kleiber DG `fc7085ae-721c-4d39-a124-8a07a9c924da`: 1974-03..04, Musikverein). Huge boxes (240/330-CD) embed recordings without relations; `mb.py dates` then pages the recording browse by release and joins by recording MBID. Browse is not position-ordered. Relation dates are `begin`/`end`, never `begin-date`. `recording-level-rels` is a 400 on the recording resource.
- No MB row (archival and radio boxes often have none): run several query variants and record their counts, so that "no MB row" is a measured claim. Then build rows from `discogs.py tracker` and retailer contents.
- MB track-level composer credits contain real errors. Cross-check composers against a retailer contents listing before posting.
- A quoted query gets mangled by the shell: put it in a file and pass `mb.py search --query-file <path>`.
- MB search through `webfetch` returns 503. Use `mb.py search`.
- Cover Art Archive (`coverartarchive.org/release/<mbid>`) returns 404 for many new releases.

## Discogs (`scripts/discogs.py`)

- `discogs.py` runs on python3-discogs-client, with 429 backoff. Search needs `DISCOGS_TOKEN`, and a release fetch works without it.
- Credits are free-text roles in `tracklist[].extraartists` and in the release `extraartists`. Main artists carry no role, so ensembles are detected by name.
- Discogs under-credits box sets: the Bernstein Live box lists 12 of 19 soloists. Use it as the tracklist spine and the per-disc split, not as complete credits.
- Search never reports "no results": an unmatched query returns fuzzy rows (a Végh box query returned Händel and DJ Smallcock). Read the returned titles before calling a hit or a miss.
- Brand-new boxes are often missing from Discogs search. Use Presto as the fallback for an absent row only.
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

## AllMusic (`scripts/allmusic.py`)

- AllMusic has no API and blocks plain fetchers (403). `allmusic.py` tries a direct fetch, then the `firecrawl` CLI (needs `FIRECRAWL_API_KEY`).
- The Credits tab HTML is in the page: each row is an artist anchor plus `<span class="artistCredits">`. Multi-role credits are comma-stacked ("Interviewee, Piano"), so judge every part.
- AllMusic never lists composers, so fill Composers from the tracklist or another source. "Director" (conductor) rows are dropped, so a conductor who plays (Bernstein at the piano) lands in Soloists correctly.

## Retailers and reviews

- **MusicWeb International**: reviews carry per-work `rec.` lines (date and venue). Box contents pages live under `/classrev/<year>/<Mon>/`, for example `classrev/2020/Nov/Barbirolli-box-9029538608-contents.htm`. Fetch with `webfetch` (text). Example: HC16001 (Fey London Symphonies) gives "Symphony No. 102 rec. May 2012 Gesellschaftshaus Pfaffengrund".
- **Presto Classical**: catalogue number, release date and per-disc tracklist, with the earliest listing for new boxes. `og:image` is a 200 px CloudFront thumbnail whose path is base64 JSON (`{"bucket":"presto-cover-images","key":"<id>.1.jpg","edits":{"resize":{"width":200}}}`). Re-encode it with `width: 800`, then rehost. The search falls back to the section front page when a query misses, so a page full of products is not a search result.
- **Europadisc** (`europadisc.co.uk/classical/<id>/<Slug>.htm`): full per-disc contents. It is often behind a Cloudflare challenge (403), and retrying does not help, so move on.
- **Horizons Music** (`horizonsmusic.co.uk/products/<slug>`): lists every disc as `CD n <timing>`, followed by composer and work. A missed search returns hundreds of unrelated products.
- **Clicmusique**: gives the recording year and venue in a `Recording :` / `Location :` line.
- **classite.com**: performers, venues and recording dates per work, for archival boxes.
- jpc answers 451 to fetches, and Gramophone sits behind Cloudflare.
- Strip `#:~:text=` fragments and truncated slugs from URLs; the id alone resolves.

## Allowed label catalogues

- Naxos publishes distributed labels' catalogues at `naxos.com/individuallabel?labelid=<code>` (Orfeo: `OFO`). `tvly extract` reads it cleanly.
- `orfeomusic.de/CatalogueDetail/?id=<cat>` is JS-only. Measured 2026-11-18: the same firecrawl call (`onlyMainContent: true, waitFor: 5000`) returned zero catalogue links once and all 6 links later. Retry before calling it empty.
- `haensslerprofil.de/shop/...` gives the full tracklist with timings per release.

## Blog posts and other leads

- A blog post's `Label :` line can be wrong. The Järvi Cincinnati Telarc box shows Decca on the blog but was issued on New Classical Adventure. Take the label from MB or a retailer.
- Forum posts (TalkClassical, Reddit) are leads only. Back every value with a database, retailer or catalogue citation.
- WorldCat is JS-rendered and sits behind a sign-in wall. Leave OCLC blank rather than guess.
