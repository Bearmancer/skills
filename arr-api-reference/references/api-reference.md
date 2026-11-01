# Arr-stack + Emby API reference

Facts that cannot be looked up. Code lives in `scripts/` (`arr_scripts.py` functions named below; `qbt_remote_add.sh`); read the function instead of re-deriving the call. Keys: `get_arr_api_key(app)`, `get_sab_api_key()`, `get_bazarr_api_key()` read each app's own config file; Emby has no key on disk (mint one in Dashboard → Advanced → API Keys, or `POST /Users/AuthenticateByName`).

## Host config (login, launch-browser)

`GET`/`PUT /api/v3/config/host` (`/api/v1` for Prowlarr), id always `1`: `bindAddress`, `port`, `authenticationMethod`, `username`/`password`/`passwordConfirmation`, `launchBrowser` (`true` opens a tab at every startup).

- **Usernames:** Sonarr/Radarr/Prowlarr lowercase `username` server-side (send `"Lance"`, stored `"lance"`). qBittorrent's `web_ui_username` keeps case (`POST /api/v2/app/setPreferences`, body `json={"web_ui_username":"<name>"}`, URL-encoded).
- **Change a username without the password:** `GET`, change only `username`, `PUT` the whole object back with `password` as `GET` returned it (the backend compares the hash byte-for-byte). Sending plaintext double-hashes it and breaks login.
- **SABnzbd** web login is `[misc] username/password` in `sabnzbd.ini`; `[[servers]]` blocks are Usenet provider accounts, not the app login. **Emby** auth is per user via `/Users`, nothing to rotate here.
- **`allowedHosts`** (same resource) on all three: `localhost,127.0.0.1,100.86.121.94,lance.tail2e6179.ts.net` (2026-10-17). `PUT` the whole object, re-`GET`, probe `/health` over the Tailscale IP to prove no lockout. Host filtering reloads only at service restart: `/health` clears at once, but a foreign `Host` is still accepted until then.
- **Login state (2026-10-17):** Sonarr/Radarr/Prowlarr `lance`, `forms`, `disabledForLocalAddresses`; qBittorrent WebUI `Lance`. SABnzbd and Bazarr have no web login (`[misc] username = ""`, `auth.type: null`). `lordlance` in `sabnzbd.ini` `[[news.bulknews.eu]]` and Bazarr `opensubtitlescom.username` are external provider accounts; never "fix" those.

## Sonarr / Radarr (v3) and Prowlarr (v1)

Header `X-Api-Key`; base `http://<host>:<port>/api/v3` (Prowlarr `/api/v1`). Plugin-style resources (download clients, applications) follow schema-then-submit: `GET .../schema`, pick the implementation, set its `fields`, `POST` the whole object.

| Action                                                          | Endpoint                                                                                                                                          |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Root folders                                                    | `GET`/`POST {"path":...}` `/rootfolder`, `DELETE /rootfolder/{id}`                                                                                |
| Download clients                                                | `GET /downloadclient`, `GET /downloadclient/schema`, `POST /downloadclient`, `POST /downloadclient/testall` → `[{id,isValid,validationFailures}]` |
| Backup                                                          | `POST /command {"name":"Backup"}`                                                                                                                 |
| Re-search one series (clears stale `downloadClientUnavailable`) | `POST /command {"name":"SeriesSearch","seriesId":<id>}`                                                                                           |
| Prowlarr applications                                           | `GET`/`POST /applications`, `GET /applications/schema`                                                                                            |
| Prowlarr force indexer→app sync                                 | `POST /command {"name":"ApplicationIndexerSync"}`                                                                                                 |
| Prowlarr client                                                 | `GET`/`PUT /downloadclient/{id}`: send `.fields` **and** `.categories`                                                                            |

Code: `add_arr_download_client`, `set_prowlarr_category_map`. `testall` / health-recheck sequence and why `SeriesSearch` replaces `queue/grab` (405): `triage.md`.

