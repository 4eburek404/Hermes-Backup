from __future__ import annotations

import re
from datetime import datetime
from typing import Any

HUMAN_ANSWER_FORMAT_VERSION = "flight_human_answer.v1"

MONTH_NAMES_SHORT = [
    "",
    "янв",
    "фев",
    "мар",
    "апр",
    "май",
    "июн",
    "июл",
    "авг",
    "сен",
    "окт",
    "ноя",
    "дек",
]

DIAGNOSTIC_MARKERS = (
    "agent report:",
    "best cli-ranked option",
    "coverage diagnostics",
    "coverage_diagnostics",
    "provider_aggregate_candidate",
    "provider-aggregate:",
    "probe_id",
)


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
    if dep is None or arr is None:
        return None
    if (dep.tzinfo is None) != (arr.tzinfo is None):
        dep = dep.replace(tzinfo=None)
        arr = arr.replace(tzinfo=None)
    return max(0, int((arr - dep).total_seconds() // 60))


def integer_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def human_duration(minutes: Any) -> str | None:
    value = integer_or_none(minutes)
    if value is None:
        return None
    hours, mins = divmod(max(0, value), 60)
    if hours and mins:
        return f"{hours}ч{mins:02d}"
    if hours:
        return f"{hours}ч"
    return f"{mins}м"


def human_date(value: Any) -> str:
    dt = parse_iso(value)
    if dt is None:
        return "?? ???"
    return f"{dt.day:02d} {MONTH_NAMES_SHORT[dt.month]}"


def human_time(value: Any) -> str:
    dt = parse_iso(value)
    return dt.strftime("%H:%M") if dt else "??:??"


def day_offset_label(start: Any, end: Any) -> str:
    dep = parse_iso(start)
    arr = parse_iso(end)
    if dep is None or arr is None:
        return ""
    offset = arr.date().toordinal() - dep.date().toordinal()
    return f" +{offset}" if offset > 0 else ""


def human_price(option: dict[str, Any]) -> str:
    price = option.get("price") if isinstance(option.get("price"), dict) else {}
    amount = price.get("amount")
    currency = str(price.get("currency") or "").upper()
    if amount is not None:
        try:
            number = int(float(amount))
            rendered = f"{number:,}".replace(",", " ")
        except (TypeError, ValueError):
            rendered = str(amount)
        if currency == "RUB":
            return f"{rendered} ₽"
        if currency:
            return f"{rendered} {currency}"
        return rendered

    raw = str(option.get("price_text") or "").strip()
    if not raw:
        return "цена н/д"
    normalized = re.sub(r"\bRUB\b", "₽", raw, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", normalized).strip()


def option_direction(option: dict[str, Any]) -> str | None:
    explicit = option.get("direction")
    if explicit in ("outbound", "return"):
        return str(explicit)
    option_id = str(option.get("id") or "")
    if option_id.startswith("provider-aggregate:outbound:"):
        return "outbound"
    if option_id.startswith("provider-aggregate:return:"):
        return "return"
    directions = {
        str(segment.get("direction"))
        for segment in option.get("segments") or []
        if isinstance(segment, dict) and segment.get("direction") in ("outbound", "return")
    }
    return next(iter(directions)) if len(directions) == 1 else None


def requested_round_trip(report: dict[str, Any]) -> bool:
    route = report.get("route") if isinstance(report.get("route"), dict) else {}
    dates = route.get("dates") if isinstance(route.get("dates"), dict) else {}
    return bool(dates.get("return") or dates.get("return_date"))


def route_text(report: dict[str, Any]) -> str:
    route = report.get("route") if isinstance(report.get("route"), dict) else {}
    origin = route.get("origin") or "???"
    destination = route.get("destination") or "???"
    return f"{origin}→{destination}"


def valid_option(option: Any) -> bool:
    if not isinstance(option, dict):
        return False
    if option.get("ok") is False:
        return False
    risk = option.get("risk") if isinstance(option.get("risk"), dict) else {}
    if risk.get("reject") is True:
        return False
    return True


def reportable_options(options: Any) -> list[dict[str, Any]]:
    return [option for option in options or [] if valid_option(option)]


def direction_segments(option: dict[str, Any], direction: str) -> list[dict[str, Any]]:
    return [
        segment
        for segment in option.get("segments") or []
        if isinstance(segment, dict) and str(segment.get("direction") or "") == direction
    ]


def first_last_segments(segments: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not segments:
        return None, None
    return segments[0], segments[-1]


def flight_numbers(segments: list[dict[str, Any]]) -> str:
    values = []
    for segment in segments:
        number = str(segment.get("flight_number") or segment.get("carrier") or "рейс").replace(" ", "").strip()
        if number:
            values.append(number)
    return "→".join(values) if values else "рейсы н/д"


def segment_time_label(segment: dict[str, Any], *, base_departure_at: Any = None) -> str:
    number = str(segment.get("flight_number") or segment.get("carrier") or "рейс").replace(" ", "").strip() or "рейс"
    departure = segment.get("departure_at")
    arrival = segment.get("arrival_at")
    dep_dt = parse_iso(departure)
    base_dt = parse_iso(base_departure_at)
    date_prefix = ""
    if dep_dt is not None and base_dt is not None and dep_dt.date() != base_dt.date():
        date_prefix = f"{human_date(departure)} "
    return f"{number} {date_prefix}{human_time(departure)}–{human_time(arrival)}{day_offset_label(departure, arrival)}"


def flight_time_sequence(segments: list[dict[str, Any]]) -> str:
    base_departure_at = segments[0].get("departure_at") if segments else None
    values = [segment_time_label(segment, base_departure_at=base_departure_at) for segment in segments]
    return " → ".join(values) if values else "рейсы н/д"


def connection_labels(segments: list[dict[str, Any]]) -> list[str]:
    labels = []
    for previous, current in zip(segments, segments[1:]):
        airport = previous.get("destination") or current.get("origin") or "???"
        duration = human_duration(minutes_between(previous.get("arrival_at"), current.get("departure_at")))
        if duration:
            labels.append(f"{airport} {duration}")
    return labels


def itinerary_elapsed(option: dict[str, Any], direction: str, segments: list[dict[str, Any]]) -> int | None:
    key = "outbound_time" if direction == "outbound" else "return_time"
    value = option.get(key)
    if isinstance(value, dict):
        minutes = integer_or_none(value.get("itinerary_elapsed_min"))
        if minutes is not None:
            return minutes
    first, last = first_last_segments(segments)
    if first and last:
        return minutes_between(first.get("departure_at"), last.get("arrival_at"))
    return integer_or_none(option.get("itinerary_elapsed_min") or option.get("elapsed_min"))


def has_long_layover(segments: list[dict[str, Any]]) -> bool:
    return any((minutes_between(prev.get("arrival_at"), cur.get("departure_at")) or 0) >= 8 * 60 for prev, cur in zip(segments, segments[1:]))


def direction_line(option: dict[str, Any], direction: str, *, label: str | None = None) -> str | None:
    segments = direction_segments(option, direction)
    if not segments:
        summary = str(option.get("user_facing_label") or option.get("label") or "").strip()
        if summary:
            return summary
        return None
    first, last = first_last_segments(segments)
    if first is None or last is None:
        return None
    connections = connection_labels(segments)
    connection_text = "; ".join(connections) if connections else "без пересадки"
    elapsed_text = human_duration(itinerary_elapsed(option, direction, segments)) or "время н/д"
    prefix = f"{label}: " if label else ""
    parts = [
        f"{prefix}{flight_time_sequence(segments)}",
        human_date(first.get("departure_at")),
        connection_text,
        f"всего {elapsed_text}",
        human_price(option),
    ]
    if has_long_layover(segments):
        parts.append("длинная стыковка")
    return " | ".join(parts)


def primary_lines(option: dict[str, Any], *, is_round_trip: bool) -> list[str]:
    if is_round_trip:
        lines = []
        outbound = direction_line(option, "outbound", label="Туда")
        inbound = direction_line(option, "return", label="Обратно")
        if outbound:
            lines.append(outbound)
        if inbound:
            lines.append(inbound)
        return lines
    line = direction_line(option, option_direction(option) or "outbound")
    return [line] if line else []


def alternative_lines(options: list[dict[str, Any]], direction: str, *, limit: int = 4) -> list[str]:
    lines = []
    for option in options:
        if option_direction(option) != direction:
            continue
        line = direction_line(option, direction)
        if not line:
            continue
        if line not in lines:
            lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def section(title: str, lines: list[str]) -> dict[str, Any]:
    return {"title": title, "lines": lines}


def verification_lines(report: dict[str, Any]) -> list[str]:
    lines = []
    through_fare_checks = report.get("through_fare_checks") if isinstance(report.get("through_fare_checks"), list) else []
    options = reportable_options(report.get("recommended_options")) + reportable_options(report.get("priority_options"))
    ticketing_models = {str(option.get("ticketing_model") or "separate_segments") for option in options}
    if through_fare_checks or any(model != "single_ticket_proven" for model in ticketing_models):
        lines.append("single PNR/багаж не доказаны — проверить на booking screen.")
    else:
        lines.append("проверить финальную цену, тариф и правила обмена/возврата на booking screen.")
    if report.get("provider_failures"):
        lines.append("часть live-проверок упала — если это влияет на выбор, повторить поиск перед покупкой.")
    return lines


def clean_text(text: str) -> str:
    cleaned = text
    for marker in DIAGNOSTIC_MARKERS:
        cleaned = cleaned.replace(marker, "")
    return cleaned.strip()


def build_human_answer(agent_report: dict[str, Any]) -> dict[str, Any]:
    is_round_trip = requested_round_trip(agent_report)
    recommended = reportable_options(agent_report.get("recommended_options"))
    priority = reportable_options(agent_report.get("priority_options"))
    route = route_text(agent_report)
    header = f"Нашёл варианты {route}." if recommended or priority else f"Не нашёл пригодных вариантов {route}."
    sections: list[dict[str, Any]] = []

    primary = recommended[0] if recommended else (priority[0] if priority else None)
    if primary:
        primary_title = "Лучшая пара / рекомендация" if is_round_trip else "Рекомендация"
        lines = primary_lines(primary, is_round_trip=is_round_trip)
        if lines:
            sections.append(section(primary_title, lines))

    primary_id = primary.get("id") if isinstance(primary, dict) else None
    alternatives = [option for option in priority if option.get("id") != primary_id]
    outbound_alternatives = alternative_lines(alternatives, "outbound")
    return_alternatives = alternative_lines(alternatives, "return")
    if outbound_alternatives:
        sections.append(section("Альтернативы туда", outbound_alternatives))
    if return_alternatives:
        sections.append(section("Альтернативы обратно", return_alternatives))

    checks = verification_lines(agent_report)
    if checks:
        sections.append(section("Проверить перед покупкой", checks))

    text_blocks = [header]
    for item in sections:
        block_lines = [f"**{item['title']}**"]
        block_lines.extend(f"- {line}" for line in item["lines"])
        text_blocks.append("\n".join(block_lines))
    text = clean_text("\n\n".join(text_blocks))
    return {
        "format_version": HUMAN_ANSWER_FORMAT_VERSION,
        "text": text,
        "sections": sections,
    }
