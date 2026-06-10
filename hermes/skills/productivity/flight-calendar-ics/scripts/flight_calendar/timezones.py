"""Timezone catalog helpers for flight-calendar-ics."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import timezone_catalog as airport_catalog
from flight_calendar.envelope import add_step


def load_airport_timezone_document(catalog_path: Path | None = None) -> dict[str, Any]:
    """Load the bundled airport timezone catalog document."""
    return airport_catalog.load_catalog_document(catalog_path)


def load_airport_timezones(catalog_path: Path | None = None) -> dict[str, str]:
    """Load IATA -> IANA timezone data from the bundled airport timezone asset."""
    return airport_catalog.load_airport_timezones(catalog_path)


def build_timezone_map(
    overrides: dict[str, str] | None = None,
    *,
    catalog_path: Path | None = None,
) -> dict[str, str]:
    """Build timezone map: bundled catalog < explicit --tz overrides."""
    return airport_catalog.build_timezone_map(overrides, catalog_path=catalog_path)


def add_timezone_map_step(process: list[dict[str, Any]], catalog_timezones: dict[str, str], overrides_count: int) -> None:
    add_step(
        process,
        "load_timezone_map",
        defaults_count=0,
        catalog_source="skill-bundled-airport-timezones",
        catalog_timezones_count=len(catalog_timezones),
        overrides_count=overrides_count,
    )
