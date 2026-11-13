# Stack state: bind, firewall, login, ports and paths per machine

Current state only, verified 2026-11-13. Read the section for the machine you are on (`hostname`) before touching service config. API quirks live in `api-reference.md`; this file holds values.

## Shared design (both machines)

- **Bind wildcard, close with the firewall.** Sonarr/Radarr/Prowlarr/SABnzbd bind `*`/`0.0.0.0`/`::` instead of the Tailscale IP: a Tailscale-IP bind fails at boot with `SocketException 10049` when the app starts before `tailscaled` assigns the IP. Windows Firewall does the restricting: allow rules scoped to `100.64.0.0/10` (Tailscale CGNAT) plus block rules for LAN ranges. Block beats allow, so the block rules close a port even where a broad program rule allows it.
- **`allowedHosts` is the second layer**, per machine (values below). Each app also accepts its own machine name (`LANCE`, `HOME`, `[::1]`) on its own, so the bare hostname always passes host filtering and only the firewall closes it. `PUT /config/host` persists `allowedHosts`, but the filter reloads only at service restart (`ConfigureHostFilteringOptions` log line).
- **SABnzbd web exposure:** `inet_exposure = 0` with `local_ranges` listing the tailnet, so tailnet peers count as local and nobody else gets in; `host_whitelist` admits hostname `Host` headers.
- **Emby is the exception on both:** reachable from the LAN as well as the tailnet, login kept.
- No arr-related Scheduled Task on either machine.

## home (desktop, hostname `Home`)

Identity: `home` = 100.112.2.26 / `home.tail2e6179.ts.net` / `fd7a:115c:a1e0::3b33:21a`; LAN 192.168.0.114. Tailscale interface profile: Private. Google Drive runs in mirror mode into `G:\My Drive` on the local 4 TB disk `G:` (label `Lord Lance`); it autostarts via the `HKCU\...\Run` key `GoogleDriveFS --startup_mode` and uploads only while running.

| App         | Run as                                                             | Port | Bind                   | Login                                                                                     |
| ----------- | ------------------------------------------------------------------ | ---- | ---------------------- | ----------------------------------------------------------------------------------------- |
| Sonarr      | Windows service, Auto                                              | 8989 | `*`                    | none: `AuthenticationMethod = External`                                                    |
| Radarr      | Windows service, Auto                                              | 7878 | `*`                    | none: `External`                                                                          |
| Prowlarr    | Windows service, Auto                                              | 9696 | `*`                    | none: `External`                                                                          |
| SABnzbd     | user process `C:\Program Files\SABnzbd\SABnzbd.exe` (no service)   | 8080 | `::` (dual-stack)      | none (`username = ""`)                                                                    |
| qBittorrent | user process                                                       | 8085 | wildcard (no Address)  | bypassed for localhost and `100.64.0.0/10`, `fd7a:115c:a1e0::/48`; user `lance`           |
| Emby        | user process, Startup-folder shortcut                              | 8096 | wildcard               | kept                                                                                      |
| Bazarr      | not installed                                                      |      |                        |                                                                                           |

