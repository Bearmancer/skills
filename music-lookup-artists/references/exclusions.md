# Exclusions

A result on a banned site is discarded unread: never fetched, cited or linked. Move to the next rank in `routing.md`.

## Streaming services

The single home of the list is `rigorous-research/references/domains/music/rules.md`, section "Streaming ban": the services, the `excludeDomains` list, and the YouTube exception (a listen pointer only). Apply it on every search.

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
