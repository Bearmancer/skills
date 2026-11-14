# Redacted — requests.php?action=new

Verified 2026-11-14 against the live form (Gazelle, logged in). Pair with the shared
procedure in `../SKILL.md`.

## Form contract

- URL `https://redacted.sh/requests.php?action=new`; page title "Create a request :: Redacted".
- `form#request_form`, POST, `application/x-www-form-urlencoded`, empty `action` (posts to
  the same URL). The vote form is `form#request_form.add_form` — leave it alone.
- Hidden fields: `auth` (per-page token, has a value attribute — read it), `action=takenew`,
  `amount` (bytes, default `104857600`), `current_uploaded`, `current_downloaded`.
- Submit: `input#button[type=submit][value="Create request"]`,
  `onclick="return confirmCreation();"`.

## Category

`select#categories` (`name="type"`, `onchange="Categories();"`). Values: `Music`,
`Applications`, `E-Books`, `Audiobooks`, `E-Learning Videos`, `Comedy`, `Comics`.

`Categories()` toggles rows, moves `required` ↔ `data-required`, relabels Title, and adds a
sublabel. Nothing is cleared. Visible rows:

- Music — Artist(s), Title, Record label, Catalogue number, WorldCat (OCLC) ID, Year, Image,
  Tags, Release type, Allowed formats, Allowed bitrates, Allowed media, Log / Cue,
  Description, Bounty.
