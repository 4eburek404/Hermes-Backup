from __future__ import annotations

from typing import Any, Mapping


def route_requested_round_trip(route: Mapping[str, Any] | None) -> bool:
    route_map = route if isinstance(route, Mapping) else {}
    dates = route_map.get("dates")
    if not isinstance(dates, dict):
        dates = {}
    return bool(dates.get("return") or dates.get("return_date"))


def report_requested_round_trip(report: Mapping[str, Any] | None) -> bool:
    report_map = report if isinstance(report, Mapping) else {}
    route = report_map.get("route")
    return route_requested_round_trip(route)


def option_direction(option: Mapping[str, Any] | None) -> str | None:
    option_map = option if isinstance(option, Mapping) else {}
    explicit = option_map.get("direction")
    if explicit in ("outbound", "return"):
        return str(explicit)
    option_id = str(option_map.get("id") or "")
    if option_id.startswith("provider-aggregate:outbound:"):
        return "outbound"
    if option_id.startswith("provider-aggregate:return:"):
        return "return"
    raw_segments = option_map.get("segments")
    segments = raw_segments if isinstance(raw_segments, list) else []
    directions = {
        str(segment.get("direction"))
        for segment in segments
        if isinstance(segment, dict) and segment.get("direction")
    }
    if len(directions) == 1:
        only = next(iter(directions))
        if only in ("outbound", "return"):
            return only
    return None


def direction_segments(
    option: Mapping[str, Any] | None, direction: str
) -> list[dict[str, Any]]:
    option_map = option if isinstance(option, Mapping) else {}
    return [
        segment
        for segment in option_map.get("segments") or []
        if isinstance(segment, dict)
        and str(segment.get("direction") or "") == direction
    ]
