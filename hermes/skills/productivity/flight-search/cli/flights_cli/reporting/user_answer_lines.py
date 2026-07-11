from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from .time_utils import (
    display_minutes_between as minutes_between_iso,
    integer_or_none as int_or_none,
)

AGENT_DISPLAY_STYLE = "canonical_segment_line_v1"


def numeric_or_none(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def iso_date(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    return value[:10]


def catalog_display_date(value: Any) -> str:
    date = iso_date(value)
    if not date:
        return "дата н/д"
    parts = date.split("-")
    if len(parts) == 3:
        return f"{parts[2]}.{parts[1]}"
    return date


def catalog_display_time(value: Any) -> str:
    if not isinstance(value, str) or "T" not in value:
        return "??:??"
    return value.split("T", 1)[1][:5]


def answer_display_time(value: Any) -> str:
    return catalog_display_time(value).replace(":", "")


def catalog_route_code(code: Any) -> str:
    normalized = str(code or "").strip().upper()
    return normalized or "???"


def catalog_time_window(departure_at: Any, arrival_at: Any) -> str:
    departure_date = catalog_display_date(departure_at)
    arrival_date = catalog_display_date(arrival_at)
    departure_time = catalog_display_time(departure_at)
    arrival_time = catalog_display_time(arrival_at)
    if arrival_date != departure_date:
        return f"{departure_date} {departure_time}–{arrival_date} {arrival_time}"
    return f"{departure_date} {departure_time}–{arrival_time}"


def catalog_arrival_date_suffix(departure_at: Any, arrival_at: Any) -> str:
    departure_date = catalog_display_date(departure_at)
    arrival_date = catalog_display_date(arrival_at)
    if arrival_date != departure_date:
        return f" ({arrival_date})"
    return ""


@lru_cache(maxsize=512)
def airport_city_label(code: str | None) -> str:
    normalized = str(code or "").strip().upper()
    if not normalized:
        return "???"
    try:
        from ..store import Store

        store = Store()
        airport = store.airport_by_code.get(normalized)
        city_code = (
            str(airport.get("city_code") or "").upper() if airport else normalized
        )
        city_name = store.city_name(city_code)
        if city_name:
            return city_name
    except Exception:
        return normalized
    return normalized


def terminal_label(value: Any) -> str | None:
    terminal = str(value or "").strip().upper()
    return terminal or None


def agent_endpoint_code_label(code: Any, terminal: Any) -> str:
    normalized = str(code or "").strip().upper()
    if not normalized:
        return "???"
    rendered_terminal = terminal_label(terminal)
    return f"{normalized}({rendered_terminal})" if rendered_terminal else normalized


def answer_endpoint_code_label(code: Any, terminal: Any) -> str:
    normalized = str(code or "").strip().upper()
    if not normalized:
        return "???"
    rendered_terminal = terminal_label(terminal)
    return f"{normalized},{rendered_terminal}" if rendered_terminal else normalized


def agent_endpoint_display_label(segment: dict[str, Any], endpoint: str) -> str:
    if endpoint == "origin":
        code = segment.get("origin")
        terminal = segment.get("departure_terminal")
    else:
        code = segment.get("destination")
        terminal = segment.get("arrival_terminal")
    label = airport_city_label(code)
    code_label = agent_endpoint_code_label(code, terminal)
    if str(label or "").strip().upper() == str(code or "").strip().upper():
        return code_label
    return f"{label} {code_label}"


def answer_endpoint_display_label(
    segment: dict[str, Any], endpoint: str, *, include_code: bool
) -> str:
    if endpoint == "origin":
        code = segment.get("origin")
        terminal = segment.get("departure_terminal")
    else:
        code = segment.get("destination")
        terminal = segment.get("arrival_terminal")
    label = airport_city_label(str(code or ""))
    normalized = str(code or "").strip().upper()
    if not include_code:
        return label
    code_label = answer_endpoint_code_label(code, terminal)
    if str(label or "").strip().upper() == normalized:
        return f"({code_label})"
    return f"{label} ({code_label})"


@lru_cache(maxsize=512)
def aircraft_display_label(code: str | None) -> str | None:
    raw = str(code or "").strip().upper()
    if not raw:
        return None
    if raw == "737" or raw.startswith("73") or raw.startswith("7M"):
        return "B737"
    if raw in {"318", "319", "320", "321"}:
        return f"A{raw}"
    if raw in {"32A", "32B", "32N", "32Q"} or raw.startswith("A32"):
        return "A320"
    if raw.startswith("32") and len(raw) >= 3:
        return f"A{raw[:3]}"
    if raw.startswith("33") and len(raw) >= 3:
        return f"A{raw[:3]}"
    if raw.startswith("35") and len(raw) >= 3:
        return f"A{raw[:3]}"
    return raw


def segment_duration_minutes(segment: dict[str, Any]) -> int | None:
    duration = int_or_none(segment.get("duration_min"))
    if duration is not None:
        return duration
    return minutes_between_iso(segment.get("departure_at"), segment.get("arrival_at"))


def segment_duration_display(segment: dict[str, Any]) -> str:
    duration = segment_duration_minutes(segment)
    if duration is None:
        return "н/д"
    hours, minutes = divmod(duration, 60)
    if hours and minutes:
        return f"{hours}ч {minutes}мин"
    if hours:
        return f"{hours}ч"
    return f"{minutes}мин"


def segment_duration_clock_display(segment: dict[str, Any]) -> str:
    duration = segment_duration_minutes(segment)
    if duration is None:
        return "н/д"
    hours, minutes = divmod(max(0, duration), 60)
    return f"{hours}:{minutes:02d}"


def minutes_display(value: Any) -> str:
    minutes = int_or_none(value)
    if minutes is None:
        return "н/д"
    hours, mins = divmod(max(0, minutes), 60)
    return f"{hours}:{mins:02d}"


def layover_minutes_display(value: Any) -> str:
    minutes = int_or_none(value)
    if minutes is None:
        return "н/д"
    hours, mins = divmod(max(0, minutes), 60)
    if hours and mins:
        return f"{hours}ч {mins:02d}мин"
    if hours:
        return f"{hours}ч"
    return f"{mins}мин"


def catalog_price_for_traveler_line(price: dict[str, Any]) -> str:
    display = str(price.get("display") or "цена н/д").strip()
    display = re.sub(r"\bRUB\b", "руб", display, flags=re.IGNORECASE).replace(
        "₽", "руб"
    )
    return re.sub(r"\s+", " ", display).strip()


def catalog_price_for_agent_display(price: dict[str, Any]) -> str:
    amount = numeric_or_none(price.get("amount"))
    currency = str(price.get("currency") or "").upper()
    if amount is not None:
        rendered = (
            f"{int(amount):,}".replace(",", " ")
            if float(amount).is_integer()
            else str(amount)
        )
        if currency == "RUB":
            return f"{rendered} рублей"
        if currency:
            return f"{rendered} {currency}"
        return rendered
    display = catalog_price_for_traveler_line(price)
    return re.sub(r"\bруб\b", "рублей", display)


def render_catalog_segment_for_traveler(segment: dict[str, Any]) -> str:
    number = segment.get("flight_number") or segment.get("carrier") or "рейс"
    origin = catalog_route_code(segment.get("origin"))
    destination = catalog_route_code(segment.get("destination"))
    time_window = catalog_time_window(
        segment.get("departure_at"), segment.get("arrival_at")
    )
    line = f"{number} {origin}→{destination} {time_window}"
    aircraft = aircraft_display_label(segment.get("aircraft_code"))
    if aircraft:
        line = f"{line} {aircraft}"
    return line


def render_direction_for_catalog(
    segments: list[dict[str, Any]], direction: str
) -> str | None:
    if not segments:
        return None
    flights = [render_catalog_segment_for_traveler(segment) for segment in segments]
    label = "туда" if direction == "outbound" else "обратно"
    return f"{label}: " + " -> ".join(flights)


def render_agent_display_segment(
    segment: dict[str, Any],
) -> str:
    departure_at = segment.get("departure_at")
    arrival_at = segment.get("arrival_at")
    origin = agent_endpoint_display_label(segment, "origin")
    destination = agent_endpoint_display_label(segment, "destination")
    aircraft = aircraft_display_label(segment.get("aircraft_code")) or "н/д"
    duration = segment_duration_display(segment)
    return (
        f"{catalog_display_date(departure_at)} {origin} → {destination} "
        f"{catalog_display_time(departure_at)}–{catalog_display_time(arrival_at)}"
        f"{catalog_arrival_date_suffix(departure_at, arrival_at)} "
        f"борт {aircraft} в пути {duration}"
    )


def render_agent_display_layover(layover: dict[str, Any]) -> str:
    return f"пересадка {minutes_display(layover.get('duration_min'))},"


def render_answer_display_segment(
    segment: dict[str, Any],
    *,
    prefix: str,
    include_origin_code: bool,
) -> str:
    departure_at = segment.get("departure_at")
    arrival_at = segment.get("arrival_at")
    origin = answer_endpoint_display_label(
        segment, "origin", include_code=include_origin_code
    )
    destination = answer_endpoint_display_label(segment, "destination", include_code=True)
    return (
        f"{prefix}{catalog_display_date(departure_at)} {origin}-{destination} "
        f"{answer_display_time(departure_at)} {answer_display_time(arrival_at)}"
        f"{catalog_arrival_date_suffix(departure_at, arrival_at)} "
        f"в пути {segment_duration_clock_display(segment)}"
    )


def self_transfer_warning(item: dict[str, Any]) -> str | None:
    protection = (
        item.get("protection")
        if isinstance(item.get("protection"), dict)
        else {}
    )
    risk = item.get("risk") if isinstance(item.get("risk"), dict) else {}
    has_provider_evidence = bool(
        risk.get("self_transfer_source") or risk.get("self_transfer_note")
    )
    if protection.get("self_transfer") is True and has_provider_evidence:
        return (
            "Самостоятельная пересадка: единый PNR и защита стыковки не подтверждены."
        )
    return None


def answer_display_lines_for_item(item: dict[str, Any]) -> list[str]:
    body_lines: list[str] = []
    directions = (
        item.get("directions") if isinstance(item.get("directions"), dict) else {}
    )
    first_segment = True
    for key in ("outbound", "return"):
        detail = directions.get(key)
        if not isinstance(detail, dict):
            continue
        segments = [
            segment
            for segment in (detail.get("segments") or [])
            if isinstance(segment, dict)
        ]
        layovers = [
            layover
            for layover in (detail.get("layovers") or [])
            if isinstance(layover, dict)
        ]
        for index, segment in enumerate(segments):
            prefix = f"{item.get('number')}. " if first_segment else "   "
            body_lines.append(
                render_answer_display_segment(
                    segment,
                    prefix=prefix,
                    include_origin_code=not first_segment,
                )
            )
            first_segment = False
            if index < len(segments) - 1:
                layover = layovers[index] if index < len(layovers) else {}
                body_lines.append(
                    f"    пересадка {layover_minutes_display(layover.get('duration_min'))}"
                )
    price_line = catalog_price_for_agent_display(
        item["total_price"] if isinstance(item.get("total_price"), dict) else {}
    )
    warning = self_transfer_warning(item)
    if warning:
        price_line = f"{price_line} · {warning}"
    if body_lines:
        return [*body_lines, f"    {price_line}"]
    return [f"{item.get('number')}. вариант без детализации", f"    {price_line}"]


def agent_display_body_lines_for_direction(detail: dict[str, Any]) -> list[str]:
    body_lines: list[str] = []
    segments = [
        segment
        for segment in (detail.get("segments") or [])
        if isinstance(segment, dict)
    ]
    layovers = [
        layover
        for layover in (detail.get("layovers") or [])
        if isinstance(layover, dict)
    ]
    for index, segment in enumerate(segments):
        body_lines.append(render_agent_display_segment(segment))
        if index < len(segments) - 1:
            layover = layovers[index] if index < len(layovers) else {}
            body_lines.append(render_agent_display_layover(layover))
    return body_lines


def agent_display_lines_for_item(item: dict[str, Any]) -> list[str]:
    body_lines: list[str] = []
    directions = (
        item.get("directions") if isinstance(item.get("directions"), dict) else {}
    )
    for key in ("outbound", "return"):
        detail = directions.get(key)
        if not isinstance(detail, dict):
            continue
        body_lines.extend(agent_display_body_lines_for_direction(detail))
    price_line = catalog_price_for_agent_display(
        item["total_price"] if isinstance(item.get("total_price"), dict) else {}
    )
    source_note = next(
        (
            str(caveat)
            for caveat in item.get("caveats") or []
            if str(caveat).startswith("источник:")
        ),
        "",
    )
    if source_note:
        price_line = f"{price_line} · {source_note}"
    warning = self_transfer_warning(item)
    if warning:
        price_line = f"{price_line} · {warning}"
    if body_lines:
        first, *rest = body_lines
        return [
            f"{item.get('number')}. {first}",
            *(f"    {line}" for line in rest),
            f"    {price_line}",
        ]
    return [
        f"{item.get('number')}. вариант без детализации",
        f"    {price_line}",
    ]


def agent_display_contract(item: dict[str, Any]) -> dict[str, Any]:
    lines = agent_display_lines_for_item(item)
    return {
        "style": AGENT_DISPLAY_STYLE,
        "lines": lines,
        "text": "\n".join(lines),
    }


def catalog_segment_count(item: dict[str, Any]) -> int:
    directions = (
        item.get("directions") if isinstance(item.get("directions"), dict) else {}
    )
    total = 0
    for key in ("outbound", "return"):
        detail = directions.get(key)
        if isinstance(detail, dict):
            total += sum(
                1
                for segment in detail.get("segments") or []
                if isinstance(segment, dict)
            )
    return total


def has_agent_display_segment_suffix(line: str) -> bool:
    return bool(
        re.search(
            r"борт (?:\b[A-Z0-9][A-Z0-9-]*|н/д) в пути "
            r"(?:(?:\d+ч(?: \d+мин)?)|(?:\d+мин)|н/д)$",
            line,
        )
    )


def is_agent_display_layover_line(line: str) -> bool:
    return bool(re.fullmatch(r"пересадка (?:\d+:\d{2}|н/д),", str(line).strip()))
