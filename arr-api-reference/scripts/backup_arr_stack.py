# /// script
# requires-python = ">=3.12"
# dependencies = ["requests"]
# ///

import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

import requests

sys.dont_write_bytecode = True
from arr_scripts import arr_base_and_headers, sab_api

DRIVE_FS_DIR = Path(r"C:\Program Files\Google\Drive File Stream")
CONFIGS_SUBPATH = Path("My Drive") / "Computer" / "Configs"


def find_configs_dir():
    """`<letter>:\\My Drive\\Computer\\Configs` on whichever letter holds it.

    Streamed Drive shows up as its own letter only while GoogleDriveFS runs; mirrored Drive
    (home: G:\\My Drive on a local disk) is always present but uploads only while it runs.
    """
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        candidate = Path(f"{letter}:\\") / CONFIGS_SUBPATH
        if candidate.exists():
            return candidate
    return None


def drive_running():
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq GoogleDriveFS.exe", "/NH"],
        capture_output=True,
        text=True,
    ).stdout
    return "GoogleDriveFS.exe" in out


def start_drive():
    # Each Drive update installs a new version folder; launch the newest.
    exes = sorted(
        DRIVE_FS_DIR.glob("*/GoogleDriveFS.exe"),
        key=lambda p: tuple(int(x) for x in p.parent.name.split(".") if x.isdigit()),
    )
    if not exes:
        raise FileNotFoundError(f"No GoogleDriveFS.exe under {DRIVE_FS_DIR}")
    subprocess.Popen([str(exes[-1])])


def backup_arr_stack():
    if not drive_running():
        start_drive()
    configs = find_configs_dir()
    if configs is None:
        for _ in range(30):
            time.sleep(1)
            configs = find_configs_dir()
            if configs:
                break
    if configs is None:
        raise FileNotFoundError(f"No drive letter has {CONFIGS_SUBPATH}; not creating it")

    date = datetime.now().strftime("%Y-%m-%d")

    apps = ["Sonarr", "Radarr", "Prowlarr"]
    for app in apps:
        base, headers = arr_base_and_headers(app)
        triggered_at = time.time()
        resp = requests.post(
            f"{base}/command", headers=headers, json={"name": "Backup"}, timeout=10
        )
        resp.raise_for_status()
        command_id = resp.json()["id"]

        status = None
        for _ in range(30):
            time.sleep(1)
            status_resp = requests.get(
                f"{base}/command/{command_id}", headers=headers, timeout=10
            )
            status_resp.raise_for_status()
            status = status_resp.json().get("status")
            if status == "completed":
                break
        else:
            raise TimeoutError(
                f"{app} backup command {command_id} did not complete within 30s "
                f"(last status: {status})"
            )

        backups_dir = Path(rf"C:\ProgramData\{app}\Backups\manual")
        zips = sorted(
            backups_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if not zips:
            raise FileNotFoundError(
                f"{app} backup command reported completed but no zip found in {backups_dir}"
            )
        newest = zips[0]
        if newest.stat().st_mtime < triggered_at:
            raise RuntimeError(
                f"{app} backup command reported completed but newest zip {newest} "
                f"predates the backup trigger time — refusing to copy a stale backup"
            )
        shutil.copy2(newest, configs / f"{app} - {date}.zip")

    sab_resp = sab_api(mode="config", name="create_backup")
    sab_backup_path = Path(sab_resp["value"]["message"])
    shutil.copy2(sab_backup_path, configs / f"SABnzbd - {date}.zip")

    qbt_dir = Path.home() / "AppData" / "Roaming" / "qBittorrent"
    qbt_zip = configs / f"qBittorrent - {date}.zip"
    with zipfile.ZipFile(qbt_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in qbt_dir.iterdir():
            if item.name == "lockfile":
                continue
            if item.is_file():
                zf.write(item, item.relative_to(qbt_dir))
            else:
                for sub in item.rglob("*"):
                    if sub.is_file():
                        zf.write(sub, sub.relative_to(qbt_dir))

    return sorted(configs.glob(f"* - {date}.zip"))


def main():
    for f in backup_arr_stack():
        print(f)


if __name__ == "__main__":
    main()
