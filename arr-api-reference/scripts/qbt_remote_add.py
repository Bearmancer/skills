# /// script
# requires-python = ">=3.12"
# dependencies = ["paramiko"]
# ///
"""Add every .torrent in <dir> to a qBittorrent WebUI that is only reachable over ssh.

usage: qbt_remote_add.py <ssh-host> <dir-with-.torrent-files> [webui-port=8080]

paramiko only — the `ssh`/`scp`/`sftp`/`tar` command-line binaries are blocked host-wide by
the `ssh-paramiko-only` plugin, so the alias is resolved through `paramiko.SSHConfig`, files
move over one `paramiko.SFTPClient` session, and the WebUI calls run in one remote bash.

Same design as the shell script it replaced: one upload stream (not one upload per file),
batches of 25 (one curl per batch), counts before and after. Staging is removed only when
every batch returned 200. Re-adding a known hash is a silent no-op in qBittorrent, so no
dedupe is needed here. The file list travels as positional args of the single remote
command, so names with spaces, commas or semicolons stay intact.

Run it (no venvs on this box, uv only):
    uv run --no-project --with paramiko "C:\\Users\\Lance\\.agents\\skills\\arr-api-reference\\scripts\\qbt_remote_add.py" oci <dir> 8080
"""

import io
import os
import shlex
import sys
from pathlib import Path

sys.dont_write_bytecode = True

import paramiko

REMOTE_DIR = "/tmp/qbt_add"
BATCH_SIZE = 25

USAGE = (
    "usage: qbt_remote_add.py <ssh-host> <dir-with-.torrent-files> [webui-port=8080]\n"
    "  <ssh-host>                 alias from ~/.ssh/config (e.g. oci)\n"
    "  <dir-with-.torrent-files>  local folder holding the *.torrent files\n"
    "  [webui-port=8080]          qBittorrent WebUI port on the remote side\n"
    "run: uv run --no-project --with paramiko <this file> <ssh-host> <dir> [port]"
)

# Runs remotely in one bash, like the heredoc the shell version piped to `ssh "$host"
# bash -s -- "$port"`. $3.. are the staged file paths.
REMOTE_SCRIPT = r"""set -euo pipefail
port=$1
batch=$2
shift 2
api=localhost:$port/api/v2
count() { curl -s "$api/torrents/info" | grep -o '"hash"' | wc -l; }
before=$(count); failed=0
number=1
while [ "$#" -gt 0 ]; do
  group=("${@:1:$batch}")
  args=()
  # inner quotes: curl splits unquoted -F values on "," and ";" (file names contain both)
  for f in "${group[@]}"; do args+=(-F "torrents=@\"$f\""); done
  code=$(curl -sS -m 60 -o /dev/null -w '%{http_code}' "${args[@]}" "$api/torrents/add") || code=000
  [ "$code" = 200 ] || { echo "batch $number: HTTP $code"; failed=1; }
  shift "${#group[@]}"
  number=$((number + 1))
done
sleep 5
echo "qBittorrent torrents: $before -> $(count)"
[ "$failed" = 0 ] && rm -rf /tmp/qbt_add /tmp/qbt_add.batch.* || echo "kept /tmp/qbt_add for retry"
exit "$failed"
"""


def fail(message: str) -> None:
    print(f"qbt_remote_add: {message}", file=sys.stderr)
    raise SystemExit(1)


def expand(path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path)))


def resolve_host(alias: str) -> dict:
    """Resolve an alias from ~/.ssh/config the way the ssh CLI would (Includes followed)."""
    cfg = paramiko.SSHConfig()
    cfg_path = Path.home() / ".ssh" / "config"
    if cfg_path.is_file():
        with cfg_path.open("r", encoding="utf-8", errors="replace") as handle:
            cfg.parse(handle)
    entry = cfg.lookup(alias)
    if entry.get("proxycommand"):
        fail(
            f"host {alias!r} uses ProxyCommand {entry['proxycommand']!r}, which paramiko "
            "cannot run (the ssh CLI is blocked). Give the host a direct Hostname in ~/.ssh/config."
        )
    return {
        "alias": alias,
        "hostname": entry.get("hostname") or alias,
        "username": entry.get("user") or os.environ.get("USERNAME") or os.environ.get("USER"),
        "port": int(entry.get("port") or 22),
        "identity": [expand(p) for p in entry.get("identityfile") or []],
    }


def key_candidates(spec: dict) -> "list[Path]":
    """identityfile from the config first, then ~/.ssh/id_* (never the .pub halves)."""
    candidates = [path for path in spec["identity"] if path.is_file()]
    for path in sorted((Path.home() / ".ssh").glob("id_*")):
        if path.suffix != ".pub" and path not in candidates:
            candidates.append(path)
    return candidates


def load_key(path: Path):
    """Return a paramiko PKey, or None if this file is not a key we can read."""
    for name in ("Ed25519Key", "RSAKey", "ECDSAKey", "DSSKey"):
        key_class = getattr(paramiko, name, None)
        if key_class is None:
            continue
        try:
            return key_class.from_private_key_file(str(path))
        except paramiko.PasswordRequiredException:
            fail(
                f"key {path} is passphrase-protected and paramiko cannot prompt (the ssh CLI "
                "is blocked): use an unencrypted key."
            )
        except (paramiko.SSHException, ValueError, OSError):
            continue
    return None


