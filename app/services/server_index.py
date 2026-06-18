import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_INDEX: Optional[List[Dict]] = None

INDEX_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

SERVER_CONFIGS = {
    "file_index_200T.tsv": {
        "name": "200T 서버",
        "host": "192.168.1.10",
        "description": "병리 슬라이드 원본 저장소 (230TB, /mnt)",
    },
    "file_index_server05.tsv": {
        "name": "서버5",
        "host": "192.168.1.15",
        "description": "병리 슬라이드 저장소 (14T-1~4 디스크)",
    },
}


def _load_index():
    global _INDEX
    if _INDEX is not None:
        return _INDEX

    _INDEX = []
    for filename, server_info in SERVER_CONFIGS.items():
        filepath = os.path.join(INDEX_DIR, filename)
        if not os.path.exists(filepath):
            logger.warning("Index file not found: %s", filepath)
            continue

        count = 0
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                path = line.strip()
                if not path:
                    continue
                basename = os.path.basename(path)
                name_no_ext = os.path.splitext(basename)[0]
                ext = os.path.splitext(basename)[1].lower()
                _INDEX.append({
                    "server": server_info["name"],
                    "host": server_info["host"],
                    "path": path,
                    "filename": basename,
                    "name_lower": name_no_ext.lower(),
                    "ext": ext,
                })
                count += 1

        logger.info("Loaded %d entries from %s", count, filename)

    return _INDEX


def search_servers(
    query: str = "",
    organ: Optional[str] = None,
    stain: Optional[str] = None,
    limit: int = 30,
):
    index = _load_index()

    if not index:
        return {
            "message": "서버 파일 인덱스가 아직 구축되지 않았습니다.",
            "total": 0,
            "results": [],
        }

    keywords = []
    if query:
        keywords.extend(query.lower().split())
    if organ:
        keywords.append(organ.lower())
    if stain:
        keywords.append(stain.lower())

    if not keywords:
        server_stats = {}
        for entry in index:
            s = entry["server"]
            server_stats[s] = server_stats.get(s, 0) + 1
        return {
            "message": "검색어를 입력해주세요.",
            "total_indexed": len(index),
            "servers": [
                {"name": k, "file_count": v} for k, v in server_stats.items()
            ],
        }

    matches = []
    for entry in index:
        searchable = entry["name_lower"] + " " + entry["path"].lower()
        if all(kw in searchable for kw in keywords):
            matches.append(entry)

    results = [
        {
            "server": m["server"],
            "host": m["host"],
            "path": m["path"],
            "filename": m["filename"],
        }
        for m in matches[:limit]
    ]

    server_counts = {}
    for m in matches:
        s = m["server"]
        server_counts[s] = server_counts.get(s, 0) + 1

    return {
        "total": len(matches),
        "returned": len(results),
        "by_server": server_counts,
        "results": results,
    }
