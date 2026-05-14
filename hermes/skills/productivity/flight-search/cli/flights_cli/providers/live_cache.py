from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from ..config import LIVE_SEARCH_CACHE_DIR


def live_cache_key(provider: str, params: dict[str, Any]) -> str:
    payload = {"provider": provider, "params": params}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def live_cache_path(key: str, cache_dir: Path = LIVE_SEARCH_CACHE_DIR) -> Path:
    return cache_dir / f"{key}.json"


def read_live_cache(key: str, *, ttl_seconds: int, cache_dir: Path = LIVE_SEARCH_CACHE_DIR) -> dict[str, Any] | None:
    if ttl_seconds <= 0:
        return None
    path = live_cache_path(key, cache_dir)
    try:
        stat = path.stat()
    except OSError:
        return None
    age_seconds = max(0, int(time.time() - stat.st_mtime))
    if age_seconds > ttl_seconds:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
        return None
    result = dict(payload["result"])
    result["cache"] = {
        "hit": True,
        "key": key,
        "path": str(path),
        "age_seconds": age_seconds,
        "ttl_seconds": ttl_seconds,
    }
    return result


def write_live_cache(
    key: str,
    result: dict[str, Any],
    *,
    cache_dir: Path = LIVE_SEARCH_CACHE_DIR,
) -> dict[str, Any]:
    cached = dict(result)
    cached.pop("cache", None)
    path = live_cache_path(key, cache_dir)
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"written_at": int(time.time()), "result": cached}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        result["cache"] = {"hit": False, "key": key, "write_error": True}
        return result
    result["cache"] = {"hit": False, "key": key, "path": str(path)}
    return result
