"""
Filesystem inventory helpers for mods. This is read-only and side-effect free.
"""

import os
from dataclasses import dataclass
from typing import Dict, List

from config import AppConfig


@dataclass
class ModFile:
    mod_id: str
    filename: str
    path: str
    size_bytes: int


@dataclass
class InventoryResult:
    mods: Dict[str, ModFile]
    missing: List[str]
    unexpected: List[ModFile]


def _normalize_token(value: str) -> str:
    """Lowercase and replace spaces with hyphens to make matching more tolerant."""
    return value.strip().lower().replace(" ", "-")


def inventory_mods(cfg: AppConfig) -> InventoryResult:
    """
    Inspect the mods directory and classify files:
    - mods: matched to configured mod_ids by slug presence in filename
    - missing: configured mod_ids not present in directory
    - unexpected: jar files that don't match any configured mod_id
    """
    mods_dir = cfg.server.mods_dir
    if not os.path.isdir(mods_dir):
        raise FileNotFoundError(f"Mods directory does not exist: {mods_dir}")

    normalized_ids = {mid: _normalize_token(mid) for mid in cfg.mods.keys()}

    found: Dict[str, ModFile] = {}
    unexpected: List[ModFile] = []

    for entry in os.listdir(mods_dir):
        if not entry.lower().endswith(".jar"):
            continue
        entry_path = os.path.join(mods_dir, entry)
        if not os.path.isfile(entry_path):
            continue

        matched_mod_id = None
        fname_norm = entry.lower()
        for mod_id, norm in normalized_ids.items():
            if norm in fname_norm:
                matched_mod_id = mod_id
                break

        mod_file = ModFile(
            mod_id=matched_mod_id or "",
            filename=entry,
            path=entry_path,
            size_bytes=os.path.getsize(entry_path),
        )
        if matched_mod_id:
            # If duplicates exist for same mod_id, keep the first and treat others unexpected.
            if matched_mod_id in found:
                unexpected.append(mod_file)
            else:
                found[matched_mod_id] = mod_file
        else:
            unexpected.append(mod_file)

    missing = [mid for mid in cfg.mods.keys() if mid not in found]

    return InventoryResult(mods=found, missing=missing, unexpected=unexpected)
