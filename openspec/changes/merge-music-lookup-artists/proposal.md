# Proposal

## Why

Guidance on finding music metadata is spread over six places: `classical-audio-tagging`, `lookup-music-artists`, `dvd-concert-curation/references/metadata-research.md`, `file-tracker-request/references/sources.md` + `scripts/extract_release_artists.py`, `rigorous-research/references/domains/music/`, and `~/.agents/refdocs/musicbrainz.md`. They disagree on source order and on label sites, and none of them says when to stop. In the 2026-11-20 Fey Haydn 102 session, the agent had the recording date (May 2012, Gesellschaftshaus Pfaffengrund) from a booklet-derived page after about 10 calls. It then spent about 35 more calls on hand-rolled MusicBrainz `curl` and got 503 "busy" replies. Two separate Python MusicBrainz clients exist.

## What Changes

- New skill `music-lookup-artists` in `Dev\Skills`. It is the single home for finding music metadata: release identification, credits (cast sheet), recording date and venue, track lists, label and catalogue numbers, and per-chapter DVD `tags.json` research.
- A routing matrix inside the skill, built like `rigorous-research`'s routing: for each metadata need it gives an ordered list of sources and a stop rule, and it lists the banned sources.
- The exclusions keep the streaming ban and add a per-label site ban picked by the owner on 2026-11-20. Banned: Decca, Deutsche Grammophon, Philips/Mercury, Eloquence, Sony Classical, Warner Classics, Harmonia Mundi/Alpha. The existing bans on Amazon and The Guardian stay. Wikipedia is not mentioned anywhere in the skill.
- One set of Python clients, each on a maintained library where one exists:
  - MusicBrainz through `musicbrainzngs` (from `extract_release_artists.py`).
  - Discogs through `python3-discogs-client` (library pacing and 429 backoff), with the same subcommands as MusicBrainz where Discogs has the data.
  - AllMusic, kept as is.

  `lookup-music-artists/scripts/musicbrainz.py` (a hand-rolled urllib retry loop) is deleted, and the urllib `discogs.py` is rewritten.
- **BREAKING**: skill `lookup-music-artists` is renamed to `music-lookup-artists`. Skill `classical-audio-tagging` is merged into it and deleted; its FLAC-writing workflow runs the existing `toolbox audio tag` command unchanged.
- **BREAKING**: other skills lose their copies of metadata guidance and point to `music-lookup-artists`:
  - `file-tracker-request` loses `references/sources.md` and `scripts/extract_release_artists.py`, and keeps the form-filling workflow.
  - `dvd-concert-curation` loses `references/metadata-research.md`, keeps merge/split/verify, and moves into `Dev\Skills` (rule #261).
  - The Discography section of `rigorous-research` `music/rules.md` is replaced by a pointer to the new skill. Its streaming ban and composer ban list stay where they are, because `scripts/domains.py` parses them.
  - The tagging contract, box MBIDs and API traps in `~/.agents/refdocs/musicbrainz.md` move into the skill.
  - `~/.agents/refdocs/wikipedia.md` (Solti date cross-check) is deleted with no replacement.

## Capabilities

### New Capabilities
- `music-metadata/source-routing`: the routing matrix (metadata need → ordered sources → stop rule), the exclusions (streaming, banned label sites, other banned hosts), and the rule that no other skill carries metadata-source guidance.
- `music-metadata/lookup-clients`: the single Python client set (MusicBrainz via musicbrainzngs, Discogs via python3-discogs-client, AllMusic) and its outputs: release search, cast sheet, tracker extract (artist rows + per-disc work list), per-track recording date and venue.
- `music-metadata/tag-writing`: how looked-up metadata is written. FLAC goes through `toolbox audio tag` (backup, dry-run, owner gate, verify with mutagen) and DVD research goes into `tags.json`, with confidence and evidence.

### Modified Capabilities
None (no existing specs in `openspec/specs/`).

## Impact

- `Dev\Skills` (Bearmancer/skills): new `music-lookup-artists/`. Deleted: `lookup-music-artists/` and `classical-audio-tagging/`. Edited: `file-tracker-request/`, `rigorous-research/references/domains/music/rules.md` and `popular/sources.md`. Added: `dvd-concert-curation/` (moved in from `~/.agents/skills`).
- `~/.agents/skills` junctions: add `music-lookup-artists` and `dvd-concert-curation`; remove `lookup-music-artists` and `classical-audio-tagging`. `.claude\skills` mirrors follow.
- `~/.agents/refdocs/musicbrainz.md`: its contents move into the skill, then the file is deleted. `~/.agents/refdocs/wikipedia.md` is deleted.
- Python dependencies: `musicbrainzngs` (already used) and `python3-discogs-client` (new), each declared inline in its script. The `firecrawl` CLI stays as AllMusic's fallback. A Discogs search needs a `DISCOGS_TOKEN` in the environment.
- Not changed: the Toolbox repo, `rigorous-research` scripts and the composer ban list.
