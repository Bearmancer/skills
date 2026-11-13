# /// script
# requires-python = ">=3.12"
# dependencies = ["requests"]
# ///

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

# Keys are read from this machine's own config files, so every call targets this machine.
HOST = "localhost"
ARR_PORTS = {"Sonarr": 8989, "Radarr": 7878, "Prowlarr": 9696}
ARR_API_VER = {"Sonarr": "v3", "Radarr": "v3", "Prowlarr": "v1"}
SAB_URL = f"http://{HOST}:8080/api"


def get_arr_api_key(app):
    tree = ET.parse(Path(rf"C:\ProgramData\{app}\config.xml"))
    api_key = tree.getroot().find("ApiKey")
    return api_key.text if api_key is not None and api_key.text is not None else ""


def get_sab_api_key():
    ini_path = Path.home() / "AppData" / "Local" / "sabnzbd" / "sabnzbd.ini"
    pattern = re.compile(r"^api_key\s*=\s*(.+)", re.IGNORECASE)
    for line in ini_path.read_text().splitlines():
        m = pattern.match(line)
        if m:
            return m.group(1).strip()
    raise ValueError(f"api_key not found in {ini_path}")


def _reachable_bind(addr):
    """Address to call for a bind value: a wildcard bind is reached on loopback."""
    return "127.0.0.1" if addr in ("", "*", "0.0.0.0", "::", "[::]") else addr


def qbt_base():
    """WebUI base URL from this machine's qBittorrent.ini.

    qBittorrent writes either `WebUI\\Port=` under [Preferences] or `Port=` under [WebUI],
    depending on version; the WebUI may be bound to one address (lance binds its
    Tailscale IP, so localhost is refused there).
    """
    text = (Path.home() / "AppData" / "Roaming" / "qBittorrent" / "qBittorrent.ini").read_text()
    web = re.search(r"^\[WebUI\]\n((?:(?!\[).*\n?)*)", text, re.MULTILINE)
    section = web.group(1) if web else ""

    def key(name):
        m = re.search(rf"^{name}=(.*)$", section, re.MULTILINE) or re.search(
            rf"^WebUI\\{name}=(.*)$", text, re.MULTILINE
        )
        return m.group(1).strip() if m else ""

    return f"http://{_reachable_bind(key('Address'))}:{key('Port') or 8080}"


def bazarr_base():
    """Bazarr base URL from `general.ip`/`general.port` in its config.yaml."""
    text = Path(r"C:\ProgramData\Bazarr\config\config.yaml").read_text()
    general = re.search(r"^general:\n((?:  .*\n)*)", text, re.MULTILINE)
    block = general.group(1) if general else ""
    ip = re.search(r"^  ip: (\S+)", block, re.MULTILINE)
    port = re.search(r"^  port: (\d+)", block, re.MULTILINE)
    addr = _reachable_bind(ip.group(1).strip("'\"") if ip else "")
    return f"http://{addr}:{port.group(1) if port else 6767}"


def arr_base_and_headers(app):
    base = f"http://{HOST}:{ARR_PORTS[app]}/api/{ARR_API_VER[app]}"
    return base, {"X-Api-Key": get_arr_api_key(app)}


