#!/usr/bin/env bash
# Add every .torrent in <dir> to a qBittorrent WebUI that is only reachable over ssh.
# usage: qbt_remote_add.sh <ssh-host> <dir-with-.torrent-files> [webui-port=8080]
# One tar stream (not one scp per file), batches of 25 (one curl per batch), counts before
# and after. Staging is removed only when every batch returned 200. Re-adding a known hash
# is a silent no-op in qBittorrent, so no dedupe is needed here.
set -euo pipefail
host=$1 dir=$2 port=${3:-8080}

(cd "$dir" && tar -cf - ./*.torrent) | ssh "$host" 'rm -rf /tmp/qbt_add && mkdir /tmp/qbt_add && tar -xf - -C /tmp/qbt_add'

ssh "$host" bash -s -- "$port" <<'REMOTE'
port=$1
api=localhost:$port/api/v2
count() { curl -s "$api/torrents/info" | grep -o '"hash"' | wc -l; }
before=$(count); failed=0
cd /tmp/qbt_add && ls | split -l 25 - /tmp/qbt_add.batch.
for b in /tmp/qbt_add.batch.*; do
  args=()
  # inner quotes: curl splits unquoted -F values on "," and ";" (file names contain both)
  while read -r f; do args+=(-F "torrents=@\"$f\""); done < "$b"
  code=$(curl -sS -m 60 -o /dev/null -w '%{http_code}' "${args[@]}" "$api/torrents/add") || code=000
  [ "$code" = 200 ] || { echo "batch $b: HTTP $code"; failed=1; }
done
sleep 5
echo "qBittorrent torrents: $before -> $(count)"
[ "$failed" = 0 ] && rm -rf /tmp/qbt_add /tmp/qbt_add.batch.* || echo "kept /tmp/qbt_add for retry"
exit "$failed"
REMOTE
