# Spec Delta

## Purpose

Tells an agent which source to query for each kind of music metadata, in what order, and when to stop, so that a lookup ends as soon as a trusted source answers it.

## ADDED Requirements

### Requirement: Routing matrix by metadata need
The skill SHALL hold one routing matrix. Each row is a metadata need: release identification, credits/cast sheet, recording date and venue, track list/contents, label and catalogue number, cover image, DVD/concert-video chapter data. Each row lists sources in rank order and the stop rule for that need.

#### Scenario: Recording date asked
- **WHEN** the agent must find the recording date of a work on a known release
- **THEN** the matrix gives an ordered source list for "recording date and venue", with booklet-derived sources (MusicWeb contents lists, retailer contents listings, independent-label catalogue pages) ranked before MusicBrainz relations

#### Scenario: Need not in matrix
- **WHEN** the agent needs a metadata field that no matrix row covers
- **THEN** it uses the "release identification" row's order and records the gap as a proposed new row in its reply

### Requirement: Stop rule ends the lookup
Each matrix row SHALL define a stop condition. The agent MUST stop querying further sources for that field once the stop condition is met. It reports the answer with its source, and it does not cross-check against a lower-ranked source unless the owner asks for a cross-check.

#### Scenario: Booklet-derived source answers
- **WHEN** a booklet-derived source gives both the date and the venue for the asked work
- **THEN** the agent reports them with that citation and makes no further MusicBrainz or Discogs calls for that field

#### Scenario: Sources conflict
- **WHEN** two sources ranked at the same level give different values
- **THEN** the agent reports both values with their citations in one line and does not pick one silently

### Requirement: Source exhausted is reported
When every source in a row has been tried without the field, the agent SHALL report the field as not found and list the sources it tried. It MUST NOT guess a value.

#### Scenario: MusicBrainz has no relations
- **WHEN** MusicBrainz returns a release whose recordings carry no "recorded at" relations, and the higher-ranked sources also lack the field
- **THEN** the agent reports "recording date: not found" with the list of tried sources

### Requirement: Streaming ban
Music streaming services SHALL NOT be fetched, cited or linked as a metadata source. The banned service and domain list is the one in `rigorous-research/references/domains/music/rules.md` "Streaming ban", and the skill points to it instead of copying it.

#### Scenario: Search hit on a streaming domain
- **WHEN** a search result is on a domain in the streaming ban list
- **THEN** the agent discards it unread

### Requirement: Label-site ban per label
The skill SHALL ban the owner-selected label sites as metadata sources: Decca, Deutsche Grammophon, Philips/Mercury, Eloquence, Sony Classical, Warner Classics, Harmonia Mundi/Alpha. The ban covers catalogue, storefront and news pages on their domains. Label sites not on the list stay allowed as a low-rank source.

#### Scenario: Banned label page found
- **WHEN** a search returns a page on a banned label's domain (for example `deccaclassics.com`, `store.deutschegrammophon.com`, `sonyclassical.com`, `warnerclassics.com`)
- **THEN** the agent does not fetch or cite it and moves to the next ranked source

#### Scenario: Allowed label catalogue
- **WHEN** an allowed label's catalogue page (for example Naxos, Orfeo, Hänssler, CPO, Hyperion, Chandos, BIS, Arthaus, RCA, Erato, EMI) carries the field
- **THEN** the agent may use it at the rank the matrix gives label catalogues

### Requirement: Other banned hosts
The skill SHALL exclude Amazon and The Guardian from routine lookups. A host is unbanned only when the owner names it explicitly, and then only for that one fetch.

#### Scenario: Owner points at an Amazon page
- **WHEN** the owner gives an Amazon URL for a lookup
- **THEN** the agent fetches that one URL and keeps the ban for later lookups

### Requirement: Sources outside the matrix are unmentioned
The skill SHALL name only the sources it ranks or bans. Sources dropped by the owner (Wikipedia) MUST NOT appear in any skill file, not even as a ban.

#### Scenario: Wikipedia audit
- **WHEN** `music-lookup-artists` is searched for "wikipedia"
- **THEN** there are no hits

### Requirement: Single home for metadata-source guidance
No skill other than `music-lookup-artists` SHALL carry its own music-metadata source order, label exclusions or MusicBrainz/Discogs client code. Other skills that need metadata MUST point to `music-lookup-artists`.

#### Scenario: Audit of user skills
- **WHEN** the owner's skills in `Dev\Skills` are searched for MusicBrainz/Discogs source-order tables or client scripts
- **THEN** the only hits outside `music-lookup-artists` are pointers to it, plus `rigorous-research`'s machine-parsed streaming ban and composer ban list
