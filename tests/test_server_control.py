import sys
from pathlib import Path
import subprocess

import pytest

# Ensure repo root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import AppConfig, OptionsConfig, ServerConfig, StateConfig
from server_control import (
    run_backup,
    send_screen_command,
    start_server,
    stop_server,
    warn_players,
    restore_latest_backup,
    ServerControlError,
)


def make_cfg(screen_session="mc", backup_script="", start_script=""):
    server_cfg = ServerConfig(
        server_dir="/tmp/server",
        mods_dir="/tmp/server/mods",
        server_jar="server.jar",
        backup_dir="/tmp/backups",
        screen_session=screen_session,
        screen_cmd='screen -S {session} -X stuff "{cmd}\\n"',
        warn_players=True,
        warn_delay_seconds=1,
        auto_backup=True,
        backup_script=backup_script,
        start_script=start_script,
        log_file="server-update.log",
    )
    opts_cfg = OptionsConfig(assume_yes=False)
    state_cfg = StateConfig(mc_version="", server_version="", mods={})
    return AppConfig(server=server_cfg, options=opts_cfg, mods={}, datapacks={}, state=state_cfg)


def test_send_screen_command_sends(monkeypatch):
    captured = {}

    def fake_run(cmd, shell, stdout, stderr, text, timeout, check):
        captured["cmd"] = cmd
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""
        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)
    cfg = make_cfg()
    assert send_screen_command(cfg, "say hi") is True
    assert "say hi" in captured["cmd"]


def test_send_screen_command_no_session(monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *a, **k: None)
    cfg = make_cfg(screen_session="")
    assert send_screen_command(cfg, "say hi") is False


def test_warn_players_sends_title(monkeypatch):
    sent_cmds = []

    def fake_send(cfg, command):
        sent_cmds.append(command)
        return True

    monkeypatch.setattr("server_control.send_screen_command", fake_send)
    monkeypatch.setattr("server_control._screen_session_exists", lambda session: True)
    monkeypatch.setattr("time.sleep", lambda _: None)
    cfg = make_cfg()
    warn_players(cfg, "Shutdown soon", "Save your work", delay_seconds=0)
    assert any("title @a title" in c for c in sent_cmds)
    assert any("subtitle" in c for c in sent_cmds)


def test_stop_server_no_session(monkeypatch):
    monkeypatch.setattr("server_control.send_screen_command", lambda *a, **k: False)
    cfg = make_cfg(screen_session="")
    # Should not raise
    stop_server(cfg)


def test_run_backup_success(monkeypatch):
    cfg = make_cfg(backup_script="backup.sh")
    monkeypatch.setattr("server_control._run_shell", lambda cmd, timeout=None: None)
    run_backup(cfg)  # Should not raise


def test_run_backup_failure(monkeypatch):
    cfg = make_cfg(backup_script="backup.sh")
    def fake_run(cmd, timeout=None):
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd, output="", stderr="fail")
    monkeypatch.setattr("server_control._run_shell", fake_run)
    with pytest.raises(ServerControlError):
        run_backup(cfg)


def test_start_server_success(monkeypatch):
    cfg = make_cfg(start_script="start.sh")
    class DummyProc:
        stdout = "ok"
        stderr = ""
    monkeypatch.setattr("server_control._run_shell", lambda cmd, timeout=None: DummyProc())
    start_server(cfg)  # Should not raise


def test_start_server_failure(monkeypatch):
    cfg = make_cfg(start_script="start.sh")
    def fake_run(cmd, timeout=None):
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd, output="", stderr="fail")
    monkeypatch.setattr("server_control._run_shell", fake_run)
    with pytest.raises(ServerControlError):
        start_server(cfg)


def test_restore_latest_backup(tmp_path: Path):
    # Prepare backup dir structure and archive
    server_dir = tmp_path / "mc_survival"
    server_dir.mkdir()
    (server_dir / "old.txt").write_text("old")

    backup_root = tmp_path / "backups"
    backup_target_dir = backup_root / "mc_survival"
    backup_target_dir.mkdir(parents=True)

    # Create a backup tar.gz
    import tarfile
    backup_file = backup_target_dir / "mc_survival_1.tar.gz"
    with tarfile.open(backup_file, "w:gz") as tar:
        # Tar the server_dir contents
        tar.add(server_dir, arcname=".")

    # Modify server_dir to ensure restore overwrites
    (server_dir / "old.txt").write_text("modified")
    (server_dir / "new.txt").write_text("should go away")

    cfg = make_cfg()
    cfg.server.server_dir = str(server_dir)

    # Invoke restore
    restore_latest_backup(cfg, backup_dir=str(backup_target_dir))

    # Assert contents match backup (no new.txt, old.txt restored)
    assert (server_dir / "old.txt").read_text() == "old"
    assert not (server_dir / "new.txt").exists()
