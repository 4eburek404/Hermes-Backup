from __future__ import annotations

from typing import Any

CACHE_STATUS_LIVE = "live"
CACHE_STATUS_HIT = "cache_hit"
CACHE_STATUS_STALE = "stale_cache_used"
CACHE_STATUS_DISABLED = "disabled"
CACHE_STATUS_UNKNOWN = "unknown"


def cache_status_from_metadata(cache: Any) -> str:
    if not isinstance(cache, dict):
        return CACHE_STATUS_UNKNOWN
    if cache.get("disabled") is True:
        return CACHE_STATUS_DISABLED
    if cache.get("stale") is True or cache.get("stale_used") is True:
        return CACHE_STATUS_STALE
    if cache.get("hit") is True:
        return CACHE_STATUS_HIT
    if cache.get("hit") is False:
        return CACHE_STATUS_LIVE
    return CACHE_STATUS_UNKNOWN


def cache_status_from_result(result: dict[str, Any] | None) -> str:
    if not isinstance(result, dict):
        return CACHE_STATUS_UNKNOWN
    return cache_status_from_metadata(result.get("cache"))
