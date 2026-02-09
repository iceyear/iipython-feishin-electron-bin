#!/usr/bin/env python3
import json
import os
from urllib.request import urlopen


def main() -> int:
    upstream_repo = "iiPythonx/feishin"
    tag = os.environ.get("INPUT_TAG") or ""
    release_tag = os.environ.get("INPUT_RELEASE_TAG") or ""
    pkgver = os.environ.get("INPUT_PKGVER") or ""
    assetver = os.environ.get("INPUT_ASSETVER") or ""

    if tag:
        release_url = f"https://api.github.com/repos/{upstream_repo}/releases/tags/{tag}"
    else:
        release_url = f"https://api.github.com/repos/{upstream_repo}/releases/latest"

    with urlopen(release_url, timeout=10) as resp:
        data = json.load(resp)

    latest_tag = data["tag_name"]
    assets = data.get("assets", [])
    asset = next(
        (item for item in assets if item.get("name", "").endswith("linux-amd64.deb")),
        None,
    )
    if not asset:
        raise SystemExit("No linux-amd64.deb asset found in upstream release")

    asset_name = asset["name"]
    derived_assetver = asset_name.replace("feishin-", "").split("-linux-")[0]

    pkgver = pkgver or latest_tag.replace("-", "_")
    assetver = assetver or derived_assetver
    release_tag = release_tag or latest_tag

    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
        handle.write(f"upstream_tag={latest_tag}\n")
        handle.write(f"release_tag={release_tag}\n")
        handle.write(f"pkgver={pkgver}\n")
        handle.write(f"assetver={assetver}\n")

    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as handle:
        handle.write(f"FEISHIN_TAG={release_tag}\n")
        handle.write(f"FEISHIN_PKGVER={pkgver}\n")
        handle.write(f"FEISHIN_ASSETVER={assetver}\n")
        handle.write(f"FEISHIN_UPSTREAM_TAG={latest_tag}\n")
        handle.write(f"UPSTREAM_TAG={latest_tag}\n")
        handle.write(f"UPSTREAM_REPO={upstream_repo}\n")

    print(f"Resolved upstream tag: {latest_tag}")
    print(f"Resolved release tag: {release_tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
