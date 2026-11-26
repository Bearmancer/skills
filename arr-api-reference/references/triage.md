# Triage: runbooks for a stack that is broken right now

Read when an app is down, a queue is stuck, a health check is red or indexers fail. Normal wiring and config work does not need this file.

## Before calling any app's API

Confirm the app is really serving first. A down app gives a misleading "connection refused", and a call made while it was down can leave a false "API key missing" entry in its own health log once it is back up: the log records a request that arrived with no key, not a config problem. Do not chase that entry.

**A stuck process looks running but serves nothing.** `Get-Process` showing the exe does not mean it listens. Sonarr/Radarr/Prowlarr's `SingleInstancePolicy` kills a fresh launch when another instance holds the lock, and that older instance can be a zombie (crashed past its HTTP listener, mutex still held). Symptom: the process exists, `Get-NetTCPConnection -State Listen -OwningProcess <pid>` returns nothing, `curl` gets connection refused. Fix: `Stop-Process -Id <pid> -Force`, relaunch.

**Trust the listener, not the service state.** Service Control Manager state and the process table can disagree (seen: all four services `STOPPED` while orphan Sonarr/Prowlarr processes still served the API). Check `Get-NetTCPConnection -State Listen` for the app's port (per machine in `stack-state.md`).

**SABnzbd duplicate-process outage.** Two `SABnzbd.exe` at once (one boot-time, one manual launch), neither listening on SAB's port, log tail days old. Fix: `Stop-Process` both, start one (`sc.exe start SABnzbd` when it runs as a service; otherwise launch the exe through `explorer.exe` so it keeps the interactive user's integrity level), verify a single PID listens on SAB's port before touching anything else. Client config in Sonarr needs no change afterwards: the outage was the process, not a setting.

## "All download clients are unavailable due to failures"

This health error almost always means the client app is down, not misconfigured. In order:

1. Confirm the listener (`Get-NetTCPConnection -State Listen` for SAB's port, or the qBittorrent port; ports in `stack-state.md`).
2. Read the Sonarr log tail for the cause. SABnzbd down looks like `DownloadClientUnavailableException: Unable to connect to SABnzbd, No connection could be made because the target machine actively refused it.` under `DownloadMonitoringService|Unable to retrieve queue and history items from SABnzbd`.
3. Fix the process (zombie section above).
4. `POST /api/v3/downloadclient/testall`: expect `[{id, isValid: true, validationFailures: []}]`, then re-`GET /api/v3/health` and confirm the error is gone with no config edit.

Stale queue entries with `status: downloadClientUnavailable` stay after the client recovers, because they reference grab-time state. `POST /api/v3/queue/grab` with `{ids}` answers 405; queue a search instead: `POST /api/v3/command {"name":"SeriesSearch","seriesId":<id>}` → `queued`, wait about 90 s, then group `GET /queue` by `status` and check SABnzbd `mode=queue` shows `Downloading` jobs.

**Paused jobs.** A Sonarr queue entry with `status: paused` mirrors the SABnzbd job, so resume it in SABnzbd: `mode=queue&name=resume&value=<nzo_id>&output=json&apikey=...` → `{"status":true}`, then re-query the queue for `Downloading`. Take each `nzo_id` from `mode=queue` (`.queue.slots[].nzo_id`). Several paused Sonarr entries for one release can map to one real SABnzbd job; the rest are stale references to an `nzo_id` lost in a restart and drop off on the next poll once the real job resumes.

## Indexers failing or missing after a sync

Symptoms: Sonarr/Radarr health says "No indexers available with RSS sync enabled", an app has fewer indexers than Prowlarr offers, or the sync log shows `Validation failed`.

1. Read the app's `*.debug.txt` for the ` -- ` lines under `Validation failed` (the plain log omits them):
   - `Unable to connect to indexer ... 429:TooManyRequests ... localhost:<prowlarr-port>/<id>/` is Prowlarr's backoff on indexer `<id>` (`GET /api/v1/indexerstatus`), not the site.
   - `Name: Should be unique` means an app indexer with that name already exists outside Prowlarr's mapping.
2. Run `POST /api/v1/indexer/test` per Prowlarr indexer to get each site's real answer. Bad keys, 403s and bans need the user's new credentials; disable those indexers rather than retrying.
3. For each app indexer, read its `baseUrl`. One pointing at the other machine's Prowlarr (`http://<other-tailnet-ip>:<port>/...`) is outside sync and may be the only working copy: test it with a real search (`<baseUrl>api?t=tvsearch&apikey=<that Prowlarr's key>`) before deleting it. To bring it onto this machine, copy that Prowlarr's key for the indexer into the local Prowlarr (`api-reference.md`, masked secrets), sync, then delete the foreign entry.
4. One indexer keeps vanishing from an app on every sync: mapping collision (`api-reference.md`). Delete that app indexer and sync again.
5. Done when every app indexer points at the local Prowlarr, `POST /api/v3/indexer/testall` is all valid, and both apps' health is empty after one more sync.
