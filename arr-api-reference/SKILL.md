---
name: arr-api-reference
description: "Use when configuring or locating Sonarr, Radarr, Prowlarr, SABnzbd, qBittorrent, Emby or Bazarr through its HTTP APIs or on-disk paths: download clients, categories, indexers, root folders, ports, logins, logs and autostart."
---

Configure Sonarr/Radarr/Prowlarr/SABnzbd/qBittorrent/Emby (plus Bazarr) through HTTP APIs or on-disk locations, not UI clicks. PowerShell pitfalls go to `shell-gotchas`; web research goes to `rigorous-research`.

## Which machine

Two Windows machines run their own copy of the stack. Every port, path, login and firewall rule is per machine, so identify the machine first (`hostname`):

| Hostname          | Tailnet name | Tailnet IPv4    | Media root |
| ----------------- | ------------ | --------------- | ---------- |
| `Home`            | `home`       | 100.112.2.26    | `D:\Media` |
| `Lance-HP-3141KU` | `lance`      | 100.86.121.94   | `C:\Media` |

Values for one machine never transfer to the other: copied `allowedHosts` 400 every tailnet request, and copied indexers silently route through the other machine's Prowlarr. Sonarr, Radarr and SABnzbd use the **same API key on both machines** (Prowlarr's differ), so a call aimed at the wrong machine succeeds without error and returns, or changes, the other machine's data; check the host in every URL you build. Per-machine bind, firewall, login, port and path values: `references/stack-state.md`. The scripts read keys from the local config files and call the local apps, so run them on the machine you mean to change; reach the other machine through `paramiko` (see below).

## Core pattern: schema-then-submit

For pluggable items (download clients, applications, indexers, notifications) in Sonarr, Radarr and Prowlarr:

1. `GET .../schema`: one template object per implementation (e.g. `Sabnzbd`, `QBittorrent`, `Radarr`, `MediaBrowser` for Emby), each with a `fields` array of `{name, value, ...}`.
2. Filter to the needed implementation and set `.value` on its fields.
3. `POST`/`PUT` the whole object, not just the changed field.

`references/api-reference.md` is the single home for exact endpoints, auth header/param, request bodies, the category code table (Movies/TV/Music/XXX/Books/etc.) and per-app quirks.

## Category wiring

The apps work as a pipeline only if every app uses the same category **string** for a content type (e.g. `tv`, `movies`). No shared namespace enforces it, so verify by hand:

- SABnzbd category name (`[[categories]]` section): SAB lowercases category ids whatever is sent; `dir` casing is kept as sent. Keep category names lowercase everywhere.
- qBittorrent categories (`tv`, `movies`) carry their own save path.
- Sonarr download-client `tvCategory` and Radarr download-client `movieCategory` match those names, for both the SABnzbd and the qBittorrent client.
- Prowlarr download-client `categories` array (separate from `fields`) maps numeric category codes to client category strings: `[{clientCategory: "tv", categories: [5000,5010,...]}]`. Unmapped categories fall through to the client's default `category` field.

A mismatch fails silently: the download lands in the wrong or default category/folder with no error. Verify end to end with a real (or old) job, not by re-reading config. `uv run scripts/verify_category_wiring.py` cross-checks the chain in one call (SAB category list vs Sonarr/Radarr download-client category vs Prowlarr mapping); run it after any category or download-client edit.

Staging mirrors by protocol under the machine's media root: `<root>\Usenet\TV` (SABnzbd) and `<root>\Torrent\TV` (qBittorrent) both feed `<root>\Library\TV`, and Movies follows the same pattern. Other categories differ per machine (on lance some skip staging): `stack-state.md`.

## Indexers

Sonarr and Radarr get every indexer from the local Prowlarr (`http://localhost:9696/<id>/`); add or fix indexers in Prowlarr, then run `ApplicationIndexerSync`. An app indexer whose `baseUrl` points at another machine's Prowlarr is outside sync: Prowlarr neither updates nor removes it. Before deleting such an entry, test it: it may be the only working copy of that indexer. Sync failures, the 429 that is Prowlarr's own backoff, and copying indexer keys between machines: `references/api-reference.md` Prowlarr section and `references/triage.md`.

## Emby

Outside the category pipeline. Sonarr and Radarr each tell Emby to rescan through an `Emby` connection (implementation `MediaBrowser`, its own Emby API key). Keys live in Emby's `authentication.db`; add-library-path needs the `Guid`, not `name` or `ItemId` (`name=` gives HTTP 500). Detail: `references/api-reference.md` Emby section.

