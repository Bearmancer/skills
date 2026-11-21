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
- **Catalogue number is mandatory** (owner ruling 2026-11-18). Every request carries the
  label's catalogue number — it is what identifies the exact edition, and without it a
  filler cannot tell which pressing to rip. Do not post with it blank. When the ranked
  sources have no row, keep going: an allowed label catalogue (`music-lookup-artists`
  `references/exclusions.md`), the retailer listings, the Discogs label page, and the other MCPs (`exa`, `tavily`, `firecrawl`, `browse`) are all
  legitimate next steps. A JS-rendered label page that returns an empty shell is not
  "no catalogue" — render it through the browser or a scraping MCP and read it again.
  Only stop and ask the owner when every route is exhausted, and say which ones failed.
- **Tags:** `classical` plus fitting tags, ≤ 200 chars, dots inside multi-word tags.
  RED accepts free tags; OPS official `#genre_tags` values only (rejection is
  server-side, after the POST).
- **Image:** HTTPS, verified 200 + image content-type. OPS rejects Discogs URLs
  ("Please rehost images from discogs.com elsewhere") — rehost via postimages.org
  (no login: upload, take the "Direct link" `https://i.postimg.cc/…`).

## Research and extraction

Sources, their order, bans and per-site traps live in `music-lookup-artists` (`references/routing.md`,
`references/exclusions.md`, `references/sites.md`); a blocked or empty source → next rank, say which
failed. Artist rows and the per-disc work list come from its tracker extract:

```
uv run <music-lookup-artists>/scripts/mb.py search --query-file q.txt
uv run <music-lookup-artists>/scripts/mb.py tracker <mbid> [--conductor "Name"] --out extract.json
uv run <music-lookup-artists>/scripts/discogs.py tracker <discogs-id> --out extract.json   # no MB row
```

Roles: conductors → 5, composers (track-level credits) → 4, orchestras/choirs/soloists → 1.
Resolve `dual_credit_review` / `conductor_review` per `music-lookup-artists` `references/sites.md`
(MusicBrainz) before filling, and Latinize native-script artist names (Елена Образцова → Elena
Obraztsova). The blog's label and catalogue can be short forms - "Memories" was really **Memories
Excellence**, "ME 1031" really **ME1031-36**.

**Image + cue sources:** when the source rip is a single image with a cue sheet, the
request still asks for FLAC / Lossless / CD and the body says to split/convert to
per-track FLAC (owner ruling 2026-11-19). Log, cue and checksum boxes stay unticked.

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
   **The check is cross-site** (owner ruling 2026-11-19): if *either* tracker already
   has the album, do not request it on the other one either. For a multi-volume series,
   drop every volume present on either site and request only the remainder — the Inbal
   Exton Bruckner request covers 2/4/7/8 because RED holds 5/6/9, and the Mahler request
   covers 1/3/4/6 because OPS holds 2/5/7/9/10. A parent box also covers its subsets:
   RED's Frankfurt complete-symphonies box (1624654) holds Bruckner 1 and 3, so neither
   was requested.
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
   barcode). The catalogue number is part of the payload, not an optional extra —
   settle it before filling anything.
4. Fill immediately — no skill edits, retros or questions first — per
   `references/browser-fill.md` (main-world injection, DOM-stashed payload,
   `make_bundle.py` + `serve_payload.py`). Done when the readback says `ok:true`.
5. Read the payload back in one compact block — the only confirmation.
6. On yes: assert `#amount` + button, submit; accept a dialog only if the numbers
   match (RED fires one ≥ 25 GB; OPS none).
7. Verify on the site: redirect to `requests.php?id=<newid>` and the request on the
   account — a returned click is not evidence. Kill the payload server afterwards.

### Search mechanics — "not found" must be earned

A conductor's surname is a starting point, never proof of absence (owner ruling
2026-11-18). Record the terms, the pages walked and the distinct-group count per site.

- **Walk every page.** Results paginate at 50 groups. Follow `&page=N` until a page
  adds no new group ids; a page-1 miss means nothing. Measured: `searchstr=Beethoven`
  on RED fills page 1 and links to page 20+, while `searchstr=Vegh` is 38 groups on one
  page. If pagination links exist and you did not follow them, you have not searched.
- **Count group links only**: `torrents.php?id=<n>` and
  `requests.php?action=view&id=<n>`. Download, `userid` and `torrentid` links inflate
  the count — OPS `searchstr=Vegh` looks like 134 hits but is 32 groups.
- **A regex that misses `action=view&` returns a false zero on requests.** The first
  probe of `requests.php?search=Vegh` read 0; the correct pattern found 1. Validate
  the pattern against a query you know has a hit (e.g. `search=Maazel` → OPS 83111)
  before trusting any zero.
- **Surnames collide.** RED `search=Vegh` returns request 204889 "Imrich Végh – Wave
  Earplug No.4", an electronic artist, not Sándor Végh. Read the titles; a namesake is
  not your release. Try the accented and ASCII spellings both ways.

## Artist credit rules (owner ruling 2026-11-19)

