# Orpheus (OPS) — requests.php?action=new

Verified 2026-11-14 against the live form; fill mechanics re-verified 2026-11-18
(request 83109). Pair with `../SKILL.md` and `browser-fill.md`.

## Form contract

- URL `https://orpheus.network/requests.php?action=new`; title "Request › Create ⠶ Orpheus".
- `form#request_form`, POST, `application/x-www-form-urlencoded`, empty `action`.
- Hidden: `auth` (no value attribute in markup — read `.value` live;
  `document.body.dataset.auth` mirrors it), `action=takenew`, `amount` (bytes),
  `current_uploaded`, `current_downloaded`, `current_rr`, `request_tax`.
- **No `required` attributes, no maxlengths** — all validation is server-side; the
  browser will happily post an empty artist row.
- Submit `input#button[value="Create request"]`; no confirm dialog on create. A
  rejected POST returns the form with values preserved and the error message on top.

## Category

`select#categories` (`name="type"`), same 7 values as RED. Handler bound in JS
(`init_category_form`) — fire a real `change` event. It only adds/removes `hidden`;
nothing is cleared, Title is never relabelled.

Music rows: Release type, Artist(s), Title, Record label, Catalogue number, Year,
Image, Tags, Allowed media, Allowed formats, Log/Checksum/Cue, Allowed encodings,
Description, Torrent group, Bounty. Non-Music hides artist, encodings,
cataloguenumber, formats, logcue, media, recordlabel, releasetypes, and (outside
Audiobooks/Comedy) year.

## Music fields

- Artist(s) — `input#artist_0[name="artists[]"]`, `data-gazelle-autocomplete`
  (`artist.php?action=autocomplete`). Paired `select#importance_0[name="importance[]"]`,
  standard 8 roles. Add via `#artist-add` anchor (`artist_add()`), remove
  `#artist-remove`; JS-bound, max 200 rows. New rows get `artist_N`/`importance_N`
  and inherit the previous role. First field's `blur` runs `check_various_artists()`
  against `/^va(rious(\s?a(rtists?)))?$/` on **any** row → `#vawarning`.
- Title `input[name="title"]` · Record label `input[name="recordlabel"]` ·
  Catalogue number `input[name="cataloguenumber"]` · Year `input[name="year"]`.
- Image `input[name="image"]`, plain text. **Discogs URLs are rejected server-side**
  ("Please rehost images from discogs.com elsewhere") — rehost per SKILL.md defaults.
- Tags `#tags`, autocomplete; `select#genre_tags` holds 172 official tags, `change`
  appends via `add_tag()`. Free tags were accepted on create and edit (83332–83356,
  2026-11-24). Tags split on commas only; OPS turns spaces into dots and drops `;` and
  `-`, so a `;`-joined string posts as one tag.
- Release type `select#releasetype`: `1` Album, `3` Soundtrack, `5` EP, `6` Anthology,
  `7` Compilation, `8` Sampler, `9` Single, `10` Demo, `11` Live album, `12` Split,
  `13` Remix, `14` Bootleg, `15` Interview, `16` Mixtape, `17` DJ Mix,
  `18` Concert recording, `21` Unknown.
- Allowed media — master `#toggle_media[name="all_media"]`; `media[]`: `0` CD,
  `1` WEB, `2` Vinyl, `3` DVD, `4` BD, `5` Soundboard, `6` SACD, `7` DAT, `8` Cassette.
  All checked on load.
- Allowed formats — master `#toggle_formats[name="all_formats"]`; `formats[]`:
  `0` MP3, `1` FLAC, `2` Ogg Vorbis, `3` AAC, `4` AC3, `5` DTS. All checked on load.
- Allowed encodings — master `#toggle_bitrates[name="all_bitrates"]`; `bitrates[]`
  (still named "bitrates"): `0` Lossless, `1` 24bit Lossless, `2` V0, `3` V1, `4` V2,
  `5` 320, `6` 256, `7` 192, `8` 160, `9` 128, `10` 96, `11` 64, `12` APS, `13` APX,
  `14` q8.x. All checked on load.
- Log/Checksum/Cue — `#logcue_tr`, shown by `toggle_log_cue()` only when FLAC
  (`formats[]` 1) **and** CD (`media[]` 0) are both checked. `#needlog` reveals
  `#logscore` with `input#minlogscore[type=range][min=0][max=100]` (default 100) and
  readout `#needlogscore`; `#needcksum` (note spelling) and `#needcue`. All three
  default checked — leave them unticked per SKILL.md unless the user asks.
