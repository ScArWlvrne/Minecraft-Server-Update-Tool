"""
State persistence helpers.
"""

import os
from configparser import ConfigParser
from typing import Dict

from config import AppConfig, StateConfig


def load_state(path: str) -> StateConfig:
    """
    Load only the state sections from the INI file.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    parser = ConfigParser()
    parser.read(path)

    mc_version = parser.get("state", "mc_version", fallback="").strip()
    server_version = parser.get("state", "server_version", fallback="").strip()
    mods = {}
    if parser.has_section("state.mods"):
        for mod_id, version in parser.items("state.mods"):
            mods[mod_id.strip()] = version.strip()
    return StateConfig(mc_version=mc_version, server_version=server_version, mods=mods)


def save_state(path: str, app_config: AppConfig, new_state: StateConfig) -> None:
    """
    Persist state back into the INI file, preserving other sections/keys.
    """
    parser = ConfigParser()
    if os.path.exists(path):
        parser.read(path)

    if not parser.has_section("state"):
        parser.add_section("state")
    parser.set("state", "mc_version", new_state.mc_version)
    parser.set("state", "server_version", new_state.server_version)

    # Replace state.mods section
    if parser.has_section("state.mods"):
        parser.remove_section("state.mods")
    parser.add_section("state.mods")
    for mod_id, version in new_state.mods.items():
        parser.set("state.mods", mod_id, version)

    with open(path, "w") as f:
        parser.write(f)
