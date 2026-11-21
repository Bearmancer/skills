---
name: music-lookup-artists
description: "Use for any music metadata lookup or write: recording date or venue, credits or a cast sheet (Composers/Orchestras/Soloists), release/MBID/Discogs/catalogue identification, track lists, cover images, artist extraction for a tracker request, tagging classical FLAC via Toolbox, and DVD concert tags.json research. Triggers on a MusicBrainz, Discogs or AllMusic URL/id."
---

# music-lookup-artists

This skill is the single home for music metadata: where to look, in what order, when to stop, what is banned, the scripts that fetch, and how results are written. Pick the branch, read only its files, and stop at the branch's done line.

The decisive rule: **a lookup ends at the first source that answers it** (`references/routing.md`, Stop rule). A booklet-derived page that gives the date and venue is the answer. Do not then go on to query MusicBrainz.

## Scripts

Run them as `uv run <skill dir>/scripts/<script>.py <subcommand> ...`. Each script declares its own dependencies, so never hand-roll `curl` or urllib against these sites.

| Script | Subcommands | Library and notes |
| --- | --- | --- |
| `mb.py` | `search`, `tracker`, `cast`, `dates` | musicbrainzngs: 1 req/s, 503 retry built in |
| `discogs.py` | `search`, `tracker`, `cast` | python3-discogs-client: 429 backoff. Search needs `DISCOGS_TOKEN` |
| `allmusic.py` | `<album-url-or-mw-id>` | direct fetch, then `firecrawl`. Lists no composers |

JSON goes to stdout or to `--out FILE`. `tracker` gives the same keys from both `mb.py` and `discogs.py`.

## Branches

1. **Answer a fact** (recording date and venue, label, catalogue, edition, track list).
   Read `references/routing.md` and `references/exclusions.md`. Open `references/sites.md` only for the site you are about to query.
   *Done when:* the row's stop condition holds and the answer carries its citation, or the field is reported as not found with the sources tried.

2. **Cast sheet** (Composers / Orchestras / Soloists).
   Run `mb.py cast <mbid>`, `discogs.py cast <id>` or `allmusic.py <url>`. Each writes `%USERPROFILE%\Desktop\md-library\<site>\<slug>.md`.
   The sheet has three headings, with one bare name per line, alphabetized and deduplicated. It never shows a role after a name (`Byron Janis piano` is wrong), and an empty group reads `(none found)`.
   Then review the file against the release page (leak directions are in `references/sites.md`) and fix names in place. Several sources each go to their own `<site>` folder, and they disagree by design: Discogs under-credits, AllMusic omits composers, MusicBrainz carries the booklet data.
   *Done when:* every name traces to a credit line, every performer credit is either listed or consciously dropped, and a second source is reconciled.

3. **Tracker extract** (artist rows and the per-disc work list for `file-tracker-request`).
   Run `mb.py tracker <mbid> [--conductor NAME] --out extract.json`. Roles: 1 Main, 4 Composer, 5 Conductor. When MusicBrainz has no row, run `discogs.py tracker <id>`. Check `dual_credit_review` and `conductor_review`, and cross-check composers against retailer contents.
   *Done when:* the JSON is written and every review list is resolved.

4. **Tag FLAC** (classical library). Follow `references/tagging.md`: fresh exe, dry run, backup, owner gate, apply, mutagen proof.
   *Done when:* the tags on disk match the approved plan.

5. **DVD tags.json research.** Follow `references/dvd-tags-json.md`. Merging and naming stay in `dvd-concert-curation`.
   *Done when:* every chapter has a value with confidence and evidence, or a flag for the owner.

## Files

- `references/routing.md`: the matrix (need, ranked sources, stop rule), plus discovery and fetch notes.
- `references/exclusions.md`: banned label sites, banned hosts, and the pointer to the streaming ban.
- `references/sites.md`: per-site facts, page patterns and traps.
- `references/tagging.md`: Toolbox FLAC workflow, the field contract, box MBIDs.
- `references/dvd-tags-json.md`: tags.json schema, join rule, research method.
