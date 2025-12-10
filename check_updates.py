"""
Utilities to query Fabric and Modrinth for latest available versions without
downloading artifacts. This module is side-effect free and only hits HTTP APIs.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional

from config import AppConfig

USER_AGENT = "minecraft-server-update-tool/0.1"


@dataclass
class FabricCheck:
    target_mc: str
    target_loader: str
    current_mc: str
    current_loader: str
    needs_update: bool


@dataclass
class ModCheck:
    mod_id: str
    name: str
    current_version: str
    latest_version: str
    download_url: str
    sha1: str
    version_type: str
    mc_compatible: bool
    dependencies: List[str]
    game_versions: List[str]
    auto_added: bool


@dataclass
class CheckResult:
    fabric: FabricCheck
    mods: List[ModCheck]
    datapacks: List[ModCheck]


def _fetch_json(url: str):
    """Fetch JSON from a URL using stdlib to avoid extra dependencies."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Request failed ({resp.status}): {url}")
        return json.load(resp)


def _fetch_project_title(project_id: str) -> str:
    """Get project title for a Modrinth project id/slug."""
    data = _fetch_json(f"https://api.modrinth.com/v2/project/{urllib.parse.quote(project_id)}")
    return data.get("title") or project_id


def _resolve_project_id(project_id: str) -> str:
    """
    Resolve a Modrinth project identifier via search, used after a 404.
    """
    project_id = project_id.strip()
    # First, text search
    search_url = "https://api.modrinth.com/v2/search?" + urllib.parse.urlencode({"limit": 1, "query": project_id})
    search = _fetch_json(search_url)
    hits = (search or {}).get("hits") or []
    if hits:
        hit = hits[0]
        return hit.get("project_id") or hit.get("slug") or project_id

    # Try slug facet
    facet_slug = json.dumps([[f"slug:{project_id}"]])
    search_url = "https://api.modrinth.com/v2/search?" + urllib.parse.urlencode({"limit": 1, "facets": facet_slug})
    search = _fetch_json(search_url)
    hits = (search or {}).get("hits") or []
    if hits:
        hit = hits[0]
        return hit.get("project_id") or hit.get("slug") or project_id

    # Try project_id facet with case variants
    for pid in {project_id, project_id.lower(), project_id.upper()}:
        facet_pid = json.dumps([[f"project_id:{pid}"]])
        search_url = "https://api.modrinth.com/v2/search?" + urllib.parse.urlencode({"limit": 1, "facets": facet_pid})
        search = _fetch_json(search_url)
        hits = (search or {}).get("hits") or []
        if hits:
            hit = hits[0]
            return hit.get("project_id") or hit.get("slug") or project_id

    raise RuntimeError(f"Failed to resolve Modrinth project id/slug '{project_id}' (not found)")


def _latest_fabric(target_mc: Optional[str] = None) -> Dict[str, str]:
    """
    Get latest Minecraft + Fabric loader versions from Fabric meta API.
    Prefers stable releases; falls back to first entry if none marked stable.
    If target_mc is provided, uses that MC version (must exist in the list).
    """
    game_versions = _fetch_json("https://meta.fabricmc.net/v2/versions/game")
    loader_versions = _fetch_json("https://meta.fabricmc.net/v2/versions/loader")

    def pick_latest(entries):
        for entry in entries:
            if entry.get("stable"):
                return entry["version"]
        # If nothing marked stable, just take the first entry.
        return entries[0]["version"]

    if target_mc:
        if not any(entry.get("version") == target_mc for entry in game_versions):
            raise RuntimeError(f"Requested MC version {target_mc} not found in Fabric meta")
    else:
        target_mc = pick_latest(game_versions)
    target_loader = pick_latest(loader_versions)
    return {"mc": target_mc, "loader": target_loader}


def _pick_modrinth_version(project_id: str, target_mc: str) -> Dict:
    """
    Choose the best Modrinth version entry:
    - Prefer latest (API returns newest first) that matches target_mc and is release.
    - If none, take latest matching target_mc of any type.
    - If none match MC, take the very latest overall.
    """
    query = urllib.parse.urlencode(
        {
            "loaders": json.dumps(["fabric"]),
        }
    )
    url = f"https://api.modrinth.com/v2/project/{urllib.parse.quote(project_id)}/version?{query}"
    try:
        versions = _fetch_json(url)
    except urllib.error.HTTPError as http_exc:
        if http_exc.code == 404:
            resolved_id = _resolve_project_id(project_id)
            url = f"https://api.modrinth.com/v2/project/{urllib.parse.quote(resolved_id)}/version?{query}"
            try:
                versions = _fetch_json(url)
            except Exception as exc:
                raise RuntimeError(f"Failed to fetch versions for {project_id}: {exc}") from exc
        else:
            raise RuntimeError(f"Failed to fetch versions for {project_id}: {http_exc}") from http_exc
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch versions for {project_id}: {exc}") from exc
    if not versions:
        raise RuntimeError(f"No versions found on Modrinth for {project_id}")

    matching_release = [
        v
        for v in versions
        if target_mc in v.get("game_versions", [])
        and "fabric" in v.get("loaders", [])
        and v.get("version_type") == "release"
    ]
    matching_any = [
        v
        for v in versions
        if target_mc in v.get("game_versions", []) and "fabric" in v.get("loaders", [])
    ]

    def mc_tuple(ver: str) -> tuple:
        nums = [int(x) for x in re.split(r"[^\d]+", ver) if x.isdigit()]
        return tuple(nums) if nums else (0,)

    def best_nonmatching():
        candidates = [v for v in versions if "fabric" in v.get("loaders", [])]
        if not candidates:
            return versions[0]
        def key(v):
            gv = v.get("game_versions") or []
            top = mc_tuple(gv[0]) if gv else (0,)
            vt = v.get("version_type") or ""
            vt_rank = {"release": 3, "beta": 2, "alpha": 1}.get(vt, 0)
            return (top, vt_rank)
        return max(candidates, key=key)

    if matching_release:
        chosen = matching_release[0]
    elif matching_any:
        chosen = matching_any[0]
    else:
        chosen = best_nonmatching()

    return {
        "version_number": chosen.get("version_number", ""),
        "version_type": chosen.get("version_type", "unknown"),
        "game_versions": chosen.get("game_versions", []),
        "files": chosen.get("files", []),
        "dependencies": chosen.get("dependencies", []),
    }


