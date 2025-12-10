"""
Apply flow orchestration: download/stage server and mods, stop server, backup, apply, restart.
"""

import logging
import os
import shutil
from typing import List

from check_updates import CheckResult, ModCheck
from config import AppConfig
from download import DownloadError, DownloadResult, create_staging, download_file, cleanup_staging
from fabric_installer import download_installer, run_installer
from inventory import InventoryResult
from server_control import (
    run_backup,
    start_server,
    stop_server,
    warn_players,
    restore_latest_backup,
    ServerControlError,
)
from state import StateConfig, save_state
from ui import prompt_yes_no


class ApplyError(Exception):
    pass


def _stage_mods(cfg: AppConfig, checks: List[ModCheck], staging_dir: str) -> List[DownloadResult]:
    results = []
    seen = set()
    for mod in checks:
        filename = f"{mod.name.replace(' ', '_')}_{mod.latest_version}.jar"
        dest = os.path.join(staging_dir, filename)
        if dest in seen:
            continue
        seen.add(dest)
        logging.info("Staging mod %s (%s) version %s", mod.name, mod.mod_id, mod.latest_version)
        results.append(download_file(mod.download_url, dest, expected_sha1=mod.sha1))
    return results


def _stage_datapacks(cfg: AppConfig, checks: List[ModCheck], staging_dir: str) -> List[DownloadResult]:
    results = []
    seen = set()
    for dp in checks:
        filename = f"{dp.name.replace(' ', '_')}_{dp.latest_version}.zip"
        dest = os.path.join(staging_dir, filename)
        if dest in seen:
            continue
        seen.add(dest)
        logging.info("Staging datapack %s (%s) version %s", dp.name, dp.mod_id, dp.latest_version)
        results.append(download_file(dp.download_url, dest, expected_sha1=dp.sha1))
    return results


def _apply_mods(cfg: AppConfig, staged_mods: List[DownloadResult], inv: InventoryResult, expected_mod_ids: List[str]) -> None:
    # Remove unexpected mods not in config (based on mod_id membership)
    expected_set = set(expected_mod_ids)
    for mod in inv.unexpected:
        if mod.mod_id and mod.mod_id in expected_set:
            continue
        try:
            os.remove(mod.path)
            logging.info("Removed unexpected mod: %s", mod.filename)
        except Exception as exc:
            logging.warning("Failed to remove unexpected mod %s: %s", mod.filename, exc)

    # Remove old versions of configured mods
    for mod_id, mod_file in inv.mods.items():
        try:
            os.remove(mod_file.path)
        except Exception as exc:
            logging.warning("Failed to remove old mod %s: %s", mod_file.filename, exc)

    # Move staged mods into place
    for staged in staged_mods:
        dest = os.path.join(cfg.server.mods_dir, os.path.basename(staged.path))
        shutil.move(staged.path, dest)
        logging.info("Installed mod: %s", dest)


