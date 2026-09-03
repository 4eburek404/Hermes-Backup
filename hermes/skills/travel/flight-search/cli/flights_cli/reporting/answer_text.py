"""Текст ответа путешественнику. Единственное место, где данные становятся словами.

Читает только `options` контракта `.v1`. Ни каталога, ни трассы, ни второго
представления цены и длительности: формат здесь один, и он один на весь
продукт.
"""

from __future__ import annotations

from typing import Any

from ..domain.normalize import numeric_or_none
from .time_utils import integer_or_none

SELF_TRANSFER_TEXT = (
    "Отдельные билеты: при задержке первого рейса следующий сегмент не защищён."
)


def duration_text(value: Any) -> str:
    """Единственный формат длительности в продукте: «2 ч 45 мин»."""

    minutes = integer_or_none(value)
    if minutes is None or minutes < 0:
        return "н/д"
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours} ч {mins} мин"
    if hours:
        return f"{hours} ч"
    return f"{mins} мин"


def price_text(amount: Any, currency: Any) -> str:
    """Единственный формат цены в продукте: «8 043 ₽»."""

    number = numeric_or_none(amount)
    if number is None:
        return "цена н/д"
    rendered = (
        f"{int(number):,}".replace(",", " ")
        if float(number).is_integer()
        else str(number)
    )
    code = str(currency or "").upper()
    if code == "RUB":
        return f"{rendered} ₽"
    return f"{rendered} {code}".strip()


def _iso_date(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    return value[:10]


def display_date(value: Any) -> str:
    date = _iso_date(value)
    if not date:
        return "дата н/д"
    parts = date.split("-")
    return f"{parts[2]}.{parts[1]}" if len(parts) == 3 else date


def display_time(value: Any) -> str:
    if not isinstance(value, str) or "T" not in value:
        return "??:??"
    return value.split("T", 1)[1][:5]


def _compact_time(value: Any) -> str:
    return display_time(value).replace(":", "")


def arrival_date_suffix(departure_at: Any, arrival_at: Any) -> str:
    departure_date = display_date(departure_at)
    arrival_date = display_date(arrival_at)
    return f" ({arrival_date})" if arrival_date != departure_date else ""


def _endpoint_label(
    segment: dict[str, Any], endpoint: str, *, include_code: bool
) -> str:
    if endpoint == "origin":
        code, terminal = segment.get("origin"), segment.get("departure_terminal")
    else:
        code, terminal = segment.get("destination"), segment.get("arrival_terminal")
    normalized = str(code or "").strip().upper() or "???"
    if not include_code:
        return normalized
    rendered_terminal = str(terminal or "").strip().upper()
    return (
        f"({normalized},{rendered_terminal})"
        if rendered_terminal
        else f"({normalized})"
    )


def render_segment(
    segment: dict[str, Any], *, prefix: str, include_origin_code: bool
) -> str:
    departure_at = segment.get("departure_at")
    arrival_at = segment.get("arrival_at")
    origin = _endpoint_label(segment, "origin", include_code=include_origin_code)
    destination = _endpoint_label(segment, "destination", include_code=True)
    flight_number = str(segment.get("flight_number") or "").strip()
    flight_label = flight_number or "номер рейса не предоставлен"
    return (
        f"{prefix}{flight_label} {display_date(departure_at)} "
        f"{origin}-{destination} {_compact_time(departure_at)} "
        f"{_compact_time(arrival_at)}"
        f"{arrival_date_suffix(departure_at, arrival_at)} "
        f"в пути {duration_text(segment.get('duration_min'))}"
    )


def option_lines(option: dict[str, Any]) -> list[str]:
    body_lines: list[str] = []
    directions = (
        option.get("directions") if isinstance(option.get("directions"), dict) else {}
    )
    first_segment = True
    for key in ("outbound", "return"):
        leg = directions.get(key)
        if not isinstance(leg, dict):
            continue
        segments = [
            segment
            for segment in leg.get("segments") or []
            if isinstance(segment, dict)
        ]
        connections = [
            connection
            for connection in leg.get("connections") or []
            if isinstance(connection, dict)
        ]
        for index, segment in enumerate(segments):
            prefix = f"{option.get('number')}. " if first_segment else "   "
            body_lines.append(
                render_segment(
                    segment, prefix=prefix, include_origin_code=not first_segment
                )
            )
            first_segment = False
            if index < len(segments) - 1:
                connection = connections[index] if index < len(connections) else {}
                body_lines.append(
                    f"    пересадка {duration_text(connection.get('minutes'))}"
                )
    price = option.get("price") if isinstance(option.get("price"), dict) else {}
    price_line = price_text(price.get("amount"), price.get("currency"))
    if "self_transfer" in (option.get("warnings") or []):
        price_line = f"{price_line} · {SELF_TRANSFER_TEXT}"
    if body_lines:
        return [*body_lines, f"    {price_line}"]
    return [f"{option.get('number')}. вариант без детализации", f"    {price_line}"]


def render_answer(
    route: dict[str, Any], options: list[dict[str, Any]], *, evidence: dict[str, Any]
) -> str:
    """Собрать текст ответа из тех же фактов, что уехали в контракт."""

    origin = route.get("origin") or "???"
    destination = route.get("destination") or "???"
    incomplete = not evidence.get("complete")
    failures = bool(evidence.get("provider_failures"))
    rendered_options = [
        option_lines(option) for option in options if isinstance(option, dict)
    ]
    rendered_options = [lines for lines in rendered_options if lines]
    if not rendered_options:
        return _render_no_options(
            origin, destination, incomplete=incomplete, failures=failures
        )
    lines = [f"Нашёл варианты {origin}→{destination}."]
    for index, rendered_option in enumerate(rendered_options):
        if index > 0:
            lines.append("")
        lines.extend(rendered_option)
    check_parts = [
        "Перед оплатой проверьте багаж, финальный тариф и правила обмена/возврата"
    ]
    if incomplete and not failures:
        check_parts.append("покрытие неполное: не все live-проверки выполнены")
    if failures:
        check_parts.append("часть live-проверок упала")
    check_parts.append("результат не доказывает варианты вне границ источников")
    lines.append("")
    lines.append("; ".join(check_parts) + ".")
    return "\n".join(lines).strip()


def _render_no_options(
    origin: str, destination: str, *, incomplete: bool, failures: bool
) -> str:
    lines = [f"Не нашёл пригодных вариантов {origin}→{destination}."]
    checks = [
        "не нашёл в выполненных live/probe источниках; это не доказательство отсутствия вне границ источника",
        "финальную цену, тариф, багаж и правила проверить на booking screen.",
    ]
    if incomplete and not failures:
        checks.append("coverage неполное: не все live-проверки выполнены.")
    if failures:
        checks.append(
            "часть live-проверок упала — если это влияет на выбор, повторить поиск перед покупкой."
        )
    lines.append("")
    lines.append("**Проверить перед покупкой**")
    lines.extend(f"- {line}" for line in checks)
    return "\n".join(lines).strip()


__all__ = [
    "SELF_TRANSFER_TEXT",
    "arrival_date_suffix",
    "display_date",
    "display_time",
    "duration_text",
    "option_lines",
    "price_text",
    "render_answer",
    "render_segment",
]
