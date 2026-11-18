---
name: track-requests
description: Fill, verify or edit a request on Redacted (redacted.sh, "RED") or Orpheus (orpheus.network, "OPS") — the "Create a request" form. Use whenever asked to post a request, fill or check the requests form, or work out which fields and bounty a request needs. Defaults to 10 GB, extracts every conductor, composer, orchestra and soloist into artist rows and the full work list into the body, rehosts covers for OPS, and confirms only once, immediately before posting. Field maps live in references/, the reusable scripts in scripts/.
---

# Track requests — RED and OPS

Two Gazelle trackers, one form skeleton, different details:

- **RED** = `redacted.sh` → `references/redacted.md`
- **OPS** = `orpheus.network` → `references/orpheus.md`

Read the matching reference before touching the page; trust it over memory for value
maps and JS quirks. Browser fill mechanics (both sites): `references/browser-fill.md`.
Any other tracker: say these notes do not cover it.

## Ground rules (rules.php?p=requests)

- One title per request; no discographies, no vague asks.
- Multiple formats allowed, never all, never contradictory (FLAC **or** V0).
- A request cannot be more specific than the upload rules.
- Bounty is a reward, not a ransom; no steering to a named filler.
- Submitting spends upload credit and cannot be undone by editing. Confirm exactly
  once: read the finished payload back, get a yes, click Create. Defaults below are
  settled — do not ask about them beforehand.

## Defaults (automatic)

- **Bounty 10 GB** unless the user names a number. RED: `#amount_box`=10, `#unit`=gb,
  `Calculate()`. OPS: 10 GiB, fire native `input` on box and unit (jQuery handler; no
  global to call); hidden `request_tax` reduces the credited bounty.
- **Classical CD shape:** Music; Compilation for collections, Album for a single
  original album; FLAC only; Lossless; CD. **Log, cue and checksum stay unticked** on
  both sites — demanding them is more specific than the upload rules; tick only on
  explicit user request.
- **Year** = edition release year, not recording dates.
- **Tags:** `classical` plus fitting tags, ≤ 200 chars, dots inside multi-word tags.
  RED accepts free tags; OPS official `#genre_tags` values only (rejection is
  server-side, after the POST).
- **Image:** HTTPS, verified 200 + image content-type. OPS rejects Discogs URLs
  ("Please rehost images from discogs.com elsewhere") — rehost via postimages.org
  (no login: upload, take the "Direct link" `https://i.postimg.cc/…`).

## Research sources

`references/sources.md`: Europadisc, Discogs, MusicBrainz, MusicWeb International,
Presto, AllMusic, Horizons. Wikipedia, Amazon, The Guardian and UMG label storefronts
are outside the routine; a blocked allowed source → move to the next and say which
failed.

## Extraction (classical)

`scripts/extract_release_artists.py --mbid <id> [--conductor "Name"] --out extract.json`
(or `--file <saved MB JSON>`) emits artist rows + per-disc work list from
`release?inc=recordings+artist-credits+labels`. Roles: conductors → 5, composers
(track-level credits) → 4, orchestras/choirs/soloists → 1. Pass the conductor
explicitly — soloists who also conduct (Ashkenazy, Perlman, Zukerman) stay Main;
`conductor_review` flags ambiguous cases. Max 200 rows; `[no artist]` dropped.

Work list → description body: per disc `Composer – Work`, movement suffix after `:`
stripped, disc order; excerpt discs list the actual arias/excerpts; drop applause.

**Cross-check against the retailer contents listing before posting.** MB composer
credits contain real errors — on Mehta's *Philharmonic Edition*, *Les préludes* was
credited to Wagner, the *Manon* aria to Verdi, BWV 1043 to Vivaldi. Fix composer/work/
opus typos and add any composer the correction introduces to the artist rows.

## Procedure

1. Identify tracker; read its reference. Search its requests for the title first
   (duplicate check).
2. Research via sources; run extraction; cross-check; build description (overview +
   full work list + source links + barcode).
3. Fill immediately — no skill edits, retros or questions first — per
   `references/browser-fill.md` (main-world injection, DOM-stashed payload,
   `serve_payload.py` + `fill_request.js`). Done when the readback says `ok:true`.
4. Read the payload back in one compact block — the only confirmation.
5. On yes: assert `#amount` + button, submit; accept a dialog only if the numbers
   match (RED fires one ≥ 25 GB; OPS none).
6. Verify on the site: redirect to `requests.php?id=<newid>` and the request on the
   account — a returned click is not evidence. Kill the payload server afterwards.

## Failure modes

- Stale bounty: the conversion never ran after a programmatic edit → 100 MiB posts.
- Hidden rows keep values across category switches and can still post.
- Submit disabled by insufficient credit — read the on-page message, do not retry.
- Server rejects a duplicate or rule-break — surface the message; never "fix" it by
  loosening the request.
- OPS image rejection → rehost (postimages), resubmit; the POST returns the form with
  values preserved.
- MB composer errors propagated unchecked — always cross-check.
