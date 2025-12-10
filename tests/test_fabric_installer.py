import sys
from pathlib import Path

import pytest

# Ensure repo root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fabric_installer import (
    FabricInstallerError,
    download_installer,
    latest_installer_version,
    run_installer,
)
from download import create_staging, cleanup_staging


class DummyResponse:
    def __init__(self, data: bytes, status: int = 200):
        self._data = data
        self.status = status
        self._offset = 0

    def read(self, size: int = -1):
        if size == -1:
            size = len(self._data)
        if self._offset >= len(self._data):
            return b""
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


@pytest.fixture()
def stub_urlopen(monkeypatch):
    responses = {}

    def fake_urlopen(req, timeout=20):
        url = req.full_url if hasattr(req, "full_url") else req
        if url not in responses:
            pytest.fail(f"Unexpected URL: {url}")
        data, status = responses[url]
        return DummyResponse(data, status=status)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return responses


def test_latest_installer_version_prefers_stable(monkeypatch, stub_urlopen):
    stub_urlopen["https://meta.fabricmc.net/v2/versions/installer"] = (
        b'[{"version": "0.12.0", "stable": true}, {"version": "0.13.0", "stable": false}]',
        200,
    )
    ver = latest_installer_version()
    assert ver == "0.12.0"


def test_download_installer_uses_latest(stub_urlopen, tmp_path):
    # Stub meta call and jar download
    stub_urlopen["https://meta.fabricmc.net/v2/versions/installer"] = (
        b'[{"version": "0.12.0", "stable": true}]',
        200,
    )
    jar_url = "https://maven.fabricmc.net/net/fabricmc/fabric-installer/0.12.0/fabric-installer-0.12.0.jar"
    stub_urlopen[jar_url] = (b"installer-bytes", 200)

    staging = create_staging(str(tmp_path))
    try:
        result = download_installer(staging)
        assert Path(result.path).exists()
        assert Path(result.path).read_bytes() == b"installer-bytes"
    finally:
        cleanup_staging(staging)


def test_run_installer_invokes_java(monkeypatch, tmp_path):
    staging = create_staging(str(tmp_path))
    installer_path = staging.path("fabric-installer.jar")
    Path(installer_path).write_bytes(b"installer")

    # Pretend java exists
    monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/java")

    captured = {}

    def fake_run(cmd, stdout, stderr, text, check):
        captured["cmd"] = cmd
        # Simulate installer output by writing launch jar
        Path(staging.path("fabric-server-launch.jar")).write_text("jar")
        class Result:
            returncode = 0
            stdout = "ok"
            stderr = ""
        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    try:
        launch_path = run_installer(
            installer_path=installer_path,
            staging=staging,
            mc_version="1.21.1",
            loader_version="0.15.0",
        )
        assert Path(launch_path).exists()
        # Ensure CLI args passed through
        assert "-mcversion" in captured["cmd"]
        assert "1.21.1" in captured["cmd"]
        assert "-loader" in captured["cmd"]
        assert "0.15.0" in captured["cmd"]
    finally:
        cleanup_staging(staging)


def test_run_installer_missing_java(monkeypatch, tmp_path):
    staging = create_staging(str(tmp_path))
    installer_path = staging.path("fabric-installer.jar")
    Path(installer_path).write_bytes(b"installer")
    monkeypatch.setattr("shutil.which", lambda x: None)
    with pytest.raises(FabricInstallerError):
        run_installer(
            installer_path=installer_path,
            staging=staging,
            mc_version="1.21.1",
            loader_version="0.15.0",
        )
    cleanup_staging(staging)
