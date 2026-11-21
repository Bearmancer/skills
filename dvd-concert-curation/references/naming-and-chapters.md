# Naming and chapters

## Output naming

One file per musical work, possessive-surname style (owner ruling 2026-11-17):

```
Surname's Work - Performers (Year).mkv
```

Example: `Rossini's Il barbiere di Siviglia Overture - Georg Solti and Chicago Symphony Orchestra (1978).mkv`

- The composer is the surname in possessive form (`Rossini's`, `Mendelssohn's`,
  `Beethoven's`), never `Gioachino Rossini - Work`. First names drop from the name.
- Performer enumeration: exactly two performers join with ` and `; three or more join
  with `, ` (commas). Roles stay curated (soloists, conductor, orchestra).
- No track numbering anywhere in the name.
- Soloists/conductor/orchestra are curated per folder from tags.json (the research pass),
  not parsed from filenames — filename performer strings are often incomplete or wrong
  (a curated pass once wrongly added the soloist to purely orchestral works).
- Year is the performance year from tags.json, never the release year. When genuinely
  unknown, leave the year out and flag it (`missingYear`) rather than guess.
- Accented names stay accented end-to-end (András Schiff). The MKV segment title and the
  global TITLE tag must equal the filename minus extension, byte-for-byte.

## Songs (pop/rock video)

Non-classical song files (the BD pop/rock folders) use:

```
Song name - Artist (Year).mkv
```

No possessive, no composer/work split — the song title leads, then the performing artist.

## Talks and interviews

Standalone talk/interview extras use the song-parallel form, subject leading and the
generic kind keyword dropped: `Idil Biret interview - Idil Biret (2008).mkv`. The
manifest generator emits these via the standalone naming path (no possessive).

## Disc folder names

Folder names are coherent descriptive disc titles, never default/incoherent strings
(`Mahler_9_Barenboim_dvd`, `Beethoven {Solti-Perahia}`, `???`, underscore/bracket
catalogue-style names). Name the disc by its content in the same possessive spirit
(e.g. `Mahler's Symphony No. 9 (Barenboim)`); a multi-composer disc gets a descriptive
title covering its composers. The ` / ` in the owner's example was illustrative, not a
mandated join. Folder renames are owner-gated through the title-survey review.

## Filename sanitization (Windows)

Tags-derived titles can contain characters NTFS forbids in filenames. Substitution rule
(owner-approved "Option A"): ASCII `"` → paired curly quotes `“ ”`, `:` → U+A789 modifier
letter colon `꞉`. Appearance and the name==title invariant survive; chapter names inside
the MKV are metadata and keep the original characters.

Systematic assertions the manifest must pass (hard-fail on any residue):

- no `<>:"/\|?*`, control characters, trailing dot/space, reserved device names
  (CON, PRN, AUX, NUL, COM1–9, LPT1–9) in any outputName, standalone name or mkvTitle;
- name == mkvTitle + `.mkv` everywhere; names unique;
- every full path ≤ 240 chars. When a name overflows, drop opus/catalogue detail first
  (D3 shortening), record `nameShortened`, never truncate mid-word.

## Chapter naming

- Every merged output carries one chapter per movement, named from tags.json with the
  movement number verbatim (`1. Allegro con brio`), so gaps in the original numbering
  stay visible inside the file.
- Folded extras keep their kind label (`Applause`, `Encore 1 (unidentified)`).
- Chapter boundaries come from the source rips' own chapter marks (mkvextract →
  rewrite → mkvpropedit), never re-derived from durations.

## Extras classification

Per tags.json `kind` and the chapter role:

- **music** → part of a work (movement).
- **intro / title card / bumper / credits** → never ripped per-movement; not movements,
  so never listed as missing movements of adjacent works.
- **applause / encore** → folded into the work as chapters (owner ruling).
- **talk / interview** → standalone output, renamed with the same naming rules.
- **trailer** → dropped entirely (owner ruling).

## missingChapters

For each output, compare against the work's complete movement set in tags.json (all
music chapters of that work on the title, ripped or not). Record per missing entry:
`{number, name, seconds, reason}` with reason ∈ {never ripped, intro/title card,
not on film, merged into adjacent chapter}. Surface the list in the review doc and a
count in every runlog row. Documented example: a Firebird (1945) suite whose 17 s
"1a. Introduction" was never ripped and whose final chapter merges two sections —
one `never ripped` entry, one `merged into adjacent chapter` entry, nothing else.
