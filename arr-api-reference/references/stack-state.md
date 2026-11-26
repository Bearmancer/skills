# Stack state: device-specific values (credentials, bind, firewall, login, ports, paths)

Everything machine-specific lives here and nowhere else in the skill; `SKILL.md`, `api-reference.md` and `triage.md` are device-agnostic and use `<host>:<port>` placeholders. Current state only. Read the section for the machine you are on (`hostname`) before touching service config. Home desktop section refreshed 2026-11-23 against live state; the laptop section is the 2026-11-13 snapshot and has not been refreshed.

## Credentials: `~/.secrets` only

Every credential lives only in `~\.secrets\`, one `.env` per service (`KEY=value` lines, no quotes), never in this repo, a ledger or a log. Nothing secret is committed to the public repo and no secrets file exists inside `Dev\Skills`.

Source them by enumerating the directory, not by naming files; read the values into the process and never print them:

```powershell
$secrets = @{}
Get-ChildItem "$HOME\.secrets\*.env" | ForEach-Object {
    Get-Content $_ | Where-Object { $_ -match '^\s*[^#=\s][^=]*=' } | ForEach-Object {
        $k, $v = $_ -split '=', 2
        $secrets[$k.Trim()] = $v.Trim()
    }
}
Invoke-RestMethod http://localhost:8989/api/v3/system/status -Headers @{ 'X-Api-Key' = $secrets['SONARR_API_KEY'] }
```

Python: `arr_scripts.secrets_env()` does the same merge, and the key getters prefer it over the app's own config file.

| File                    | Keys the file must contain (placeholder values)                          | Where the live value comes from                                  |
| ----------------------- | ------------------------------------------------------------------------ | ---------------------------------------------------------------- |
| `Sonarr.env`            | `SONARR_API_KEY=<32-hex>`                                                | `C:\ProgramData\Sonarr\config.xml` `ApiKey`                       |
| `Radarr.env`            | `RADARR_API_KEY=<32-hex>`                                                | `C:\ProgramData\Radarr\config.xml` `ApiKey`                       |
| `Prowlarr.env`          | `PROWLARR_API_KEY=<32-hex>`                                              | `C:\ProgramData\Prowlarr\config.xml` `ApiKey`                     |
| `SABnzbd.env`           | `SABNZBD_API_KEY=<32-hex>`                                               | `sabnzbd.ini` `api_key` (path below)                              |
| `qBittorrent.env`       | `QBITTORRENT_USERNAME=<name>` (WebUI user; no password stored, see below) | `GET /api/v2/app/preferences` `web_ui_username`                   |
| `Bazarr.env`            | `BAZARR_API_KEY=<32-hex>`                                                | `C:\ProgramData\Bazarr\config\config.yaml` `auth.apikey`          |
| `Emby.env`              | `EMBY_API_KEY=<32-hex>`                                                  | Emby `authentication.db` `Tokens_2.AccessToken` (the `Sonarr` key) |
| `OpenSubtitles.env`     | `OPENSUBTITLES_USERNAME=<name>`, `OPENSUBTITLES_PASSWORD=<password>`     | provider account (Bazarr `opensubtitlescom`)                      |
| `Addic7ed.env`          | `ADDIC7ED_USERNAME=<name>`, `ADDIC7ED_PASSWORD=<password>`               | provider account (Bazarr, provider disabled)                      |
| `SubDL.env`             | `SUBDL_API_KEY=<key>`                                                    | provider account (Bazarr `subdl`)                                 |

- **Verify a copy** by re-reading the live value in-process and comparing (print the boolean, never the value), then proving the copy works: an authenticated call with the `.env` value answers 200, a wrong key answers 401.
- **qBittorrent has no stored login to keep:** its WebUI skips auth for localhost and the tailnet ranges, and the password exists only as a PBKDF2 hash in `qBittorrent.ini`, so there is no plaintext to put in `qBittorrent.env`. If a login is ever needed, set a new password via `setPreferences` and add `QBITTORRENT_PASSWORD` to that file.
- **Emby** uses the existing `Sonarr`-named API key; mint a dedicated one with `POST /emby/Auth/Keys?App=<name>` if the arr key should not be shared.
- Servarr `External` auth means these keys are the only gate for API calls; SABnzbd has no web login (`username = ""`) but still requires its `apikey` for the API.

## Shared design (both machines)

- **Bind wildcard, close with the firewall.** Sonarr/Radarr/Prowlarr/SABnzbd bind `*`/`0.0.0.0`/`::` instead of the Tailscale IP: a Tailscale-IP bind fails at boot with `SocketException 10049` when the app starts before `tailscaled` assigns the IP. Windows Firewall does the restricting: allow rules scoped to `100.64.0.0/10` (Tailscale CGNAT) plus block rules for LAN ranges. Block beats allow, so the block rules close a port even where a broad program rule allows it.
- **`allowedHosts` is the second layer**, per machine (values below). Each app also accepts its own machine name (`LANCE`, `HOME`, `[::1]`) on its own, so the bare hostname always passes host filtering and only the firewall closes it. `PUT /config/host` persists `allowedHosts`, but the filter reloads only at service restart (`ConfigureHostFilteringOptions` log line).
- **SABnzbd web exposure:** `inet_exposure = 0` with `local_ranges` listing the tailnet, so tailnet peers count as local and nobody else gets in; `host_whitelist` admits hostname `Host` headers.
- **Emby is the exception on both:** reachable from the LAN as well as the tailnet, login kept.
- No arr-related Scheduled Task on either machine.

## home (desktop, hostname `Home`)

Identity: `home` = 100.112.2.26 / `home.tail2e6179.ts.net` / `fd7a:115c:a1e0::3b33:21a`; LAN 192.168.0.114. Tailscale interface profile: Private. Google Drive runs in mirror mode into `G:\My Drive` on the local 4 TB disk `G:` (label `Lord Lance`); it autostarts via the `HKCU\...\Run` key `GoogleDriveFS --startup_mode` and uploads only while running. Media root `D:\Media`; qBittorrent downloads on `E:`.

### Services and listeners (Get-Service, Get-NetTCPConnection, 2026-11-23)

| App         | Run as                                                                                                                                          | Port | Bind                  | Login                                                                              | Version |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ---- | --------------------- | ---------------------------------------------------------------------------------- | ------- |
| Sonarr      | Windows service `Sonarr`, Automatic, `NT AUTHORITY\LocalService`, `C:\ProgramData\Sonarr\bin\Sonarr.Console.exe`                                  | 8989 | `*`                   | none: `AuthenticationMethod = External`                                            | 5.0.0.3041 |
| Radarr      | Windows service `Radarr`, Automatic, `LocalService`, `C:\ProgramData\Radarr\bin\Radarr.Console.exe`                                               | 7878 | `*`                   | none: `External`                                                                   | 7.0.3.10918 |
| Prowlarr    | Windows service `Prowlarr`, Automatic, `LocalService`, `C:\ProgramData\Prowlarr\bin\Prowlarr.Console.exe`                                         | 9696 | `*`                   | none: `External`                                                                   | 3.0.2.5780 |
| SABnzbd     | Windows service `SABnzbd`, Automatic, `LocalSystem`, `"C:\Program Files\SABnzbd\SABnzbd.exe"` with `-f C:\Users\Lance\AppData\Local\sabnzbd\sabnzbd.ini` | 8080 | `::` (dual-stack)     | none (`username = ""`)                                                             | 5.1.3 |
| qBittorrent | user process `C:\Program Files\qBittorrent\qbittorrent.exe`, autostart `HKCU\...\Run`                                                           | 8085 | wildcard (no Address) | bypassed for localhost and `100.64.0.0/10`, `fd7a:115c:a1e0::/48`; user `lance`    | v5.3.0 |
| Emby        | user process `%AppData%\Emby-Server\system\EmbyServer.exe` + `embytray`, Startup-folder shortcut `Emby Server.lnk`                                | 8096 (also 8920 TLS, UDP 7359) | wildcard | kept                                                                               | 4.10.2.0 |
| Bazarr      | Windows service `Bazarr`, Automatic, `LocalSystem`, nssm `D:\Bazarr\nssm.exe` running `D:\Bazarr\WinPython\python-3.13.11.1\python.exe "D:\Bazarr\bazarr.py" --release-update --config "C:\ProgramData\Bazarr"` | 6767 | `*` (`general.ip`) | none (`auth.type` empty); API key still required                                    | 1.6.2 |

- **Process names** for kill/relaunch: `Sonarr.Console`, `Radarr.Console`, `Prowlarr.Console` (the services run the console exes; the windowless `<App>.exe` also exists), `SABnzbd`, `qbittorrent`, `EmbyServer`, `embytray`, Bazarr's `python` under `nssm`.
- **SABnzbd service:** created with `sc create`; `-f <ini>` sits in `HKLM\SYSTEM\CurrentControlSet\services\SABnzbd\CommandLine` (`REG_MULTI_SZ`). Recovery actions restart after 5 s, 60 s, 300 s (reset 86400 s). Its Start-menu launcher opens `http://localhost:8080/`. The user-process relaunch recipe (`explorer.exe "C:\Program Files\SABnzbd\SABnzbd.exe"`) no longer applies; use `Restart-Service SABnzbd`.
- **Bazarr reboot resilience:** persistent port exclusions for 6767 on IPv4 and IPv6 (`netsh int ipv4/ipv6 show excludedportrange protocol=tcp` lists `6767 6767 *`) because 6767 sits in Windows' dynamic reserved range 6751-6850; nssm `AppExit Default Restart` + `AppRestartDelay 5000`; `sc failure Bazarr` restart after 5 s, 60 s, 300 s (reset 86400 s).
- **`allowedHosts`** (all three Servarr): `localhost,127.0.0.1,100.112.2.26,home,home.tail2e6179.ts.net,fd7a:115c:a1e0::3b33:21a`. The IPv6 literal is required for IPv6 `Host` headers.
- **Servarr usernames:** Sonarr/Radarr `lance`, Prowlarr's is in `GET /api/v1/config/host`; with `External` auth they only matter if auth is turned back on.
- **Log levels:** Sonarr `info`, Radarr `debug`, Prowlarr `info`.

