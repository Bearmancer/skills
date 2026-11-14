---
name: track-requests
description: Fill, verify or edit a request on Redacted (redacted.sh) or Orpheus (orpheus.network) — the "Create a request" form. Use whenever asked to post a request, fill or check the requests form, or work out which fields and bounty a request needs. Per-tracker field maps, selectors, category rules and JS quirks live in references/.
---

# Track requests — Redacted and Orpheus

Two Gazelle trackers share one form skeleton with different details. Open the matching
reference before touching the page:

- `redacted.sh` → `references/redacted.md`
- `orpheus.network` → `references/orpheus.md`

For any other tracker, say plainly that these notes do not cover it; do not extrapolate.

## Ground rules (both sites, from rules.php?p=requests)

- One title per request. No discographies, no vague asks.
- Multiple formats allowed, never all of them, never contradictory (FLAC **or** V0, not both).
- A request cannot be more specific than the upload rules (e.g. demanding a log for MP3).
- The bounty is a reward, not a ransom, and requests must not be steered to a named filler.
- Submitting spends upload credit and cannot be undone by editing — read the payload back to
  the user and get a yes before clicking Create.

## Shared mechanics (verified on both)

- `form#request_form`, POST to the same URL, `application/x-www-form-urlencoded`.
  On Redacted the voting form carries `.add_form` and must not be touched.
- Hidden `auth` token plus `action=takenew`. Re-read `auth` on every load; Orpheus also
  mirrors it on `document.body.dataset.auth`.
- Category select `#categories` (`name="type"`) with the same 7 values. Set it first: it
  hides rows and on Redacted also moves `required` to `data-required` and relabels Title.
  Entered values survive a switch on both sites.
- Artists are `artists[]` text inputs paired index-for-index with `importance[]`:
  `1` Main, `2` Guest, `3` Remixer, `4` Composer, `5` Conductor, `6` DJ / Compiler,
  `7` Producer, `8` Arranger. "+" adds a row (max 200), "−" removes one. Both flag
  "Various Artists" and want multiple rows instead.
- Tags: `#tags`, comma-separated, period inside multi-word tags (`hip.hop`); the
  `#genre_tags` select appends the official tag through `add_tag()`.
- Description: `#description` textarea, BBCode, with an inline Preview button.
- Bounty: `#amount_box` + `#unit`, converted to bytes into hidden `#amount`. The site's
  conversion function must run after any programmatic change or the stale default posts.
- Pre-submit assertions: hidden `#amount` equals the intended byte count and `#button` is
  not disabled.

## Where the two diverge (trust the reference, not memory)

- Required attributes: Redacted marks required inputs in HTML; Orpheus marks nothing and
  validates server-side.
- Log/cue: Redacted gates the row on FLAC alone and uses a 4-character text box for the
  minimum log score; Orpheus gates on FLAC **and** CD and uses a 0–100 range slider.
- Bounty units: Redacted MB/GB; Orpheus MiB/GiB, plus a hidden `request_tax` — the credited
  bounty is `amount × (1 − tax)`.
- Format list: Orpheus adds Ogg Vorbis and has no DSD; its "Allowed encodings" row is
  Redacted's "Allowed bitrates", with a different value map.
- Release-type value maps differ (Orpheus adds Sampler and Split, drops several Redacted
  values) — copy from the reference, never from the other site.
- Orpheus has a `groupid` "Torrent group" field; Redacted has `oclc` WorldCat.
- Artist ids: Orpheus uses `artist_0..n`; Redacted reuses `id="artist"` on every row, so
  select artists by `name` there.
- Submit confirmation: Redacted fires `confirm()` above 25 GB; Orpheus fires none on create.
- "All" checkbox: Redacted disables the sub-boxes when ticked (they post nothing); Orpheus
  only checks them.

## Procedure

1. Identify the tracker and read its reference file.
2. Read the planned request back to the user in one compact block — category, artists and
   roles, title, year, release type, tags, formats/bitrates/media, log requirements,
   description gist, bounty. Get confirmation.
3. Open the form, read `auth`, set the category, fill in the order the reference gives.
4. Run the bounty calculation, then assert `#amount` and the submit button state.
5. Submit. Accept a dialog only when the numbers match what was agreed.
6. Verify on the site itself: redirect to the new request id and the request present on the
   account. A returned click is not evidence.

## Failure modes worth checking first

- Form posts 100 MiB because the bounty calculation never ran after a programmatic edit.
- Hidden rows keep their values, so a field filled under one category can still post.
- Submit disabled by insufficient credit — read the on-page message rather than retrying.
- Duplicate or rule-breaking request — the server rejects it; surface the message, do not
  "fix" it by loosening the request.
