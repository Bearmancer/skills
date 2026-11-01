---
name: subtitle-triage
description: "Use whenever subtitles are the subject in a Sonarr/Radarr/Bazarr library: provenance, fit to the video (late, out of sync, past the end), a better replacement, resync or cleanup. Measure the fit first, even when the user only says \"the subtitles are wrong\"."
---

# Subtitle triage

Answer with numbers: where the file came from, whether it fits _this_ video, and the smallest correct repair. Write to the library only when the user asks for a change.

Wiring (ports, apikeys, config paths, category chain): the `arr-api-reference` skill. Bazarr base URL and `auth.apikey` come from `C:\ProgramData\Bazarr\config\config.yaml`, sent as header `X-API-KEY`.

## 1. Provenance: which source wrote this file

- `C:\ProgramData\Bazarr\db\bazarr.db`, opened read-only (`sqlite3.connect("file:...?mode=ro", uri=True)`), table `table_history`: `action` (1 auto download, 2 manual, 3 upgrade, 5 sync), `provider`, `subs_id`, `subtitles_path`, `video_path`, `score/score_out_of`, `timestamp`, `upgradedFromId`.
- The row whose `subtitles_path` equals the file on disk is the source. An `action 3` row supersedes the row it points to via `upgradedFromId`: read the pair; the older row is the previous sub, not a second copy.
- Episode/season ids: `GET {sonarr}/api/v3/episode?seriesId=<id>&seasonNumber=<n>`, then `/api/v3/episodefile/<id>` (path, sceneName, `mediaInfo.runTime`, `videoFps`: Sonarr's own analysis, the cheapest source of duration and fps).
- Bazarr side: `GET {bazarr}/api/episodes?seriesid[]=<sonarrSeriesId>` gives each episode's `subtitles[]` with the on-disk `path`, `file_size`, `hi`, and the Bazarr row `id`.

## 2. Fit: measure against the video, not the cue list

The reference in sync with the picture is the file's **own embedded track**:

- `ffprobe -v error -show_entries stream=index,codec_type:stream_tags=language,title -show_entries format=duration -of json <mkv>` lists subtitle stream indices.
- `ffmpeg -v error -y -i <mkv> -vn -an -map 0:<idx> -c:s srt ref.srt` extracts one into a temp dir.

Measure three ways; one alone lies:

- **Content anchors** (strongest): compare the times of the same line in the sub and the reference. For a translated reference, use language-invariant anchors (names such as "Bruce", numbers): a name's time is the same in every language.
- **Interval-overlap cosine** at a scanned offset: merge the cue intervals of both, score overlap / sqrt(ref_dur*sub_dur), scan the offset. ~0.9 = same timeline; ~0.6-0.7 = different. With a 23.976/25 fps factor in play, also scan scale.
- **Drift buckets**: median signed delta per 4-minute bucket. Flat = constant offset; growing ~4.3% per minute = fps mismatch (23.976 vs 25).

Traps that produced wrong verdicts before:

- **Nearest-cue deltas are worthless on dense subs.** With ~600 cues every ~2.4 s, any time is within ~1.5 s of a cue, so a sub 15 s late still looks "±400 ms". Only content anchors or the cosine settle it.
- `silencedetect` coverage is too blunt: audio here is ~88% non-silent, and time past the audio end scores as covered.
- Frame checks settle on-screen text: `ffmpeg -v error -y -ss <t> -i <mkv> -frames:v 1 -vf scale=560:-1 f.png`, then view the image. That is how "the card at 3.0 s says 11:30 AM" is known, not assumed.

## 3. Repair: pick one, ask first

- **Replace with another subtitle** (the default; "get me a new subtitle"): `GET {bazarr}/api/providers/episodes?episodeid=<bazarr episode id>` lists candidates (`provider`, `score`, `subtitle` id, `release_info`, `url`). `POST {bazarr}/api/providers/episodes?seriesid=<id>&episodeid=<id>&hi=False&forced=False&original_format=False&provider=<p>&subtitle=<id>` installs it (204, async, lands in history as action 2). Prefer a sub from the same kind of release as the file (WEB sub for a WEB rip); score matches release-name metadata only, never sync.
- **Trim broadcast-only cues** (only while keeping the existing sub): broadcast captures carry pre-show promos, post-episode promos and caption cards that a streaming/WEB file lacks. Drop blocks starting past the video duration, keep the file's line endings, then re-read cue count and span. Frame-check boundary cues first: a cue can sit over a card that does exist.
- **Sync in place, LAST RESORT**: use it only when the sub you have is the right edit and no provider offers a fitting replacement, or the user says keep the current file. It repairs the timebase only: a broadcast capture stays a broadcast capture, so replacing beats it whenever a fitting sub exists. `PATCH {bazarr}/api/subtitles?action=sync&language=<code2>&type=episode&id=<bazarr episode id>&path=<sub file>&forced=False&hi=False&reference=a:0&no_fix_framerate=False&gss=True&max_offset_seconds=60`. **Without `path` it returns 501 "Path not provided"**; the swagger marks it optional, but the query param is mandatory. Async: 204, file rewritten ~1 s later, history action 5 records "offset X and framerate scale factor Y" (0.95-0.96 = the 25 fps vs 23.976 case).
- After any write: re-read `GET /api/episodes?seriesid[]=<id>` and confirm `file_size` matches the file on disk. Bazarr updates its record when it writes, not when you do.

## Discipline

- Candidates go to a temp dir (gestdown `url`s are plain HTTP, no auth). Fetch into the temp dir only.
- Before a library write: copy the file to the temp dir, record size and sha256, and report the exact restore command. Subtitle files are small, but they are still the user's data.
- Report the fix with the numbers that prove it (anchors and cosine before/after), not with what was run.
