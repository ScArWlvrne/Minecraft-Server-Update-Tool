import sys
from pathlib import Path

import pytest

# Ensure repo root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from download import DownloadError, create_staging, download_file, cleanup_staging


class DummyResponse:
    def __init__(self, data: bytes, status: int = 200):
        self._data = data
        self.status = status
        self._offset = 0

    def read(self, size: int):
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
    captured_requests = {}

    def fake_urlopen(req, timeout=60):
        url = req.full_url if hasattr(req, "full_url") else req
        captured_requests["last_url"] = url
        # Return predictable content
        return DummyResponse(b"hello world", status=200)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return captured_requests


def test_download_file_success(tmp_path: Path, stub_urlopen):
    dest = tmp_path / "file.bin"
    expected_sha1 = "2aae6c35c94fcfb415dbe95f408b9ce91ee846ed"  # sha1 of "hello world"
    result = download_file("https://example.com/file", str(dest), expected_sha1)

    assert dest.exists()
    assert result.sha1 == expected_sha1
    assert result.size_bytes == dest.stat().st_size
    assert stub_urlopen["last_url"] == "https://example.com/file"


def test_download_file_sha_mismatch(tmp_path: Path, stub_urlopen):
    dest = tmp_path / "file.bin"
    with pytest.raises(DownloadError):
        download_file("https://example.com/file", str(dest), "badsha")
    # Should clean up on mismatch
    assert not dest.exists()


def test_download_file_error_cleans_partial(tmp_path: Path, monkeypatch):
    dest = tmp_path / "file.bin"

    def fake_urlopen(req, timeout=60):
        raise RuntimeError("network down")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(DownloadError):
        download_file("https://example.com/file", str(dest))
    assert not dest.exists()


def test_staging_create_and_cleanup(tmp_path: Path):
    staging = create_staging(str(tmp_path), prefix="test_")
    assert Path(staging.base_dir).exists()
    cleanup_staging(staging)
    assert not Path(staging.base_dir).exists()
