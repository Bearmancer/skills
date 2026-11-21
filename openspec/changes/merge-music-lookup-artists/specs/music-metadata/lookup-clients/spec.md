# Spec Delta

## Purpose

Gives the agent one set of scripted clients for MusicBrainz, Discogs and AllMusic. They respect each site's rate limits and print the outputs the other music skills consume, so that no agent hand-rolls requests.

## ADDED Requirements

### Requirement: One client per site
The skill SHALL provide exactly one scripted client each for MusicBrainz, Discogs and AllMusic. Each runs with `uv run` and declares its own dependencies. No other skill in `Dev\Skills` ships a client for these sites.

#### Scenario: Old MusicBrainz scripts gone
- **WHEN** the change is applied
- **THEN** `lookup-music-artists/scripts/musicbrainz.py` and `file-tracker-request/scripts/extract_release_artists.py` no longer exist, and their behavior is available from the `music-lookup-artists` MusicBrainz client

### Requirement: MusicBrainz pacing and retry
The MusicBrainz client SHALL send at most one request in flight and at most about one request per second. It SHALL retry 503 "busy" replies with backoff. A busy reply MUST NOT be saved or parsed as a result.

#### Scenario: Server busy
- **WHEN** MusicBrainz answers a request with 503 "currently busy"
- **THEN** the client waits and retries, and exits non-zero with a clear message only after its retries are exhausted

### Requirement: Discogs pacing and backoff
The Discogs client SHALL use a maintained Discogs library that paces requests and backs off on 429 replies. It reads the token from the `DISCOGS_TOKEN` environment variable. A search without a token MUST fail with a message that names the variable.

#### Scenario: Rate limited
- **WHEN** Discogs answers 429
- **THEN** the client backs off and retries instead of failing or returning partial data

#### Scenario: No token for search
- **WHEN** `DISCOGS_TOKEN` is unset and a search is requested
- **THEN** the client exits non-zero and says that `DISCOGS_TOKEN` is required for Discogs search

### Requirement: Discogs subcommands mirror MusicBrainz
The Discogs client SHALL offer `search`, `cast` and `tracker`, with the same output shapes as the MusicBrainz client's subcommands of the same names. It has no `dates`, because Discogs exposes no recording dates.

#### Scenario: MusicBrainz has no row
- **WHEN** a box has no MusicBrainz release and the tracker form needs artist rows
- **THEN** `discogs tracker <release-id>` emits the same JSON keys as `mb tracker`, built from Discogs credits

#### Scenario: Search by barcode
- **WHEN** the agent runs a Discogs search with a barcode or catalogue number
- **THEN** the client prints candidate releases with id, title, year, label, catalogue and format, and reads the returned titles rather than trusting a non-empty result

### Requirement: Generic User-Agent
Every client SHALL send a fixed, generic User-Agent that names the skill. It MUST NOT contain the owner's email address or other personal data.

#### Scenario: Request headers
- **WHEN** any client sends a request
- **THEN** its User-Agent names `music-lookup-artists` and contains no email address

### Requirement: Release identification
The MusicBrainz client SHALL accept a Lucene search query and print the candidate releases with MBID, title, artist credit, year and track count, so that the agent can pick the release whose layout matches the files.

#### Scenario: Search by catalogue or barcode
- **WHEN** the agent searches with a barcode or catalogue query
- **THEN** the client prints the matching releases, or states that none matched

### Requirement: Cast sheet output
Given a release MBID, Discogs release id or AllMusic album URL, the matching client SHALL write a cast sheet to `%USERPROFILE%\Desktop\md-library\<site>\<slug>.md`. The sheet has the headings Composers, Orchestras and Soloists, one bare display name per line, alphabetized and deduplicated, with `(none found)` for an empty group.

#### Scenario: Role text stripped
- **WHEN** a credit reads "Byron Janis, piano"
- **THEN** the sheet lists `Byron Janis` under Soloists with no role text

### Requirement: Tracker extract output
Given a release MBID or a saved release JSON, the MusicBrainz client SHALL emit JSON with the release facts, the artist rows with Gazelle importance roles (1 Main, 4 Composer, 5 Conductor) in display-name form, and the composer/work groups for each disc, as `file-tracker-request` consumes today.

#### Scenario: Tracker skill consumes extract
- **WHEN** `file-tracker-request` needs artist rows for a request form
- **THEN** it calls the `music-lookup-artists` MusicBrainz client and gets the same JSON shape that `extract_release_artists.py` produced

### Requirement: Recording date and venue output
Given a release MBID, the MusicBrainz client SHALL print each track with the begin/end dates and the place from its recording's relations. It reads the relation `begin`/`end` keys and leaves the field empty when the release has none.

#### Scenario: Release without recording relations
- **WHEN** the release's recordings carry no "recorded at" or dated relations
- **THEN** the output shows empty date and venue for each track, and the agent follows the routing matrix's stop/exhaust rules

### Requirement: AllMusic fallback fetch
The AllMusic client SHALL try a direct fetch first and fall back to the `firecrawl` CLI when AllMusic blocks plain fetchers.

#### Scenario: Direct fetch 403
- **WHEN** AllMusic returns 403 to the direct fetch
- **THEN** the client renders the page through `firecrawl` and parses the Credits tab
