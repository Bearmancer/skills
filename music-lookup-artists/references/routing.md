# Routing matrix

Find the row for the metadata need. Query its sources in rank order, and move down a rank only when the current source has no row, is blocked, or lacks the field. Say which source failed. Bans: `exclusions.md`. Per-site traps and page patterns: `sites.md`.

## Stop rule (every row)

- **Stop** when the row's stop condition holds. Report the value with its citation. Do not cross-check a lower rank unless the owner asks for a cross-check.
- **Conflict**: if two sources at the same rank disagree, report both values with their citations in one line. Never pick one silently.
- **Exhausted**: if every rank has been tried, report `<field>: not found` and list the sources tried. Never guess a value.
- **Fact versus write**: a fact question ends at the stop condition. A tag write follows `tagging.md`, and DATE stays as Toolbox writes it, even when a higher rank here disagrees.

## Matrix

| Need | 1 | 2 | 3 | 4 | 5 | Stop when |
| --- | --- | --- | --- | --- | --- | --- |
| Release identification (MBID, Discogs id, edition) | `mb.py search` (`barcode:`, `catno:`, `release:` + `artist:`) | `discogs.py search --barcode/--catno` | Presto (newest boxes appear here first) | Europadisc / Horizons | - | One release whose disc and track layout matches the files or the asked box. When several editions exist, record which edition you chose and why. |
| Credits / cast sheet | `mb.py cast` / `mb.py tracker` | `discogs.py cast` / `discogs.py tracker` (under-credits boxes) | `allmusic.py` (never lists composers) | Retailer contents (Presto, Europadisc, Horizons) | MusicWeb review | Every name traces to a credit line. When a second source was used, it is reconciled. |
| Recording date and venue | MusicWeb contents list or review `rec.` lines | Retailer contents (Presto, Europadisc), booklet notes | Allowed label catalogue page (Naxos, Orfeo, Hänssler, CPO, Hyperion, Chandos, BIS) | `mb.py dates` (relation `begin`/`end`, `recorded at` place) | Discogs release notes / `Recorded At` credits | Date and venue for the asked work, both from one source. |
| Track list / contents | `mb.py tracker` (works per disc) | `discogs.py tracker` | Europadisc / Horizons | MusicWeb contents page | Presto, then AllMusic | Every disc's contents listed, with the per-disc split confirmed. |
| Label and catalogue number | `mb.py search` / `mb.py tracker` facts | Discogs | Presto | Allowed label catalogue | - | Label and catalogue number from a database or a retailer, never from a blog post. |
| Cover image | Cover Art Archive (`coverartarchive.org/release/<mbid>`) | Discogs `og:image` | Presto (resize trick in `sites.md`) | Europadisc / Horizons | - | HTTPS 200 with an image content-type. OPS needs a rehosted copy of any Discogs image. |
| DVD / concert-video chapter data | The disc folder's `tags.json` and its scans (`Scans\`) | Allowed video-label catalogue (Arthaus, Unitel, C Major), medici.tv | Venue archives (Southbank, Concertgebouw, RFH) | Reviews (MusicWeb, NRC) | Retailer track lists (CDJapan, Oricon), then duration matching | Every chapter has a value with `confidence` and `evidence`, or a flag for the owner (`dvd-tags-json.md`). |

A need not in the matrix: use the release-identification order and propose the new row in the reply.

## Finding and fetching pages

- Discovery: run `tvly search "<work> <performer> <label> <catalogue>"` or the agent's web search, with the streaming and label domains in `exclusions.md` excluded. A MusicWeb hit's search snippet often already holds the `rec.` line. Read it before fetching.
- Static and old table-layout pages (MusicWeb): use `webfetch` in text format. `tvly extract` returns only the site's navigation menus and sidebars there (measured 2026-11-20).
- JS-rendered pages (orfeomusic.de and other label shops): retry once before calling the page empty. A cold scrape returns a shell.
- Bot-blocked (401/403/429/503, a challenge page, an empty body): walk the bot-block chain in `rigorous-research/references/fleet.md` and stop at the first fetch that holds the content.