def is_host_key_error(message: str) -> bool:
    lowered = message.lower()
    return "host key" in lowered or "unknown host key list" in lowered or "mismatch" in lowered


def connect(alias: str) -> paramiko.SSHClient:
    spec = resolve_host(alias)
    client = paramiko.SSHClient()
    # RejectPolicy + load_host_keys: strict checking, fail closed, never auto-add.
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    known = Path.home() / ".ssh" / "known_hosts"
    if not known.is_file():
        fail(f"no host key database at {known}, so an unknown host key for {spec['hostname']} is refused")
    client.load_host_keys(str(known))
    if client.get_host_keys().lookup(spec["hostname"]) is None:
        fail(
            f"no host key for {spec['hostname']} in {known}: strict checking, refusing to "
            "auto-add. A human must trust it in a real terminal: "
            f"`uv run --no-project --with paramiko ~/.agents/scripts/paramiko-run.py {spec['alias']} --trust`"
        )

    keys = key_candidates(spec)
    if not keys:
        fail(
            f"no private key for {alias}: identityfile {spec['identity']} and ~/.ssh/id_* are empty"
        )

    errors = []
    for path in keys:
        key = load_key(path)
        if key is None:
            errors.append(f"  {path}: not a readable private key")
            continue
        try:
            client.connect(
                hostname=spec["hostname"],
                port=spec["port"],
                username=spec["username"],
                pkey=key,
                password=None,
                look_for_keys=False,
                allow_agent=False,
                timeout=20,
                banner_timeout=20,
                auth_timeout=20,
            )
        except paramiko.BadHostKeyException as error:
            fail(f"host key mismatch for {spec['hostname']}: {error}")
        except paramiko.SSHException as error:
            if is_host_key_error(str(error)):
                fail(f"{spec['hostname']}: {error}")
            errors.append(f"  {path} -> {spec['hostname']}:{spec['port']}: {error}")
            continue
        except OSError as error:
            # transport-level (unreachable, refused) — no other key can help
            fail(f"{spec['hostname']}:{spec['port']}: {type(error).__name__}: {error}")
        print(f"connected {spec['username']}@{spec['hostname']}:{spec['port']} (key {path})")
        return client
    fail(
        f"could not authenticate to {alias} ({spec['username']}@{spec['hostname']}:{spec['port']})"
        " with any key:\n" + "\n".join(errors)
    )


def exec_plain(client: paramiko.SSHClient, command: str) -> None:
    """Run a quiet setup command; fail with its stderr if it errors."""
    _, stdout, stderr = client.exec_command(command)
    if stdout.channel.recv_exit_status() != 0:
        detail = stderr.read().decode("utf-8", "replace").strip()
        fail(f"remote {command!r} failed" + (f": {detail}" if detail else ""))


def upload(client: paramiko.SSHClient, files: "list[Path]") -> None:
    """One SFTP session for the whole set — the shell version used one tar stream."""
    exec_plain(
        client,
        f"rm -rf {shlex.quote(REMOTE_DIR)} && mkdir -p {shlex.quote(REMOTE_DIR)}",
    )
    sftp = client.open_sftp()
    try:
        for index, local in enumerate(files, start=1):
            sftp.put(str(local), f"{REMOTE_DIR}/{local.name}")
            if index % 50 == 0 or index == len(files):
                print(f"uploaded {index}/{len(files)} files")
    finally:
        sftp.close()


def add_torrents(client: paramiko.SSHClient, files: "list[Path]", port: int) -> int:
    """Stream the remote's own output through as it arrives, keep its exit code."""
    command = (
        f"bash -s -- {shlex.quote(str(port))} {BATCH_SIZE} "
        + " ".join(shlex.quote(f"{REMOTE_DIR}/{path.name}") for path in files)
        + f"\n{REMOTE_SCRIPT}"
    )
    _, stdout, stderr = client.exec_command(command)
    out = io.TextIOWrapper(stdout, encoding="utf-8", errors="replace")
    err = io.TextIOWrapper(stderr, encoding="utf-8", errors="replace")
    for line in out:
        sys.stdout.buffer.write(line.encode("utf-8", "replace"))
        sys.stdout.buffer.flush()
    remaining = err.read()
    status = stdout.channel.recv_exit_status()
    if remaining:
        sys.stderr.buffer.write(remaining.encode("utf-8", "replace"))
        sys.stderr.buffer.flush()
    print(f"added {len(files)} files in {-(-len(files) // BATCH_SIZE)} batches: exit {status}")
    return status


def main(argv: "list[str]") -> int:
    if any(arg in ("-h", "--help") for arg in argv):
        print(USAGE)
        return 0
    if len(argv) < 2:
        print(USAGE, file=sys.stderr)
        print("qbt_remote_add: <ssh-host> and <dir-with-.torrent-files> are both required", file=sys.stderr)
        return 2

    alias = argv[0]
    stage = expand(argv[1])
    port = int(argv[2]) if len(argv) > 2 else 8080

    if not stage.is_dir():
        fail(f"not a directory: {stage}")
    files = sorted(stage.glob("*.torrent"), key=lambda path: path.name)
    if not files:
        fail(f"no .torrent files in {stage}")

    client = connect(alias)
    try:
        upload(client, files)
        return add_torrents(client, files, port)
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