def sab_api(**params):
    params.setdefault("apikey", get_sab_api_key())
    params.setdefault("output", "json")
    resp = requests.get(SAB_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def merge_arr_fields(fields):
    deduped = {}
    for f in fields:
        deduped[f["name"]] = f
    return list(deduped.values())


def set_arr_field_value(fields, name, value):
    for f in fields:
        if f["name"] == name:
            f["value"] = value


def add_arr_download_client(
    app,
    implementation,
    dc_host,
    dc_port,
    api_key,
    category_value,
):
    category_field = {"Sonarr": "tvCategory", "Radarr": "movieCategory"}[app]
    base, headers = arr_base_and_headers(app)

    resp = requests.get(f"{base}/downloadclient/schema", headers=headers, timeout=10)
    resp.raise_for_status()
    tmpl = next(
        (
            t
            for t in resp.json()
            if t["implementation"].casefold() == implementation.casefold()
        ),
        None,
    )
    if tmpl is None:
        raise ValueError(
            f"No download client implementation named '{implementation}' in {app}'s schema."
        )

    set_arr_field_value(tmpl["fields"], "host", dc_host)
    set_arr_field_value(tmpl["fields"], "port", dc_port)
    set_arr_field_value(tmpl["fields"], "apiKey", api_key)
    set_arr_field_value(tmpl["fields"], category_field, category_value)

    body = {
        "enable": True,
        "protocol": tmpl["protocol"],
        "priority": 1,
        "name": implementation,
        "fields": tmpl["fields"],
        "implementationName": tmpl["implementationName"],
        "implementation": tmpl["implementation"],
        "configContract": tmpl["configContract"],
        "infoLink": tmpl["infoLink"],
        "tags": [],
    }

    resp = requests.post(
        f"{base}/downloadclient", headers=headers, json=body, timeout=10
    )
    resp.raise_for_status()
    return resp.json()


def set_prowlarr_category_map(client_id, mapping, default_category=None):
    base, headers = arr_base_and_headers("Prowlarr")

    resp = requests.get(
        f"{base}/downloadclient/{client_id}", headers=headers, timeout=10
    )
    resp.raise_for_status()
    client = resp.json()
    client["fields"] = merge_arr_fields(client["fields"])

    if default_category:
        set_arr_field_value(client["fields"], "category", default_category)

    client["categories"] = [
        {"clientCategory": k, "categories": v} for k, v in mapping.items()
    ]

    resp = requests.put(
        f"{base}/downloadclient/{client_id}", headers=headers, json=client, timeout=10
    )
    resp.raise_for_status()
    return resp.json()


def set_sab_category_dir(category, dir_):
    return sab_api(mode="set_config", section="categories", keyword=category, dir=dir_)


def remove_sab_category(category):
    return sab_api(mode="del_config", section="categories", keyword=category)


def set_qbt_category_dir(category, dir_):
    resp = requests.post(
        f"{qbt_base()}/api/v2/torrents/editCategory",
        data={"category": category, "savePath": dir_},
        timeout=10,
    )
    resp.raise_for_status()


def qbt_info_hash(data):
    """SHA-1 infohash of a .torrent's raw bytes (hash of the bencoded `info` dict)."""
    import hashlib

    def parse(i):
        c = data[i : i + 1]
        if c == b"i":
            j = data.index(b"e", i)
            return int(data[i + 1 : j]), j + 1
        if c in (b"l", b"d"):
            i += 1
            items, info_span = [], None
            while data[i : i + 1] != b"e":
                start = i
                v, i = parse(i)
                items.append(v)
                if c == b"d" and len(items) % 2 == 0 and items[-2] == b"info":
                    info_span = (start, i)
            return (items, info_span), i + 1
        j = data.index(b":", i)
        n = int(data[i:j])
        return data[j + 1 : j + 1 + n], j + 1 + n

    (_, span), _ = parse(0)
    return hashlib.sha1(data[span[0] : span[1]]).hexdigest()


def _qbt_torrents(base):
    # A 401/403 comes back as a plain-text body; check status first so it surfaces as
    # that, not a JSONDecodeError.
    resp = requests.get(f"{base}/api/v2/torrents/info", timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"qBittorrent {base}: HTTP {resp.status_code} {resp.text!r}")
    return resp.json()


def add_qbt_torrents(paths, base=None, save_path=None, category=None):
    """Upload .torrent files to qBittorrent, skipping ones it already has.

    base defaults to this machine's WebUI (qbt_base()); pass another machine's tailnet
    URL to target it. Dedupes by infohash against /torrents/info (re-adding a known hash
    is a silent no-op, so counting is the only way to see what landed). Sends no login:
    needs the localhost bypass or a whitelisted subnet, else /torrents/add returns 403.
    Returns (added, skipped, count_after).
    """
    base = base or qbt_base()
    have = {t["hash"] for t in _qbt_torrents(base)}
    paths = [Path(p) for p in paths]
    todo = []
    for p in paths:
        raw = p.read_bytes()
        if qbt_info_hash(raw) not in have:
            todo.append((p.name, raw))
    if todo:
        data = {k: v for k, v in (("savepath", save_path), ("category", category)) if v}
        resp = requests.post(
            f"{base}/api/v2/torrents/add",
            data=data,
            files=[("torrents", (n, b, "application/x-bittorrent")) for n, b in todo],
            timeout=120,
        )
        resp.raise_for_status()  # body "Ok." on success, "Fails." if every file was rejected
    return len(todo), len(paths) - len(todo), len(_qbt_torrents(base))


def find_arr_job(name_match):
    hist = sab_api(mode="history", limit=200)
    pattern = re.compile(re.escape(name_match), re.IGNORECASE)
    return [
        {
            "name": slot["name"],
            "category": slot["category"],
            "status": slot["status"],
            "storage": slot["storage"],
            "path": slot["path"],
            "fail_message": slot["fail_message"],
        }
        for slot in hist["history"]["slots"]
        if pattern.search(slot["name"])
    ]


def add_emby_library_path(
    library_name, path, api_key, emby_base="http://localhost:8096"
):
    headers = {"X-Emby-Token": api_key}
    resp = requests.get(
        f"{emby_base}/Library/VirtualFolders", headers=headers, timeout=10
    )
    resp.raise_for_status()
    libs = resp.json()
    target = next(
        (lib for lib in libs if lib["Name"].casefold() == library_name.casefold()), None
    )
    if target is None:
        raise ValueError(f"No Emby library named '{library_name}'.")

    resp = requests.post(
        f"{emby_base}/Library/VirtualFolders/Paths",
        params={"id": target["Guid"], "path": path, "refreshLibrary": "true"},
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    if resp.text:
        try:
            return resp.json()
        except ValueError:
            return resp.text
    return None


def get_bazarr_api_key():
    # The key is in the top-level `auth:` block (not `general:`, as older docs said). A
    # scoped regex avoids a pyyaml dependency; ceiling: breaks if Bazarr stops writing
    # 2-space-indented keys.
    text = Path(r"C:\ProgramData\Bazarr\config\config.yaml").read_text()
    m = re.search(r"^auth:\n(?:  .*\n)*?  apikey: (\S+)", text, re.MULTILINE)
    if m is None:
        raise ValueError("auth.apikey not found in Bazarr config.yaml")
    return m.group(1)


def wire_bazarr(bazarr=None):
    """Point Bazarr at Sonarr + Radarr. Returns {app: wired?} read back from Bazarr.

    The endpoint takes form-encoded `settings-<section>-<key>` fields, not JSON (JSON is
    silently ignored); it saves partial updates, answers 204, and needs no restart.
    """
    bazarr = bazarr or bazarr_base()
    headers = {"X-API-KEY": get_bazarr_api_key()}
    form = {}
    for app in ("Sonarr", "Radarr"):
        s = app.lower()
        form |= {
            f"settings-general-use_{s}": "true",
            f"settings-{s}-ip": "127.0.0.1",
            f"settings-{s}-port": str(ARR_PORTS[app]),
            f"settings-{s}-base_url": "/",
            f"settings-{s}-ssl": "false",
            f"settings-{s}-apikey": get_arr_api_key(app),
        }
    resp = requests.post(
        f"{bazarr}/api/system/settings", headers=headers, data=form, timeout=10
    )
    resp.raise_for_status()
    got = requests.get(
        f"{bazarr}/api/system/settings", headers=headers, timeout=10
    ).json()
    return {
        s: bool(got["general"][f"use_{s}"] and got[s]["apikey"])
        for s in ("sonarr", "radarr")
    }
