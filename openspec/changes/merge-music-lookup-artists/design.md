# Design

## Context

See proposal.md (Why) for the motivation. Current state that shapes the approach:

- `Dev\Skills` is the Bearmancer/skills repo. Owner skills reach `~/.agents/skills/<name>` through junctions, and `.claude\skills` mirrors them. Third-party skills there are real directories and stay untouched.
- `dvd-concert-curation` is a real directory in `~/.agents/skills` and is not in the repo. Its `scripts/*.ps1` (about 160 KB) read `tags.json` but fetch nothing from the web (grep found no MusicBrainz/Discogs/AllMusic use).
- `rigorous-research/scripts/domains.py` parses two files at runtime:
  - the `- Domains,` line of `music/rules.md` (the streaming ban host list);
  - the `## Composer ban list` section of `music/classical/exclusions.md`.

  It also injects `music/rules.md`, `<domain>/sources.md` and `<domain>/exclusions.md` verbatim into research prompts.
- `file-tracker-request/scripts/extract_release_artists.py` already uses `musicbrainzngs`, with a 4-try retry wrapper. Its UA includes an email address.
- The owner picked the banned labels per label on 2026-11-20 (see the source-routing spec).

## Goals / Non-Goals

**Goals:**
- One skill directory holds every metadata source rule, site trap, client script and write workflow.
- The router stays short. Each branch's material sits in its own reference file, so a date question never loads the tagging workflow.

**Non-Goals:**
- No edit to Toolbox, the rigorous-research scripts or registry, or `domains.py` parsing.
- No generated routing table. The matrix is short enough to maintain by hand.
- No new fetch vendors. The generic fetch ladder (tvly, firecrawl, webfetch) stays owned by `rigorous-research/references/fleet.md`. The matrix points there for bot-blocked pages.

## Decisions

### D1. Skill layout

```
music-lookup-artists/
  SKILL.md                    router: branches (answer a fact, cast sheet, tracker extract,
                              tag FLAC, DVD tags.json), each with a done-when line
  references/routing.md       the matrix: need -> ranked sources -> stop rule
  references/exclusions.md    banned labels + banned hosts; points to rigorous-research for the streaming list
  references/sites.md         per-site traps: MusicBrainz, Discogs, AllMusic, Presto, MusicWeb,
                              Europadisc, Horizons, Naxos/Orfeo, haensslerprofil, Cover Art Archive
  references/tagging.md       FLAC via `toolbox audio tag`: fresh exe, dry-run, backup, gate, verify
  references/dvd-tags-json.md tags.json schema, chapter join rule, research method, reconciliation
  scripts/mb.py               MusicBrainz: search | cast | tracker | dates
  scripts/discogs.py          Discogs: search | cast | tracker (python3-discogs-client)
  scripts/allmusic.py         AllMusic cast sheet (direct, then firecrawl)
  scripts/credits_lib.py      shared name cleaning, grouping, md writer (3 consumers)
```

Alternative considered: one SKILL.md holding everything (about 25 KB). Rejected: branches load what they do not need, and the stop rule gets buried (writing-for-agents: disclose per branch).

### D2. Matrix format: hand-written markdown table

The columns are need / rank 1..n sources / stop rule / notes. The rows come from the source-routing spec. The ranks for "release identification" and "track list" reuse the owner-mandated order from `file-tracker-request/references/sources.md`: MusicBrainz, Discogs, Europadisc, Horizons, MusicWeb, AllMusic, Presto. The "recording date and venue" row ranks sources that copy the booklet first:

1. MusicWeb contents list
2. retailer contents (Presto, Europadisc)
3. allowed label catalogue (Naxos, Orfeo, Hänssler and others)
4. MusicBrainz relations (`mb.py dates`)
5. Discogs notes

Alternative considered: a registry.yaml plus a generator, as in rigorous-research. Rejected: that is two artifacts and a script for about 8 rows.

### D3. One MusicBrainz client: `mb.py` built on musicbrainzngs

`extract_release_artists.py` is the base, because the library already owns transport and rate limiting.

- Add `cast`, which uses the grouping from the deleted `musicbrainz.py` with display names via `credits_lib`.
- Add `dates`, which looks up the release with `recordings`, `recording-level-rels`, `artist-rels` and `place-rels`, reads relation `begin`/`end`, and pages a recording browse by release when the embedded recordings carry no relations (huge boxes).
- Keep `tracker`, whose JSON shape is unchanged.
- Keep `search`.
- Set the UA to `set_useragent("music-lookup-artists", "1.0")` with no contact field.

The retry wrapper stays, and it catches 503s explicitly.

Alternative considered: keep the urllib `musicbrainz.py`. Rejected by the owner ("use py for mb, discogs and other things"), and it duplicates what the library does.

Apply-time check: confirm that `recording-level-rels` returns relations on a release GET when it is paired with `artist-rels`/`place-rels`. The old SKILL.md says the release GET came back empty, while Toolbox's include set gets relations. Test it on release `09268153-9c28-4221-b571-ec458fb25e5b` (expected: no dates) and on one release known to carry relations.

