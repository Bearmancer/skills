# Writing FLAC tags (Toolbox)

FLAC tags are written only by `toolbox audio tag` (repo `C:\Users\Lance\Dev\Toolbox`, used as is). It pairs files to the release's tracks by disc and track number and writes a journalled, undoable tag set (`state/toolbox.db`). Undo restores only the newest run. MKV video goes through mkvpropedit (`dvd-concert-curation`), and APE images are split to per-track FLAC first.

## What Toolbox writes

There are 15 Vorbis keys: ALBUM, ALBUMARTIST, TITLE, COMPOSER, CONDUCTOR, ORCHESTRA, SOLOISTS, ARTIST, VENUE, DATE, LABEL, DISCNUMBER, TRACKNUMBER, TOTALDISCS, TOTALTRACKS. There is no PERFORMER key, and Comment and Rating are never written.

- **DATE stays as written (owner ruling 2026-11-17).** It spans the earliest begin to the latest end across a recording's relations. A single exact date is written verbatim (YYYY-MM-DD); the same year and month gives YYYY-MM; the same year but different months gives YYYY; several years give YYYY-YY or YYYY-YYYY. A MusicBrainz date value can be wrong for the actual performance (Solti London Dance Suite: MB 1965-02, actual 1965-05). Report a difference; override DATE only when the owner asks for a named box.
- Names come as sort names ("Solti, Georg"), and honorifics ("Sir") are stripped. A non-Latin credit resolves to the artist's primary English alias.
- LABEL comes from the release's label-info. TOTALDISCS counts audio media only (no DVD, Blu-ray or Data discs).
- Keep-on-missing: a field the source lacks keeps its value on disk. This is how a stale year or a foobar `«multiple values»` placeholder survives a run.
- The Discogs source writes no DATE.

Library boxes (partial copies: fewer discs on disk than in MB, and unmatched MB media are skipped):

| Box | Release MBID |
| --- | --- |
| Karajan - Complete EMI Recordings v.1 | b92d6fd5-c9d9-427d-9c97-02a03a1ea384 |
| Karajan DG Split | 4a31ba40-a2d1-4491-b7b3-3bc4abaaca3d |
| Solti Complete Chicago Recordings | 4f4e5b1f-29e0-4407-b95b-67d834820ba9 |
| Solti in Europe (2023) | 648443f1-5ee6-4f92-b218-53cbd11a6a45 |
| Solti London (2021) | f01d0418-f03c-4c86-b4af-20fd33dbd920 |

## Steps

1. **Resolve the release.** `toolbox audio tag` takes a release MBID (`--mbid`) or a Discogs release (`--discogs`), never a release-group. Find it through the matrix's release-identification row (`mb.py search`).
   *Done when:* the release's media and track layout matches the files on disk.
2. **Fresh exe.** Compare `git -C C:\Users\Lance\Dev\Toolbox log -1 --format=%ci -- src` with the LastWriteTime of `artifacts\publish\src\App\release\toolbox.exe`. If the source is newer, run `dotnet publish C:\Users\Lance\Dev\Toolbox\src\App -c Release`.
   *Done when:* the exe is newer than the last `src` commit.
3. **Dry run.** Set a UTF-8 console first, because pwsh defaults to cp1252:
   ```powershell
   [Console]::OutputEncoding = [Text.Encoding]::UTF8
   toolbox audio tag "<path>" --mbid <mbid> --dry-run 2>&1 | Tee-Object "$env:TEMP\opencode\dry_<name>.txt"
   ```
   *Done when:* it exits 0 with a plan.
4. **Read the plan.** Tally the changes by key, check the LABEL values, check the name fields for non-Latin residue (expect none), and confirm the DATE changes (normally none). Explain any pairing error (a duplicate track number, no matching row) before going on.
   *Done when:* every anomaly is explained or fixed.
5. **Back up** every FLAC's tags:
   ```powershell
   uv run --no-project --with mutagen python -I -c "import json,sys; from pathlib import Path; from mutagen.flac import FLAC; root=Path(sys.argv[1]); print(json.dumps({str(p):{k:list(v) for k,v in (FLAC(str(p)).tags or {}).items()} for p in sorted(root.rglob('*.flac'))}, ensure_ascii=False))" "<path>" > "$env:TEMP\opencode\backup_<name>.json"
   ```
   *Done when:* the JSON covers every FLAC.
6. **Apply, owner-gated.** Show the plan and get approval, then run the same command without `--dry-run`.
   *Done when:* it exits 0 and reports a Run ID.
7. **Prove it on disk** with mutagen (`FLAC(path).tags`) or `metaflac --export-tags-to=-`, never ffprobe (ffprobe renames Vorbis keys and collapses duplicates). Set-check the whole tree: each field's distinct values match the plan, there is one spelling per person, and the file count equals `fd -e flac`.
   *Done when:* the tags on disk match the approved plan.
8. **Close out.** Delete the dry-run, write logs and backup once verified, and ask keep-or-delete for anything ambiguous.

## Traps

- foobar2000 bulk Properties writes its UI placeholder literally and renames Toolbox's fields, so re-run Toolbox after any foobar tag pass.
- G: (Google Drive) enumeration: a plain recursive listing of a deep path can return empty. Use `fd -e flac . "<path>"` or `[IO.Directory]::EnumerateFiles(path,'*.flac','AllDirectories')`.
- Huge boxes take longer, because Toolbox backfills credits by browsing recordings.
