---
name: subtitle-triage
description: "Use when subtitles are the problem in a Sonarr, Radarr or Bazarr library: provenance, sync fit, a better replacement, resync or cleanup. Measure the fit first."
---

# Subtitle triage

Answer with numbers: where the file came from, whether it fits _this_ video, and the smallest correct repair. Write to the library only when the user asks for a change.

Wiring (ports, apikeys, config paths, category chain): the `arr-api-reference` skill. Bazarr base URL and `auth.apikey` come from `C:\ProgramData\Bazarr\config\config.yaml`, sent as header `X-API-KEY`.

## 1. Provenance: which source wrote this file

- `C:\ProgramData\Bazarr\db\bazarr.db`, opened read-only (`sqlite3.connect("file:...?mode=ro", uri=True)`), table `table_history`: `action` (1 auto download, 2 manual, 3 upgrade, 5 sync), `provider`, `subs_id`, `subtitles_path`, `video_path`, `score/score_out_of`, `timestamp`, `upgradedFromId`.
- The row whose `subtitles_path` equals the file on disk is the source. An `action 3` row supersedes the row it points to via `upgradedFromId`: read the pair; the older row is the previous sub, not a second copy.
- Episode/season ids: `GET {sonarr}/api/v3/episode?seriesId=<id>&seasonNumber=<n>`, then `/api/v3/episodefile/<id>` (path, sceneName, `mediaInfo.runTime`, `videoFps`: Sonarr's own analysis, the cheapest source of duration and fps).
- Bazarr side: `GET {bazarr}/api/episodes?seriesid[]=<sonarrSeriesId>` gives each episode's `subtitles[]` with the on-disk `path`, `file_size`, `hi` and the subtitle record `id`. The episode record itself has no Bazarr id: every other endpoint's `episodeid`/`id` is the **Sonarr** episode id.
- Sidecar names come in two generations: with `single_language` on, new subs save as `<video>.srt` / `<video>.hi.srt`; older batches saved `<video>.en.srt` / `<video>.en.hi.srt`. Bazarr indexes both as English, so test for **all** of them before calling a file unsubtitled - and never read `wanted` 0 as "the subtitles fit".

## 2. Fit: measure against the video, not the cue list

The reference in sync with the picture is the file's **own embedded track**:

- `ffprobe -v error -show_entries stream=index,codec_type:stream_tags=language,title -show_entries format=duration -of json <mkv>` lists subtitle stream indices.
- `ffmpeg -v error -y -i <mkv> -vn -an -map 0:<idx> -c:s srt ref.srt` extracts one into a temp dir.

No embedded track (the usual WEB-DL case): build the reference from the file's **own audio** instead - `-map 0:<idx>` for the stream whose `language=eng`, at 16 kHz mono, and transcribe it (`parakeet ref.wav`; 22 min takes ~2 min on CPU). Pick the track by its language tag, never by default: a Netflix `NF WEB-DL` here defaults to the Portuguese dub, and ASR of the wrong language silently scores every cue as a miss.

Measure three ways; one alone lies:

- **Content anchors** (strongest): compare the times of the same line in the sub and the reference. For a translated reference, use language-invariant anchors (names such as "Bruce", numbers): a name's time is the same in every language.
- **Interval-overlap cosine** at a scanned offset: merge the cue intervals of both, score overlap / sqrt(ref_dur*sub_dur), scan the offset. ~0.9 = same timeline; ~0.6-0.7 = different. With a 23.976/25 fps factor in play, also scan scale.
- **Drift buckets**: median signed delta per 4-minute bucket. Flat = constant offset; growing ~4.3% per minute = fps mismatch (23.976 vs 25).

Traps that produced wrong verdicts before:

- **Nearest-cue deltas are worthless on dense subs.** With ~600 cues every ~2.4 s, any time is within ~1.5 s of a cue, so a sub 15 s late still looks "±400 ms". Only content anchors or the cosine settle it.
- **The sub can belong to a different video altogether.** A 22-minute file subtitled only from 0:00 to 2:52, whose words are a trailer's, is not a sync failure: measure **coverage** (merged cue span / runtime) and **anchor ratio** (share of cues whose words appear in the reference near their own timestamp). Cosine at the best offset and nearest-cue deltas both hide it, and a 93.61% provider score bought exactly this file - because score compares release-name metadata, never content.
- `silencedetect` coverage is too blunt: audio here is ~88% non-silent, and time past the audio end scores as covered.
- Frame checks settle on-screen text: `ffmpeg -v error -y -ss <t> -i <mkv> -frames:v 1 -vf scale=560:-1 f.png`, then view the image. That is how "the card at 3.0 s says 11:30 AM" is known, not assumed.

## 3. Repair: pick one, ask first

- **Replace with another subtitle** (the default; "get me a new subtitle"): `GET {bazarr}/api/providers/episodes?episodeid=<sonarr episode id>` lists candidates (`provider`, `score`, `subtitle`, `release_info`, `url`). `POST {bazarr}/api/providers/episodes?seriesid=<sonarr series id>&episodeid=<sonarr episode id>&hi=False&forced=False&original_format=False&provider=<p>&subtitle=<id>` installs it (204, async, lands in history as action 2). Both ids are **Sonarr** ids, and the `subtitle` value is a key into Bazarr's in-memory `subtitle_cache` from *your* search: install right after searching, an expired one answers "Subtitle not found in cache. Please search again." Measure a candidate before you install it (fetch into the temp dir, run the section-2 numbers); score matches release-name metadata only, never sync. Prefer a sub from the same kind of release as the file (WEB sub for a WEB rip). When nothing fits at offset 0, rank by the **offset-scanned** cosine - what a resync can still reach - then install that one and resync: a lower metadata score can carry the better timeline (measured on S01E06: an 86-score 2HD sub reached 0.896 after a +6 s shift where the 93-score WEB-DL reached only 0.854). Bazarr then applies ffsubsync itself when the score is at or under `subsync.use_subsync_threshold` (90 here) - history gets an `action 5` row naming "offset X and framerate scale factor Y", which is the provider's own sync receipt; re-measure anyway.
- **Trim broadcast-only cues** (only while keeping the existing sub): broadcast captures carry pre-show promos, post-episode promos and caption cards that a streaming/WEB file lacks. Drop blocks starting past the video duration, keep the file's line endings, then re-read cue count and span. Frame-check boundary cues first: a cue can sit over a card that does exist.
- **Sync in place, LAST RESORT**: use it only when the sub you have is the right edit and no provider offers a fitting replacement, or the user says keep the current file. It repairs the timebase only: a broadcast capture stays a broadcast capture, so replacing beats it whenever a fitting sub exists. `PATCH {bazarr}/api/subtitles?action=sync&language=<code2>&type=episode&id=<sonarr episode id>&path=<sub file>&forced=False&hi=False&reference=a:0&no_fix_framerate=False&gss=True&max_offset_seconds=60`. **Without `path` it returns 501 "Path not provided"**; the swagger marks it optional, but the query param is mandatory. `reference` takes an audio track of the video (`a:0`), another subtitle file as the timeline, or nothing - omitted means the video file itself. Pick the track by its language tag (`a:1` when the English audio is the second stream), and for a constant offset pass `no_fix_framerate=True` first: letting ffsubsync also scale the framerate made one measured case worse (drift -2.9 s instead of -0.2 s). Async: 204, file rewritten ~1 s later, history action 5 records "offset X and framerate scale factor Y" (0.95-0.96 = the 25 fps vs 23.976 case).
- After any write: re-read `GET /api/episodes?seriesid[]=<id>` and confirm `file_size` matches the file on disk. Bazarr updates its record when it writes, not when you do. The install **overwrites `<video>.srt` in place** when that name already exists, so detect the write by a size/mtime change on the existing paths as well as by a new filename - and never retire the path you just wrote. If you replaced a sidecar that still sits beside the video, retire it (gate first, then move it out of the library - two English files means the player still offers the broken one) and re-index with `PATCH {bazarr}/api/series?action=scan-disk&seriesid=<sonarr series id>` (204).

- **Protect the repair from the upgrade search.** Bazarr's 12-hourly upgrade considers any candidate scoring above the installed sub's score (`subtitles/upgrade.py:140`, `forced_minimum_score = score + 1`), from **every** provider - a manual repair at 312/360 was replaced by a subdl entry at 313/360, and by gestdown HMAX entries at 336/360 that measured unfit. Blocking ids is the surgical fix, but block by **measurement across providers and id namespaces**, not by the ids one search returned: gestdown serves the same trailer file under two id families. `POST /api/episodes/blacklist` **deletes the indexed `subtitles_path` you pass and re-searches**, and a decoy path is not indexed so it answers 500 - the safe route is an INSERT into `table_blacklist` (columns as in `sonarr/blacklist.py:blacklist_log()`) with the service stopped and the db backed up; `subtitles/pool.py` re-reads it on every search. For literal byte-identity of manual repairs, `general.upgrade_manual: false` makes the upgrade ignore action-2 rows (`upgrade.py:264-266`) - propose it, do not apply it unasked.
- To make every install audio-checked: `settings-subsync-subsync_threshold=100` (and `subsync_movie_threshold`), `settings-subsync-no_fix_framerate=false`, `settings-subsync-quality_min_score=@float 0.5`. The `@float` token is required: `save_settings` only int-casts, so a bare `0.5` is stored as a string and the POST is rejected **406**. A rejected sync only logs - the file is already saved - so this is a detector, not a gate.

## Discipline

- Candidates go to a temp dir (gestdown `url`s are plain HTTP, no auth). Fetch into the temp dir only.
- Before a library write: copy the file to the temp dir, record size and sha256, and report the exact restore command. Subtitle files are small, but they are still the user's data.
- Report the fix with the numbers that prove it (anchors and cosine before/after), not with what was run.
- Hold the verdict to a number line instead of a feeling. A sub is GOOD only when all four pass: coverage >= 60% of runtime, interval-overlap cosine at offset 0 >= 0.85, anchor ratio >= 0.5 of cues, |median drift| <= 1.5 s. Fitted and broken files sit far apart on all four (0.916/0.789/0.2 s against 0.269/0.075/10% coverage), so the line can stay blunt - but check a file that lands between the populations by hand.
- Run the triage twice. The second run must reach NO ACTION and write nothing; prove it with size, sha256 and mtime before and after, never with "no error was printed". Take both readings with **one clock**: .NET `LastWriteTimeUtc.Ticks` counts from 1601 and Python `st_mtime_ns` from 1970, so comparing the two flags identical files as changed.
