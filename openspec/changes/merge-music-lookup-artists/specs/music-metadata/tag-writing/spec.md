# Spec Delta

## Purpose

Defines how metadata found through `music-lookup-artists` is written to the library: FLAC tags through the existing Toolbox tagger, and DVD research into `tags.json`, so that writes stay backed up, owner-gated and verified on disk.

## ADDED Requirements

### Requirement: FLAC writes go through the Toolbox tagger
The skill SHALL write FLAC tags only by running the existing `toolbox audio tag` command with a release MBID or Discogs id. The skill MUST NOT change Toolbox and MUST NOT write FLAC tags with its own scripts.

#### Scenario: Tag a box from MusicBrainz
- **WHEN** the owner asks to tag a FLAC folder from a resolved release MBID
- **THEN** the agent runs `toolbox audio tag "<path>" --mbid <mbid> --dry-run` first and shows the plan

### Requirement: Fresh exe before tagging
Before a dry run, the agent SHALL compare the newest Toolbox `src` commit time with the published exe's write time, and republish the exe when the source is newer.

#### Scenario: Stale exe
- **WHEN** the newest commit under `src` is later than the exe's LastWriteTime
- **THEN** the agent runs `dotnet publish src/App -c Release` before the dry run

### Requirement: Backup and owner gate
Before a FLAC write, the agent SHALL dump every FLAC's current tags to JSON with mutagen and get the owner's approval of the dry-run plan. A write without both MUST NOT happen.

#### Scenario: Owner has not approved
- **WHEN** the dry run is shown but the owner has not approved it
- **THEN** the agent does not run the write

### Requirement: Verify on disk with mutagen
After a FLAC write, the agent SHALL read the tags back with mutagen or `metaflac` and compare them with the approved plan. It MUST NOT use ffprobe to audit tags.

#### Scenario: Post-write check
- **WHEN** `toolbox audio tag` exits 0 with a Run ID
- **THEN** the agent re-reads the written fields with mutagen and reports any field that differs from the plan

### Requirement: Dates pass through unchanged
The skill SHALL keep the DATE values Toolbox writes (day-level dates, year-only spans, `YYYY-YY` ranges). It MUST NOT override them from other sources unless the owner asks for this for a named box.

#### Scenario: Web source disagrees with the MusicBrainz date
- **WHEN** a booklet-derived source gives a different recording date from MusicBrainz for a box being tagged
- **THEN** the agent reports the difference and leaves DATE as Toolbox writes it

### Requirement: DVD research fills tags.json
For concert-video discs, the skill SHALL record researched per-chapter metadata in the disc folder's `tags.json`, using its existing schema. Each value carries `confidence` and `evidence`. A correction to an existing value is recorded with its citation and with both the old and the new value.

#### Scenario: Gap in tags.json
- **WHEN** a chapter entry has no performance year
- **THEN** the agent researches it through the routing matrix, writes the value with confidence and evidence URLs, or leaves it empty with a flag for the owner

### Requirement: Low confidence goes to the owner
A value that only low-confidence evidence supports SHALL be flagged for the owner and MUST NOT be written as fact.

#### Scenario: Single forum post is the only witness
- **WHEN** the only source for a soloist's name is a forum post
- **THEN** the agent flags the value as low confidence and asks the owner
