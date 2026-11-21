# Request description body

Read at procedure step 3, when building the description.

## Contents block

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

## Mandatory closing block (owner ruling 2026-11-19)

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
