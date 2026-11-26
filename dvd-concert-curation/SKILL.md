---
name: dvd-concert-curation
description: 'Use when processing ripped classical or concert DVD folders (D:\DVDs) into a curated video library: classify works, movements and extras, merge split movement MKVs into one file per work, or re-curate kept whole-title rips by cutting chapter ranges out of them (strategy B), name every chapter, restyle titles, filenames and folders, and verify merges and cuts losslessly before deleting sources. Triggers: DVDs, tags.json, movement chapters, per-work merge, title rip, whole-title rips, strategy B, cut chapters from a title rip, concert video.'
---

# dvd-concert-curation

Turn folders of ripped concert DVDs (whole-title MKVs plus per-movement split rips) into
one verified, chapter-named file per musical work, with a researched metadata record
beside every folder. The whole pipeline is gated: the owner approves the manifest before
anything merges, and nothing deletes until verification passes.

## Python seam — entry point for both rip shapes

`scripts/curate.py` is the one entry point for disc folders: per-movement rips
(`Ttt-cc - …` / `NN - …` names, strategy A) and kept whole-title rips (`title NN.mkv`,
strategy B). Run it with uv, never through a PowerShell wrapper:

```
uv run --quiet scripts/curate.py plan   <disc folder> [--research overrides.json] --out manifest.json
uv run --quiet scripts/curate.py plan   <disc folder> --strategy b --manifest <approved-A.json> [--research overrides.json] --out manifest-B.json
uv run --quiet scripts/curate.py merge  <disc folder> --manifest manifest.json --out-dir <dir> --approved-by "<owner ruling>"
uv run --quiet scripts/curate.py verify <disc folder> --manifest manifest.json --out-dir <dir>
```

`plan` detects the rip shape, groups works from tags.json (never filenames), applies the
naming/sanitization rules and writes the manifest for the owner gate. Owner research
corrections go in a `--research` JSON keyed `"<title_file>|<chapter>"` (owner research >
tags.json); tags.json itself is never hand-edited. `merge` re-plans and refuses a stale
manifest, checks free space (2×), runs the three-pass append/chapter/title contract and
the six checks + title invariant per output, resume-verifies existing outputs, and never
deletes or overwrites. Strategy B (the second `plan` line above, or auto-detected on a
folder of kept whole-title rips) re-curates the approved plan by cutting keyframe-snapped
stream-copy ranges out of `title NN.mkv`, remaps and names the inner chapters from the
research, and proves each cut against the folder's approved merged outputs (names,
chapters, durations, title bytes) plus full chapter coverage. Evidence mechanics:
`references/verification.md`.
The PowerShell pipeline below remains the prior art until its retirement (EPIC 1.1.4).

## Ground rules

- **tags.json-first**: the folder's `tags.json` sidecar (researched per-chapter metadata)
  supersedes filename parsing and web lookups. Read it before inventing anything.
- **verify-then-delete**: movement sources delete only after the merged output passes all
  six checks (see `references/verification.md`). Whole-title rips (`title NN.mkv`) are
  never touched, renamed or deleted — they are the safety net.
- **stop-don't-repair**: the first failure inside a folder stops that folder; every source
  stays. Never repair mid-run; re-run the folder later (resume-verify handles it).
- **one lane per folder**: the driver holds an exclusive per-folder lock; a second
  instance exits clean. Never run two writers on one folder.
- **name == title**: the output filename (minus extension) equals the MKV segment title
  and the global TITLE tag, exactly.

## Pipeline

1. **Research metadata** — per disc folder, fill or refresh `tags.json`: composer, work,
   movement numbers/names, performers (soloists, conductor, orchestra, choir),
   performance year/date, venue, kind (music / intro / trailer / talk), confidence and
   evidence URLs. Method, schema and sources: `music-lookup-artists/references/dvd-tags-json.md`
   (sources ranked in `music-lookup-artists/references/routing.md`).
   *Done when*: every chapter of every title has a tags.json entry, gaps carry explicit
   flags, and the owner has answered the research questions.

