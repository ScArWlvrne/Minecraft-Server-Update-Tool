"""
Helper to fetch and run the Fabric installer CLI to produce a server launch jar.
Keeps all work inside a staging directory; caller can move/rename the jar later.
"""

import json
import os
import shutil
import subprocess
import urllib.request
from typing import Optional

from download import DownloadError, DownloadResult, StagingArea, download_file

USER_AGENT = "minecraft-server-update-tool/0.1"


class FabricInstallerError(Exception):
    pass


def _fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Request failed ({resp.status}): {url}")
        return json.load(resp)


def latest_installer_version() -> str:
    """
    Get the latest Fabric installer version (prefers stable).
    """
    entries = _fetch_json("https://meta.fabricmc.net/v2/versions/installer")
    if not entries:
        raise FabricInstallerError("No installer versions returned by Fabric meta")
    for entry in entries:
        if entry.get("stable"):
            return entry["version"]
    return entries[0]["version"]


def download_installer(staging: StagingArea, version: Optional[str] = None) -> DownloadResult:
    """
    Download the Fabric installer jar into staging. Returns download result.
    """
    ver = version or latest_installer_version()
    jar_name = f"fabric-installer-{ver}.jar"
    url = f"https://maven.fabricmc.net/net/fabricmc/fabric-installer/{ver}/{jar_name}"
    dest = staging.path(jar_name)
    return download_file(url, dest)


def run_installer(
    installer_path: str,
    staging: StagingArea,
    mc_version: str,
    loader_version: str,
    java_cmd: str = "java",
) -> str:
    """
    Invoke the Fabric installer to generate the server launch jar in staging.
    Returns the path to fabric-server-launch.jar.
    """
    if not shutil.which(java_cmd):
        raise FabricInstallerError(f"Java not found on PATH (looked for '{java_cmd}')")

    cmd = [
        java_cmd,
        "-jar",
        installer_path,
        "server",
        "-mcversion",
        mc_version,
        "-loader",
        loader_version,
        "-downloadMinecraft",
        "-dir",
        staging.base_dir,
    ]

    try:
        completed = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise FabricInstallerError(
            f"Fabric installer failed (exit {exc.returncode}): {exc.stderr or exc.stdout}"
        ) from exc

    launch_path = staging.path("fabric-server-launch.jar")
    if not launch_path or not os.path.isfile(launch_path):
        raise FabricInstallerError("Installer did not produce fabric-server-launch.jar")
    return launch_path
