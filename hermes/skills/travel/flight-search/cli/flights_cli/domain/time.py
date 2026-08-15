from __future__ import annotations

from datetime import datetime


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
