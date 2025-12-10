"""
Helpers to interact with the running server via screen and to run backup/start scripts.
"""

import glob
import logging
import os
import shlex
import shutil
import subprocess
import tarfile
import time
from typing import Optional

from config import AppConfig


class ServerControlError(Exception):
    pass


def _screen_session_exists(session: str) -> bool:
    """Return True if a screen session with the given name exists."""
    proc = subprocess.run(
        f"screen -list | grep -q '\\.{session}\\b'",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0


def _run_shell(cmd: str, timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """Run a shell command, returning the completed process; raises on nonzero exit."""
    logging.debug("Running shell command: %s", cmd)
    return subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=True,
    )


def send_screen_command(cfg: AppConfig, command: str) -> bool:
    """
    Send a command to the server's screen session. Returns True if sent, False if no session configured.
    """
    session = cfg.server.screen_session
    if not session:
        logging.info("No screen session configured; skipping send: %s", command)
        return False
    cmd = cfg.server.screen_cmd.format(session=session, cmd=command)
    try:
        _run_shell(cmd)
        return True
    except subprocess.CalledProcessError as exc:
        logging.warning("Failed to send to screen: %s (stderr: %s)", cmd, exc.stderr)
        return False


def warn_players(cfg: AppConfig, title: str, subtitle: str = "", delay_seconds: int = 60) -> None:
    """
    Send a title to all players warning of impending shutdown, then wait delay_seconds.
    Uses Minecraft /title to show on screen instead of chat.
    """
    if not cfg.server.screen_session or not _screen_session_exists(cfg.server.screen_session):
        logging.info("No active screen session for warnings; skipping warn/wait.")
        return

    sent_title = send_screen_command(
        cfg,
        f'title @a title {{"text":"{title}","color":"red"}}',
    )
    if subtitle:
        send_screen_command(
            cfg,
            f'title @a subtitle {{"text":"{subtitle}","color":"yellow"}}',
        )
    # Also send a tellraw to chat as a fallback
    send_screen_command(
        cfg,
        f'tellraw @a {{"text":"{title} - {subtitle or ""}","color":"red"}}',
    )
    if sent_title and delay_seconds > 0:
        logging.info("Warned players; waiting %s seconds before stop", delay_seconds)
        time.sleep(delay_seconds)


def stop_server(cfg: AppConfig) -> None:
    """
    Send a graceful stop to the server via screen, then wait for the session to disappear.
    If no session configured, assume already stopped.
    """
    if not cfg.server.screen_session:
        logging.info("No screen session configured; assuming server is already stopped.")
        return
    session = cfg.server.screen_session
    ok = send_screen_command(cfg, "stop")
    if not ok:
        logging.warning("Stop command not sent; server may already be down.")
        return

    # Wait for the screen session to disappear to avoid "already running" when starting
    timeout = 60
    for _ in range(timeout):
        if not _screen_session_exists(session):
            logging.info("Server session %s stopped.", session)
            return
        time.sleep(1)

    logging.warning("Server session %s still running after %s seconds.", session, timeout)


def run_backup(cfg: AppConfig) -> None:
    """
    Execute the backup script if configured. Raises on failure.
    """
    if not cfg.server.backup_script:
        logging.info("No backup_script configured; skipping backup.")
        return
    logging.info("Starting backup via: %s", cfg.server.backup_script)
    try:
        _run_shell(cfg.server.backup_script)
        logging.info("Backup script completed.")
    except subprocess.CalledProcessError as exc:
        raise ServerControlError(
            f"Backup script failed with exit {exc.returncode}: {exc.stderr or exc.stdout}"
        ) from exc


def start_server(cfg: AppConfig) -> None:
    """
    Execute the start script. Raises on failure.
    """
    if not cfg.server.start_script:
        raise ServerControlError("start_script is not configured")
    try:
        proc = _run_shell(cfg.server.start_script)
        if proc.stdout:
            logging.info("Start script stdout: %s", proc.stdout.strip())
        if proc.stderr:
            logging.info("Start script stderr: %s", proc.stderr.strip())
    except subprocess.CalledProcessError as exc:
        raise ServerControlError(
            f"Start script failed with exit {exc.returncode}: {exc.stderr or exc.stdout}"
        ) from exc


def restore_latest_backup(cfg: AppConfig, backup_dir: Optional[str] = None) -> None:
    """
    Restore the latest backup tarball for this server_dir.
    If backup_dir is provided, it is treated as the directory containing the tar.gz files.
    Otherwise uses cfg.server.backup_dir; if that is unset, falls back to ~/mc_backups/<server_name>.
    """
    server_dir = cfg.server.server_dir
    server_name = os.path.basename(os.path.normpath(server_dir))
    if backup_dir:
        target_dir = os.path.expanduser(backup_dir)
    elif cfg.server.backup_dir:
        target_dir = os.path.expanduser(cfg.server.backup_dir)
    else:
        target_dir = os.path.expanduser(os.path.join("~/mc_backups", server_name))

    if not os.path.isdir(target_dir):
        raise ServerControlError(f"No backup directory found at {target_dir}")

    backups = sorted(
        glob.glob(os.path.join(target_dir, "*.tar.gz")),
        key=os.path.getmtime,
        reverse=True,
    )
    if not backups:
        raise ServerControlError(f"No backups found in {target_dir}")

    latest = backups[0]
    logging.info("Restoring backup from %s", latest)

    # Clear current server_dir contents but keep the directory itself
    if os.path.isdir(server_dir):
        for entry in os.listdir(server_dir):
            path = os.path.join(server_dir, entry)
            try:
                if os.path.isfile(path) or os.path.islink(path):
                    os.remove(path)
                else:
                    shutil.rmtree(path)
            except Exception as exc:
                logging.warning("Failed to remove %s during restore: %s", path, exc)
    else:
        os.makedirs(server_dir, exist_ok=True)

    # Extract backup
    try:
        with tarfile.open(latest, "r:gz") as tar:
            tar.extractall(server_dir)
    except Exception as exc:
        raise ServerControlError(f"Failed to restore backup {latest}: {exc}") from exc
