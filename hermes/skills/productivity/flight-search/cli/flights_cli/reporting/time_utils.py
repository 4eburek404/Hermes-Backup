from __future__ import annotations

from datetime import datetime
from typing import Any


def parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def display_minutes_between(start: Any, end: Any) -> int | None:
    first = parse_iso(start)
    second = parse_iso(end)
    if first is None or second is None:
        return None
    if (first.tzinfo is None) != (second.tzinfo is None):
        first = first.replace(tzinfo=None)
        second = second.replace(tzinfo=None)
    return max(0, int((second - first).total_seconds() // 60))


def integer_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