### Data dirs, logs, config files

| App      | Config                                              | Logs                                                                    |
| -------- | --------------------------------------------------- | ----------------------------------------------------------------------- |
| Sonarr   | `C:\ProgramData\Sonarr\config.xml`                  | `C:\ProgramData\Sonarr\logs\sonarr.*.txt` (`sonarr.debug.*.txt` verbose) |
| Radarr   | `C:\ProgramData\Radarr\config.xml`                  | `C:\ProgramData\Radarr\logs\radarr*.txt`                                 |
| Prowlarr | `C:\ProgramData\Prowlarr\config.xml`, `prowlarr.db` | `C:\ProgramData\Prowlarr\logs\prowlarr*.txt`                             |
| SABnzbd  | `C:\Users\Lance\AppData\Local\sabnzbd\sabnzbd.ini`  | `C:\Users\Lance\AppData\Local\sabnzbd\logs\sabnzbd.log`                  |
| qBittorrent | `C:\Users\Lance\AppData\Roaming\qBittorrent\qBittorrent.ini` | (app log in its profile)                                       |
| Bazarr   | `C:\ProgramData\Bazarr\config\config.yaml`          | `C:\ProgramData\Bazarr\log\bazarr.log`                                   |
| Emby     | `%AppData%\Emby-Server\programdata\config\system.xml`, `...\data\authentication.db` | `%AppData%\Emby-Server\programdata\logs\embyserver.txt`   |

