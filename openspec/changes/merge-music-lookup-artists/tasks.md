# Tasks

## 1. Clients (`scripts/`)

- [x] 1.1 Create `music-lookup-artists/scripts/` and copy `credits_lib.py` and `allmusic.py` from `lookup-music-artists/scripts/`; verify `uv run scripts/allmusic.py --help` exits 0
- [x] 1.2 Add `tracker_json(facts, rows, works)` to `credits_lib.py` producing the `extract_release_artists.py` output keys; verify keys equal the old script's output keys
- [x] 1.3 Create `mb.py` from `file-tracker-request/scripts/extract_release_artists.py` with subcommands `search` and `tracker` (via `tracker_json`), UA `set_useragent("music-lookup-artists", "1.0")` with no contact; verify `tracker --mbid 09268153-9c28-4221-b571-ec458fb25e5b` output keys and artist rows equal the old script's for the same MBID, and `rg '@' scripts/mb.py` finds no email
- [x] 1.4 (Verified: musicbrainzngs `_safe_read` retries 500/502/503 eight times with growing delay, then raises NetworkError; no wrapper added) Add explicit 503 retry with backoff around every musicbrainzngs call; verify by reading the code path that a busy reply raises after the last retry and is never parsed as a result
- [x] 1.5 Add `mb.py cast` (grouping from `lookup-music-artists/scripts/musicbrainz.py`, display names, writes `Desktop\md-library\musicbrainz\<slug>.md` through `credits_lib.write_md`); verify on one known release that the sheet matches the old `musicbrainz.py` sheet line for line
- [x] 1.6 (Result 2026-11-20: relations DO come back - Kleiber DG fc7085ae… gave begin/end + 'recorded at' Musikverein; the old 'release GET returns empty' note is wrong when artist-rels/place-rels are paired with recording-level-rels) Run the D3 include check: release GET with `recordings recording-level-rels artist-rels place-rels` on a release known to carry "recorded at" relations; record whether relations come back
- [x] 1.7 Add `mb.py dates` (per track: relation `begin`/`end`, place name; browse-by-release fallback when embedded recordings have no relations); verify the Fey Vol. 18 MBID prints 11 tracks with empty date/venue and the relation-bearing release prints its dates and venue
- [x] 1.8 Confirm `python3-discogs-client` package name, `Client(user_agent, user_token=...)`, `backoff_enabled` and `search(type="release", barcode=..., catno=...)` against its README; record the confirmed API in the script header
- [x] 1.9 Write `discogs.py` on `python3-discogs-client` with `search`, `cast` (grouping unchanged from old `discogs.py`, via `release.data`) and `tracker` (via `tracker_json`); no token → search exits non-zero naming `DISCOGS_TOKEN`; verify `cast` on a known release equals the old `discogs.py` sheet, `tracker` keys equal `mb.py tracker` keys, and `search` without a token prints the token message

## 2. Skill documents

- [x] 2.1 Write `references/routing.md` with the matrix rows from the source-routing spec and stop rules from design D2; verify every spec row name appears as a row and every row has a stop rule
- [x] 2.2 Write `references/exclusions.md`: the 7 banned label families with their domains, Amazon/Guardian ban with one-fetch owner override, pointer to rigorous-research "Streaming ban"; verify no streaming domain list is copied (`rg 'spotify' references/` finds only the pointer line, if any)
- [x] 2.3 Write `references/sites.md` from `file-tracker-request/references/sources.md` (page patterns, access traps), `lookup-music-artists/SKILL.md` per-site facts, and `~/.agents/refdocs/musicbrainz.md` API/box-MBID content; verify each source file's trap bullets are present or consciously dropped (list drops in the commit message)
- [x] 2.4 Write `references/tagging.md` from `classical-audio-tagging/SKILL.md` workflow and the refdoc's tagging contract, dropping its Wikipedia references; verify each tag-writing spec requirement maps to a step
- [x] 2.5 Write `references/dvd-tags-json.md` from `dvd-concert-curation/references/metadata-research.md`, with step 3's source list replaced by a pointer to routing.md (Decca removed per ban); verify schema, join rule and reconciliation sections are intact
- [x] 2.6 Write `SKILL.md` (router, design D6 description, one done-when per branch, stop-rule stated in the fact branch, commands for `mb.py`/`discogs.py`/`allmusic.py`); verify frontmatter parses (`uv run --with pyyaml python -I -c` load), the file stays under 6 KB, and `rg -i wikipedia music-lookup-artists` returns nothing

