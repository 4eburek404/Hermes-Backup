#!/usr/bin/env python3
"""Runtime support for the bundled flight-calendar-ics timezone catalog.

The bundled asset is a compact derived catalog with a single field needed for
calendar correctness: IATA airport code -> IANA timezone. It is not a copy of
any full airport reference dictionary; only ``code -> time_zone`` is retained.
Catalog generation and updates live in ``scripts/update_airport_timezones.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, NoReturn

SCHEMA_VERSION = "airport-timezones.v1"
SKILL_DIR = Path(__file__).resolve().parents[2]
CATALOG_PATH = SKILL_DIR / "data" / "airport-timezones.json"
IATA_RE = re.compile(r"^[A-Z0-9]{3}$")


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


def _looks_like_iata_timezone(code: str, timezone: str) -> bool:
    return bool(
        IATA_RE.fullmatch(code) and "/" in timezone and not timezone.startswith("/")
    )


def load_catalog_document(catalog_path: Path | None = None) -> dict[str, Any]:
    path = catalog_path or CATALOG_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"{path} has unsupported schema_version {data.get('schema_version')!r}"
        )
    timezones = data.get("timezones")
    if not isinstance(timezones, dict):
        raise ValueError(f"{path} has no timezones object")
    return data


def load_airport_timezones(catalog_path: Path | None = None) -> dict[str, str]:
    document = load_catalog_document(catalog_path)
    timezones: dict[str, str] = {}
    for code, timezone in document["timezones"].items():
        norm_code = _normalize_code(code)
        norm_tz = _normalize_timezone(timezone)
        if _looks_like_iata_timezone(norm_code, norm_tz):
            timezones[norm_code] = norm_tz
    return timezones


def build_timezone_map(
    overrides: dict[str, str] | None = None, *, catalog_path: Path | None = None
) -> dict[str, str]:
    """Build timezone map: bundled catalog < explicit runtime overrides."""
    timezone_map = load_airport_timezones(catalog_path)
    for code, timezone in (overrides or {}).items():
        norm_code = _normalize_code(code)
        norm_tz = _normalize_timezone(timezone)
        if norm_code and norm_tz:
            timezone_map[norm_code] = norm_tz
    return timezone_map