### Paths and wiring

- **Root folders:** Sonarr `D:\Media\Library\TV`, Radarr `D:\Media\Library\Movies`.
- **SABnzbd:** `download_dir = D:\Media\Usenet\.incomplete`, `complete_dir = D:\Media\Usenet`, watch folder `dirscan_dir = D:\Media\Usenet\watch`; `local_ranges = 100.64.0.0/10,fd7a:115c:a1e0::/48,`, `host_whitelist = home.tail2e6179.ts.net, home`; categories `*`, `movies`, `tv`, `music`, `books`, `xxx`, `general` with dirs `General`, `Movies`, `TV`, `Music`, `Books`, `XXX`, `General` under `complete_dir`. Probing the short name `home` from home itself resolves to `fe80::` first and is refused by design; remote peers resolve `home` to the tailnet addresses.
- **qBittorrent:** default save path `E:\`, temp path `E:\.incomplete` (enabled); categories `tv` -> `E:/tv`, `movies` -> `E:/movies`, `prowlarr` -> `E:/prowlarr`, `bowie` -> `G:/.incomplete`. Download client in Sonarr, Radarr and Prowlarr at `localhost:8085`; Sonarr `tvCategory` `tv`, Radarr `movieCategory` `movies`; SABnzbd client at `localhost:8080` with the same categories. Home stages every SABnzbd category under `D:\Media\Usenet`.
- **Emby:** libraries (GET `/Library/VirtualFolders`, 2026-11-23): Classical `E:\Music` + `G:\My Drive\Music\Classical`, Concerts `G:\My Drive\Music\Classical\Concerts`, Movies `D:\Media\Library\Movies`, Pop Concerts (three folders under `G:\My Drive\Music\Songs`), Songs `G:\My Drive\Music\Songs`, TV `D:\Media\Library\TV`, XXX `D:\Media\Library\XXX`. Sonarr and Radarr each have an `Emby` connection (`localhost:8096`, `updateLibrary` true). Remote bitrate limit 0, so tailnet clients counting as remote costs nothing.
- **Bazarr:** `use_sonarr` and `use_radarr` true, both pointed at `127.0.0.1` on 8989/7878; language profile English only; provider accounts in `OpenSubtitles.env`, `Addic7ed.env`, `SubDL.env`. Its OpenSubtitles username is the external provider account, not an app login.
- **SSH aliases** (`~/.ssh/config`): `laptop` (the laptop below) and `oci` (the Ubuntu box; its qBittorrent WebUI listens on `localhost:8080` on that box).

### Indexers (Prowlarr `GET /api/v1/indexer`, 2026-11-23: 10 enabled)

Every Sonarr/Radarr indexer points at home's own Prowlarr. App sync profile `Unlimited` has RSS on, `Limited` is interactive search only.

| Indexer       | Protocol | App sync profile |
| ------------- | -------- | ---------------- |
| AlphaRatio    | torrent  | Limited          |
| altHUB        | usenet   | Unlimited        |
| DrunkenSlug   | usenet   | Unlimited        |
| FileList.io   | torrent  | Limited          |
| Nzb.life      | usenet   | Unlimited        |
| NZBgeek       | usenet   | Unlimited        |
| NzbNoob       | usenet   | Limited          |
| Orpheus       | torrent  | Unlimited        |
| Secret Cinema | torrent  | Unlimited        |
| TorrentLeech  | torrent  | Limited          |

Disabled in Prowlarr (not in the table above): MoreThanTV and RuTracker. NZBFinder was removed by the owner on 2026-11-22.

### Firewall (Get-NetFirewallRule, 2026-11-23)

- `NzbDrone` allows TCP 7878/8989/9696 from `100.64.0.0/10`; `SABnzbd`/`SABnzbd-console` program allows from `100.64.0.0/10`; `qBittorrent` TCP 8085 allow from `100.64.0.0/10`; `Tailscale-In` allows anything addressed to the tailnet IPs.
- `Bazarr` allows TCP 6767 from `100.64.0.0/10` + `fd7a:115c:a1e0::/48`; `Bazarr-block-LAN` blocks TCP 6767 from `192.168.0.0/16`, `172.16.0.0/12`, `10.0.0.0/8`, `fd00::/8`, `fe80::/10` (loopback is exempt by the OS).
- Blocks: `arr-block-LAN` (remote `192.168.0.0/24`) and `arr-block-HyperV` (remote `172.17.160.1`), both TCP 8989,7878,9696,8080,8085; `qbt-webui-tailnet-only` blocks TCP 8085 from every address outside `100.64.0.0/10` and `fd7a:115c:a1e0::/48` (qBittorrent's own program rules allow any port from anywhere for peer traffic).
- Emby rules (TCP 8096, 8920, UDP 7359, program rules) allow from anywhere.

### Runnable examples (this desktop)

```powershell
# keys from ~\.secrets (see Credentials), then:
curl.exe -s -H "X-Api-Key: $($secrets['SONARR_API_KEY'])" http://localhost:8989/api/v3/system/status
curl.exe -s "http://localhost:8080/api?mode=version&output=json&apikey=$($secrets['SABNZBD_API_KEY'])"
curl.exe -s http://localhost:8085/api/v2/app/version        # localhost bypass, no login
curl.exe -s -H "X-API-KEY: $($secrets['BAZARR_API_KEY'])" http://localhost:6767/api/system/status
```

Radarr 7878 and Prowlarr 9696 follow the Sonarr pattern (`/api/v3` for Radarr, `/api/v1` for Prowlarr); Emby: `http://localhost:8096/emby/System/Info?api_key=<EMBY_API_KEY>`.

