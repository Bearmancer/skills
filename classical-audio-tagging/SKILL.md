---
name: classical-audio-tagging
description: >
  Use whenever tagging classical music FLAC files or box sets with Toolbox and MusicBrainz —
  conductor, orchestra, soloist and composer credits, LABEL, recording dates, album artist,
  track/disc numbering. Triggers on: tagging or retagging classical audio, the library at
  G:\My Drive\Music\Classical, "toolbox audio tag", a MusicBrainz MBID or release-group, box
  sets (Solti, Karajan, Bernstein), fixing conductor/orchestra/soloist/composer tags, filling
  LABEL, Latinizing native-script artist names, or any request to tag a classical album or box.
  Not for concert DVD video — use dvd-concert-curation for MKVs.
---

# classical-audio-tagging

Tag classical FLAC libraries from MusicBrainz (MB) using **Toolbox**
(`C:\Users\Lance\Dev\Toolbox`, CLI `toolbox`). MB is already structured JSON — release →
media → tracks → recording → relations — so there is nothing to parse or decompose. Toolbox
reads it, pairs files to tracks by disc/track number, and writes a journalled, undoable tag
set. This skill is the workflow around that command: resolve the release, verify the plan,
back up, apply, and prove the result on disk.

Deep detail (MB API, the .NET client surface, box MBIDs, the Wikipedia date cross-check
method) lives in the **classical-tagging reference** at `~/.agents/refdocs/`
(`musicbrainz.md`, `wikipedia.md`). Read it when you need API specifics; this file is the
workflow.

## Ground rules

- **MB is the anchor; dates stay as Toolbox writes them.** The owner ruled (2026-11-17) that
  Toolbox's `WidenDate` logic is kept unchanged — day-level dates, year-only multi-month
  spans, and multi-year ranges all pass through verbatim. Do not add date normalization or
  override dates from Wikipedia/Stuart unless the owner explicitly asks for a specific box.
  MB date *values* can be wrong for a box's actual performance; that is accepted, not a bug
  to fix here.
- **Backup before any bulk write.** Dump existing tags to JSON (mutagen) first. Toolbox also
  journals each run (`state/toolbox.db`) for undo, but undo restores only the newest run.
- **Verify on disk with mutagen, never ffprobe.** ffprobe renames Vorbis keys
  (ALBUMARTIST→ALBUM_ARTIST, TRACKNUMBER→TRACK) and collapses duplicates, so it cannot prove
  a key absent. Use `uv run --no-project --with mutagen --python 3.15 python -I -c "..."`
  with `FLAC(path).tags`, or `metaflac --export-tags-to=-`. ffprobe is fine for durations.
- **Ask before the bulk write.** Show the dry-run plan and get owner approval before applying.
- **Keep the exe fresh.** A stale published exe writes old behavior. Compare `git -C
  C:\Users\Lance\Dev\Toolbox log -1 --format=%ci -- src` against the exe's LastWriteTime;
  if source is newer, `dotnet publish C:\Users\Lance\Dev\Toolbox\src\App -c Release` first.
- **Purge scaffolding after.** Generated scripts, backups and handoff notes are scaffolding;
  remove them once the write is verified (keep only the shipped tags + this skill + ref docs).

## What Toolbox writes

15 Vorbis keys: ALBUM, ALBUMARTIST, TITLE, COMPOSER, CONDUCTOR, ORCHESTRA, SOLOISTS, ARTIST,
VENUE, DATE, LABEL, DISCNUMBER, TRACKNUMBER, TOTALDISCS, TOTALTRACKS.

