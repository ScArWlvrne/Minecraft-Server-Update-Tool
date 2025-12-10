import sys
from pathlib import Path

import pytest

# Ensure repo root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import AppConfig, OptionsConfig, ServerConfig, StateConfig
from inventory import inventory_mods


def make_cfg(mods_dir: str, mods_map):
    server_cfg = ServerConfig(
        server_dir="/tmp/server",
        mods_dir=mods_dir,
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
    state_cfg = StateConfig(mc_version="", server_version="", mods={})
    return AppConfig(server=server_cfg, options=opts_cfg, mods=mods_map, datapacks={}, state=state_cfg)


def test_inventory_classifies_found_missing_unexpected(tmp_path: Path):
    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()

    # Expected mods (by slug presence)
    (mods_dir / "lithium-fabric-1.0.0.jar").write_text("x")
    (mods_dir / "fabric-api-0.1.0.jar").write_text("x")
    # Duplicate for same mod
    (mods_dir / "lithium-duplicate.jar").write_text("x")
    # Unexpected mod
    (mods_dir / "random-mod.jar").write_text("x")
    # Non-jar should be ignored
    (mods_dir / "readme.txt").write_text("ignored")

    cfg = make_cfg(str(mods_dir), {"lithium": "Lithium", "fabric-api": "Fabric API", "c2me-fabric": "C2ME"})

    result = inventory_mods(cfg)

    assert set(result.mods.keys()) == {"lithium", "fabric-api"}
    assert result.mods["lithium"].filename == "lithium-fabric-1.0.0.jar"
    assert "c2me-fabric" in result.missing

    unexpected_names = sorted([m.filename for m in result.unexpected])
    assert "lithium-duplicate.jar" in unexpected_names
    assert "random-mod.jar" in unexpected_names


def test_inventory_missing_dir_raises(tmp_path: Path):
    cfg = make_cfg(str(tmp_path / "missing_mods"), {"mod-a": "Mod A"})
    with pytest.raises(FileNotFoundError):
        inventory_mods(cfg)
