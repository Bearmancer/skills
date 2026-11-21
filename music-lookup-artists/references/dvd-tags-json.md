# DVD research: tags.json

Every concert-video disc folder (`D:\DVDs\<disc>\`) carries a `tags.json` sidecar (7-25 KB) with researched data for each chapter. It is the primary source: it supersedes filename parsing and web lookups. A library pass reads it first, and research fills what is missing or thin. Merging, naming and verification belong to `dvd-concert-curation`.

## Schema

One entry per title chapter:

```json
{
  "title": "title 01.mkv",
  "chapter": 2,
  "composer": "Ludwig van Beethoven",
  "work": "Piano Concerto No. 5 in E-flat major, Op. 73 \"Emperor\"",
  "movement_number": 1,
  "movement": "Allegro",
  "kind": "music",
  "conductor": "Antoni Wit",
  "orchestra": "Bilkent Symphony Orchestra",
  "soloists": ["Idil Biret"],
  "choir": null,
  "performance_year": 2008,
  "performance_date": null,
  "venue": null,
  "seconds": 1087.5,
  "confidence": "high",
  "evidence": ["https://..."],
  "release": { "label": "Arthaus", "catalogue": "100 148", "urls": ["https://..."] }
}
```

- `kind` is music, intro, trailer or talk. Per-movement rips exist only for music chapters; intro and title-card chapters were never ripped.
- `seconds` (older files: `duration_seconds`) is the chapter duration, and it is the key for duration matching.
- `confidence` is high, medium or low, and `evidence` holds the URLs or artefacts that establish the value. A low-confidence value is flagged for the owner, never guessed.

## Chapter join rule

A file prefix `T<tt>-<cc>` means chapter `cc` of `title <tt>.mkv`. A bare `NN - ...` means chapter NN of the covering title (usually `title 00.mkv`). The manifest generator implements this join. A mismatch between the filename and the tags is flagged (`tagsMismatch`), never silently resolved.

## Research method

1. Read `tags.json` and list what is missing or low-confidence.
2. Scan the folder artwork (covers and booklets, often under `Scans\` or `scans\`) with a vision lane. It corroborates performers and adds venue, date and catalogue data.
3. Research each gap through the `routing.md` row "DVD / concert-video chapter data", with the label bans in `exclusions.md`. Reconcile multi-site sweeps against `tags.json`, and give every correction its source.
4. Duration matching pins unnamed sections. Compare chapter seconds against a known tracklist, with PAL/NTSC factors where relevant (1000/1001, 25/24, 24/25). Worked case: on a 1965 Firebird concert the disc left the middle sections unnamed. A medici.tv section list plus duration matching named every chapter, and two contemporaneous sources confirmed the opening work.
5. Incomplete films stay incomplete. If the film really contains only some movements (checked against a second source's tracklist), record that. Never invent the missing movements, and never delete the work without the owner's ruling.

## Reconciliation

When independent research contradicts `tags.json` (a wrong year, a missing soloist, an unclear venue), the correction wins only with its citation. Record both the old and the new value in the manifest's flags, so the owner can see what changed and why.
