import json
import os

_SERVER_MAP = None


def _load_server_map():
    global _SERVER_MAP
    if _SERVER_MAP is not None:
        return _SERVER_MAP

    config_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "config", "server_map.json"
    )
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            _SERVER_MAP = json.load(f)
    except FileNotFoundError:
        _SERVER_MAP = {"servers": []}

    return _SERVER_MAP


def search_servers(query: str = "", organ: str = None, stain: str = None):
    data = _load_server_map()
    results = []

    query_lower = query.lower() if query else ""
    organ_lower = organ.lower() if organ else ""
    stain_lower = stain.lower() if stain else ""

    for server in data.get("servers", []):
        matching_paths = []
        for path_info in server.get("paths", []):
            desc = path_info.get("description", "").lower()
            tags = [t.lower() for t in path_info.get("tags", [])]
            path = path_info.get("path", "").lower()
            searchable = [desc, path] + tags

            if query_lower and not any(query_lower in s for s in searchable):
                continue
            if organ_lower and not any(organ_lower in s for s in searchable):
                continue
            if stain_lower and not any(stain_lower in s for s in searchable):
                continue

            matching_paths.append(path_info)

        if matching_paths:
            results.append({
                "name": server["name"],
                "host": server["host"],
                "description": server.get("description", ""),
                "matching_paths": matching_paths,
            })

    if not results:
        return {
            "message": "검색 조건에 맞는 서버 데이터를 찾을 수 없습니다.",
            "servers": [],
        }

    return {"servers": results}
