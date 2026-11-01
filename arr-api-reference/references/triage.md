# Triage — live runbooks for stuck/down symptoms

Active diagnostic playbooks for this media stack. Read when the stack looks broken right now (down app, stuck queue, health error) — not needed for normal wiring/config work.

## Before hitting any app's API

Confirm app really running first (`Get-Process <App>`). Down app give
misleading "connection refused" — worse, call made while down can leave
false "API key missing" entry in _its own_ health log once back up,
since log just record request that arrive with no key attach (app not
there to catch one, not real config problem). Don't chase that log
entry like it live thing.

**Stuck/zombie process look "running" but serve nothing.**
`Get-Process` show exe no mean it listen —
Sonarr/Radarr/Prowlarr `SingleInstancePolicy` self-kill fresh
launch if see another instance already hold lock, but older
instance itself can be zombie (crash past HTTP listener, mutex still
hold). Symptom: process exist, `Get-NetTCPConnection -OwningProcess
<pid>` give back nothing, `curl` get connection-refused. Fix:
`Stop-Process -Id <pid> -Force`, relaunch.

**SABnzbd duplicate-process outage.** Two
`SABnzbd.exe` at once (one boot-time, one late-night manual launch),
both bare cmdline `"C:\Program Files\SABnzbd\SABnzbd.exe"`, neither
listen on 8080, log tail 3 day old. Meanwhile `sc.exe query` show
all four service `STOPPED` while Sonarr/Prowlarr orphan process
still serve API fine — SCM state and process table disagree, trust
`Get-NetTCPConnection -State Listen` for port 8989/7878/9696/8080,
not service state. Fix: `Stop-Process -Id <both> -Force`,
`sc.exe start SABnzbd`, verify single PID listen `0.0.0.0:8080`
before touch anything else. Sonarr-side client config need zero
change after — outage was process, not setting.

## "All download clients are unavailable due to failures" triage

Health error almost always mean client app down, not client config
wrong. Order: (1) confirm listener (`Get-NetTCPConnection -State
Listen` for 8080), (2) read Sonarr log tail for exact cause —
SAB-down look like `DownloadClientUnavailableException: Unable to
connect to SABnzbd, No connection could be made because the target
machine actively refused it. (100.86.121.94:8080)` under
`DownloadMonitoringService|Unable to retrieve queue and history
items from SABnzbd`, (3) fix process (see zombie section above),
(4) `POST /api/v3/downloadclient/testall` — expect
`[{id, isValid: True, validationFailures: []}]`, then re-`GET
/api/v3/health` and confirm download-client error gone with no
config edit.

Stale queue entries with `status: downloadClientUnavailable` persist
after client recover (they reference grab-time state). Don't hand-
`POST /api/v3/queue/grab` with `{ids}` — it 405. Instead queue a
`SeriesSearch`: `POST /api/v3/command`
`{"name":"SeriesSearch","seriesId":<id>}` → `queued`, wait ~90s,
then `GET /queue` group by `status` and SAB `mode=queue` show
`Downloading` jobs.

Pause live SAB-side: Sonarr queue `status: paused` mirror SAB job
status, so resume in SAB, not Sonarr:
`mode=queue&name=resume&value=<nzo_id>&output=json&apikey=...` →
`{"status":true}`, re-query queue confirm job `Downloading`.
Find `nzo_id` per job from same `mode=queue` response (`.queue.slots[].nzo_id`).
Duplicate-pause pattern: several Sonarr paused entries for the same
release can map to only one or two real SAB jobs — rest are stale
tracked refs to a `nzo_id` lost in restart. Resume the real one,
stale refs drop on re-poll by themselves, don't chase them.
