# /// script
# requires-python = ">=3.12"
# dependencies = ["requests"]
# ///

import argparse
import sys

sys.dont_write_bytecode = True


def get_sab_categories():
    from arr_scripts import sab_api

    cats = sab_api(mode="get_config", section="categories")["config"]["categories"]
    return {c["name"] for c in cats if c["name"] != "*"}


def get_arr_download_client_categories(app, category_field):
    import requests

    from arr_scripts import arr_base_and_headers

    base, headers = arr_base_and_headers(app)
    resp = requests.get(f"{base}/downloadclient", headers=headers, timeout=10)
    resp.raise_for_status()
    out = {}
    for client in resp.json():
        for field in client["fields"]:
            if field["name"] == category_field and field.get("value"):
                out[client["name"]] = field["value"]
    return out


def get_prowlarr_client_categories():
    import requests

    from arr_scripts import arr_base_and_headers

    base, headers = arr_base_and_headers("Prowlarr")
    resp = requests.get(f"{base}/downloadclient", headers=headers, timeout=10)
    resp.raise_for_status()
    out = {}
    for client in resp.json():
        mapped = [c["clientCategory"] for c in client.get("categories", [])]
        if mapped:
            out[client["name"]] = mapped
    return out


def main():
    argparse.ArgumentParser(
        description="Check that every arr download-client category exists in SABnzbd and is mapped in Prowlarr. Reads the live services; takes no options."
    ).parse_args()
    problems = []

    sab_cats = get_sab_categories()
    sonarr_cats = get_arr_download_client_categories("Sonarr", "tvCategory")
    radarr_cats = get_arr_download_client_categories("Radarr", "movieCategory")
    prowlarr_cats = get_prowlarr_client_categories()

    arr_cats = {**sonarr_cats, **radarr_cats}

    for client_name, category in arr_cats.items():
        if category not in sab_cats:
            problems.append(
                f"'{client_name}' download-client category '{category}' "
                f"has no matching SABnzbd category (SAB has: {sorted(sab_cats)})"
            )

    prowlarr_all_mapped = {c for cats in prowlarr_cats.values() for c in cats}
    for category in arr_cats.values():
        if category not in prowlarr_all_mapped:
            problems.append(
                f"category '{category}' used by an arr download-client has no "
                f"Prowlarr clientCategory mapping — matched jobs fall through to "
                f"Prowlarr's default client category instead"
            )

    if problems:
        print(f"Category wiring mismatch ({len(problems)}):")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"Category wiring OK. SAB categories: {sorted(sab_cats)}")
    print(f"Sonarr: {sonarr_cats}")
    print(f"Radarr: {radarr_cats}")
    print(f"Prowlarr mapped: {prowlarr_cats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