### D3b. Discogs client: `discogs.py` on python3-discogs-client

Rewrite the urllib `discogs.py` on `python3-discogs-client` (the maintained fork; import `discogs_client`):

- `Client("music-lookup-artists/1.0", user_token=os.environ.get("DISCOGS_TOKEN"))`. The library's `backoff_enabled` (default on) handles 429 and Discogs' 60 requests/min authenticated limit.
- Each subcommand reads `release.data`, the raw API dict, so the existing `harvest` and `credits_lib` classification code stays unchanged. The library's object model stays unused.
- `search <query> [--barcode] [--catno]` calls `client.search(type="release", ...)`. Search needs a token, so without one the script exits with a message naming `DISCOGS_TOKEN`.
- `cast <id|url>` keeps today's grouping.
- `tracker <id|url>` emits the `mb.py tracker` JSON keys from Discogs data:
  - artist rows: Composer from `Composed By`, Conductor from `Conductor`, everything performing as Main;
  - per-disc work list: from `tracklist` positions `<disc>-<track>` and heading rows.

  It reuses the role names in `credits_lib`. This is the "MusicBrainz has no row" path that `file-tracker-request` describes today as manual work.

The shared tracker JSON shape lives in one function in `credits_lib` (`tracker_json(facts, rows, works)`), and both clients call it. With `discogs.py`, `mb.py` and `allmusic.py`, credits_lib now has 3 consumers.

Alternative considered: keep urllib with a hand-written 429 sleep. Rejected for the same reason as D3.

Apply-time check: confirm the package name and the `backoff_enabled` attribute against the library's README before writing.

### D4. Exclusions: one home per list

- Banned labels and banned hosts live only in `references/exclusions.md`.
- The streaming list stays in `rigorous-research/music/rules.md`, because `domains.py` parses it. `exclusions.md` points to it.
- The composer ban list is a recommendation rule, not a metadata rule. It stays in rigorous-research and is not referenced.

### D5. Scrub of the other skills

- `file-tracker-request`: delete `references/sources.md` and `scripts/extract_release_artists.py`. Replace SKILL.md lines 58-75 with a pointer to `music-lookup-artists` (routing.md for sources, `mb.py tracker` for extraction). Keep the OPS/RED image rules (not metadata sources).
- `rigorous-research`: replace `music/rules.md` "## Discography" with one line pointing to `music-lookup-artists/references/routing.md`. Repoint `classical/sources.md` item 5 and `popular/sources.md` item 1. The text is injected into prompts that the main agent answers with skills available, so a pointer resolves.
- `dvd-concert-curation`: delete `references/metadata-research.md`. Point SKILL.md step 1 and its Files list to `music-lookup-artists/references/dvd-tags-json.md`. Move the directory into `Dev\Skills` and junction it back.
- `classical-audio-tagging` and `lookup-music-artists`: delete them. Their content moves to tagging.md, sites.md and the scripts.
- `~/.agents/refdocs/musicbrainz.md`: fold it into sites.md and tagging.md, then delete it. `~/.agents/refdocs/wikipedia.md`: delete it unread into the skill. Wikipedia is not mentioned anywhere in the new skill, not even as a ban.

### D6. Description trigger

SKILL.md description, front-loaded with one trigger per branch:

> Use for any music metadata lookup or write: recording date/venue, credits or cast sheet (Composers/Orchestras/Soloists), release/MBID/catalogue identification, track lists, tracker-request artist extraction, tagging classical FLAC via Toolbox, DVD concert tags.json research.

## Risks / Trade-offs

- [Dangling references to the old skill names in AGENTS.md, CLAUDE.md, memories, epics or other skills] → apply greps `~/.agents`, `~/.claude`, `~/.config/opencode`, `Dev\Skills` and project memory for `lookup-music-artists|classical-audio-tagging|metadata-research.md|refdocs/musicbrainz|extract_release_artists`, and repoints every hit.
- [Pointer from rigorous-research prompts to another skill: a fresh-subagent extractor cannot follow it] → only discovery asks (main agent) use source order, and extractor/verifier asks never route sources.
- [`musicbrainzngs` include names differ from ws/2 tokens] → D3 apply-time check, run before deleting the old scripts.
- [The junction swap for dvd-concert-curation loses local edits] → before the swap, compare the copied tree's file count and total size with the original (rule #312 coverage style), and keep the original until the junction resolves.
- [The deleted refdocs are referenced by other skills] → covered by the grep above.

## Migration Plan

1. Build `music-lookup-artists` beside the old skills, and verify `mb.py` on the two test releases.
2. Repoint the other skills, delete the old skills and refdocs, swap the junctions.
3. Grep for dangling names, then commit and push to Bearmancer/skills main (rule #261).

Rollback: `git revert` the commit in `Dev\Skills` and restore the old junctions. The deleted refdocs are restored from the commit content, because they move verbatim into the skill.
