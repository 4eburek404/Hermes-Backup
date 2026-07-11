from __future__ import annotations

from functools import lru_cache
import re
from typing import Any

from ..domain.normalize import numeric_or_none
from .time_utils import integer_or_none as int_or_none


def _iso_date(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    return value[:10]


def catalog_display_date(value: Any) -> str:
    date = _iso_date(value)
    if not date:
        return "дата н/д"
    parts = date.split("-")
    return f"{parts[2]}.{parts[1]}" if len(parts) == 3 else date


def catalog_display_time(value: Any) -> str:
    if not isinstance(value, str) or "T" not in value:
        return "??:??"
    return value.split("T", 1)[1][:5]


def answer_display_time(value: Any) -> str:
    return catalog_display_time(value).replace(":", "")


def catalog_arrival_date_suffix(departure_at: Any, arrival_at: Any) -> str:
    departure_date = catalog_display_date(departure_at)
    arrival_date = catalog_display_date(arrival_at)
    return f" ({arrival_date})" if arrival_date != departure_date else ""


def airport_city_label(code: str | None) -> str:
    normalized = str(code or "").strip().upper()
    return normalized or "???"


def _terminal_label(value: Any) -> str | None:
    terminal = str(value or "").strip().upper()
    return terminal or None


def answer_endpoint_display_label(
    segment: dict[str, Any], endpoint: str, *, include_code: bool
) -> str:
    if endpoint == "origin":
        code = segment.get("origin")
        terminal = segment.get("departure_terminal")
    else:
        code = segment.get("destination")
        terminal = segment.get("arrival_terminal")
    label = str(segment.get(f"{endpoint}_label") or airport_city_label(str(code or "")))
    if not include_code:
        return label
    normalized = str(code or "").strip().upper()
    rendered_terminal = _terminal_label(terminal)
    code_label = (
        f"{normalized},{rendered_terminal}" if rendered_terminal else normalized
    )
    if label.strip().upper() == normalized:
        return f"({code_label})"
    return f"{label} ({code_label})"


@lru_cache(maxsize=512)
def aircraft_display_label(code: str | None) -> str | None:
    raw = str(code or "").strip().upper()
    if not raw:
        return None
    if raw == "737" or raw.startswith(("73", "7M")):
        return "B737"
    if raw in {"318", "319", "320", "321"}:
        return f"A{raw}"
    if raw in {"32A", "32B", "32N", "32Q"} or raw.startswith("A32"):
        return "A320"
    if raw.startswith("32") and len(raw) >= 3:
        return "A320"
    if raw.startswith("33") or raw.startswith("A33"):
        return "A330"
    if raw.startswith("35") or raw.startswith("A35"):
        return "A350"
    if raw.startswith("77") or raw.startswith("B77"):
        return "B777"
    if raw.startswith("78") or raw.startswith("B78"):
        return "B787"
    return raw


def _segment_duration_minutes(segment: dict[str, Any]) -> int | None:
    for key in ("duration_min", "duration"):
        value = int_or_none(segment.get(key))
        if value is not None and value >= 0:
            return value
    return None


def segment_duration_clock_display(segment: dict[str, Any]) -> str:
    value = _segment_duration_minutes(segment)
    if value is None:
        return "н/д"
    return f"{value // 60}:{value % 60:02d}"


def layover_minutes_display(value: Any) -> str:
    minutes = int_or_none(value)
    if minutes is None or minutes < 0:
        return "н/д"
    hours, remainder = divmod(minutes, 60)
    if hours and remainder:
        return f"{hours}ч {remainder}мин"
    if hours:
        return f"{hours}ч"
    return f"{remainder}мин"


def catalog_price_for_answer(price: dict[str, Any]) -> str:
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
    display = str(price.get("display") or "цена н/д")
    return re.sub(r"\bруб\b", "рублей", display)


def render_answer_display_segment(
    segment: dict[str, Any], *, prefix: str, include_origin_code: bool
) -> str:
    departure_at = segment.get("departure_at")
    arrival_at = segment.get("arrival_at")
    origin = answer_endpoint_display_label(
        segment, "origin", include_code=include_origin_code
    )
    destination = answer_endpoint_display_label(
        segment, "destination", include_code=True
    )
    flight_number = str(segment.get("flight_number") or "").strip()
    flight_label = flight_number or "номер рейса не предоставлен"
    return (
        f"{prefix}{flight_label} {catalog_display_date(departure_at)} "
        f"{origin}-{destination} {answer_display_time(departure_at)} "
        f"{answer_display_time(arrival_at)}"
        f"{catalog_arrival_date_suffix(departure_at, arrival_at)} "
        f"в пути {segment_duration_clock_display(segment)}"
    )


def _self_transfer_warning(item: dict[str, Any]) -> str | None:
    protection = (
        item.get("protection") if isinstance(item.get("protection"), dict) else {}
    )
    ticket_protection = (
        item.get("ticket_protection")
        if isinstance(item.get("ticket_protection"), dict)
        else {}
    )
    risk = item.get("risk") if isinstance(item.get("risk"), dict) else {}
    if ticket_protection.get("status") == "unprotected" or (
        protection.get("self_transfer") is True
        and (risk.get("self_transfer_source") or risk.get("self_transfer_note"))
    ):
        return (
            "Отдельные билеты: при задержке первого рейса следующий сегмент не защищён."
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
            for segment in detail.get("segments") or []
            if isinstance(segment, dict)
        ]
        layovers = [
            layover
            for layover in detail.get("layovers") or []
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
    price_line = catalog_price_for_answer(
        item["total_price"] if isinstance(item.get("total_price"), dict) else {}
    )
    warning = _self_transfer_warning(item)
    if warning:
        price_line = f"{price_line} · {warning}"
    if body_lines:
        return [*body_lines, f"    {price_line}"]
    return [f"{item.get('number')}. вариант без детализации", f"    {price_line}"]
