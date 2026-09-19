#!/usr/bin/env python3
"""Runtime timezone catalog loading with synchronous 15-day refresh."""

from __future__ import annotations

import fcntl
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, NoReturn

from flight_calendar.timezone_catalog_source import (
    CANONICAL_SOURCE_URL,
    CatalogUpdateFailure,
    SCHEMA_VERSION,
    atomic_write_bytes,
    build_catalog_document,
    fetch_source as default_fetch_source,
    serialize_catalog,
    validate_catalog_document,
)

SKILL_DIR = Path(__file__).resolve().parents[2]
CATALOG_PATH = SKILL_DIR / "data" / "airport-timezones.json"
DEFAULT_RUNTIME_CACHE_DIR = Path.home() / ".hermes" / "cache" / "flight-calendar-ics"
RUNTIME_CACHE_FILENAME = "airport-timezones.json"
REFRESH_STATE_FILENAME = "refresh-state.json"
REFRESH_LOCK_FILENAME = "refresh.lock"
REFRESH_INTERVAL = timedelta(days=15)
IATA_RE = re.compile(r"^[A-Z]{3}$")
FetchSource = Callable[[str], bytes]


def parse_tz_overrides(items: list[str]) -> dict[str, str]:
    """Parse repeated CODE=Area/City timezone overrides."""
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            _reject_timezone_override(item)
        code, tzid = item.split("=", 1)
        code = code.strip().upper()
        tzid = tzid.strip()
        if not code or not tzid:
            _reject_timezone_override(item)
        out[code] = tzid
    return out


def _reject_timezone_override(item: str) -> NoReturn:
    raise ValueError(f"bad --tz value {item!r}; use CODE=Area/City")


def _normalize_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_timezone(value: Any) -> str:
    return str(value or "").strip()


def _looks_like_iata_timezone(code: str, timezone_value: str) -> bool:
    return bool(
        IATA_RE.fullmatch(code)
        and "/" in timezone_value
        and not timezone_value.startswith("/")
    )


def load_catalog_document(catalog_path: Path | None = None) -> dict[str, Any]:
    path = catalog_path or CATALOG_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    try:
        validate_catalog_document(data)
    except CatalogUpdateFailure as exc:
        raise ValueError(f"{path}: {exc}") from exc
    return data


def _load_catalog_map(path: Path) -> dict[str, str]:
    document = load_catalog_document(path)
    timezones: dict[str, str] = {}
    for code, timezone_value in document["timezones"].items():
        norm_code = _normalize_code(code)
        norm_tz = _normalize_timezone(timezone_value)
        if _looks_like_iata_timezone(norm_code, norm_tz):
            timezones[norm_code] = norm_tz
    return timezones


def _runtime_cache_dir() -> Path:
    override = os.environ.get("FLIGHT_CALENDAR_CACHE_DIR")
    if override and override.strip():
        return Path(override).expanduser()
    return DEFAULT_RUNTIME_CACHE_DIR


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _read_last_success(path: Path) -> datetime | None:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(state, dict):
        return None
    return _parse_timestamp(state.get("last_success"))


def _catalog_is_fresh(path: Path, now: datetime) -> bool:
    last_success = _read_last_success(path)
    if last_success is None:
        return False
    return now.astimezone(timezone.utc) - last_success < REFRESH_INTERVAL


def _write_success_state(path: Path, now: datetime) -> None:
    atomic_write_bytes(
        path,
        (
            json.dumps(
                {"last_success": now.astimezone(timezone.utc).isoformat()},
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
    )


@contextmanager
def _refresh_critical_section(cache_dir: Path) -> Iterator[None]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    lock_path = cache_dir / REFRESH_LOCK_FILENAME
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _try_load_fallback(cache_path: Path, bundled_path: Path) -> dict[str, str]:
    for path in (cache_path, bundled_path):
        try:
            return _load_catalog_map(path)
        except (OSError, ValueError, TypeError, KeyError):
            continue
    raise ValueError("no valid runtime or bundled timezone catalog is available")


def _load_runtime_catalog(
    *,
    runtime_cache_dir: Path,
    bundled_catalog_path: Path,
    fetch_source: FetchSource,
    now: datetime,
) -> dict[str, str]:
    cache_path = runtime_cache_dir / RUNTIME_CACHE_FILENAME
    state_path = runtime_cache_dir / REFRESH_STATE_FILENAME
    try:
        cached = _load_catalog_map(cache_path)
    except (OSError, ValueError, TypeError, KeyError):
        cached = None
    try:
        bundled = _load_catalog_map(bundled_catalog_path)
    except (OSError, ValueError, TypeError, KeyError):
        bundled = None

    if cached is None and bundled is not None:
        return bundled
    if cached is not None and _catalog_is_fresh(state_path, now):
        return cached

    try:
        with _refresh_critical_section(runtime_cache_dir):
            try:
                cached = _load_catalog_map(cache_path)
            except (OSError, ValueError, TypeError, KeyError):
                cached = None
            try:
                bundled = _load_catalog_map(bundled_catalog_path)
            except (OSError, ValueError, TypeError, KeyError):
                bundled = None
            if cached is None and bundled is not None:
                return bundled
            if cached is not None and _catalog_is_fresh(state_path, now):
                return cached

            raw = fetch_source(CANONICAL_SOURCE_URL)
            document = build_catalog_document(raw, url=CANONICAL_SOURCE_URL)
            candidate_bytes = serialize_catalog(document)
            atomic_write_bytes(cache_path, candidate_bytes)
            _write_success_state(state_path, now)
            return {
                code: timezone_value
                for code, timezone_value in document["timezones"].items()
                if _looks_like_iata_timezone(code, timezone_value)
            }
    except Exception:
        return _try_load_fallback(cache_path, bundled_catalog_path)


def load_airport_timezones(
    catalog_path: Path | None = None,
    *,
    runtime_cache_dir: Path | None = None,
    bundled_catalog_path: Path | None = None,
    fetch_source: FetchSource = default_fetch_source,
    now: datetime | None = None,
) -> dict[str, str]:
    """Load an explicit catalog or refresh/select the runtime catalog."""
    if catalog_path is not None:
        return _load_catalog_map(catalog_path)
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return _load_runtime_catalog(
        runtime_cache_dir=runtime_cache_dir or _runtime_cache_dir(),
        bundled_catalog_path=bundled_catalog_path or CATALOG_PATH,
        fetch_source=fetch_source,
        now=current_time,
    )


def build_timezone_map(
    overrides: dict[str, str] | None = None, *, catalog_path: Path | None = None
) -> dict[str, str]:
    """Build timezone map: runtime/bundled catalog < explicit overrides."""
    timezone_map = load_airport_timezones(catalog_path)
    for code, timezone_value in (overrides or {}).items():
        norm_code = _normalize_code(code)
        norm_tz = _normalize_timezone(timezone_value)
        if norm_code and norm_tz:
            timezone_map[norm_code] = norm_tz
    return timezone_map
