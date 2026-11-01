# Music rules: every music domain

## Streaming ban

Music streaming services = not a source, not a mention, on any music task.

- Services: Spotify, Apple Music, Apple Classical, Amazon Music, YouTube Music, Tidal, Deezer, Qobuz, Idagio, Primephonic, Naxos Music Library, SoundCloud, Pandora, any other streaming platform.
- Domains, pass as `excludeDomains` (or tool equivalent) on every search: `spotify.com`, `music.apple.com`, `classical.music.apple.com`, `music.amazon.*`, `music.youtube.com`, `tidal.com`, `deezer.com`, `qobuz.com`, `idagio.com`, `naxosmusiclibrary.com`, `soundcloud.com`, `pandora.com`.
- Result lands on one anyway: discard unread. Never fetch, cite, quote, link.
- Output: no listen pointers, no "available on X", no streaming track totals. `Recording:` names conductor / orchestra / label only. Fact whose only witness is streaming: `[unverified — dropped]`.
- YouTube (`youtube.com`, `youtu.be`) outside ban: listen pointer only, never fact or timing source.

## Discography: entry -> trace -> verify

"Every recording of X" / "duration of Y" = research task.

1. Entry: MusicBrainz (MBID-citable, release/recording/work relations) + Discogs (pressing variants, catalog numbers). Query 2+ angles: work + performer; performer + label; catalog number; work title filtered by era/orchestra.
2. Trace each candidate to original session (venue, dates, orchestra), not sleeve date. Repress of known session: say so ("all other listings repress [session]"). MusicBrainz/Discogs thin or disagree: Presto Classical, then label's own site as tie-breaker.
3. Verify: state date/catalog/session conflicts in one line. "N recordings exist" only after N distinct sessions traced. State depth reached (one query / one source / full sweep).

Cite: MusicBrainz, Discogs, Presto Classical, label sites, liner notes.

## Timing: every duration

1. Publisher-stated duration (if any) + two independent label track totals (Naxos / CPO / Chandos / Hyperion / BIS / Discogs / Presto). Give movement breakdown with its sum. Example: Glass 5 CPO 35:20 = 10:28 + 6:42 + 5:50 + 12:20.
2. Movement sum contradicts stated total: say so. Never copy album total covering two works (Naxos 68:26 = Glass 5+6).
3. Known cuts: flag complete vs cut, never one number ("74:13 complete Maksymiuk – 63:39 cut Boguszewski/DUX").
4. Recordings differ beyond tempo variance: named range ("35:36 Raiskin – 41:37 Todorov"). Never memory number.
5. Instrumentation exactly per publisher score/parts. No chorus, organ, soloists publisher/label omit.
6. Disambiguate namesakes every time: Louis Glass (1864-1936) is not Philip Glass (1937-).
7. Forum posts (TalkClassical, Reddit) = leads only; back every forum number with publisher or label citation.
8. Length-bounded request (e.g. 45-60 min): drop works whose verified maximum < minimum (Glass 5 max 41:37, out of 45+).
9. No finale/chorus claim without movement-track evidence. Unverifiable: `[unverified — dropped]`, omitted from length-filtered answers.
