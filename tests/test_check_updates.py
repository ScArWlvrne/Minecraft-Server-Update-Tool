import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Ensure repo root is on sys.path for direct module imports
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import AppConfig, OptionsConfig, ServerConfig, StateConfig
from check_updates import CheckResult, check_updates


def make_app_config(mods: Dict[str, str], state_mods: Dict[str, str]) -> AppConfig:
    """Helper to build an AppConfig without reading files."""
    server_cfg = ServerConfig(
        server_dir="/tmp/server",
        mods_dir="/tmp/server/mods",
        server_jar="server.jar",
        backup_dir="/tmp/backups",
        screen_session="mc",
        screen_cmd='screen -S {session} -X stuff "{cmd}\\n"',
        warn_players=False,
        warn_delay_seconds=60,
        auto_backup=True,
        backup_script="backup.sh",
        start_script="start.sh",
        log_file="server-update.log",
    )
    opts_cfg = OptionsConfig(assume_yes=False)
    state_cfg = StateConfig(
        mc_version="1.20.1",
        server_version="0.15.0",
        mods=state_mods,
    )
    return AppConfig(server=server_cfg, options=opts_cfg, mods=mods, datapacks={}, state=state_cfg)


@pytest.fixture()
def stub_fetch_json(monkeypatch):
    """Monkeypatch check_updates._fetch_json to avoid real HTTP calls."""
    from check_updates import _fetch_json as real_fetch

    responses: Dict[str, Any] = {
        "https://meta.fabricmc.net/v2/versions/game": [
            {"version": "1.21.8", "stable": True},
            {"version": "1.21.7", "stable": True},
        ],
        "https://meta.fabricmc.net/v2/versions/loader": [
            {"version": "0.16.0", "stable": True},
            {"version": "0.15.0", "stable": True},
        ],
        # Mod A: has release matching target MC with sha1
        "https://api.modrinth.com/v2/project/mod-a/version?loaders=%5B%22fabric%22%5D": [
            {
                "version_number": "2.0.0",
                "version_type": "release",
                "game_versions": ["1.21.8"],
                "loaders": ["fabric"],
                "dependencies": [
                    {"project_id": "dep-1", "dependency_type": "required"},
                    {"project_id": "dep-optional", "dependency_type": "optional"},
                ],
                "files": [
                    {"url": "https://cdn/mod-a-2.0.0.jar", "hashes": {"sha1": "aaa"}}
                ],
            }
        ],
        # Mod B: only beta matching target MC
        "https://api.modrinth.com/v2/project/mod-b/version?loaders=%5B%22fabric%22%5D": [
            {
                "version_number": "1.5.0-beta",
                "version_type": "beta",
                "game_versions": ["1.21.8"],
                "loaders": ["fabric"],
                "files": [
                    {"url": "https://cdn/mod-b-1.5.0-beta.jar", "hashes": {"sha1": "bbb"}}
                ],
            }
        ],
        # Mod C: no versions match target MC; should take latest overall (alpha)
        "https://api.modrinth.com/v2/project/mod-c/version?loaders=%5B%22fabric%22%5D": [
            {
                "version_number": "0.9.0-alpha",
                "version_type": "alpha",
                "game_versions": ["1.21.5"],
                "loaders": ["fabric"],
                "files": [
                    {"url": "https://cdn/mod-c-0.9.0-alpha.jar", "hashes": {"sha1": "ccc"}}
                ],
            }
        ],
        # dep-1 metadata and version
        "https://api.modrinth.com/v2/project/dep-1": {"title": "Dep One"},
        "https://api.modrinth.com/v2/project/dep-1/version?loaders=%5B%22fabric%22%5D": [
            {
                "version_number": "0.0.1",
                "version_type": "release",
                "game_versions": ["1.21.8"],
                "loaders": ["fabric"],
                "files": [
                    {"url": "https://cdn/dep-1-0.0.1.jar", "hashes": {"sha1": "ddd"}}
                ],
            }
        ],
    }

    def fake_fetch(url: str):
        if url not in responses:
            pytest.fail(f"Unexpected URL: {url}")
        return responses[url]

    monkeypatch.setattr("check_updates._fetch_json", fake_fetch)
    return fake_fetch


def test_check_updates_selects_expected_versions(stub_fetch_json):
    app_cfg = make_app_config(
        mods={"mod-a": "Mod A", "mod-b": "Mod B", "mod-c": "Mod C"},
        state_mods={"mod-a": "1.0.0", "mod-b": "1.4.0", "mod-c": "0.8.0"},
    )

    result: CheckResult = check_updates(app_cfg)

    # Fabric targets latest stable from stubbed meta
    assert result.fabric.target_mc == "1.21.8"
    assert result.fabric.target_loader == "0.16.0"
    assert result.fabric.needs_update is True

    # Mod A picks release matching MC
    mod_a = next(m for m in result.mods if m.mod_id == "mod-a")
    assert mod_a.latest_version == "2.0.0"
    assert mod_a.mc_compatible is True
    assert mod_a.version_type == "release"
    assert mod_a.download_url.endswith("mod-a-2.0.0.jar")
    assert mod_a.sha1 == "aaa"
    assert mod_a.dependencies == ["dep-1"]
    assert mod_a.game_versions == ["1.21.8"]
    assert mod_a.auto_added is False

    # Mod B falls back to beta matching MC
    mod_b = next(m for m in result.mods if m.mod_id == "mod-b")
    assert mod_b.latest_version == "1.5.0-beta"
    assert mod_b.version_type == "beta"
    assert mod_b.mc_compatible is True

    # Mod C takes latest overall when no MC match; marks incompatible
    mod_c = next(m for m in result.mods if m.mod_id == "mod-c")
    assert mod_c.latest_version == "0.9.0-alpha"
    assert mod_c.version_type == "alpha"
    assert mod_c.mc_compatible is False

    # Dependency was auto-added
    dep = next(m for m in result.mods if m.mod_id == "dep-1")
    assert dep.auto_added is True
