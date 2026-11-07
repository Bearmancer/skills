---
name: lookup-music-artists
description: "Use when the user shares a MusicBrainz, Discogs or AllMusic release URL or id and asks who is on it: extract Composers, Orchestras and Soloists as bare name lists to Desktop\\md-library\\<site>\\<release-slug>.md."
---

# lookup-music-artists

One decisive idea: the output is a **cast sheet**, not a review. Three groups —
Composers, Orchestras, Soloists — one bare name per line, alphabetized, deduped.
No bullet dashes, no commas between entities, never a role after a name
(`Byron Janis piano` is wrong; the role dies at the parser). Source line and a
title heading are the only extra text.

## Workflow

1. Identify the site from the URL/id and run the matching script from `scripts/`
   (bare `python` is blocked on this host — always `uv run`):
   - MusicBrainz: `uv run scripts/musicbrainz.py <url-or-mbid>`
   - Discogs: `uv run scripts/discogs.py <url-or-id>` (optional `DISCOGS_TOKEN`)
   - AllMusic: `uv run scripts/allmusic.py <album-url-or-mw-id>` (uses the
     local `firecrawl` CLI when direct fetch 403s — needs `FIRECRAWL_API_KEY`)
2. Open the written file and **review it against the release page** (known leak
   directions below), then fix names directly in the file. The script output is
   a strong draft, never the final claim.
3. Multiple sources for one release: run each into its own `<site>` subfolder —
   they disagree on purpose (Discogs under-credits, AllMusic omits composers,
   MB carries the box booklet data).

## Per-site facts (hard-won — do not re-derive)

**MusicBrainz** — one request suffices:
`GET /ws/2/release/{mbid}?fmt=json&inc=artists+labels+media+recordings`.
Track-level artist-credit is the composer (classical release convention);
recording-level credits mix soloists and ensembles — split by `artist.type`
(Orchestra/Choir/Ensemble → Orchestras; the release-credit lead, usually the
conductor, and composer names are subtracted from Person → Soloists).
Traps: `recording-level-rels`/`work-level-rels` come back EMPTY on the release
GET; `/js/` and `/ws2/js/` dump endpoints 404 on live; `media` without
`recordings` yields track stubs with no recording objects; 503s under load —
back off. A second conductor credited only on some discs can leak into Soloists
(surname filter catches most variants like bare "Stravinsky"/"Georg Solti").

**Discogs** — `GET api.discogs.com/releases/{id}`, UA required. Credits live in
`tracklist[].extraartists` as free-text roles. Discogs is the **under-credited**
source: box sets frequently omit soloists (the Bernstein Live box lists 12 of 19).
Use it for the tracklist spine; don't trust its completeness.

**AllMusic** — no API, blocks plain fetchers. The Credits tab HTML is in-page
(hidden div; rows = artist anchor + `<span class="artistCredits">roles</span>`,
multi-role comma-stacked like "Interviewee, Piano" — judge every part). AllMusic
never lists composers in Credits; "Director" (conductor) rows are dropped, so
person-who-plays (e.g. Bernstein on piano) lands in Soloists correctly.

## Output contract

- Path: `%USERPROFILE%\Desktop\md-library\{musicbrainz|discogs|allmusic}\<slug>.md`
- Headings `Composers` `Orchestras` `Soloists`, `(none found)` when empty
  (AllMusic always empty Composers — fill it from the tracklist or another source).
- Names keep their native accents; the files are UTF-8 (PowerShell console may
  display them garbled — trust the file, not the terminal).

## Completion criterion

Every name in each list traceable to a credit line on the page, every page
performer-credit either listed or consciously dropped as crew/conductor. When a
second source was used for the same release, reconcile before calling it done.
