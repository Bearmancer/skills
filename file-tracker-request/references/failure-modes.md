# Failure modes

Read before filling, and when a fill, search or submit misbehaves.

- Hand-written batch fill instead of `build_payload.py` + `fill_request.js`: on
  2026-11-24 a Nott batch joined tags with `;` (50 requests got one merged tag) and
  passed `[5,1]` as an artist (11 RED requests with artists named "1"). Both are now
  refused by the builder and the fill lint; RED rows could only be fixed by comment
  because a second voter locks the edit form.
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
