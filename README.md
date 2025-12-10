# Minecraft Server Update Tool

Automates updating a Fabric-based Minecraft server on Linux: checks Fabric loader + MC version, refreshes mods/datapacks from Modrinth (with dependency resolution), stages downloads, stops the server, optionally backs up, applies changes atomically, restarts, and logs the session.

## Features
- Fabric server update via Fabric installer (uses SHA-verified downloads).
- Modrinth mod + dependency resolution; optional datapacks.
- Inventory of current mods; removes anything not in config.
- Player warning via screen (titles + chat) with delay.
- Optional backup + rollback to latest backup on failure.
- State tracking to avoid unnecessary updates.
- Logging to `server-update.log`.

## Requirements
- Python 3.11+ (tested on Linux).
- Fabric-based server.
- `screen` for console commands (server must be running in a named screen session).
- Java installed (for Fabric installer / server).

Mod/datapack IDs must be valid Modrinth project IDs/slugs (case-sensitive).

## Configuration
Fill out `config.ini` (see the template committed in the repo):

```
[environment]
server_dir = /root/mc_server          # server root
mods_dir = mods                       # relative to server_dir or absolute
server_jar = fabric-server-launch.jar
backup_dir = /root/mc_backups/mc_server
screen_session = survival
screen_cmd = screen -S {session} -X stuff '{cmd}\r'
backup_script = /root/mc_management/backup_survival.sh
start_script = /root/mc_server/start.sh
log_file = server-update.log

[options]
assume_yes = false
auto_backup = true
warn_players = true
warn_delay_seconds = 60

[mods]
fabric-api = Fabric API
# add more: modid = Friendly Name

[datapacks]
# datapack-id = Friendly Name

[state]
# managed by the tool; clear to force server update
mc_version =
server_version =
```

Notes:
- `mods_dir` can be relative to `server_dir` or absolute.
- `screen_cmd` uses `\r` to ensure commands execute via `screen -X stuff`.
- If `auto_backup` is true, `backup_script` must exist; otherwise set to false.
- Warns players only if `screen_session` exists and is active.
- The server must be running inside the named `screen_session` for warnings/commands to be delivered.

## Usage
Activate your virtualenv if you have one, then run:

```
python3 main.py            # just check and report
python3 main.py --apply    # perform updates (prompts)
python3 main.py --apply -y # perform updates without prompts
python3 main.py --mc-version X.XX.X   # target specific MC version
```

Flow:
1) Parse config/state.
2) Inventory mods.
3) Check Fabric + mods/datapacks on Modrinth; resolve required deps.
4) Show report; prompt unless `-y`.
5) Warn players (if configured), stop server.
6) Optional backup.
7) Stage downloads; apply server jar, mods, datapacks.
8) Save state; restart server.

## Quickstart
1) Copy `config.ini` and edit paths/session names for your server.
2) Ensure the server is running inside the named `screen_session`.
3) (Optional) Activate your virtualenv.
4) Run `python3 main.py --apply` (add `-y` to auto-confirm).
5) Watch `server-update.log` and `logs/latest.log` for results.

## Logs
- Update run: `server-update.log` (path set in config).
- Server console: your server’s `logs/latest.log` or screen logfile per your start script.

## Caveats
- Designed for Fabric + Modrinth; not for Forge.
- World data referencing missing mods will still crash your server; ensure required mods are present.
- Ensure enough memory for startup; OOM kills will abort startup.

## Testing
Run the test suite:
```
pytest -q
```
