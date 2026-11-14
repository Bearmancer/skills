# Orpheus — requests.php?action=new

Verified 2026-11-14 against the live form (Gazelle, logged in). Pair with the shared
procedure in `../SKILL.md`.

## Form contract

- URL `https://orpheus.network/requests.php?action=new`; title "Request › Create ⠶ Orpheus".
- `form#request_form`, POST, `application/x-www-form-urlencoded`, empty `action`.
- Hidden fields: `auth` (no value attribute in the markup — read `.value` from the live
  input, and note `document.body.dataset.auth` mirrors it), `action=takenew`, `amount`
  (bytes), `current_uploaded`, `current_downloaded`, `current_rr`, `request_tax`.
- **No `required` attributes and no maxlengths anywhere in this form.** All validation is
  server-side; the browser will happily post an empty artist row.
- Submit: `input#button[value="Create request"]`, no confirm dialog on create. The click
  handler belongs to voting and only acts when `#requestid` exists.

## Category

`select#categories` (`name="type"`), same 7 values as Redacted. The change handler is bound
in JS (`init_category_form`), not inline, so fire a real `change` event.

`init_category_form()` only adds/removes the `hidden` class; nothing is cleared and Title is
never relabelled — every category keeps the plain `Title` label.

- Music — Release type, Artist(s), Title, Record label, Catalogue number, Year, Image, Tags,
  Allowed media, Allowed formats, Log / Checksum / Cue, Allowed encodings, Description,
  Torrent group, Bounty.
- Audiobooks, Comedy — Title, Year, Image, Tags, Description, Torrent group, Bounty.
- Applications, E-Books, E-Learning Videos, Comics — Title, Image, Tags, Description,
  Torrent group, Bounty.

Hidden for every non-Music category: artist, encodings, cataloguenumber, formats, logcue,
media, recordlabel, releasetypes, and (outside Audiobooks/Comedy) year.

## Music fields

- Artist(s) — `input#artist_0[name="artists[]"]`, size 45, `data-gazelle-autocomplete`,
  autocomplete endpoint `artist.php?action=autocomplete`. Paired
  `select#importance_0[name="importance[]"]` with the standard 8 roles. Add with the
  `#artist-add` anchor (`artist_add()`), remove with `#artist-remove`; both bound in JS,
  max 200 rows. Each new row gets `artist_N` / `importance_N` and inherits the previous
  role value. The first field's `blur` runs `check_various_artists()`, which tests **any**
  row against `/^va(rious(\s?a(rtists?)))?$/` and unhides `#vawarning`.
- Title — `input[name="title"]`, size 45.
- Record label — `input[name="recordlabel"]`, size 45.
- Catalogue number — `input[name="cataloguenumber"]`, size 15.
- Year — `input[name="year"]`, size 5.
- Image — `input[name="image"]`, plain text (not `type=url`), size 45. No HTTPS-only note
  on this form.
- Tags — `#tags` (`name="tags"`), size 45, autocomplete. `select#genre_tags` holds 172
  official tags; `change` appends through `add_tag()`.
- Release type — `select#releasetype[name="releasetype"]`:
  `1` Album, `3` Soundtrack, `5` EP, `6` Anthology, `7` Compilation, `8` Sampler,
  `9` Single, `10` Demo, `11` Live album, `12` Split, `13` Remix, `14` Bootleg,
  `15` Interview, `16` Mixtape, `17` DJ Mix, `18` Concert recording, `21` Unknown.
- Allowed media — master `#toggle_media[name="all_media"]`, then `media[]`:
  `0` CD, `1` WEB, `2` Vinyl, `3` DVD, `4` BD, `5` Soundboard, `6` SACD, `7` DAT,
  `8` Cassette. All checked on load.
- Allowed formats — master `#toggle_formats[name="all_formats"]`, then `formats[]`:
  `0` MP3, `1` FLAC, `2` Ogg Vorbis, `3` AAC, `4` AC3, `5` DTS. All checked on load.
- Allowed encodings — master `#toggle_bitrates[name="all_bitrates"]`, then `bitrates[]`
  (still named "bitrates" in the form): `0` Lossless, `1` 24bit Lossless, `2` V0 (VBR),
  `3` V1 (VBR), `4` V2 (VBR), `5` 320, `6` 256, `7` 192, `8` 160, `9` 128, `10` 96,
  `11` 64, `12` APS (VBR), `13` APX (VBR), `14` q8.x (VBR). All checked on load.
