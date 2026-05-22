from __future__ import annotations

from datetime import datetime
from typing import Any

MONTH_CODES = [
    "",
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
]

SUMMARY_ONLY_DETAIL_FALLBACK = "Подробности рейсов не включены в краткий отчёт."


def parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def minutes_between(start: Any, end: Any) -> int | None:
    dep = parse_iso(start)
    arr = parse_iso(end)
    if not dep or not arr:
        return None
    if (dep.tzinfo is None) != (arr.tzinfo is None):
        dep = dep.replace(tzinfo=None)
        arr = arr.replace(tzinfo=None)
    return max(0, int((arr - dep).total_seconds() // 60))


def display_time(value: Any) -> str:
    dt = parse_iso(value)
    return dt.strftime("%H:%M") if dt else "??:??"


def display_date(value: Any) -> str:
    dt = parse_iso(value)
    if not dt:
        return "??MON"
    return f"{dt.day:02d}{MONTH_CODES[dt.month]}"


def display_duration(minutes: Any) -> str:
    if minutes is None:
        return "?:??"
    try:
        value = int(minutes)
    except (TypeError, ValueError):
        return "?:??"
    hours, mins = divmod(max(0, value), 60)
    return f"{hours}:{mins:02d}"


def integer_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class PlaceLookup:

    def __init__(self, store: Any | None = None):
        self.store = store
        self.airports = self._load_by_code("airports_ru.json")
        self.cities = self._load_by_code("cities_ru.json")

    def _load_by_code(self, filename: str) -> dict[str, dict[str, Any]]:
        if self.store is None:
            return {}
        try:
            items = self.store.load_json(filename)
        except Exception:
            return {}
        return {str(item.get("code") or "").upper(): item for item in items if item.get("code")}

    def place_name(self, code: Any) -> str:
        normalized = str(code or "").upper()
        if not normalized:
            return "???"
        airport = self.airports.get(normalized)
        if airport:
            city_code = str(airport.get("city_code") or "").upper()
            city = self.cities.get(city_code)
            if city_code == normalized and city and city.get("name"):
                return str(city["name"])
            if airport.get("name"):
                return str(airport["name"])
        city = self.cities.get(normalized)
        if city and city.get("name"):
            return str(city["name"])
        return normalized


def segment_duration(segment: dict[str, Any]) -> int | None:
    for key in ("duration_min", "duration"):
        if segment.get(key) is None:
            continue
        try:
            return int(float(segment[key]))
        except (TypeError, ValueError):
            continue
    return minutes_between(segment.get("departure_at"), segment.get("arrival_at"))


def render_segment_line(segment: dict[str, Any], places: PlaceLookup) -> str:
    flight = str(segment.get("flight_number") or segment.get("carrier") or "flight").replace(" ", "")
    origin = places.place_name(segment.get("origin"))
    destination = places.place_name(segment.get("destination"))
    aircraft = str(segment.get("aircraft_code") or segment.get("aircraft") or "н/д")
    return (
        f"{flight} {display_date(segment.get('departure_at'))} "
        f"{origin} - {destination} "
        f"{display_time(segment.get('departure_at'))} - {display_time(segment.get('arrival_at'))} "
        f"борт {aircraft} в полете {display_duration(segment_duration(segment))}"
    )


def render_connection_line(previous: dict[str, Any], next_segment: dict[str, Any], places: PlaceLookup) -> str:
    airport = previous.get("destination") or next_segment.get("origin")
    duration = minutes_between(previous.get("arrival_at"), next_segment.get("departure_at"))
    return f"пересадка {places.place_name(airport)} {display_duration(duration)}"


def direction_label(direction: Any) -> str:
    value = str(direction or "").lower()
    if value == "outbound":
        return "туда"
    if value == "return":
        return "обратно"
    return "маршрут"


def segment_groups(segments: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    current_direction: str | None = None
    current_segments: list[dict[str, Any]] = []
    for segment in segments:
        direction = str(segment.get("direction") or "")
        if current_segments and direction and current_direction and direction != current_direction:
            groups.append((current_direction, current_segments))
            current_segments = []
        current_direction = direction or current_direction or ""
        current_segments.append(segment)
    if current_segments:
        groups.append((current_direction or "", current_segments))
    return groups


def group_elapsed(segments: list[dict[str, Any]]) -> int | None:
    if not segments:
        return None
    return minutes_between(segments[0].get("departure_at"), segments[-1].get("arrival_at"))


def render_group_lines(segments: list[dict[str, Any]], places: PlaceLookup) -> list[str]:
    lines: list[str] = []
    for index, segment in enumerate(segments):
        if index:
            lines.append(render_connection_line(segments[index - 1], segment, places))
        lines.append(render_segment_line(segment, places))
    return lines


def summary_elapsed_text(option: dict[str, Any]) -> str:
    for key in ("itinerary_elapsed_min", "elapsed_min"):
        minutes = integer_or_none(option.get(key))
        if minutes is not None:
            return display_duration(minutes)
    elapsed = str(option.get("elapsed") or "").strip()
    if elapsed:
        return elapsed
    directional_parts: list[str] = []
    for key, label in (("outbound_time", "туда"), ("return_time", "обратно")):
        value = option.get(key)
        if not isinstance(value, dict):
            continue
        minutes = integer_or_none(value.get("itinerary_elapsed_min"))
        if minutes is None:
            minutes = integer_or_none(value.get("flight_time_min"))
        if minutes is not None:
            directional_parts.append(f"{label} {display_duration(minutes)}")
    return "; ".join(directional_parts) if directional_parts else "?:??"


def summary_connection_count(option: dict[str, Any]) -> int | None:
    for key in ("max_connections_per_journey", "connection_count"):
        value = integer_or_none(option.get(key))
        if value is not None:
            return max(0, value)
    connections = option.get("connections")
    if isinstance(connections, list) and connections:
        return len(connections)
    return None


def summary_only_option_display(option: dict[str, Any]) -> dict[str, Any]:
    elapsed = summary_elapsed_text(option)
    connection_count = summary_connection_count(option)
    header_parts = [str(option.get("price_text") or "price n/a")]
    if elapsed != "?:??":
        header_parts.append(f"всего {elapsed}")
    if connection_count is not None:
        header_parts.append(f"пересадок {connection_count}")
    header = " | ".join(header_parts)
    lines = [SUMMARY_ONLY_DETAIL_FALLBACK]
    return {
        "id": option.get("id"),
        "category": option.get("category"),
        "price_text": str(option.get("price_text") or "price n/a"),
        "total_elapsed": elapsed,
        "connection_count": connection_count if connection_count is not None else 0,
        "lines": lines,
        "text": "\n".join([header] + lines),
    }


def option_display(option: dict[str, Any], places: PlaceLookup) -> dict[str, Any] | None:
    if option.get("detail_status") == "summary_only":
        return summary_only_option_display(option)
    segments = [segment for segment in option.get("segments") or [] if isinstance(segment, dict)]
    if not segments:
        return None
    groups = segment_groups(segments)
    lines: list[str] = []
    elapsed_parts: list[str] = []
    connection_count = 0
    multiple_groups = len(groups) > 1
    for direction, group_segments in groups:
        elapsed = group_elapsed(group_segments)
        connections = max(0, len(group_segments) - 1)
        connection_count += connections
        label = direction_label(direction)
        elapsed_label = display_duration(elapsed)
        elapsed_parts.append(f"{label} {elapsed_label}" if multiple_groups else elapsed_label)
        if multiple_groups:
            lines.append(f"{label}: всего {elapsed_label}, пересадок {connections}")
        lines.extend(render_group_lines(group_segments, places))
    total_elapsed = "; ".join(elapsed_parts)
    header = f"{option.get('price_text') or 'price n/a'} | всего {total_elapsed} | пересадок {connection_count}"
    text = "\n".join([header] + lines)
    return {
        "id": option.get("id"),
        "category": option.get("category"),
        "price_text": str(option.get("price_text") or "price n/a"),
        "total_elapsed": total_elapsed,
        "connection_count": connection_count,
        "lines": lines,
        "text": text,
    }


def build_flight_display(report: dict[str, Any], store: Any | None = None, *, limit: int = 5) -> dict[str, Any]:
    places = PlaceLookup(store)
    candidates = []
    for option in (report.get("recommended_options") or []) + (report.get("priority_options") or []):
        if isinstance(option, dict):
            rendered = option_display(option, places)
            if rendered is not None:
                candidates.append(rendered)
        if len(candidates) >= limit:
            break
    return {
        "format_version": "flight_display.v1",
        "text": "\n\n".join(item["text"] for item in candidates),
        "options": candidates,
    }


def sanitize_summary_only_display(report: dict[str, Any]) -> None:
    display = report.get("display")
    if not isinstance(display, dict):
        return
    display_options = display.get("options")
    if not isinstance(display_options, list):
        return
    summary_options = {
        option.get("id"): option
        for option in (report.get("recommended_options") or []) + (report.get("priority_options") or [])
        if isinstance(option, dict) and option.get("detail_status") == "summary_only"
    }
    if not summary_options:
        return
    changed = False
    sanitized_options: list[Any] = []
    for display_option in display_options:
        if isinstance(display_option, dict) and display_option.get("id") in summary_options:
            sanitized_options.append(summary_only_option_display(summary_options[display_option.get("id")]))
            changed = True
        else:
            sanitized_options.append(display_option)
    if not changed:
        return
    display["options"] = sanitized_options
    display["text"] = "\n\n".join(str(option.get("text") or "") for option in sanitized_options if isinstance(option, dict))
