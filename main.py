import argparse
import logging
import sys

from config import parse_config
from check_updates import check_updates
from inventory import inventory_mods
from apply_flow import apply_updates
from ui import prompt_yes_no, setup_logging
import os
import shutil


def parse_args():
    parser = argparse.ArgumentParser(description="Minecraft server updater.")
    parser.add_argument(
        "-c",
        "--config",
        default="config.ini",
        help="Path to config file (default: config.ini)",
    )
    parser.add_argument(
        "-y",
        "--yes",
        dest="assume_yes",
        action="store_true",
        help="Assume yes for prompts.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates (default is check/report only).",
    )
    parser.add_argument(
        "--mc-version",
        dest="mc_version",
        help="Override target Minecraft version (default: latest).",
    )
    return parser.parse_args()


def validate_paths(cfg):
    errors = []
    if not os.path.isdir(cfg.server.server_dir):
        errors.append(f"server_dir does not exist: {cfg.server.server_dir}")
    if not os.path.isdir(cfg.server.mods_dir):
        errors.append(f"mods_dir does not exist: {cfg.server.mods_dir}")
    if cfg.server.backup_script and not os.path.exists(cfg.server.backup_script):
        errors.append(f"backup_script not found: {cfg.server.backup_script}")
    if cfg.server.start_script and not os.path.exists(cfg.server.start_script):
        errors.append(f"start_script not found: {cfg.server.start_script}")
    if not shutil.which("java"):
        errors.append("java not found on PATH (required for Fabric installer)")
    if errors:
        raise SystemExit("Config validation failed:\n- " + "\n- ".join(errors))


def main():
    args = parse_args()
    cfg = parse_config(args.config, args.assume_yes)
    validate_paths(cfg)
    setup_logging(cfg.server.log_file)

    result = check_updates(cfg, target_mc=args.mc_version)
    inv = inventory_mods(cfg)
    mismatched = [m for m in result.mods if not m.mc_compatible]

    print("Fabric:")
    print(
        f"  Target MC {result.fabric.target_mc}, loader {result.fabric.target_loader} | "
        f"Current MC {result.fabric.current_mc or 'unknown'}, loader {result.fabric.current_loader or 'unknown'} | "
        f"Needs update: {'yes' if result.fabric.needs_update else 'no'}"
    )

    print("\nMods:")
    for mod in result.mods:
        compatible = "compatible" if mod.mc_compatible else "mismatch"
        present = inv.mods.get(mod.mod_id)
        print(
            f"  {mod.name} ({mod.mod_id}): "
            f"current={mod.current_version or 'unknown'}, latest={mod.latest_version} "
            f"[{mod.version_type}, {compatible}] "
            f"sha1={mod.sha1} url={mod.download_url} "
            f"{'FOUND' if present else 'MISSING'}"
        )
        if not mod.mc_compatible:
            supported = ",".join(mod.game_versions) if mod.game_versions else "unknown"
            logging.warning(
                "Version mismatch for %s (%s): target MC %s, mod supports %s",
                mod.name,
                mod.mod_id,
                result.fabric.target_mc,
                supported,
            )

    if inv.unexpected:
        print("\nUnexpected mods in directory:")
        for mod in inv.unexpected:
            print(f"  {mod.filename}")

    if inv.missing:
        print("\nMissing mods (configured but not found):")
        for mid in inv.missing:
            print(f"  {mid}")

    if not args.apply:
        return

    logging.info("Starting apply flow...")
    try:
        apply_updates(cfg, args.config, result, inv)
        logging.info("Apply flow completed successfully.")
    except Exception as exc:
        logging.error("Apply flow failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
