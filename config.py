import os
from configparser import ConfigParser
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class ServerConfig:
    server_dir: str
    mods_dir: str
    server_jar: str
    backup_dir: str
    screen_session: str
    screen_cmd: str
    warn_players: bool
    warn_delay_seconds: int
    auto_backup: bool
    backup_script: str
    start_script: str
    log_file: str


@dataclass
class OptionsConfig:
    assume_yes: bool


@dataclass
class StateConfig:
    mc_version: str
    server_version: str
    mods: Dict[str, str] = field(default_factory=dict)


@dataclass
class AppConfig:
    server: ServerConfig
    options: OptionsConfig
    mods: Dict[str, str]
    datapacks: Dict[str, str]
    state: StateConfig


def _getboolean(cfg: ConfigParser, section: str, option: str, fallback: bool) -> bool:
    try:
        return cfg.getboolean(section, option)
    except Exception:
        return fallback


def parse_config(path: str = 'config.ini', cli_assume_yes: bool = False) -> AppConfig:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    parser = ConfigParser()
    parser.optionxform = str  # preserve case for mod IDs
    parser.read(path)

    # Support new layout with [environment] for server settings; fall back to [server] for compatibility.
    env_section = "environment" if parser.has_section("environment") else "server"
    if not parser.has_section(env_section):
        raise ValueError("Missing [environment] (or legacy [server]) section in config.")

    server_dir = parser.get(env_section, "server_dir", fallback="").strip()
    if not server_dir:
        raise ValueError(f"server_dir is required in [{env_section}].")

    mods_dir_raw = parser.get(env_section, "mods_dir", fallback="mods").strip() or "mods"
    mods_dir = mods_dir_raw
    if not os.path.isabs(mods_dir_raw):
        mods_dir = os.path.join(server_dir, mods_dir_raw)

    server_jar = parser.get(env_section, "server_jar", fallback="").strip()
    if not server_jar:
        raise ValueError(f"server_jar is required in [{env_section}].")

    # Options now live under [options]; warn/auto_backup moved there in new layout.
    opts_section = "options"
    auto_backup_opt = _getboolean(parser, opts_section, "auto_backup", True)
    warn_players_opt = _getboolean(parser, opts_section, "warn_players", False)
    warn_delay_opt = parser.getint(opts_section, "warn_delay_seconds", fallback=60)

    server_cfg = ServerConfig(
        server_dir=server_dir,
        mods_dir=mods_dir,
        server_jar=server_jar,
        backup_dir=parser.get(env_section, "backup_dir", fallback="~/mc_backups").strip()
        or "~/mc_backups",
        screen_session=parser.get(env_section, "screen_session", fallback="").strip(),
        screen_cmd=parser.get(
            env_section,
            "screen_cmd",
            fallback='screen -S {session} -X stuff "{cmd}\\n"',
        ).strip(),
        warn_players=warn_players_opt,
        warn_delay_seconds=warn_delay_opt,
        auto_backup=auto_backup_opt,
        backup_script=parser.get(env_section, "backup_script", fallback="").strip(),
        start_script=parser.get(env_section, "start_script", fallback="").strip(),
        log_file=parser.get(env_section, "log_file", fallback="server-update.log").strip()
        or "server-update.log",
    )

    opts_cfg = OptionsConfig(
        assume_yes=cli_assume_yes
        or _getboolean(parser, "options", "assume_yes", False)
    )

    mods_cfg = {}
    if parser.has_section("mods"):
        for mod_id, name in parser.items("mods"):
            mod_id_clean = mod_id.strip()
            if not mod_id_clean:
                continue
            mods_cfg[mod_id_clean] = name.strip()

    datapacks_cfg = {}
    if parser.has_section("datapacks"):
        for dp_id, name in parser.items("datapacks"):
            dp_id_clean = dp_id.strip()
            if not dp_id_clean:
                continue
            datapacks_cfg[dp_id_clean] = name.strip()

    state_mc_version = parser.get("state", "mc_version", fallback="").strip()
    state_server_version = parser.get("state", "server_version", fallback="").strip()
    state_mods = {}
    if parser.has_section("state.mods"):
        for mod_id, version in parser.items("state.mods"):
            mod_id_clean = mod_id.strip()
            if not mod_id_clean:
                continue
            state_mods[mod_id_clean] = version.strip()

    state_cfg = StateConfig(
        mc_version=state_mc_version,
        server_version=state_server_version,
        mods=state_mods,
    )

    return AppConfig(
        server=server_cfg,
        options=opts_cfg,
        mods=mods_cfg,
        datapacks=datapacks_cfg,
        state=state_cfg,
    )
