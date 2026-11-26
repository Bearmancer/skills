---
name: music-lookup-artists
description: "Use for any music metadata lookup: recording date or venue, credits or a cast sheet (Composers/Orchestras/Soloists), release/MBID/Discogs/catalogue identification, track lists, cover images, artist extraction for a tracker request, and DVD concert tags.json research. Runs credential-free in Claude Chat on Desktop and Android (MusicBrainz open API + Exa/Tavily/Firecrawl for Discogs and AllMusic) and in OpenCode. Triggers on a MusicBrainz, Discogs or AllMusic URL/id. FLAC tag writes stay OpenCode-only via Toolbox."
---

# music-lookup-artists

The single home for music metadata: where to look, in what order, when to stop, what is banned, and how every search delegation is briefed. Pick the branch, read only its files, and stop at the branch's done line.

The decisive rule: **a lookup ends at the first source that answers it** (`references/routing.md`, Stop rule). A booklet-derived page that gives the date and venue is the answer. Do not then go on to query MusicBrainz.

## Environment contract

- **No user credentials, ever.** No Discogs token, no scraping API key, no local secret files, no shell assumed. MusicBrainz is an open API (fixed User-Agent `music-lookup-artists/1.0`, never a personal address). Discogs and AllMusic are read as public web pages through the search MCPs.
- **Tools — MCPs first:** use the connected **Exa**, **Tavily** and **Firecrawl** MCPs before the environment's built-in web search and web fetch. The built-ins are the fallback only when an MCP is not connected or its route failed. How to drive each one, and the decision ladder between them: `references/mcp-playbook.md`.
- **OpenCode host note:** Firecrawl's OpenCode situation (disabled in research-rigorously's registry; `just-scrape` fills the render slot): `references/mcp-playbook.md`. In Claude Chat, Firecrawl is the hosted connector. No other environment difference matters.
- **Every search excludes the streaming domains and the banned label sites** (`references/exclusions.md`). A result on a banned site is discarded unread.

## The failure ledger (mandatory on every MCP delegation)

Keep a running list of every source that failed this lookup, each with its route and reason. **Every call to Exa, Tavily or Firecrawl carries the whole list plus the new sites to try** — template and worked example in `references/mcp-playbook.md`, measured seed failures in `references/failures.md`. Never re-delegate a failed route; a blocked or empty source moves to the next rank and is appended to the ledger.

## Branches

1. **Answer a fact** (recording date and venue, label, catalogue, edition, track list).
   Read `references/routing.md` and `references/exclusions.md`. Open `references/sites.md` only for the site you are about to query.
   *Done when:* the row's stop condition holds and the answer carries its citation, or the field is reported as not found with the sources tried.

2. **Cast sheet** (Composers / Orchestras / Soloists).
   Build it from the source's credits per `references/extract.md` (Cast sheet). In OpenCode write `%USERPROFILE%\Desktop\md-library\<site>\<slug>.md` (`<site>` = literal `musicbrainz`, `discogs` or `allmusic`; `<slug>` = release title lowercased, non-alphanumerics to `-`, cut at 60 chars); in chat, output the same sheet in the reply.
   Three headings, one bare name per line, alphabetized and deduplicated; the heading is the source's release title verbatim, errors included; never a role after a name (`Byron Janis piano` is wrong); an empty group reads `(none found)`.
   Review against the release page (leak directions in `references/sites.md`). Never hand-edit the sheet (owner rule): when a name is wrong, fix the extraction and regenerate from the source. Sources disagree by design: Discogs under-credits, AllMusic omits composers, MusicBrainz carries the booklet data.
   *Done when:* every name traces to a credit line, every performer credit is either listed or consciously dropped, and a second source is reconciled.

3. **Tracker extract** (artist rows and the per-disc work list for `file-tracker-request`).
   Build the JSON exactly per `references/extract.md`. Roles: 1 Main, 4 Composer, 5 Conductor. MusicBrainz first; when it has no row, Discogs. Check `dual_credit_review` and `conductor_review`, and cross-check composers against retailer contents. In OpenCode write `extract.json`; in chat, output the JSON block.
   *Done when:* the JSON matches the schema and every review list is resolved.

4. **Tag FLAC** (classical library) — **OpenCode only** (needs a shell and the local Toolbox exe). Follow `references/tagging.md`: fresh exe, dry run, backup, owner gate, apply, mutagen proof. In Claude Chat, stop at the lookup and hand the tag plan to the owner.
   *Done when:* the tags on disk match the approved plan.

5. **DVD tags.json research.** Follow `references/dvd-tags-json.md`. Merging and naming stay in `dvd-concert-curation`.
   *Done when:* every chapter has a value with confidence and evidence, or a flag for the owner.

## Files

- `references/routing.md`: the matrix (need, ranked sources, stop rule), the failure-ledger rule, discovery and fetch routes.
- `references/exclusions.md`: the streaming ban, banned label sites, banned hosts.
- `references/failures.md`: measured dead routes (the ledger seed) and the delegation briefing template.
- `references/sites.md`: per-site facts, page patterns and traps; the MusicBrainz API endpoints.
- `references/mcp-playbook.md`: how to drive Exa, Tavily and Firecrawl; the decision ladder; the full delegation briefing.
- `references/extract.md`: tracker-extract JSON schema, artist classification, work grouping, cast-sheet rules.
- `references/tagging.md`: Toolbox FLAC workflow (OpenCode only), the field contract, box MBIDs.
- `references/dvd-tags-json.md`: tags.json schema, join rule, research method.