- Log / Checksum / Cue — row `#logcue_tr`, shown by `toggle_log_cue()` only when FLAC
  (`formats[]` index 1) **and** CD (`media[]` index 0) are both checked. Page note: "The
  requirement for .log and .cue files applies only to CD FLAC uploads."
  `#needlog` (default checked) reveals `#logscore`, which holds
  `input#minlogscore[type=range][min=0][max=100]` (default 100) and the live readout
  `#needlogscore`. Also `#needcksum` "Require a log file with a valid checksum" and
  `#needcue` "Require a .cue file" — note the spelling `needcksum`, not `needchecksum`.
  All three default to checked.
- Description — `textarea#description[name="description"]`, BBCode, Preview bound through
  `TextareaPreview`.
- Torrent group — `input[name="groupid"]`, size 15, rendered as
  `https://orpheus.network/torrents.php?id=<input>`. Copy: "If this request matches a
  torrent group already existing on the site, please indicate that here." Leave empty for a
  request that creates a new group; fill it when the group exists and the ask is a format
  the site lacks.
- Bounty (MiB) — `#amount_box[name="amount_box"]` (default `100.00`), `#unit`
  (`mb`=MiB, `gb`=GiB). Page note: "Bounty must be greater than or equal to 100 MiB."
  No pattern or required attribute — the floor is enforced server-side.

## JS (edge.opsfet.ch/functions/requests.js)

`add_bounty`, `recalculate_bounty`, `artist_add`, `artist_remove`,
`check_various_artists`, `init_category_form`, `add_tag`, `toggle_group`, `toggle_log_cue`,
`toggle_log_score`, `recheck_all`, `init_input`, `init_checkbox_all`, `init_vote`,
`init_request_page`, `init_index_page`.

- `recalculate_bounty()` runs on `input` for `#amount_box` and `#unit`, and once on load.
  It writes `floor(value × 1024²|1024³)` into `#amount`, updates `#new_uploaded`,
  `#new_bounty`, `#bounty_after_tax` (amount × (1 − `#request_tax`)), `#new_ratio`, and
  disables `#button` when the amount exceeds `#current_uploaded`.
- Toggle semantics: changing a sub-box clears its "All" master and re-derives it through
  `recheck_all`; ticking a master checks or unchecks every sub-box but never disables them.
  So "All" is a convenience, not a separate submission — every checked sub-box posts.
- `init_vote()` is also wired on `action=new` (for the bounty preview); its `#button` click
  handler no-ops without `#requestid`.

## Rules digest (rules.php?p=requests)

Same five rules as Redacted, with "FLS" instead of "first-line support": one title per
request; multiple formats but not all and not contradictory; cannot be more specific than
upload rules; do not unfill for trivial reasons; no bounty trading or ransom. Requests
that break the rules are deleted without the bounty.

## Fill recipe

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
await page.fill('input[name="image"]', 'https://…');         // optional
await page.selectOption('#releasetype', '1');
await page.fill('#tags', 'rock, alternative');
await page.fill('#description', 'Reason for the request…');
// Defaults are "all"; deselect rather than select when narrowing.
for (const v of ['0', '2', '3', '4', '5']) await page.uncheck(`input[name="formats[]"][value="${v}"]`);
await page.fill('#amount_box', '100');
await page.selectOption('#unit', 'mb');
await page.evaluate(() => recalculate_bounty());
// assert #amount and #button, then submit (no dialog expected)
await page.click('#button');
```

## Verify and gotchas

- Success lands on `requests.php?id=<newid>`. **Unverified**: the exact flash/confirmation
  wording; verify by URL id plus the request appearing on the account.
- Everything defaults to "all media / all formats / all encodings", which the rules forbid
  for requests ("you may ask for multiple formats, but… not all of them"). Narrow the
  selection before submitting or the request is rule-breaking by default.
- `needlog`, `needcksum`, `needcue` default to checked; clear them unless the ask really
  requires them, and remember they only bite on CD FLAC.
- The log/cue row disappears the moment either FLAC or CD is unchecked — set formats and
  media before touching log options.
- `#amount` is recomputed on `input`; `page.fill` fires it, but direct `.value =` assignment
  does not.
- No client-side length limits: keep tags on the official list and descriptions reasonably
  short, since rejection happens after the POST.