**No conductor may sit in a Composer row, except Maazel.** Audit every payload before
filling: the set of Conductor names and the set of Composer names must be disjoint.
Maazel is the one permitted exception because he genuinely co-composed the twelve Serge
Lama chansons on the Cleveland CBS box; even there he is filed as Conductor for the set
and Serge Lama holds the composer credit.

MusicBrainz's dual-credit rule misfiles performers as composers often enough to check
every time. On the Haitink LPO extract it put **Haitink himself**, the London Philharmonic,
the Philharmonia, Rodney Friend and Ashkenazy into Composer; all five had to be moved
(Haitink to Conductor, the rest to Main). On the Bernstein Harvard Lectures it put
Bernstein in Composer; he is the lecturer/conductor and belongs in Conductor.

Latinize native-script names before filling (Елена Образцова → Elena Obraztsova). RED may
restore a canonical alias on save — "Seiji Ozawa (小澤征爾)" came back after editing — so
verify the readback rather than assuming the edit stuck.

## Raising a bounty after posting

The request edit form does not change the bounty; the **vote form** does. On both sites
it is the form whose hidden `action` is `vote`, with `#amount_box`, `#unit` and a hidden
`#amount` holding bytes.

- Set `#amount_box` and `#unit`, then **set `#amount` to the byte total directly** — the
  page's Calculate does not always re-run on synthetic change events (OPS computed 5 MB
  for a "5 gb" entry until `#amount` was set explicitly).
- Click `#button` ("Vote!"). **RED fires a confirm dialog** ("Vote on this request for
  5 GB? Your new stats will be…"); answer it with `dialog action:accept`. OPS may fire
  none. A blocked dialog pauses the whole tab, so handle it before the next call.
- OPS enforces a **minimum vote of 100 MiB**.
- Verify by reloading: `#total_bounty` and the "Top Contributors" line must show the new
  total. The "Bounty" label near the vote box is the *entered* amount, not the total —
  reading it as the total gives a false "nothing changed".

## Mandatory description block (owner ruling 2026-11-19)

Every request body ends with this block, verbatim except for the blog URL. It tells the
filler where the source rip is and what tagging standard the upload must meet, which is
what makes the resulting files usable in a classical library:

```
Can be downloaded from: <the classicalpippo9 blog post URL for this box>

It would be greatly appreciated if the uploaded files contained proper tags defined as:
1. Title - Work Name, Op. (No) - I. (Movement Name)
2. Artist - Soloists, conductor, orchestra
3. Composer
4. Date - Reflecting the recording date
5. Track number
6. Disc number
7. Total disc
8. Long path issues resolved via shortening box name
```

Put it after the Contents and Sources sections. Keep the numbering and wording exactly —
it is the owner's specification, not a suggestion to paraphrase.

When hand-building a Contents block instead of using `format_contents.py`, prefix **every
new composer**, not just the first work on the disc: a disc holding Carter, Wuorinen,
Sessions and Di Domenica needs all four names. `format_contents.py` already tracks
`prev_composer` and does this; an `if i == 0` shortcut silently drops the other composers
and shipped a wrong body once (Levine, RED 386899, corrected 2026-11-19).

Retrofitting requests posted before the rule (owner ruling: "EDIT Red and post comment on
OPS. When edit not possible use comment"):
- **RED** — `requests.php?action=edit&id=<id>` carries the same `form#request_form`; append
  the block to `#description`, fire `change`, click `#button`. Verified on all ten requests.
- **OPS** — the request cannot be edited, so post the block as a comment:
  `form#quickpostform` (action `comments.php?page=requests`), hidden `pageid` must equal the
  request id, fill `#quickpost`, submit. **Trap:** on some request pages clicking
  `#submit_button` does nothing — the textarea stays filled and no post appears. Use
  `form.requestSubmit()` instead; it posts and lands on `&postid=<n>#post<n>`.

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
- "Not found" from page 1, or from a link regex that missed `action=view&`. Both read
  as absence and are not. Walk the pages, validate the pattern on a known hit.
- Posted with a blank catalogue number because the first few sources had no row. The
  number identifies the edition; keep hunting the label and retailer routes before
  treating it as unavailable.
- Submitting RED from a form that waited through a confirmation prompt: the auth key
  expires and the POST returns "Invalid authorization key. Go back, refresh, and try
  again." OPS is unaffected. Reopen the form, re-fill from the payload server, re-assert
  the readback and click immediately — the fill is idempotent on a fresh form.
- Trusting the blog's grouped disc markers ("CD 1-2", "CD 4-5"). Discogs gives the real
  per-disc split (Symphony 3 beginning on CD1, conclusion plus Symphony 4 on CD2), which
  is what a filler needs.
- Requesting a subset edition whose parent box is already ripped. The 7-CD Ančerl
  "Live Recordings: Concertos" has no rip of its own, but the 15-CD "Live Recordings"
  parent does — owner ruling 2026-11-19: skip, the parent covers it. When a box is a
  subset of a larger set, search for the parent too and record both group ids.