- **`allowedHosts`** (all three Servarr): `localhost,127.0.0.1,100.112.2.26,home,home.tail2e6179.ts.net,fd7a:115c:a1e0::3b33:21a`. The IPv6 literal is required for IPv6 `Host` headers.
- **Servarr usernames:** Sonarr/Radarr `lance`, Prowlarr `lordlance`; with `External` auth they only matter if auth is turned back on. The API still needs the key.
- **Firewall:** `NzbDrone` allows TCP 7878/8989/9696 from `100.64.0.0/10`; `SABnzbd`/`SABnzbd-console` program allows from `100.64.0.0/10`; `qBittorrent` TCP 8085 allow from `100.64.0.0/10`; `Tailscale-In` allows anything addressed to the tailnet IPs. Blocks: `arr-block-LAN` (remote `192.168.0.0/24`) and `arr-block-HyperV` (remote `172.17.160.1`), both TCP 8989,7878,9696,8080,8085; `qbt-webui-tailnet-only` blocks TCP 8085 from every address outside `100.64.0.0/10` and `fd7a:115c:a1e0::/48` (qBittorrent's own program rules allow any port from anywhere for peer traffic). Emby rules allow from anywhere.
- **SABnzbd:** `local_ranges = 100.64.0.0/10,fd7a:115c:a1e0::/48,`, `host_whitelist = home.tail2e6179.ts.net, home`. Paths: `download_dir = D:\Media\Usenet\.incomplete`, `complete_dir = D:\Media\Usenet`, watch folder `dirscan_dir = D:\Media\Usenet\watch`. Relaunch it via `explorer.exe "C:\Program Files\SABnzbd\SABnzbd.exe"` to keep the interactive user's integrity level. Probing the short name `home` from home itself resolves to `fe80::` first and is refused by design; remote peers resolve `home` to the tailnet addresses.
- **qBittorrent:** save `D:\Media\Torrent`, temp `D:\Media\Torrent\.incomplete`; categories `tv`, `movies`, `prowlarr` under it. Download client in Sonarr, Radarr and Prowlarr at `localhost:8085`.
- **Root folders:** Sonarr `D:\Media\Library\TV`, Radarr `D:\Media\Library\Movies`.
- **Indexers:** every Sonarr/Radarr indexer points at home's own Prowlarr. NZBgeek, NZBFinder and altHUB carry lance's working API keys, and Nzb.life was added from lance's settings; NZBgeek, NZBFinder, Nzb.life use the Unlimited sync profile (RSS on), the rest use Limited (interactive search only). Disabled in Prowlarr for bad keys or site blocks: abNZB, Digital Carnage (network banned 7 days from 2026-11-13), Square Eyed, Aither, Anthelion, RuTracker, MoreThanTV.
- **Emby:** libraries Movies `D:\Media\Library\Movies`, TV `D:\Media\Library\TV`, Concerts `D:\DVDs`, Classical `G:\My Drive\Music\Classical`, Songs `G:\My Drive\Music\Songs`. Sonarr and Radarr each have an `Emby` connection (localhost:8096, Emby API keys named `Sonarr`/`Radarr`). Remote bitrate limit 0, so tailnet clients counting as remote costs nothing.
- **Log levels:** Sonarr and Radarr `debug`, Prowlarr `info`.
- **Verified 2026-11-13:** from oci and from lance over the tailnet, all six apps on all four address forms (IPv4, `[IPv6]`, FQDN, `home`) answer 200 with redirects off (Emby 302 to its own login). From lance on the LAN, 192.168.0.114 times out on 8989/7878/9696/8080/8085 and Emby answers.

## lance (laptop, hostname `Lance-HP-3141KU`)

Identity: `lance` = 100.86.121.94 / `lance.tail2e6179.ts.net`; LAN 192.168.0.101. Google Drive not mounted (2026-11-13). SSH alias from home: `laptop`.

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
- **Category folders:** `tv` and `movies` stage as usual (`C:\Media\Usenet\TV`/`Movies`, `C:\Media\Torrent\TV`/`Movies`), but SABnzbd's `music`, `xxx`, `books`, `general` and `*` categories and qBittorrent's `music` category write straight into `C:\Media\Library\<Name>`, skipping staging. Home stages every category.
- **qBittorrent:** default save path `C:\Media\Torrent\.incomplete`.
- **Root folders:** Sonarr `C:\Media\Library\TV`, Radarr `C:\Media\Library\Movies`.
- **Bazarr:** binds `100.86.121.94:6767` (`general.ip` in `C:\ProgramData\Bazarr\config\config.yaml`), so localhost is refused and a cold boot before `tailscaled` risks the `10049` failure. Its `opensubtitlescom.username` `lordlance` is the external OpenSubtitles provider account, not an app login.
- **Log levels:** Sonarr `debug`, Radarr and Prowlarr `info`.
- Servy (`C:\Program Files\Servy`) manages only `ClaudeRemoteControl`, unrelated to the stack.
