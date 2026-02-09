#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.request import urlopen

PKGBUILD_PATH = "PKGBUILD"
SRCINFO_PATH = ".SRCINFO"
REPO = "iceyear/iipython-feishin-electron-bin"


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def write_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def extract_var(content: str, var_name: str) -> str:
    match = re.search(rf"^{re.escape(var_name)}=([^\n]+)$", content, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Missing {var_name} in PKGBUILD")
    return match.group(1).strip().strip("\"")


def set_env(key: str, value: str) -> None:
    env_path = os.environ.get("GITHUB_ENV")
    if env_path:
        with open(env_path, "a", encoding="utf-8") as handle:
            handle.write(f"{key}={value}\n")


def download_file(url: str, dest: str) -> None:
    with urlopen(url) as resp, open(dest, "wb") as handle:
        handle.write(resp.read())


def detect_electron_major(asset_path: str, appname: str) -> str:
    with tempfile.TemporaryDirectory() as workdir:
        subprocess.run(["ar", "x", asset_path], cwd=workdir, check=True)
        data_archives = sorted(
            name for name in os.listdir(workdir) if name.startswith("data.tar.")
        )
        if not data_archives:
            raise RuntimeError("Unable to locate data.tar.* in deb archive")
        extractor = "bsdtar" if shutil.which("bsdtar") else "tar"
        subprocess.run([extractor, "-xf", data_archives[0]], cwd=workdir, check=True)
        binary_path = os.path.join(workdir, "opt", "Feishin", appname)
        if not os.path.exists(binary_path):
            app_dir = f"{appname[:1].upper()}{appname[1:]}"
            binary_path = os.path.join(workdir, "opt", app_dir, appname)
        if not os.path.exists(binary_path):
            for root, _, files in os.walk(os.path.join(workdir, "opt")):
                if appname in files:
                    binary_path = os.path.join(root, appname)
                    break
        output = subprocess.check_output(["strings", binary_path], text=True)
    match = re.search(r"Chrome/[0-9.]* Electron/([0-9]+)", output)
    if not match:
        raise RuntimeError("Unable to detect Electron major version from deb")
    return match.group(1)


def main() -> int:
    override_tag = os.environ.get("FEISHIN_TAG")
    override_pkgver = os.environ.get("FEISHIN_PKGVER")
    override_assetver = os.environ.get("FEISHIN_ASSETVER")

    pkgbuild = read_text(PKGBUILD_PATH)
    current_tag = extract_var(pkgbuild, "_tag")
    current_pkgver = extract_var(pkgbuild, "pkgver")
    current_assetver = extract_var(pkgbuild, "_assetver")
    current_electron = extract_var(pkgbuild, "_electronversion")
    current_appname = extract_var(pkgbuild, "_appname")
    current_sha = extract_var(pkgbuild, "sha256sums_x86_64").strip("'()").split()[0]

    if override_tag:
        release_url = f"https://api.github.com/repos/{REPO}/releases/tags/{override_tag}"
    else:
        release_url = f"https://api.github.com/repos/{REPO}/releases/latest"

    with urlopen(release_url) as resp:
        data = json.load(resp)

    latest_tag = data["tag_name"]
    assets = data.get("assets", [])
    asset = next(
        (item for item in assets if item.get("name", "").endswith("linux-amd64.deb")),
        None,
    )
    if not asset:
        raise RuntimeError("No linux-amd64.deb asset found in latest release")

    asset_name = asset["name"]
    asset_url = asset["browser_download_url"]
    digest = asset.get("digest", "")
    if not digest.startswith("sha256:"):
        raise RuntimeError("Asset digest missing sha256")
    latest_sha = digest.split("sha256:")[-1]

    latest_assetver = override_assetver or asset_name.replace("feishin-", "").split("-linux-")[0]
    latest_pkgver = override_pkgver or latest_tag.replace("-", "_")
    with tempfile.TemporaryDirectory() as workdir:
        appimage_path = os.path.join(workdir, asset_name)
        download_file(asset_url, appimage_path)
        latest_electron = detect_electron_major(appimage_path, current_appname)

    if (
        latest_tag == current_tag
        and latest_sha == current_sha
        and latest_assetver == current_assetver
        and latest_electron == current_electron
    ):
        set_env("PKG_UPDATED", "0")
        set_env("NEW_PKGVER", current_pkgver)
        print("No update available.")
        return 0

    pkgbuild = re.sub(r"^pkgver=.*$", f"pkgver={latest_pkgver}", pkgbuild, flags=re.MULTILINE)
    pkgbuild = re.sub(r"^_tag=.*$", f"_tag={latest_tag}", pkgbuild, flags=re.MULTILINE)
    pkgbuild = re.sub(r"^_assetver=.*$", f"_assetver={latest_assetver}", pkgbuild, flags=re.MULTILINE)
    pkgbuild = re.sub(
        r"^_electronversion=.*$",
        f"_electronversion={latest_electron}",
        pkgbuild,
        flags=re.MULTILINE,
    )
    pkgbuild = re.sub(
        r"^sha256sums_x86_64=.*$",
        f"sha256sums_x86_64=('{latest_sha}')",
        pkgbuild,
        flags=re.MULTILINE,
    )

    write_text(PKGBUILD_PATH, pkgbuild)

    srcinfo = read_text(SRCINFO_PATH)
    srcinfo = re.sub(r"^pkgver = .*$", f"pkgver = {latest_pkgver}", srcinfo, flags=re.MULTILINE)
    srcinfo = re.sub(
        r"^provides = feishin=.*$",
        f"provides = feishin={latest_pkgver}",
        srcinfo,
        flags=re.MULTILINE,
    )
    srcinfo = re.sub(
        r"^depends = electron.*$",
        f"depends = electron{latest_electron}",
        srcinfo,
        flags=re.MULTILINE,
    )
    source_line = (
        f"source_x86_64 = iipython-feishin-electron-{latest_pkgver}-x86_64.deb::"
        f"https://github.com/{REPO}/releases/download/{latest_tag}/feishin-{latest_assetver}-linux-amd64.deb"
    )
    srcinfo = re.sub(r"^source_x86_64 = .*$", source_line, srcinfo, flags=re.MULTILINE)
    srcinfo = re.sub(
        r"^sha256sums_x86_64 = .*$",
        f"sha256sums_x86_64 = {latest_sha}",
        srcinfo,
        flags=re.MULTILINE,
    )
    write_text(SRCINFO_PATH, srcinfo)

    set_env("PKG_UPDATED", "1")
    set_env("NEW_PKGVER", latest_pkgver)
    print(f"Updated to {latest_pkgver} ({latest_tag}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
