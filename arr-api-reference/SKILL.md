---
name: arr-api-reference
description: "Use when configuring or locating Sonarr, Radarr, Prowlarr, SABnzbd, Emby or Bazarr through its HTTP APIs or on-disk paths: download clients, categories, root folders, ports, logs and autostart."
---

Configure Sonarr/Radarr/Prowlarr/SABnzbd/Emby (plus Bazarr) through HTTP APIs or on-disk locations, not UI clicks. General HTTP/API debugging and PowerShell pitfalls go to `shell-gotchas`; web research goes to `rigorous-research`.

## Core pattern: schema-then-submit

For pluggable items (download clients, applications, indexers, notifications) in Sonarr, Radarr and Prowlarr:

1. `GET .../schema`: one template object per implementation (e.g. `Sabnzbd`, `QBittorrent`, `Radarr`), each with a `fields` array of `{name, value, ...}`.
2. Filter to the needed implementation and set `.value` on its fields.
3. `POST`/`PUT` the whole object, not just the changed field.

`references/api-reference.md` is the single home for exact endpoints, auth header/param, request bodies, the category code table (Movies/TV/Music/XXX/Books/etc.) and per-app quirks.

## Category wiring

Four apps work as a pipeline only if every app uses the same category **string** for a content type (e.g. `tv`, `movies`). No shared namespace enforces it, so verify by hand:

- SABnzbd category name (`[[categories]]` section): SAB lowercases category ids whatever is sent; `dir` casing is kept as sent. Keep category names lowercase everywhere (`references/api-reference.md`).
- Sonarr download-client `tvCategory` matches that SAB category name.
- Radarr download-client `movieCategory` matches it too.
- Prowlarr download-client `categories` array (separate from `fields`) maps numeric category codes to client category strings: `[{clientCategory: "tv", categories: [5000,5010,...]}]`. Unmapped categories fall through to the client's default `category` field.

A mismatch fails silently: the download lands in the wrong or default category/folder with no error. Verify end to end with a real (or old) job, not by re-reading config. `uv run scripts/verify_category_wiring.py` cross-checks the chain in one call (SAB category list vs Sonarr/Radarr download-client category vs Prowlarr mapping); run it after any category or download-client edit.

Staging mirrors by protocol, not app: `C:\Media\Usenet\TV` (SABnzbd) and `C:\Media\Torrent\TV` (qBittorrent) both feed `C:\Media\Library\TV`. Movies/Music/XXX/Books/General follow the same pattern under each protocol root.

## Emby

Outside the category pipeline. No API key on disk. Add-library-path needs the `Guid`, not `name` or `ItemId` (`name=` gives HTTP 500). Detail: `references/api-reference.md` Emby section.

## Routing: stack-state vs triage vs backup

- Bind/firewall/autostart config (read before touching service config): `references/stack-state.md`.
- Stack broken now (down/stuck/zombie/stale-queue): `references/triage.md`.
- Logins: Servarr usernames are lowercase-only (normalized on save and lookup); qBittorrent keeps its case. Current values and the safe change procedure: Host config in `references/api-reference.md`.
- Before editing live config, run `uv run scripts/backup_arr_stack.py`. It fails on this host since 2026-10-17: Google Drive is not mounted (`D:\My Drive` absent) and the hardcoded `GoogleDriveFS.exe` path is missing (`FileNotFoundError` before any backup). Fall back to each app's own backup (`Backups` folder or backup API) until Drive mounts.

## qBittorrent and remote hosts

Add `.torrent` files with `add_qbt_torrents` for a WebUI you can reach (local, or via `ssh -L`), or `scripts/qbt_remote_add.sh <ssh-host> <dir>` for the Ubuntu box. Gotchas (Host header, silent no-op, ssh pitfalls): "qBittorrent" in `references/api-reference.md`. Done when the torrent count rose by the number added.

## Verify, don't assume

After any config mutation, re-`GET` and check the real value came back: many APIs accept a write, then quietly normalize or reject part of it (SABnzbd category casing; Prowlarr PUT-dedupe in `references/api-reference.md`, handled by `merge_arr_fields` in the scripts).

To explain a download that landed somewhere unexpected, query the app's history/queue for that job's `category` first. Category is set at grab time and a later mapping fix does not change it, so a job in the wrong place almost always predates the fix.

## Scripts: use these, not re-derived API calls

Import `scripts/arr_scripts.py` for everything except backup/verify, which run standalone. It already implements the schema-then-submit steps and the dedupe/mutation handling. Functions (read the docstrings): `add_arr_download_client`, `set_prowlarr_category_map`, `set_sab_category_dir`/`remove_sab_category`, `set_qbt_category_dir`, `add_qbt_torrents` (infohash-deduped upload; `qbt_info_hash`), `find_arr_job`, `add_emby_library_path`, `wire_bazarr`.

- `scripts/verify_category_wiring.py`: standalone, imports `arr_scripts`. Prints every category mismatch and exits 1 if any. Run after any category or download-client edit; prose can't enforce it.
- `scripts/backup_arr_stack.py`: imports `arr_scripts` for key/base-URL helpers. `backup_arr_stack()` triggers a backup on all four apps, zips qBittorrent's config dir (no backup API exists), renames each `<name> - <yyyy-MM-dd>.zip`, starts Google Drive if unmounted, and drops all five in `Computer\Configs`. That folder must already exist; create it by hand. Run by full path, no `$PROFILE` alias: `uv run scripts/backup_arr_stack.py`. A down app fails loudly per app while the others still write (seen: SAB `mode=config` refused with a null-path `Copy-Item` error; Sonarr and Prowlarr zip fine; Radarr zip re-dated with old content). Check each timestamp after the run; the timestamps, not the absence of red text, are the proof.

## Bazarr

Wire to Sonarr and Radarr with `wire_bazarr()` (form-encoded POST, not JSON; key under `auth:` in `config.yaml`). Quirks: `references/api-reference.md`. Autostart, bind and the `lordlance` OpenSubtitles provider account: `references/stack-state.md`.