## Routing: stack-state vs triage vs backup

- Bind/firewall/login/autostart per machine (read before touching service config): `references/stack-state.md`.
- Stack broken now (down/stuck/zombie/stale-queue/indexers failing): `references/triage.md`.
- Logins: Servarr usernames are lowercase-only (normalized on save and lookup); qBittorrent keeps its case. Change procedure: Host config in `references/api-reference.md`.
- Before editing live config, run `uv run scripts/backup_arr_stack.py`. It starts the newest installed `GoogleDriveFS.exe` if Drive is not running, then finds `<letter>:\My Drive\Computer\Configs` on whichever letter holds it. On home that is `G:\My Drive`, Drive's mirror folder on a local disk: the folder is always there, but zips reach the cloud only while Drive runs, so a present folder does not prove an upload. Where Drive never mounts (lance on 2026-11-13), it fails with `FileNotFoundError` before any backup; fall back to each app's own backup (`Backups` folder or backup API).

## qBittorrent and remote hosts

Add `.torrent` files with `add_qbt_torrents`: it targets this machine's WebUI by default (address and port read from `qBittorrent.ini`), or pass `base=` for another machine's tailnet URL. For the Ubuntu box, whose WebUI listens only on its own `localhost:8080`:

`uv run --no-project --with paramiko "C:\Users\Lance\.agents\skills\arr-api-reference\scripts\qbt_remote_add.py" oci <dir> 8080`

Gotchas (silent no-op on known hashes, login bypass): "qBittorrent" in `references/api-reference.md`. Done when the torrent count rose by the number added.

Remote work for this stack goes through Python `paramiko`, not the `ssh`/`scp`/`sftp` CLIs, which are blocked host-wide by the `ssh-paramiko-only` plugin. One-off commands and file transfer: `uv run --no-project --with paramiko ~/.agents/scripts/paramiko-run.py <alias> ...` with the `~/.ssh/config` aliases `laptop` (lance) and `oci` (Ubuntu box).

## Verify, don't assume

After any config mutation, re-`GET` and check the real value came back: many APIs accept a write, then quietly normalize or reject part of it (SABnzbd category casing; Prowlarr PUT-dedupe in `references/api-reference.md`, handled by `merge_arr_fields` in the scripts).

Probe access with redirects off (`curl -s -o /dev/null -w '%{http_code}'`, no `-L`): a login page also answers 200 once a redirect is followed, so only an unfollowed `200` proves "no login" and a `302` to `/login` proves a login wall. Prove a LAN block from another LAN device: a machine probing its own LAN address is loopback and bypasses its firewall.

To explain a download that landed somewhere unexpected, query the app's history/queue for that job's `category` first. Category is set at grab time and a later mapping fix does not change it, so a job in the wrong place almost always predates the fix.

## Scripts: use these, not re-derived API calls

Import `scripts/arr_scripts.py` for everything except backup/verify, which run standalone. It already implements the schema-then-submit steps and the dedupe/mutation handling. Functions (read the docstrings): `add_arr_download_client`, `set_prowlarr_category_map`, `set_sab_category_dir`/`remove_sab_category`, `qbt_base`, `set_qbt_category_dir`, `add_qbt_torrents` (infohash-deduped upload; `qbt_info_hash`), `find_arr_job`, `add_emby_library_path`, `bazarr_base`, `wire_bazarr`.

- `scripts/verify_category_wiring.py`: standalone, imports `arr_scripts`. Prints every category mismatch and exits 1 if any. Run after any category or download-client edit; prose can't enforce it.
- `scripts/backup_arr_stack.py`: imports `arr_scripts` for key/base-URL helpers. `backup_arr_stack()` triggers a backup on Sonarr, Radarr, Prowlarr and SABnzbd, zips qBittorrent's config dir (no backup API exists), renames each `<name> - <yyyy-MM-dd>.zip` and drops all five in `Computer\Configs` on the Drive. That folder must already exist; create it by hand. Run by full path, no `$PROFILE` alias. A down app fails loudly per app while the others still write; check each zip's timestamp after the run, since the timestamps, not the absence of red text, are the proof.

## Bazarr

Installed on lance only. Wire to Sonarr and Radarr with `wire_bazarr()` (form-encoded POST, not JSON; key under `auth:` in `config.yaml`; it reads Bazarr's own bind from `general.ip`, since lance binds Bazarr to its tailnet IP and refuses localhost). Quirks: `references/api-reference.md`. Autostart, bind and the `lordlance` OpenSubtitles provider account: `references/stack-state.md`.