- Description `textarea#description`, BBCode, Preview via `TextareaPreview`.
- Torrent group `input[name="groupid"]` — fill only when the torrent group already
  exists on site; empty for a request that creates a new group.
- Bounty (MiB) — `#amount_box` (default `100.00`), `#unit` (`mb`=MiB, `gb`=GiB).
  Floor 100 MiB enforced server-side.

## JS (edge.opsfet.ch/functions/requests.js)

`add_bounty`, `recalculate_bounty`, `artist_add`, `artist_remove`,
`check_various_artists`, `init_category_form`, `add_tag`, `toggle_group`,
`toggle_log_cue`, `toggle_log_score`, `recheck_all`, `init_input`,
`init_checkbox_all`, `init_vote`, `init_request_page`, `init_index_page`.

These are **jQuery-bound, not window globals** — `typeof recalculate_bounty` is
`undefined` even in the main world. Trigger them with native events:

- `recalculate_bounty()` runs on `input` for `#amount_box`/`#unit` and once on load.
  Fire `input` (bubbles) after setting values; it writes `floor(value × 1024²|1024³)`
  into `#amount`, updates `#new_uploaded`, `#new_bounty`, `#bounty_after_tax`
  (amount × (1 − `#request_tax`)), `#new_ratio`, and disables `#button` when the
  amount exceeds `#current_uploaded`.
- Sub-box changes clear the "All" master and re-derive it via `recheck_all`; ticking
  a master checks/unchecks every sub but never disables them. Every checked sub posts.
- `init_vote()` is wired on `action=new` for the bounty preview; its `#button` click
  handler no-ops without `#requestid`.

## Rules digest (rules.php?p=requests)

Same five rules as RED ("FLS" for first-line support): one title; multiple formats
but not all/contradictory; not more specific than upload rules; no trivial unfilling;
no bounty trading/ransom. Rule-breaking requests are deleted without the bounty.

## Fill recipe

Field order below; browser mechanics and the tested injection body live in
`browser-fill.md` / `../scripts/fill_request.js` (`payload.site = "ops"`).

```js
await page.goto('https://orpheus.network/requests.php?action=new', { waitUntil: 'domcontentloaded' });
await page.selectOption('#categories', 'Music');            // fires init_category_form()
await page.fill('#artist_0', 'Artist');
await page.selectOption('#importance_0', '1');
await page.click('#artist-add');                            // per extra artist
await page.fill('#artist_1', 'Second Artist');
await page.selectOption('#importance_1', '1');
await page.fill('input[name="title"]', 'Album');
await page.fill('input[name="year"]', '1997');
await page.fill('input[name="recordlabel"]', 'Label');       // optional
await page.fill('input[name="cataloguenumber"]', 'CAT-001'); // optional
await page.fill('input[name="image"]', 'https://i.postimg.cc/…'); // rehosted, never Discogs
await page.selectOption('#releasetype', '7');
await page.fill('#tags', 'classical, opera');                // official tags only
await page.fill('#description', 'Reason for the request…');
// Defaults are "all"; set each sub to the wanted state (narrow, don't select-all).
for (const v of ['0', '2', '3', '4', '5']) await page.uncheck(`input[name="formats[]"][value="${v}"]`);
// needlog/needcksum/needcue: uncheck (skill default).
await page.fill('#amount_box', '10');
await page.selectOption('#unit', 'gb');
// fire native 'input' on #amount_box and #unit — recalculate_bounty is jQuery-bound
// assert #amount === 10737418240 and #button not disabled, then click #button (no dialog)
```

## Verify and gotchas

- Success lands on `requests.php?action=view&id=<newid>` (verified on request 83109);
  verify by URL id plus the request on the account.
- Everything defaults to all media/formats/encodings — narrowing is mandatory or the
  request is rule-breaking by default.
- The log/cue row disappears the moment FLAC or CD is unchecked — set formats and
  media before touching log options.
- Direct `.value =` assignment does not fire the `input` handler; dispatch the event.
- No client-side length limits: official tags and reasonable descriptions only —
  rejection happens after the POST.
- A rejected POST (e.g. Discogs image) returns the form with values preserved; fix
  the flagged field and resubmit rather than refilling from scratch.
