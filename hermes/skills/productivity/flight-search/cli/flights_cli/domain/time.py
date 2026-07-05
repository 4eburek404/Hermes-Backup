from __future__ import annotations

from datetime import datetime
from typing import Any


def parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    raw = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def minutes_between(start: str, end: str) -> int | None:
    a = parse_iso_datetime(start)
    b = parse_iso_datetime(end)
    if not a or not b:
        return None
    if (a.tzinfo is None) != (b.tzinfo is None):
        a = a.replace(tzinfo=None)
        b = b.replace(tzinfo=None)
    return int((b - a).total_seconds() // 60)


def airport_hour(value: str) -> int | None:
    parsed = parse_iso_datetime(value)
    return parsed.hour if parsed else None


def elapsed_minutes(segments: list[dict[str, Any]]) -> int | None:
    if not segments:
        return None
    return minutes_between(
        str(segments[0].get("departure_at") or ""),
        str(segments[-1].get("arrival_at") or ""),
    )
