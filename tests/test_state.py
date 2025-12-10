import sys
from pathlib import Path

import pytest

# Ensure repo root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import StateConfig
from state import load_state, save_state


def test_load_state_reads_sections(tmp_path: Path):
    ini = tmp_path / "config.ini"
    ini.write_text(
        """
[server]
server_dir = /tmp/server

[state]
mc_version = 1.21.1
server_version = 0.15.0

[state.mods]
mod-a = 1.0.0
mod-b = 2.0.0
"""
    )
    state = load_state(str(ini))
    assert state.mc_version == "1.21.1"
    assert state.server_version == "0.15.0"
    assert state.mods == {"mod-a": "1.0.0", "mod-b": "2.0.0"}


def test_save_state_preserves_other_sections(tmp_path: Path):
    ini = tmp_path / "config.ini"
    ini.write_text(
        """
[server]
server_dir = /tmp/server

[state]
mc_version = old
server_version = old

[state.mods]
mod-a = old
"""
    )

    new_state = StateConfig(
        mc_version="1.21.2",
        server_version="0.16.0",
        mods={"mod-a": "1.1.0", "mod-c": "0.1.0"},
    )

    save_state(str(ini), app_config=None, new_state=new_state)  # app_config unused #type:ignore

    parser_state = load_state(str(ini))
    assert parser_state.mc_version == "1.21.2"
    assert parser_state.server_version == "0.16.0"
    assert parser_state.mods == {"mod-a": "1.1.0", "mod-c": "0.1.0"}

    # Ensure server section still present
    text = ini.read_text()
    assert "[server]" in text