2. **Build the manifest** — copy `scripts/` to a work directory (e.g.
   `%TEMP%\opencode\dvd-merge\`) and run the generator there:
   ```powershell
   pwsh -NoProfile -File .\Get-MergeManifest.ps1
   ```
   It joins movement files to title chapters, classifies extras (trailers dropped,
   applause/intro folded into the work, talks standalone), applies the naming and
   sanitization rules from `references/naming-and-chapters.md`, computes per-output
   `missingChapters`, and writes `manifest.json` + `manifest-review.md`.
   *Done when*: every named file is classified exactly once, zero unclassified, all
   filename assertions green, and the owner approves `manifest-review.md` (the gate).

3. **Pilot** — run the driver on 2–3 representative folders with `-NoDelete`:
   ```powershell
   pwsh -NoProfile -File .\Invoke-Merge.ps1 -Folder '<folder name>' -NoDelete
   ```
   Deliver the per-output evidence table (six checks per output) for owner sign-off.
   *Done when*: pilot outputs pass every check and the owner approves the batch.

4. **Batch + finalize** — one command runs all remaining folders, retries failed folders
   once, and closes with a disk-surface census (outputs exist, sources deleted, title-rip
   counts unchanged):
   ```powershell
   pwsh -NoProfile -File .\Run-Batch.ps1
   ```
   The driver deletes each folder's sources only after its own verification passes.
   *Done when*: the census reports 0 missing outputs, 0 remaining sources, 0 title-rip
   changes, and every folder exit 0. Investigate anything else from the runlog
   (`runlog.json` is JSONL — one JSON object per line) before reporting done.

5. **Close out** — record the decisions in the owning module's LEDGER (media work is
   LEDGER-only on this host), deliver the per-folder summary, and purge the work
   directory, spec and tasks scaffolding per the owner's purge rule. Ask keep-or-delete
   for anything ambiguous.
   *Done when*: only the shipped library artifacts and the skill remain.

## Title restyle (existing library)

For a library that is already merged but carries default/incoherent titles or the old
naming style, restyle without re-merging:

1. **Survey** every MKV (segment title via mkvinfo, global TITLE tag via ffprobe) and
   every folder name; classify each as default (`title NN`, volume-label, placeholder),
   mismatch (title != filename stem), old-style, or coherent. A read-only fixer lane
   produces the census + per-folder tables.
2. **Map** each folder and file to its new name per `references/naming-and-chapters.md`
   (classical possessive, songs, talks, coherent folder titles). Present the mapping for
   owner approval — folder renames and any judgment calls are owner-gated.
3. **Apply** with `scripts/Apply-Restyle.ps1`, driven by the mapping JSON (rows with
   oldFolder/newFolder/oldFile/newFile/newTitle/kind, a trailerDelete list, and a tagsSync
   plan). It preflights (tags `from` values match live tags.json, exact disk coverage,
   collision/path checks), then deletes trailers at old paths → renames folders → renames
   files → sets segment + global title per file via one mkvpropedit call → backs up and
   syncs tags.json (title_file renames last) → verifies on disk. Stop-don't-repair on first
   failure; `-PreflightOnly` and `-VerifyOnly` modes. Metadata-only; no re-merge.
4. **Verify on disk**: re-probe titles and list filenames; confirm name == title
   everywhere and no default/incoherent title remains. Never trust exit codes alone.

## Reference

- `music-lookup-artists/references/dvd-tags-json.md` — tags.json schema, join rule and the
  research method (confidence flags, duration matching, reconciliation). Read at step 1.
- `references/naming-and-chapters.md` — output naming, filename sanitization, chapter
  naming, extras folding, missingChapters. Read at step 2.
- `references/verification.md` — the six checks, exact commands and tolerances, metric
  gotchas, runlog format, lock and retry behavior. Read at steps 3–4.
