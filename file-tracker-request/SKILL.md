---
name: file-tracker-request
description: Fill, verify or edit a request on Redacted (redacted.sh, "RED") or Orpheus (orpheus.network, "OPS") — the "Create a request" form. Use whenever asked to post a request, fill or check the requests form, or work out which fields and bounty a request needs. Defaults to a disc-count bounty (2/5/7/10 GB), extracts every conductor, composer, orchestra and soloist into artist rows and the full work list into the body, rehosts covers for OPS, and confirms only once, immediately before posting. Field maps live in references/, the reusable scripts in scripts/.
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

- **Bounty scales with disc count** (owner ruling 2026-11-18): 1 disc → 2 GB; 2–10 →
  5 GB; 11–20 → 7 GB; over 20 → 10 GB. Bytes = GB × 1024³. The user naming a number
  overrides the tier. RED: `#amount_box`=<gb>, `#unit`=gb, `Calculate()`. OPS: same
  number in GiB, fire native `input` on box and unit (jQuery handler; no global to
  call); hidden `request_tax` reduces the credited bounty.
- **Classical CD shape:** Music; release type **Anthology (`6` on both sites) for every
  box set or collection — never Compilation**; **Live album** for a single non-box live
  release (value code differs per site — read the reference); Album for a single
  original studio album. **FLAC exclusively**, Lossless, CD. **Log, cue and checksum
  stay unticked** on both sites — demanding them is more specific than the upload
  rules; tick only on explicit user request.
- **Year** = edition release year, not recording dates.
- **Tags:** `classical` plus fitting tags, ≤ 200 chars, dots inside multi-word tags.
  RED accepts free tags; OPS official `#genre_tags` values only (rejection is
  server-side, after the POST).
- **Image:** HTTPS, verified 200 + image content-type. OPS rejects Discogs URLs
  ("Please rehost images from discogs.com elsewhere") — rehost via postimages.org
  (no login: upload, take the "Direct link" `https://i.postimg.cc/…`).

## Research sources

`references/sources.md`, in the owner's mandated order: MusicBrainz, Discogs,
Europadisc, Horizons, MusicWeb International, AllMusic, Presto. Wikipedia, Amazon,
The Guardian and UMG label storefronts are outside the routine; a blocked or empty
source → move to the next and say which failed. When fetches keep failing, widen
through the other MCPs (`exa`, `tavily`, `firecrawl`, `browse`) rather than stopping —
a 403/451/503 from one transport is not the source having no row.

## Extraction (classical)

`scripts/extract_release_artists.py --mbid <id> [--conductor "Name"] --out extract.json`
(or `--file <saved MB JSON>`) emits artist rows + per-disc work list from
`release?inc=recordings+artist-credits+labels`. Roles: conductors → 5, composers
(track-level credits) → 4, orchestras/choirs/soloists → 1. Pass the conductor
explicitly — soloists who also conduct (Ashkenazy, Perlman, Zukerman) stay Main;
`conductor_review` flags ambiguous cases. Max 200 rows; `[no artist]` dropped.

