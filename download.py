"""
Download/staging helpers with SHA1 verification.
"""

import hashlib
import os
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass
from typing import Optional

USER_AGENT = "minecraft-server-update-tool/0.1"


class DownloadError(Exception):
    pass


@dataclass
class DownloadResult:
    path: str
    size_bytes: int
    sha1: str


def download_file(url: str, dest_path: str, expected_sha1: Optional[str] = None) -> DownloadResult:
    """
    Stream download a file to dest_path, optionally verifying SHA1.
    Overwrites dest_path if it exists. Raises DownloadError on failure or hash mismatch.
    """
    import logging

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    hasher = hashlib.sha1()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    logging.info("Downloading %s -> %s", url, dest_path)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest_path, "wb") as out:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                out.write(chunk)
                hasher.update(chunk)
    except Exception as exc:
        # Best-effort cleanup of partial download
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass
        raise DownloadError(f"Failed to download {url}: {exc}") from exc

    digest = hasher.hexdigest()
    if expected_sha1 and digest.lower() != expected_sha1.lower():
        try:
            os.remove(dest_path)
        except Exception:
            pass
        raise DownloadError(
            f"SHA1 mismatch for {url}: expected {expected_sha1}, got {digest}"
        )

    return DownloadResult(path=dest_path, size_bytes=os.path.getsize(dest_path), sha1=digest)


@dataclass
class StagingArea:
    base_dir: str

    def path(self, *parts: str) -> str:
        return os.path.join(self.base_dir, *parts)


def create_staging(parent_dir: str, prefix: str = "update_") -> StagingArea:
    """
    Create a temp staging directory under parent_dir. Caller is responsible for cleanup.
    """
    os.makedirs(parent_dir, exist_ok=True)
    temp_dir = tempfile.mkdtemp(prefix=prefix, dir=parent_dir)
    return StagingArea(base_dir=temp_dir)


def cleanup_staging(staging: StagingArea) -> None:
    """Remove the staging directory and contents."""
    try:
        shutil.rmtree(staging.base_dir)
    except FileNotFoundError:
        pass