- **`apiKey` is a secret field:** the schema template has no `value` for it, so it must be added, not assigned (the functions do this).
- **Prowlarr category mapping** is a separate top-level `categories` array (`[{clientCategory, categories:[codes]}]`), not in `.fields`; unmapped codes fall to the client's default `category` field. `set_prowlarr_category_map` sets it.
- **PUT duplicates fields:** re-`PUT`ting an object fetched with `GET .../{id}` can duplicate a `.fields` entry (seen: `category` twice, different values). `merge_arr_fields` dedupes by name; the functions call it.
- **Applications** use `configContract` `SonarrSettings`/`RadarrSettings` and fields prowlarrUrl, `baseUrl`, `apiKey`, `syncCategories`, `syncLevel: "fullSync"`.
- **400 on `/rootfolder`** returns `[{propertyName,errorMessage,attemptedValue}]`; "Path already configured as a root folder" means it exists, so check state instead of retrying.
- **Post-restart race:** a `GET` seconds after a restart can be empty though the DB has the row; wait about 5 s and recheck.
- **Windowless exe:** each app ships `<App>.exe` (windowless) and `<App>.Console.exe` (visible); use the non-`.Console` one for anything unwatched.

### Prowlarr category codes (for `syncCategories` and `.categories`)

| Range     | Meaning                                              |
| --------- | ---------------------------------------------------- |
| 1000-1180 | Console                                              |
| 2000-2090 | Movies (2040 HD, 2045 UHD, 2050 BluRay, 2080 WEB-DL) |
| 3000-3060 | Audio/Music                                          |
| 4000-4070 | PC                                                   |
| 5000-5090 | TV (5040 HD, 5045 UHD, 5070 Anime)                   |
| 6000-6090 | XXX                                                  |
| 7000-7060 | Books                                                |
| 8000-8020 | Other                                                |

## Emby

Header `X-Emby-Token` or query `api_key`; base `http://<host>:<port>` (no `/api`, no version). `GET /Library/VirtualFolders` → per library `Name`, `Locations`, `CollectionType`, `ItemId`, `Guid`.

- **The id gotcha:** `POST /Library/VirtualFolders/Paths` takes `id=<Guid>` (32-hex, no dashes). `name=` and the decimal `ItemId` both give HTTP 500 `System.FormatException: Unrecognized Guid format`, with no other hint. Resolve the library by `Name` first. Code: `add_emby_library_path`.
- Config dir `%AppData%\Emby-Server\programdata\config\system.xml` (no secrets). On any 500, tail the log before guessing again: the .NET stack trace names the failing call.

## SABnzbd

Auth is the **query-string** `apikey=<key>`, not a header; base `http://<host>:<port>/api`, add `output=json`.

| Action               | Params                                                                                                                        |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Get config           | `mode=get_config&section=<misc\|categories>` → nested under `config`                                                          |
| Set a misc key       | `mode=set_config&section=misc&keyword=<download_dir\|complete_dir\|dirscan_dir\|...>&value=<val>`                             |
| Set a category's dir | `mode=set_config&section=categories&keyword=<cat>&dir=<path>`                                                                 |
| Delete a category    | `mode=del_config&section=categories&keyword=<cat>`                                                                            |
| Job history          | `mode=history&limit=<N>` → `.history.slots[]`: `name`, `category`, `status`, `storage` (final), `path` (temp), `fail_message` |
| Live queue           | `mode=queue` → `percentage`, `timeleft`, `cat`                                                                                |

Code: `sab_api`, `set_sab_category_dir`, `remove_sab_category`, `find_arr_job`.

- **`mode=set_cat` does not reliably update an existing category's dir**; use `set_config` on `categories`.
- **Category ids are force-lowercased** (`keyword=TV` stores `tv`); `dir` keeps its casing. Keep every app's category string (Sonarr `tvCategory`, Radarr `movieCategory`, Prowlarr `clientCategory`) lowercase.
- **Rename** a category = delete the old keyword, `set_config` the new one. The fallback category is literal `*`, URL-encoded `%2A` in a query string.

## qBittorrent (v2 WebUI)

Windows stack `http://100.86.121.94:8088`; the Ubuntu box (`ssh oci`, WebUI `:8080`) is a separate instance. No API key: either "Bypass authentication for clients on localhost" is on (it is on the Ubuntu box) or log in with `POST /api/v2/auth/login` and reuse the `SID` cookie; otherwise 403.

