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


def is_night_time(value: str) -> bool:
    hour = airport_hour(value)
    return hour is not None and (hour < 6 or hour >= 23)


def elapsed_minutes(segments: list[dict[str, Any]]) -> int | None:
    if not segments:
        return None
    return minutes_between(str(segments[0].get("departure_at") or ""), str(segments[-1].get("arrival_at") or ""))


def validation_elapsed_minutes(validation: dict[str, Any]) -> int | None:
    journeys = validation.get("journeys")
    if not isinstance(journeys, list):
        return elapsed_minutes(validation["segments"])
    total = 0
    seen = False
    segments_by_index = {segment["index"]: segment for segment in validation["segments"]}
    for journey in journeys:
        indexes = journey.get("segment_indexes") if isinstance(journey, dict) else None
        if not indexes:
            continue
        journey_segments = [segments_by_index[index] for index in indexes if index in segments_by_index]
        elapsed = elapsed_minutes(journey_segments)
        if elapsed is not None:
            total += elapsed
            seen = True
    return total if seen else None
