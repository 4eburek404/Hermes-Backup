from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .. import __version__
from ..config import ROUTE_INTEL_CACHE_DIR, SVX_OFFICIAL_ARRIVAL_SCHEDULE_URL, SVX_OFFICIAL_SCHEDULE_URL
from ..errors import CliError
from .static_catalog import atomic_write_bytes, canonical_json_bytes

SVX_ROUTE_INDEX_SCHEMA_VERSION = "svx-official-route-index-v1"
SVX_ROUTE_INDEX_FILENAME = "svx_official_route_index.json"
AIRPORT_CELL_RE = re.compile(r"<td[^>]*>\s*([A-Z]{3})\s*</td>", re.IGNORECASE)

FetchText = Callable[[str, int], str]


def default_fetch_text(url: str, timeout: int) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": f"flights-cli/{__version__}",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        raise CliError(f"SVX official schedule HTTP {exc.code}: {body}", error_type="upstream_error") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise CliError(f"SVX official schedule request failed: {type(exc).__name__}", error_type="upstream_error") from exc


def svx_route_index_path(cache_dir: Path = ROUTE_INTEL_CACHE_DIR) -> Path:
    return cache_dir / SVX_ROUTE_INDEX_FILENAME


def parse_svx_schedule_airport_codes(html: str, *, known_airports: set[str] | None = None) -> list[str]:
    codes = {
        match.group(1).upper()
        for match in AIRPORT_CELL_RE.finditer(html)
    }
    if known_airports is not None:
        codes &= {code.upper() for code in known_airports}
    return sorted(codes)


def build_svx_route_index(
    *,
    outbound_html: str,
    return_html: str,
    known_airports: set[str] | None = None,
    fetched_at: datetime | None = None,
) -> dict[str, Any]:
    timestamp = (fetched_at or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    outbound = parse_svx_schedule_airport_codes(outbound_html, known_airports=known_airports)
    inbound = parse_svx_schedule_airport_codes(return_html, known_airports=known_airports)
    content_digest = hashlib.sha256((outbound_html + "\n" + return_html).encode("utf-8")).hexdigest()
    return {
        "schema_version": SVX_ROUTE_INDEX_SCHEMA_VERSION,
        "source": "Koltsovo official seasonal schedule",
        "airport": "SVX",
        "fetched_at": timestamp,
        "source_urls": {
            "outbound": SVX_OFFICIAL_SCHEDULE_URL,
            "return": SVX_OFFICIAL_ARRIVAL_SCHEDULE_URL,
        },
        "routes": {
            "outbound": outbound,
            "return": inbound,
        },
        "route_count": {
            "outbound": len(outbound),
            "return": len(inbound),
        },
        "content_sha256": content_digest,
    }


def read_svx_route_index(
    *,
    ttl_seconds: int,
    cache_dir: Path = ROUTE_INTEL_CACHE_DIR,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    if ttl_seconds <= 0:
        return None
    path = svx_route_index_path(cache_dir)
    try:
        stat = path.stat()
    except OSError:
        return None
    age_seconds = max(0, int(time.time() - stat.st_mtime))
    if age_seconds > ttl_seconds:
        return None
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(index, dict) or index.get("schema_version") != SVX_ROUTE_INDEX_SCHEMA_VERSION:
        return None
    return index, {
        "hit": True,
        "path": str(path),
        "age_seconds": age_seconds,
        "ttl_seconds": ttl_seconds,
    }


def write_svx_route_index(index: dict[str, Any], *, cache_dir: Path = ROUTE_INTEL_CACHE_DIR) -> dict[str, Any]:
    path = svx_route_index_path(cache_dir)
    atomic_write_bytes(path, canonical_json_bytes(index))
    return {
        "hit": False,
        "path": str(path),
        "age_seconds": 0,
    }


def load_or_refresh_svx_route_index(
    *,
    ttl_seconds: int,
    timeout: int,
    known_airports: set[str] | None = None,
    cache_dir: Path = ROUTE_INTEL_CACHE_DIR,
    fetch_text: FetchText = default_fetch_text,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cached = read_svx_route_index(ttl_seconds=ttl_seconds, cache_dir=cache_dir)
    if cached is not None:
        return cached
    outbound_html = fetch_text(SVX_OFFICIAL_SCHEDULE_URL, timeout)
    return_html = fetch_text(SVX_OFFICIAL_ARRIVAL_SCHEDULE_URL, timeout)
    index = build_svx_route_index(
        outbound_html=outbound_html,
        return_html=return_html,
        known_airports=known_airports,
        fetched_at=now,
    )
    cache = write_svx_route_index(index, cache_dir=cache_dir)
    cache["ttl_seconds"] = ttl_seconds
    return index, cache


def svx_direct_route_index_summary(index: dict[str, Any], cache: dict[str, Any]) -> dict[str, Any]:
    routes = index.get("routes") if isinstance(index.get("routes"), dict) else {}
    return {
        "enabled": True,
        "available": True,
        "source": index.get("source"),
        "airport": index.get("airport"),
        "source_urls": index.get("source_urls") or {},
        "fetched_at": index.get("fetched_at"),
        "cache": cache,
        "route_count": {
            "outbound": len(routes.get("outbound") or []),
            "return": len(routes.get("return") or []),
        },
        "negative_filter": "Only exact SVX direct-control probes are skipped when the airport is absent from the official seasonal schedule.",
    }