- **LABEL** comes from MB release label-info (e.g. Decca Classics, Deutsche Grammophon, EMI
  Classics). **Latin-name standardization** (#307): a non-Latin credit (Cyrillic/Hebrew) is
  resolved to the artist's primary English alias automatically. **TOTALDISCS** counts audio
  media only (DVD/Blu-ray/Data discs excluded).
- A field the source lacks keeps its on-disk value (keep-on-missing). Honorifics ("Sir") are
  stripped from name fields. Comment and Rating are never written.
- Toolbox tags **FLAC only**. APE images must be split to per-track FLAC first; MKV video
  goes through mkvpropedit (see dvd-concert-curation), not Toolbox.

## Workflow

1. **Resolve the release MBID.** `toolbox audio tag` takes a *release* MBID (`--mbid`), not a
   release-group. If given a release-group, resolve it to its release via MB. The five
   classical box MBIDs are tabulated in `~/.agents/refdocs/musicbrainz.md`. For a new album,
   `toolbox audio search "<artist> <work>"` or query MB ws/2 to find the release that matches
   the on-disc track count.
   *Done when:* you have a release MBID whose media/track layout matches the files on disk.

2. **Fresh exe.** Check source-vs-exe freshness (ground rule); republish if stale.
   *Done when:* the published exe reflects current master.

3. **Dry-run.** Set UTF-8 console first (Toolbox output is UTF-8; pwsh defaults to cp1252 and
   mojibakes non-Latin):
   ```powershell
   [Console]::OutputEncoding = [Text.Encoding]::UTF8
   toolbox audio tag "<box path>" --mbid <release-mbid> --dry-run 2>&1 | Tee-Object "$env:TEMP\opencode\dry_<name>.txt"
   ```
   *Done when:* exit 0 and a plan listing files/fields to change.

4. **Verify the plan.** Tally fields by key; check LABEL values are the expected label; scan
   ARTIST/SOLOISTS/CONDUCTOR/ORCHESTRA/COMPOSER proposals for non-Latin residue (should be
   zero after #307); confirm DATE changes match intent (normally zero). Investigate any
   pairing error (duplicate track number, no matching row) before applying.
   *Done when:* the plan is understood and any anomaly explained or fixed.

5. **Backup.** Dump current tags to JSON for the whole box:
   ```powershell
   uv run --no-project --with mutagen --python 3.15 python -I -c "import json,sys; from pathlib import Path; from mutagen.flac import FLAC; root=Path(sys.argv[1]); print(json.dumps({str(p):{k:list(v) for k,v in (FLAC(str(p)).tags or {}).items()} for p in sorted(root.rglob('*.flac'))}, ensure_ascii=False))" "<box path>" > "$env:TEMP\opencode\backup_<name>.json"
   ```
   *Done when:* a JSON backup exists covering every FLAC.

6. **Apply (owner-gated).** Same command without `--dry-run`. Toolbox journals the run.
   ```powershell
   toolbox audio tag "<box path>" --mbid <release-mbid> 2>&1 | Tee-Object "$env:TEMP\opencode\write_<name>.txt"
   ```
   *Done when:* exit 0 and a Run ID is reported.

7. **Prove it on disk.** Re-read tags with mutagen on a sample (or all): LABEL present and
   correct, names Latin, DATE as intended, numbering right. Never trust the exit code alone.
   *Done when:* the actual file tags match the approved plan.

8. **Close out.** Record the run; purge the temp scripts/backups/notes per the purge rule
   (ask keep-or-delete for anything ambiguous). Media work is LEDGER-only on this host.
   *Done when:* only the shipped library artifacts, this skill, and the ref docs remain.

## Traps

- **foobar2000 bulk Properties** writes its UI placeholder literally ("«multiple values»")
  and renames Toolbox's fields. Re-run Toolbox after any foobar tag pass.
- **Huge boxes (240+ CD)** embed recordings without relations; Toolbox backfills credits via
  paged recording browse (ADR 0008). Relation dates serialize as `begin`/`end`. This is
  handled inside Toolbox — just expect the run to take longer.
- **Partial boxes:** the on-disc copy may have fewer discs than the MB release; Toolbox pairs
  by disc/track and skips unmatched media. A file count below MB's track count is normal.
- **G: mount quirk:** a direct `Get-ChildItem` on a deep G: path can return empty; enumerate
  with `[System.IO.Directory]::EnumerateFiles(path,'*.flac','AllDirectories')` instead.

## Reference

- `~/.agents/refdocs/musicbrainz.md` — MB ws/2 API, the MetaBrainz .NET client surface, the
  five box MBIDs, the full Toolbox tagging contract and audit rules. Read for API detail.
- `~/.agents/refdocs/wikipedia.md` — the Solti discography date cross-check method (optional;
  not used in the MB-anchored workflow). Read only if the owner asks for date verification.