## 3. Scrub other skills

- [x] 3.1 `file-tracker-request`: delete `references/sources.md` and `scripts/extract_release_artists.py`; replace SKILL.md source/extraction sections (including the Wikipedia/Amazon/Guardian sentence) with pointers to `music-lookup-artists` (`references/routing.md`, `scripts/mb.py tracker`, `scripts/discogs.py tracker` when MB has no row); verify `rg -i 'musicbrainzngs|sources\.md|extract_release|wikipedia' file-tracker-request` returns only pointer lines
- [x] 3.2 `rigorous-research`: replace `music/rules.md` "## Discography" with a pointer line; repoint `classical/sources.md` item 5 and `popular/sources.md` item 1; leave the `- Domains,` line and composer ban list untouched; verify `uv run` of a one-liner calling `domains.banned_hosts()` and `domains.prompt_block("music/classical")` succeeds and the host tuple is unchanged
- [x] 3.3 `dvd-concert-curation`: copy `~/.agents/skills/dvd-concert-curation` into `Dev\Skills`, delete `references/metadata-research.md`, repoint SKILL.md step 1 and Files list; verify copied file count and byte total equal the original before step 4.2
- [x] 3.4 Delete `Dev\Skills/lookup-music-artists` and `Dev\Skills/classical-audio-tagging`; delete `~/.agents/refdocs/musicbrainz.md` after confirming 2.3/2.4 carry its content, and delete `~/.agents/refdocs/wikipedia.md`; verify the paths no longer exist

## 4. Links and integration

- [x] 4.1 Grep `~/.agents`, `~/.claude`, `~/.config/opencode`, `Dev\Skills` and project memory for `lookup-music-artists|classical-audio-tagging|metadata-research\.md|refdocs[\\/]musicbrainz|refdocs[\\/]wikipedia|extract_release_artists`; repoint every hit; verify the grep returns zero hits outside `openspec/changes/`
- [x] 4.2 Junctions: create `~/.agents/skills/music-lookup-artists` → `Dev\Skills\music-lookup-artists`; replace the real `~/.agents/skills/dvd-concert-curation` with a junction to `Dev\Skills\dvd-concert-curation`; remove the old two junctions and their `.claude\skills` mirrors, add mirrors for the new ones; verify each junction resolves (`Get-Item` Target) and `SKILL.md` reads through it
- [x] 4.3 (2026-11-21: tvly search -> MusicWeb HC16001 contents via webfetch: 'Symphony No. 102 rec. May 2012 Gesellschaftshaus Pfaffengrund'; 2 calls, rank 1, 0 mb.py calls, no banned fetch) Integration check: from the router alone, answer "recording date of Fey's Haydn 102 (Hänssler 98582)"; verify it ends at MusicWeb/Presto (May 2012, Gesellschaftshaus Pfaffengrund) with no banned-label fetch and at most one `mb.py` call
- [ ] 4.4 Commit in `Dev\Skills` (including `openspec/`) and push to Bearmancer/skills main; verify `git status` clean and `git log origin/main -1` equals local HEAD

## Workflow follow-up

- Update project memories #258 (junction list and skill count), and any memory naming the old skills, after 4.2.
- Archive the change with `openspec archive merge-music-lookup-artists` after the owner reviews the result.
