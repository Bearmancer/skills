# Extract: tracker JSON, artist classification, cast sheet

The contracts the old script layer enforced, now built by hand from the fetched credits. `file-tracker-request` consumes the tracker JSON unchanged (`format_contents.py` reads `works[].cd` and `works[].works[].composer/work`).

## Tracker-extract JSON schema

```json
{
  "release": { "id": "...", "title": "...", "artist": "...", "date": "...",
               "barcode": "...", "label": "...", "catalogue": "..." },
  "media": 14,
  "tracks": 152,
  "distinct_artists": 40,
  "by_role": { "1": 30, "4": 8, "5": 2 },
  "dual_credit_review": ["Name"],
  "conductor_review": ["Name"],
  "artists": [ { "name": "...", "role": 1, "type": "Person|Orchestra|...|null", "id": "mbid-or-name" } ],
  "works": [ { "cd": 1, "mb_title": "disc title or null",
               "works": [ { "composer": "...", "work": "..." } ] } ]
}
```

- Roles: **1 Main** (orchestras, choirs, soloists), **4 Composer**, **5 Conductor**.
- `artists` sorted by (role, name lowercased); `by_role` counts the rows; `media`/`tracks` are totals.
- `dual_credit_review`: names credited as both composer and performer/conductor. `conductor_review`: Main-row persons whose disambiguation says conductor. Resolve both before filling a request (`sites.md`, MusicBrainz).
- Discogs rows carry `type: null` and `mb_title: null`; `id` is the Discogs artist id or the name.

## Building it from MusicBrainz

Fetch `/release/<mbid>?inc=recordings+artist-credits+labels` (`sites.md`).

1. Walk each medium's tracks. Skip tracks whose composer credit is `[no artist]` and titles `applause` / `intro` / `introduction`.
2. Track-level artist-credit → composer role; recording-level artist-credit → performer role. Track title falls back to `recording.title` when omitted.
3. Classify each distinct artist (key: MB artist id, else name):
   - composer role present → **4**; if also performer → add to `dual_credit_review`.
   - else, name in the explicit conductor list (when soloists also conduct: Ashkenazy, Perlman, Zukerman) → **5**; with no explicit list, a disambiguation ending in "conductor" with no and/&/,// → **5**.
   - else → **1**; if performer role and disambiguation contains "conductor" → add to `conductor_review`.
4. Works per disc: merge consecutive tracks with the same composer and the same stripped work title into one work (Work grouping below). `cd` = medium position.
5. Facts: first label-info's label name and catalog-number; first release-event date; barcode; release artist credit joined with its join phrases.

## Building it from Discogs (scraped page)

1. Main artists → performer. Credits with "Compos…" roles → composer; "Conduct…" → conductor; instrument/performer roles and ensemble names → performer. Skip production roles (Cast sheet classification below).
2. Tracklist position `CD n-t` / `Disc n-t` / `n-t` gives the disc number (default 1). Index tracks expand to their sub-tracks; headings name the disc section.
3. Per-track composer: track-level "Composed By" credits; else the track's main artists; else the release's sole composer; else the section heading.
4. Classification and dual-credit flags as above (conductor role present → 5 unless also composer).
5. Facts: first label's name/catno; `released` date; first Barcode identifier; main artists joined.

## Work grouping

- Strip movement suffixes: `Symphony No. 5: I. Allegro` → `Symphony No. 5`. Repeatedly drop the last `: <tail>` when the tail starts with a letter or a numbered movement (`1. `, `I.`); also strip rip noise like `(–12 dB)`.
- Consecutive tracks with identical (composer, stripped work) merge into one work entry; a single-track group keeps its full stripped title.

## Cast sheet

Three groups: **Composers, Orchestras, Soloists**.

From MusicBrainz:
- Composers: track-level credit persons (skip junk names and ensemble types).
- Orchestras: recording-level credits whose artist type is Orchestra / Choir / Ensemble / Chorus.
- Soloists: recording-level Person credits whose surname matches no lead or composer surname; plus release-credit persons who are neither composer nor conductor (a release-credit person who is neither composed nor conducted performed on it). Surname = last word after dropping particles (de, van, von, der, den, di, da, du, le, la, el, al).
- Junk names skipped: `[no artist]`, `[unknown]`, `[traditional]`, `[anonymous]`.

From Discogs / AllMusic free-text roles, classify each credit line:
- role contains composer/composed → Composers.
- role matches producer, engineer, photography, design, notes, writer, text, interview, funding, remaster, transferring, editor, archivist, coordination, music director/supervisor → **drop**.
- role says orchestra/choir/chorus/ensemble, or the name looks like an ensemble (orchestra, philharmonic, sinfonia, choir, chorus, chamber ensemble, …) → Orchestras.
- role contains conductor → **drop** (the conductor is not a cast-sheet group).
- performer/solo/instrument role, or an instrument/voice role (piano, violin, soprano, tenor, …) → Soloists.
- anything else → drop.

Name cleaning: NFKC-normalize; strip disambiguation tails like `(2)`, `(pianist)`, `(…-musician)`; collapse whitespace. Use the credited name (Discogs ANV) when present.

Sheet format:

```
# <release title verbatim, errors included>

Source: <MusicBrainz|Discogs|AllMusic> — <release URL>

Composers
<one bare name per line, alphabetized, deduplicated>

Orchestras
...

Soloists
...
```

Empty group reads `(none found)`. Never a role suffix after a name. In OpenCode the sheet goes to `%USERPROFILE%\Desktop\md-library\<site>\<slug>.md` (slug: title lowercased, non-alphanumerics to `-`, cut at 60 chars); in chat, output it in the reply. Never hand-edit: fix the extraction and regenerate from the source. Sources disagree by design — Discogs under-credits, AllMusic omits composers, MusicBrainz carries the booklet data — so each source gets its own sheet and the second source is reconciled, not merged silently.