- **Add:** `POST /api/v2/torrents/add`, multipart, one `torrents` part per file, optional `savepath`, `category`, `paused`. A known hash is a silent no-op, so judge success by the torrent count (`GET /api/v2/torrents/info`), never by the HTTP code (`000` = transport failure, 405 = empty request).
- **Local or tunnelled WebUI:** `add_qbt_torrents(paths, base, save_path, category)` dedupes by infohash (`qbt_info_hash`) and returns `(added, skipped, count_after)`.
- **Over ssh, no Python on the box:** `scripts/qbt_remote_add.sh <ssh-host> <dir> [port]` (about 8 s for 300 files).
- **401 through `ssh -L`:** host-header validation rejects a `Host` that does not match qBittorrent's port. Pin `Host: localhost:8080` (`QBT_HEADERS` does).
- **Other calls:** `GET /api/v2/app/preferences`, `POST /api/v2/torrents/editCategory` (`set_qbt_category_dir`).

### Working on the Ubuntu box over ssh

- Read `~/.ssh/config` before guessing what an alias is: `oci` is an SSH host (ubuntu@oci-vnic), not Oracle Object Storage.
- A non-interactive `ssh host 'cmd'` has a bare `PATH`: `npm` needs `. ~/.nvm/nvm.sh`; `uv` is in `~/.local/bin`.
- Ship multi-step remote work as a script (`scp` + `bash`), not a quoted one-liner. Ship files as one `tar` stream with bare names, never one `scp` per file (105 handshakes timed out).
- `pkill -f "a|b"` inside the ssh command matches the remote shell itself and kills the session (exit 255); use `pkill -x <name>` or kill by PID.
- Compare counts before deleting staging files.
- Windows-side Python cannot open Git Bash `/c/...` paths.

## Logs, process, ports

| App      | Log files                                               | Process                     | Port |
| -------- | ------------------------------------------------------- | --------------------------- | ---- |
| Sonarr   | `C:\ProgramData\Sonarr\logs\sonarr.*.txt`               | `Sonarr`                    | 8989 |
| Radarr   | `C:\ProgramData\Radarr\logs\radarr*.txt`                | `Radarr` / `Radarr.Console` | 7878 |
| Prowlarr | `C:\ProgramData\Prowlarr\logs\prowlarr*.txt`            | `Prowlarr`                  | 9696 |
| SABnzbd  | `C:\Users\Lance\AppData\Local\sabnzbd\logs\sabnzbd.log` | `SABnzbd`                   | 8080 |
| Emby     | `%AppData%\Emby-Server\programdata\logs\embyserver.txt` | `EmbyServer`, `embytray`    | 8096 |

- The arr logs roll as numbered files (`.0.txt`, `.1.txt`); the no-suffix or highest number is newest. `*.debug.*` is verbose and only useful with `LogLevel` `debug` in `config.xml` (all three run `debug` now).
- Live queue: Sonarr/Radarr `GET /api/v3/queue` (`status`, `trackedDownloadStatus`, `errorMessage`); Prowlarr has none (check the arr app or SABnzbd).
- Edits to `config.xml` / `sabnzbd.ini` made while the app runs are overwritten at the next write or exit: stop, edit, restart. API-driven changes need neither.

## Bazarr

Port `6767`, config `C:\ProgramData\Bazarr\config\config.yaml`. The API key is under `auth:` (not `general:`); header `X-API-KEY`, query `apikey`, or form field `apikey`. Code: `get_bazarr_api_key`, `wire_bazarr` (not yet run live: Bazarr was down when written).

- **`POST /api/system/settings` takes form-encoded** `settings-<section>-<key>` fields; a JSON body is silently ignored and nothing saves. It accepts partial updates and answers 204 (406 plus a message on validation failure). It is hidden from swagger; `PUT`/`PATCH` give 405.
- Saving restarts Bazarr's Sonarr/Radarr signalr clients; no service restart needed (`POST /api/system?action=restart` also exists, also hidden).
- Bazarr talks only to Sonarr and Radarr. Prowlarr feeds those; Emby is the playback front-end; neither is a Bazarr integration.