### Verified

- 2026-11-13: from oci and from lance over the tailnet, all six apps on all four address forms (IPv4, `[IPv6]`, FQDN, `home`) answer 200 with redirects off (Emby 302 to its own login). From lance on the LAN, 192.168.0.114 times out on 8989/7878/9696/8080/8085 and Emby answers.
- 2026-11-23: all seven services answer on localhost; `.env` copies of every key answer 200 and a wrong Sonarr key answers 401.

## lance (laptop, hostname `Lance-HP-3141KU`) - snapshot 2026-11-13, not refreshed (out of the current EPIC scope)

Identity: `lance` = 100.86.121.94 / `lance.tail2e6179.ts.net`; LAN 192.168.0.101. Google Drive not mounted (2026-11-13). SSH alias from home: `laptop`. Media root `C:\Media`. Sonarr, Radarr and SABnzbd used the **same API key as home** when last compared (2026-11-13; Prowlarr's differ), so a call aimed at the wrong machine succeeds silently; this laptop's own credentials follow the same `~\.secrets\<Service>.env` convention on that machine.

| App         | Run as                                                                                                  | Port  | Bind                       | Login                                                                   |
| ----------- | ------------------------------------------------------------------------------------------------------- | ----- | -------------------------- | ----------------------------------------------------------------------- |
| Sonarr      | Windows service, Auto, `NT AUTHORITY\LocalService`                                                     | 8989  | `*`                        | Forms, `DisabledForLocalAddresses`, user `lance`                        |
| Radarr      | Windows service, Auto, `LocalService`                                                                  | 7878  | `*`                        | same                                                                    |
| Prowlarr    | Windows service, Auto, `LocalService`                                                                  | 9696  | `*`                        | same                                                                    |
| SABnzbd     | Windows service, Auto, `LocalSystem` (created with `sc create`, see below)                              | 8080  | `0.0.0.0`                  | none (`username = ""`)                                                  |
| qBittorrent | manual start only, by decision                                                                          | 18088 | `100.86.121.94` only       | bypassed for `100.64.0.0/10`; user `Lance`; localhost is refused        |
| Emby        | Startup-folder shortcut (`%AppData%\Microsoft\Windows\Start Menu\Programs\Startup\Emby Server.lnk`)     | 8296  | wildcard                   | kept                                                                    |
| Bazarr      | Windows service `Bazarr`, Auto                                                                          | 6767  | `100.86.121.94` only       | none                                                                    |

- **`allowedHosts`** (all three Servarr): `localhost,127.0.0.1,100.86.121.94,lance.tail2e6179.ts.net`.
- **Firewall:** `NzbDrone` allows TCP 8989/7878/9696 from `100.64.0.0/10`; `SABnzbd`/`SABnzbd-console` allow from `100.64.0.0/10`. Blocks: `arr-tailscale-only TCP 8989`, `7878`, `9696`, `6767` from `192.168.0.0/16,172.16.0.0/12,10.0.0.0/8`. qBittorrent, Bazarr and Emby program rules allow from anywhere; qBittorrent and Bazarr are kept tailnet-only by their bind address instead.
- **Servarr login is still required over the tailnet here:** `DisabledForLocalAddresses` treats `10/8`, `172.16/12`, `192.168/16`, loopback and IPv6 ULA as local, but not Tailscale's `100.64.0.0/10`. Switching to `External` (as on home) removes the login.
- **SABnzbd:** `local_ranges = 100.64.0.0/10,` (no IPv6 range), `host_whitelist = *.tail2e6179.ts.net,`. Paths: `download_dir = C:\Media\usenet\.incomplete`, `complete_dir = C:\Media\Usenet`. No Windows service comes with its installer: SABnzbd ships one (pywin32 `ServiceFramework`, verb `install|update|remove|start|stop|restart`), but its install command misreads a non-interactive shell and refuses (`StartServiceCtrlDispatcher` error). Create it with `sc.exe create`, then write `-f <inifile>` into `HKLM\SYSTEM\CurrentControlSet\services\SABnzbd\CommandLine` (`REG_MULTI_SZ`), as the installer's `set_serv_parms` would.
- **Category folders:** `tv` and `movies` stage as usual (`C:\Media\Usenet\TV`/`Movies`, `C:\Media\Torrent\TV`/`Movies`), but SABnzbd's `music`, `xxx`, `books`, `general` and `*` categories and qBittorrent's `music` category write straight into `C:\Media\Library\<Name>`, skipping staging.
- **qBittorrent:** default save path `C:\Media\Torrent\.incomplete`.
- **Root folders:** Sonarr `C:\Media\Library\TV`, Radarr `C:\Media\Library\Movies`.
- **Bazarr:** binds `100.86.121.94:6767` (`general.ip` in `C:\ProgramData\Bazarr\config\config.yaml`), so localhost is refused and a cold boot before `tailscaled` risks the `10049` failure.
- **Log levels:** Sonarr `debug`, Radarr and Prowlarr `info`.
- Servy (`C:\Program Files\Servy`) manages only `ClaudeRemoteControl`, unrelated to the stack.