- Audiobooks — Title (relabelled `Author - Title`, sublabel "Only include the author if
  applicable."), Year, Image, Tags, Description, Bounty.
- Comedy — Title (relabelled `Author - Title`), Year, Image, Tags, Description, Bounty.
- E-Books — Title (relabelled `Author - Title`, same sublabel), Image, Tags, Description,
  Bounty.
- Applications, E-Learning Videos, Comics — Title, Image, Tags, Description, Bounty.

Image, Tags, Description and Bounty are always shown and always required.

## Music fields

- Artist(s) — `input[name="artists[]"]#artist`, `required`, size 45,
  `data-gazelle-autocomplete="true"` (endpoint `artist.php?action=autocomplete`),
  `onblur="CheckVA()"`. Paired `select#importance[name="importance[]"]` with the standard
  8 roles. Add a row with `AddArtistField()` (the `+` link), remove with
  `RemoveArtistField()`; both wired through inline `onclick`, max 200 rows.
  `CheckVA()` reveals `#vawarning` for VA / "Various Artists" / "various".
  Every added row reuses `id="artist"` and `id="importance"` — select by `name`.
- Title — `input[name="title"]`, required, maxlength 200, size 50.
- Record label — `input[name="recordlabel"]`, maxlength 80.
- Catalogue number — `input[name="cataloguenumber"]`, maxlength 80.
- WorldCat (OCLC) ID — `input[name="oclc"]`, size 15, no maxlength.
- Year — `input[name="year"]`, required, maxlength 4, size 5.
- Image — `input[name="image"][type=url]`, maxlength 255, note "HTTPS only." Buttons
  `Rehost URL` / `Upload File` (`.image_rehost_button`, `.image_upload_button`) open
  image-host modals over a hidden `input.image_file_input[type=file]`.
- Tags — `#tags` (`name="tags"`), required, minlength 2, maxlength 200, autocomplete.
  `select#genre_tags` holds the official list (~95 values, dots inside words); changing it
  appends `, <tag>` to `#tags` via `add_tag()`.
- Release type — `select#releasetype[name="releasetype"]`, required:
  `1` Album, `3` Soundtrack, `5` EP, `6` Anthology, `7` Compilation, `9` Single,
  `11` Live album, `13` Remix, `14` Bootleg, `15` Interview, `16` Mixtape, `17` Demo,
  `18` Concert Recording, `19` DJ Mix, `21` Unknown.
- Allowed formats — master `input#toggle_formats[name="all_formats"]`,
  `onchange="Toggle('formats',1,true)"`, `required` until a sub-box is ticked. Subs
  `formats[]`: `0` MP3, `1` FLAC, `2` AAC, `3` AC3, `4` DTS, `5` DSD; each carries
  `onchange="ToggleLogCue(); AdjustRequiredToggle('formats')"`. Ticking the master checks
  **and disables** every sub-box, so only `all_formats=on` posts.
- Allowed bitrates — master `#toggle_bitrates[name="all_bitrates"]`
  (`Toggle('bitrates',1,true)`). Subs `bitrates[]`: `0` 192, `1` APS (VBR), `2` V2 (VBR),
  `3` V1 (VBR), `4` 256, `5` APX (VBR), `6` V0 (VBR), `7` 320, `8` Lossless,
  `9` 24bit Lossless, `10` DSD64, `11` DSD128, `12` DSD256, `13` DSD512, `14` Other.
- Allowed media — master `#toggle_media[name="all_media"]`. Subs `media[]`: `0` CD,
  `1` DVD, `2` Vinyl, `3` Soundboard, `4` SACD, `5` DAT, `6` Cassette, `7` WEB,
  `8` Blu-Ray, `9` LaserDisc.
- Log / Cue (CD FLAC only) — row `#logcue_tr`, revealed by `ToggleLogCue()` only when
  `format_1` (FLAC) is checked. Controls `#needlog` "Require log", `#minlogscore` (text,
  size 4) with `#minlogscore_span` shown only while `#needlog` is checked
  (`ToggleLogScore()`), `#needcue` "Require cue", `#needchecksum` "Require checksum".
  Page note: "You cannot require a log or cue unless FLAC is an allowed format".
- Description — `textarea#description[name="description"]`, required, maxlength 1000000,
  BBCode, inline Preview (`.button_preview_0`).
- Bounty (MB) — `#amount_box` (required, size 8, `pattern="\d+(\.\d+)?"`, default `100`,
  `onchange="Calculate();"`), `select#unit` (`mb` | `gb`, `onchange="Calculate();"`). The
  hidden `#amount` only updates inside `Calculate()`, which also writes `#new_uploaded`,
  `#new_ratio`, `#new_bounty`, `#bounty_after_tax` and disables `#button` when the amount
  exceeds `#current_uploaded` or is below 100 MB on this page.

## JS (static/functions/requests.js)

`Vote`, `Calculate`, `AddArtistField`, `RemoveArtistField`, `Categories`,
`hideRequiredFields`, `showRequiredFields`, `renameLabel`, `resetLabel`, `sublabel`,
`showRow`, `hideRow`, `renderCategoryRows`, `add_tag`, `Toggle`, `AdjustRequiredToggle`,
`ToggleLogCue`, `ToggleLogScore`, `confirmBounty`, `confirmCreation`, `confirmVote`,
`CheckVA`.

- `confirmCreation()` → `confirmBounty(25, 'Create request')`: dialog only when the bounty
  is ≥ 25 GB (GiB branch `gb ≥ 25`, or `mb ≥ 25 × 1024`); includes the new stats and a
  below-0.60 ratio warning.
- `Calculate()` is bound to `change` only. Nothing computes at load; the initial 100 MB
  matches the default hidden `amount`, but any programmatic edit must call it explicitly.

## Rules digest (rules.php?p=requests)

One title per request; no discographies, no vague asks. Multiple formats allowed, never all
of them, never contradictory. Requests may not be more specific than upload rules. Do not
unfill for trivial reasons; do not unfill on grounds not stated in the request. No bounty
trading, favouritism, or ransom. A deleted rule-breaking request keeps no bounty.

## Fill recipe

```js
await page.goto('https://redacted.sh/requests.php?action=new', { waitUntil: 'domcontentloaded' });
await page.selectOption('#categories', 'Music');           // Categories(), rows + required
await page.fill('input[name="artists[]"]', 'Artist');
await page.selectOption('select[name="importance[]"]', '1');
await page.click('a[onclick*="AddArtistField"]');           // per extra artist
await page.locator('input[name="artists[]"]').nth(1).fill('Second Artist');
await page.fill('input[name="title"]', 'Album');
await page.fill('input[name="year"]', '1997');
await page.fill('input[name="recordlabel"]', 'Label');       // optional
await page.fill('input[name="cataloguenumber"]', 'CAT-001'); // optional
await page.fill('input[name="image"]', 'https://…');         // optional, https only
await page.selectOption('#releasetype', '1');
await page.fill('#tags', 'rock, alternative');               // official tags, comma-separated
await page.fill('#description', 'Reason for the request…');
for (const v of ['1']) await page.check(`input[name="formats[]"][value="${v}"]`);
for (const v of ['8']) await page.check(`input[name="bitrates[]"][value="${v}"]`);
for (const v of ['0', '7']) await page.check(`input[name="media[]"][value="${v}"]`);
await page.fill('#amount_box', '100');
await page.selectOption('#unit', 'mb');
await page.evaluate(() => Calculate());
// assert #amount === 104857600 and #button not disabled, then:
page.once('dialog', d => d.accept());
await page.click('#button');
```

## Verify and gotchas

- Success redirects to `requests.php?id=<newid>`. **Unverified**: the flash wording was
  never captured; verify by URL id plus the request appearing on the account.
- Stale bounty is the classic silent failure: fill `#amount_box` without `Calculate()` and
  100 MB posts regardless of the typed number.
- Hidden rows keep values; a value typed for one category survives the switch and can still
  post under `data-required` semantics.
- Master "All" boxes disable their subs, so mixing `all_formats` with hand-picked formats is
  contradictory; pick one style.
- `#tags` stops at 200 characters — trim, do not append blindly.
- Artist rows after the first share ids; never use `#artist` for anything but row one.