def _select_file_with_sha(files: List[Dict]) -> Optional[Dict]:
    for f in files:
        hashes = f.get("hashes") or {}
        if "sha1" in hashes and f.get("url"):
            return f
    return None


def _pick_datapack_version(project_id: str, target_mc: str) -> Dict:
    query = urllib.parse.urlencode({"game_versions": json.dumps([target_mc])})
    url = f"https://api.modrinth.com/v2/project/{urllib.parse.quote(project_id)}/version?{query}"
    try:
        versions = _fetch_json(url)
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch datapack versions for {project_id}: {exc}") from exc
    if not versions:
        # fallback to all versions if filter returned none
        url_all = f"https://api.modrinth.com/v2/project/{urllib.parse.quote(project_id)}/version"
        versions = _fetch_json(url_all)
    if not versions:
        raise RuntimeError(f"No versions found on Modrinth for datapack {project_id}")
    chosen = versions[0]
    return {
        "version_number": chosen.get("version_number", ""),
        "version_type": chosen.get("version_type", "unknown"),
        "game_versions": chosen.get("game_versions", []),
        "files": chosen.get("files", []),
    }


def check_updates(app_config: AppConfig, target_mc: Optional[str] = None) -> CheckResult:
    """
    Compute latest available server/mod versions based on current config/state.
    Network-only; does not modify filesystem.
    """
    target = _latest_fabric(target_mc)
    fabric_check = FabricCheck(
        target_mc=target["mc"],
        target_loader=target["loader"],
        current_mc=app_config.state.mc_version,
        current_loader=app_config.state.server_version,
        needs_update=(
            app_config.state.mc_version != target["mc"]
            or app_config.state.server_version != target["loader"]
        ),
    )

    mods_checks: List[ModCheck] = []
    visited: Dict[str, bool] = {}
    queue: List[Dict] = [
        {"mod_id": mid, "name": name, "auto_added": False}
        for mid, name in app_config.mods.items()
    ]
    enqueued = {mid for mid in app_config.mods.keys()}

    while queue:
        item = queue.pop(0)
        mod_id = item["mod_id"]
        if mod_id in visited:
            continue
        visited[mod_id] = True
        name = item["name"]
        version_info = _pick_modrinth_version(mod_id, target["mc"])
        file_entry = _select_file_with_sha(version_info["files"])
        if not file_entry:
            raise RuntimeError(f"No downloadable file with SHA1 for mod {mod_id}")
        latest_version = version_info["version_number"]
        dependencies = [
            dep.get("project_id")
            for dep in (version_info.get("dependencies") or [])
            if dep.get("dependency_type") == "required" and dep.get("project_id")
        ]
        mods_checks.append(
            ModCheck(
                mod_id=mod_id,
                name=name,
                current_version=app_config.state.mods.get(mod_id, ""),
                latest_version=latest_version,
                download_url=file_entry["url"],
                sha1=file_entry["hashes"]["sha1"],
                version_type=version_info["version_type"],
                mc_compatible=target["mc"] in version_info["game_versions"],
                dependencies=dependencies,
                game_versions=version_info.get("game_versions", []),
                auto_added=item["auto_added"],
            )
        )

        for dep_id in dependencies:
            if dep_id in visited or dep_id in enqueued:
                continue
            dep_name = app_config.mods.get(dep_id) or _fetch_project_title(dep_id)
            queue.append(
                {
                    "mod_id": dep_id,
                    "name": dep_name,
                    "auto_added": dep_id not in app_config.mods,
                }
            )
            enqueued.add(dep_id)

    # Datapacks
    datapack_checks: List[ModCheck] = []
    dp_visited = set()
    for dp_id, dp_name in app_config.datapacks.items():
        if dp_id in dp_visited:
            continue
        dp_visited.add(dp_id)
        dp_version = _pick_datapack_version(dp_id, target["mc"])
        file_entry = _select_file_with_sha(dp_version["files"])
        if not file_entry:
            raise RuntimeError(f"No downloadable file with SHA1 for datapack {dp_id}")
        datapack_checks.append(
            ModCheck(
                mod_id=dp_id,
                name=dp_name,
                current_version="",
                latest_version=dp_version.get("version_number", ""),
                download_url=file_entry["url"],
                sha1=file_entry["hashes"]["sha1"],
                version_type=dp_version.get("version_type", "unknown"),
                mc_compatible=target["mc"] in dp_version.get("game_versions", []),
                dependencies=[],
                game_versions=dp_version.get("game_versions", []),
                auto_added=False,
            )
        )

    return CheckResult(fabric=fabric_check, mods=mods_checks, datapacks=datapack_checks)