Skim the Main list for variant spellings of one ensemble (Maazel box: "New
Philharmonia" vs "New Philharmonic Orchestra") and keep one. MB fetches can die with
`IncompleteRead` — the script retries; rerun if it still fails.

Work list → description body: `scripts/format_contents.py --extract extract.json
[--performers performers.json] [--out contents.txt]` renders the block from the
extraction JSON. Shape: a `Contents:` header, then one block per disc — `Disc N` on its
own line, then one line per work `Composer — Work [Soloists, Orchestra]` (em dash U+2014;
performers in square brackets, comma-separated, soloists before orchestra, emitted only
when a performers entry exists for that disc). Consecutive works by the same composer:
the first line carries the composer, the rest are bare work lines (no composer, no
brackets); a different composer starts a new `Composer — Work [...]` line. Blank line
between disc blocks. No `CD n:` prefix, no parenthesised performers, no `·` joins.
Movement suffix after `:` stripped, disc order preserved, identical composer+work lines
deduped per disc; excerpt discs list the actual arias/excerpts; drop applause. The
performers map is disc number → string (`{"1": "Berliner Philharmoniker", "3": "Sviatoslav
Richter, Orchestre de Paris"}`), from retailer/Discogs credits. In the final BBCode
description `[b]…[/b]` may wrap the `Contents:` header and the `Disc N` labels.

```
Contents:
Disc 1
Bruckner — Symphony no. 7 in E major, WAB 107 [Berliner Philharmoniker]

Disc 2
Tchaikovsky — Piano Concerto no. 1 in B-flat minor, op. 23 [Emil Gilels, New Philharmonia Orchestra]
Piano Concerto no. 2 in G major, op. 44
```

**Cross-check against the retailer contents listing before posting.** MB composer
credits contain real errors — on Mehta's *Philharmonic Edition*, *Les préludes* was
credited to Wagner, the *Manon* aria to Verdi, BWV 1043 to Vivaldi. Fix composer/work/
opus typos and add any composer the correction introduces to the artist rows.

## Procedure

1. Identify tracker; read its reference. **Torrents first, on both sites** (owner
   ruling 2026-11-18): search `torrents.php?searchstr=<title or conductor>` for an
   existing rip, and `torrents.php?cataloguenumber=<cat>` for an exact match. Box
   titles appear under many spellings, so try conductor + label too. A rip already on
   the tracker means there is nothing to request: report the torrent and stop.
   `torrents.php?search=` is **silently ignored** on both sites and returns the
   unfiltered newest-torrents list — it reads like hundreds of hits for any query.
   Only `searchstr` (and the field filters) actually filter; `requests.php` is the
   one that takes `search`.
   A 16-bit FLAC rip ends the job. If the release exists **only as 24-bit FLAC**, the
   request still goes up — the ask is for the 16-bit CD layer — and the release is
   logged in a standing `24bit-only.md` inventory (tracker, torrent id, title, label,
   catalogue, depth, size), one row per such torrent.
2. No torrent → search `requests.php?search=<title>` for an existing request. One
   already there means **add exactly 1 GB** to its bounty (owner ruling 2026-11-18),
   never a second request.
3. Neither a torrent nor a request → research via sources; run extraction;
   cross-check; build description (overview + full work list + source links +
   barcode).
4. Fill immediately — no skill edits, retros or questions first — per
   `references/browser-fill.md` (main-world injection, DOM-stashed payload,
   `make_bundle.py` + `serve_payload.py`). Done when the readback says `ok:true`.
5. Read the payload back in one compact block — the only confirmation.
6. On yes: assert `#amount` + button, submit; accept a dialog only if the numbers
   match (RED fires one ≥ 25 GB; OPS none).
7. Verify on the site: redirect to `requests.php?id=<newid>` and the request on the
   account — a returned click is not evidence. Kill the payload server afterwards.

Record the torrent and request search terms you used and the row counts you saw, per
site. "Not found" is a claim about the tracker, so it needs the search that produced
it — an empty result from one spelling is not proof the rip is absent.

## Failure modes

- Stale bounty: the conversion never ran after a programmatic edit → 100 MiB posts.
- Hidden rows keep values across category switches and can still post.
- Submit disabled by insufficient credit — read the on-page message, do not retry.
- Server rejects a duplicate or rule-break — surface the message; never "fix" it by
  loosening the request.
- OPS image rejection → rehost (postimages), resubmit; the POST returns the form with
  values preserved.
- MB composer errors propagated unchecked — always cross-check.
- Skipped the torrent check → a request for a rip the tracker already has. Torrents,
  then requests, then create; never the reverse.
- `torrents.php?search=` looks like it worked (200+ rows) but is unfiltered. Read the
  row titles: if they are unrelated newest uploads, the parameter was ignored.
