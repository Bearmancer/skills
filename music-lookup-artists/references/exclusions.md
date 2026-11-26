# Exclusions

A result on a banned site is discarded unread: never fetched, cited or linked. Move to the next rank in `routing.md`. Pass the banned domains as exclude-domains on every search MCP call, and name them in every delegation briefing.

## Streaming services (ban)

Music streaming services are not a source, not a mention, on any music task.

- Services: Spotify, Apple Music, Apple Classical, Amazon Music, YouTube Music, Tidal, Deezer, Qobuz, Idagio, Primephonic, Naxos Music Library, SoundCloud, Pandora, any other streaming platform.
- Domains, excluded on every search: `spotify.com`, `music.apple.com`, `classical.music.apple.com`, `music.amazon.*`, `music.youtube.com`, `tidal.com`, `deezer.com`, `qobuz.com`, `idagio.com`, `naxosmusiclibrary.com`, `soundcloud.com`, `pandora.com`.
- Result lands on one anyway: discard unread. Never fetch, cite, quote, link.
- Output: no listen pointers, no "available on X", no streaming track totals. A fact whose only witness is streaming is reported as unverified and dropped.
- YouTube (`youtube.com`, `youtu.be`) is outside the ban: a listen pointer only, never a fact or timing source.

## Label sites (owner ruling 2026-11-20, chosen per label)

The ban covers the label's own catalogue, storefront and news pages. A retailer, review or database page that only names the label is fine.

| Label | Domains |
| --- | --- |
| Decca | `deccaclassics.com`, `store.deccaclassics.com`, `decca.com` |
| Deutsche Grammophon | `deutschegrammophon.com`, `store.deutschegrammophon.com` |
| Philips / Mercury | the UMG pages that carry these imprints (under `deccaclassics.com`, `deutschegrammophon.com`, `universalmusic.*`) |
| Eloquence | `eloquenceclassics.com` |
| Sony Classical | `sonyclassical.com`, `sonyclassical.de` |
| Warner Classics | `warnerclassics.com` |
| Harmonia Mundi / Alpha | `harmoniamundi.com`, `alpha-classics.com`, `outhere-music.com` |

Allowed as a low-rank source when they carry the field: Naxos (including `naxos.com/individuallabel` pages for distributed labels), Orfeo, Hänssler/Profil, CPO/Capriccio, Hyperion, Chandos, BIS, Arthaus/Unitel/C Major, RCA, Columbia, Erato/Teldec, EMI, Nonesuch.

## Other hosts

Amazon and The Guardian are outside routine lookups. When the owner names one of their URLs, fetch that one URL for that one lookup. The ban holds afterwards.