def apply_updates(cfg: AppConfig, config_path: str, checks: CheckResult, inv: InventoryResult) -> None:
    staging = create_staging(cfg.server.server_dir, prefix="staging_")
    backup_completed = False
    try:
        # Prompt if mismatches present before downtime
        mismatched = [m for m in checks.mods if not m.mc_compatible]
        if mismatched:
            names = ", ".join([m.name for m in mismatched])
            if not prompt_yes_no(f"Mods not matching target MC ({names}). Continue?", cfg.options.assume_yes):
                raise ApplyError("User aborted due to mismatched mods.")

        # Optional warn players
        if cfg.server.warn_players:
            warn_players(
                cfg,
                title="Server restarting for updates",
                subtitle=f"Restarting in {cfg.server.warn_delay_seconds}s",
                delay_seconds=cfg.server.warn_delay_seconds,
            )

        # Stop and backup early
        stop_server(cfg)
        if cfg.server.auto_backup:
            try:
                run_backup(cfg)
                backup_completed = True
            except ServerControlError as exc:
                if not prompt_yes_no(f"Backup failed: {exc}. Continue without backup?", cfg.options.assume_yes):
                    raise ApplyError("Backup failed and user declined to continue.")

        # Stage server jar if needed (after backup)
        server_launch_path = None
        staging_libraries = None
        staging_server_jar = None
        staging_launcher_props = None
        if checks.fabric.needs_update:
            installer_dl = download_installer(staging)
            server_launch_path = run_installer(
                installer_path=installer_dl.path,
                staging=staging,
                mc_version=checks.fabric.target_mc,
                loader_version=checks.fabric.target_loader,
            )
            staging_libraries = os.path.join(staging.base_dir, "libraries")
            staging_server_jar = os.path.join(staging.base_dir, "server.jar")
            staging_launcher_props = os.path.join(
                staging.base_dir, "server-launcher.properties"
            )
            new_server_path = os.path.join(
                cfg.server.server_dir, f"NEW_{os.path.basename(cfg.server.server_jar)}"
            )
            shutil.move(server_launch_path, new_server_path)
            logging.info("Staged server jar at %s", new_server_path)

        # Stage mods (after backup)
        staged_mods = _stage_mods(cfg, checks.mods, staging.base_dir)
        staged_datapacks = _stage_datapacks(cfg, checks.datapacks, staging.base_dir)

        # Apply server jar if staged
        if checks.fabric.needs_update:
            # Replace libraries and supporting files from staging
            if staging_libraries and os.path.isdir(staging_libraries):
                target_libs = os.path.join(cfg.server.server_dir, "libraries")
                if os.path.exists(target_libs):
                    shutil.rmtree(target_libs)
                shutil.copytree(staging_libraries, target_libs)
                logging.info("Updated libraries from staging.")
            if staging_server_jar and os.path.isfile(staging_server_jar):
                shutil.copy2(staging_server_jar, os.path.join(cfg.server.server_dir, "server.jar"))
            if staging_launcher_props and os.path.isfile(staging_launcher_props):
                shutil.copy2(staging_launcher_props, os.path.join(cfg.server.server_dir, "server-launcher.properties"))

            target_path = os.path.join(cfg.server.server_dir, cfg.server.server_jar)
            # Remove old jar
            if os.path.exists(target_path):
                os.remove(target_path)
            new_path = os.path.join(cfg.server.server_dir, f"NEW_{os.path.basename(cfg.server.server_jar)}")
            shutil.move(new_path, target_path)
            logging.info("Applied new server jar to %s", target_path)

        # Apply mods
        expected_ids = [m.mod_id for m in checks.mods]
        _apply_mods(cfg, staged_mods, inv, expected_ids)

        # Apply datapacks
        datapack_dir = os.path.join(cfg.server.server_dir, "world", "datapacks")
        os.makedirs(datapack_dir, exist_ok=True)
        # Optionally remove old staged datapacks with same prefix
        for staged in staged_datapacks:
            dest = os.path.join(datapack_dir, os.path.basename(staged.path))
            shutil.move(staged.path, dest)
            logging.info("Installed datapack: %s", dest)

        # Update state
        new_state = StateConfig(
            mc_version=checks.fabric.target_mc,
            server_version=checks.fabric.target_loader,
            mods={m.mod_id: m.latest_version for m in checks.mods if not m.auto_added},
        )
        save_state(config_path, cfg, new_state)

        # Restart server
        try:
            start_server(cfg)
        except ServerControlError as exc:
            logging.error("Start script failed: %s", exc)
            raise

    except Exception as exc:
        logging.error("Apply failed: %s", exc)
        # Attempt restore if we took a backup
        if backup_completed:
            try:
                restore_latest_backup(cfg)
                logging.info("Restored from latest backup after failure.")
            except Exception as rex:
                logging.error("Failed to restore from backup: %s", rex)
        raise
    finally:
        cleanup_staging(staging)
