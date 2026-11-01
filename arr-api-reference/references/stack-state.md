# Stack state — current autostart, bind, and firewall config

Current state only. Read before touching service config.

## Bind and firewall

Sonarr/Radarr/Prowlarr/SABnzbd bind to wildcard (exact values in table below) instead of the Tailscale IP directly — a Tailscale-IP bind fails at boot with `SocketException 10049` before `tailscaled` reassigns the IP. Reachability locked down by Windows Firewall instead (rules in table), scoped to `100.64.0.0/10` (Tailscale CGNAT range, matches SAB's own `local_ranges` setting).

Host filtering (`allowedHosts`) is the second layer. All three Servarr apps carry `localhost,127.0.0.1,100.86.121.94,lance.tail2e6179.ts.net`; each app appends its own machine name (`LANCE`, `Lance`, `[::1]`) at startup, so the bare hostname is always accepted and the firewall has to close it. The `arr-tailscale-only TCP <port>` block rules (RemoteAddress `192.168.0.0/16,172.16.0.0/12,10.0.0.0/8`) exist for that reason; `localhost` and the Tailscale IP still pass. `allowedHosts` is persisted by `PUT /config/host` but only takes effect at the next service restart — the health check clears immediately, the middleware reloads at startup (`ConfigureHostFilteringOptions` log line).

Bazarr has no host filter. It binds `100.86.121.94:6767` directly (`general.ip` in `C:\ProgramData\Bazarr\config\config.yaml`), so only tailnet clients reach it; localhost:6767 is refused. A cold boot in which Bazarr starts before `tailscaled` carries the same `SocketException 10049` risk the other apps avoid by binding wildcard.

SABnzbd has no Windows Service via its installer by default. It ships one native (pywin32 `ServiceFramework` in `SABnzbd.py`, verb `install|update|remove|start|stop|restart`), but the install command mis-detects a non-interactive/session-0 shell and refuses (`StartServiceCtrlDispatcher` error). Workaround: `sc.exe create` directly, plus write `-f <inifile>` into `HKLM\SYSTEM\CurrentControlSet\services\SABnzbd\CommandLine` (`REG_MULTI_SZ`), the same way the installer's `set_serv_parms` would.

## Autostart inventory

| App         | Autostart mechanism                                                                                                             | Account                     | Bind                          | Firewall                                                               |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------- | --------------------------- | ----------------------------- | ---------------------------------------------------------------------- |
| Sonarr      | native Windows Service, Auto                                                                                                    | `NT AUTHORITY\LocalService` | `*` (config.xml)              | `NzbDrone` allow `100.64.0.0/10` + `arr-tailscale-only TCP 8989` block |
| Radarr      | native Windows Service, Auto                                                                                                    | `NT AUTHORITY\LocalService` | `*` (config.xml)              | `NzbDrone` allow `100.64.0.0/10` + `arr-tailscale-only TCP 7878` block |
| Prowlarr    | native Windows Service, Auto                                                                                                    | `NT AUTHORITY\LocalService` | `*` (config.xml)              | `NzbDrone` allow `100.64.0.0/10` + `arr-tailscale-only TCP 9696` block |
| SABnzbd     | native Windows Service, Auto (`sc create`, not installer)                                                                       | `LocalSystem`               | `0.0.0.0` (sabnzbd.ini)       | `SABnzbd`/`SABnzbd-console` allow `100.64.0.0/10`                      |
| Bazarr      | native Windows Service (`Bazarr`)                                                                                               | —                           | `100.86.121.94` (config.yaml) | `arr-tailscale-only TCP 6767` block                                    |
| qBittorrent | manual start only, by decision — no service/task                                                                                | —                           | `100.86.121.94:18088` WebUI   | none                                                                   |
| Emby        | login Startup-folder shortcut (`%AppData%\Microsoft\Windows\Start Menu\Programs\Startup\Emby Server.lnk`), runs as current user | current user                | —                             | none                                                                   |

No arr-related Scheduled Task. Servy (`C:\Program Files\Servy`) manages only `ClaudeRemoteControl` — unrelated.
