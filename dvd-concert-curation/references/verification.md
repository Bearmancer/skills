# Verification

Every merged output passes six checks before its folder's sources may delete.
Exact commands and the tolerances that matter:

## The six checks

1. **mkvmerge append exit 0** — default append mapping notices are informational, not
   warnings; archive the full mergeOutput verbatim in the runlog.
2. **Chapters** — count equals movement count, names match tags.json exactly
   (`mkvextract chapters` → rewrite ChapterString → `mkvpropedit --chapters`).
3. **Duration** — output vs Σinputs within max(2 s, 1%). Measure the right thing:
   video-stream duration when present, else format.duration gated on a hard
   no-subtitle assertion (a diverging subtitle track can inflate format.duration).
   ffprobe 9.x returns NO stream duration for these DVD MKVs — the fallback is normal,
   not an error.
4. **Codecs** — video and audio codec names unchanged vs the first input.
5. **Size** — output vs Σinput bytes; a small negative delta (≈ −0.02%) is normal
   container overhead removal; a large delta is a red flag.
6. **Full decode** — `ffmpeg -v error -xerror -i OUT -map 0:v -map 0:a -f null -`
   exit 0. Never map subtitle streams (dvd_subtitle has no null encoder). Non-monotonic
   DTS notices at append joins are accepted; anything else fails.

Plus metadata: segment title (mkvinfo) AND global TITLE tag both equal the work title.
Measure the global TITLE with `mkvextract tags <file>` — the TITLE simple tag under the
`Tag` with empty `Targets` is the true global tag. **`ffprobe format_tags=title` is NOT a
reliable global-tag measurement**: FFmpeg's Matroska demuxer falls back to the segment
title when no global TITLE exists, and prefers part/track-level TITLE tags over the global
one (verified wrong on 233/414 files in the 2026-11-17 survey). Set the global tag via
mkvpropedit (TargetTypeValue 50 tags XML), then verify with mkvextract, never ffprobe.

## Tool gotchas (this host)

- mkvmerge JSON identification (`-J`): durations in NANOSECONDS (÷1e9); tracks at top
  level (`$j.tracks`); the `--` separator is REJECTED in identification mode.
- mkvpropedit: `--edit info --set title=<t> --tags all:<xml>`; Matroska tags XML lists
  TargetTypeValue 50 (album) before 30 (track).
- Keep output paths ≤ 240 chars; UTF-8 without BOM for tags/chapters XML.
- Chapter cuts with `-c copy` start on keyframes: allow max(2 s, 5%) length tolerance;
  MakeMKV remux drift needs max(10 s, 1%).

## Runlog

`runlog.json` is JSONL — one compressed JSON object per line, NOT one document.
Parse line by line. Row types: `output` (per-output checks, pass, error, mergeOutput,
missingChaptersCount, sourcesCount, resumed) and `folder-summary` (deletedCount,
sourcesRenamed, title-rip evidence). Resume-verify reads prior passing rows by output
name to skip re-merging an existing output.

## Concurrency and resilience

- The driver holds an exclusive per-folder lock (FileStream, Share.None,
  DeleteOnClose — released automatically on crash). A second instance exits clean.
- ffprobe calls retry 3× with linear backoff; existence checks re-check once after 5 s
  before declaring a file missing. Both were added after four 2026-11-17 batch
  failures caused by single-shot probe misses on files that existed minutes later.
- Run-Batch pre-flights the manifest (parse + folder present) and the driver hash
  before every folder, retries failed folders exactly once, and closes with a census:
  outputs exist, sources deleted, title-rip counts unchanged.
- Stop-don't-repair: first failure stops the folder, sources kept, failure row logged.
  Re-running the folder resumes: passing outputs verify-only, failed ones retry.

## Title toolchain (efficient)

Measured on this host (2026-11-17): mkvinfo ~290 ms (segment title only, fragile text),
mkvextract tags ~480 ms (global tags ground truth), ffprobe ~660 ms (unreliable global
title), mkvmerge -J ~800 ms (segment title + duration + codecs, structured JSON, but NO
global tags). Pick by job:

- **Read segment title + duration + codecs**: `mkvmerge -J <file>` — one spawn,
  `container.properties.title` is the segment title, duration in nanoseconds, tracks at
  top level. Preferred over mkvinfo (structured) and ffprobe (more value per spawn).
- **Read global TITLE**: `mkvextract tags <file>` parsed as XML
  (`[xml](... | Out-String)`); the TITLE under the empty-Targets Tag. mkvmerge -J does
  not expose global tags, so this second spawn is required when the global tag matters.
- **Write segment + global title together**: one `mkvpropedit --edit info --set title=<t>
  --tags all:<xml>` call (TargetTypeValue 50). Metadata-only, no remux.
- **Verify a restyle**: re-read segment (mkvmerge -J) and global (mkvextract tags); assert
  both equal the new filename stem. ffprobe is reserved for merge duration/codec checks,
  never for title verification.

**Encoding trap (cost two halts on 2026-11-17):** `mkvextract tags` emits a UTF-8 BOM, and
the host console code page is ibm437 — capturing native stdout naively corrupts multibyte
chars and the BOM breaks the `[xml]` cast ("specified node cannot be inserted... wrong
type"). Capture MKVToolNix output via a Process with explicit UTF-8 decoding and exact
ArgumentList, or strip the BOM (`TrimStart([char]0xFEFF)`) and parse with
`XmlDocument.LoadXml`. Set `[Console]::OutputEncoding = UTF8` for any inline probe.

## Delete-after-verify

Only manifest-listed movement sources delete, only after every output in the folder
passes, only in merge mode without -NoDelete. Whole-title rips (`title NN.mkv`) are
snapshotted (name/length/mtime) before and after every run and must be unchanged.
The census proves the end state on disk — never trust exit codes or logs alone.
