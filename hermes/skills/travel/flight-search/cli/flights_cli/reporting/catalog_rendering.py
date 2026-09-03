from __future__ import annotations

import re
from typing import Any

from ..domain.normalize import numeric_or_none
from ..domain.vocabulary import RouteFamily
from .catalog_semantics import (
    is_provider_aggregate_option,
    option_provider_labels,
    option_source_type,
)
from .time_utils import integer_or_none as int_or_none


_SELF_TRANSFER_CAVEAT = (
    "Отдельные билеты: при задержке первого рейса следующий сегмент не защищён."
)

# Предупреждения живут кодами, а текст к ним — только здесь. Дедупликация идёт
# по коду, поэтому один и тот же смысл больше не может приехать дважды разными
# словами. В .v1 сериализоваться будут сами коды, а не эти строки.
CAVEAT_TEXTS: dict[str, str] = {
    "single_pnr_unproven": (
        "Единый PNR, сквозной багаж и защита пересадки не подтверждены."
    ),
    "baggage_unknown": "Багаж не подтверждён до проверки тарифа.",
    "self_transfer": _SELF_TRANSFER_CAVEAT,
    "verify_on_booking_screen": (
        "Финальный тариф, багаж и правила обмена проверить на странице оплаты."
    ),
}


def source_boundaries() -> list[str]:
    """Render the stable human-readable evidence boundaries."""

    return [
        "Segment assembly prices direct one-way legs and does not construct GDS, airline through-fares, or guaranteed single-PNR fares.",
        "KupiBilet full-route offers can reveal provider-assembled itineraries, but ticket protection, baggage, fare rules, and final price still require booking-screen verification.",
        "Static city, airport, route, carrier, and aircraft catalogs are metadata only and cannot prove flight availability or absence.",
        "Cached or non-live price-source absence is not negative evidence.",
        "Provider failures are source availability failures, not route absence evidence.",
    ]


def duration_text(value: Any) -> str:
    """Единственный формат длительности в продукте: «2 ч 45 мин»."""

    minutes = int_or_none(value)
    if minutes is None or minutes < 0:
        return "н/д"
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours} ч {mins} мин"
    if hours:
        return f"{hours} ч"
    return f"{mins} мин"


def minutes_label(value: Any) -> str | None:
    if value is None:
        return None
    if int_or_none(value) is None:
        return None
    return duration_text(value)


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


def price_label(amount: Any, currency: Any) -> str:
    return price_text(amount, currency)


def provider_label(option: dict[str, Any]) -> str:
    """Имя источника или пустая строка — заглушку в родительном падеже не даём."""

    return " + ".join(option_provider_labels(option))


def _provider_suffix(option: dict[str, Any]) -> str:
    provider = provider_label(option)
    return f" ({provider})" if provider else ""


def _provider_from(option: dict[str, Any]) -> str:
    provider = provider_label(option)
    return f" от {provider}" if provider else ""


def source_ticketing_note(
    option: dict[str, Any],
    *,
    journey_scope: str,
    ticketing_model: str,
    max_connections: int,
) -> str:
    """Откуда взялся вариант и на чём стоит цена.

    Предупреждения об отсутствии единого PNR и о багаже сюда больше не входят:
    они приезжают кодами и рендерятся один раз, иначе один и тот же смысл
    повторяется в списке дважды разными словами.
    """

    source_type = option_source_type(option)
    raw_ticketing = str(option.get("ticketing_model") or "").strip()
    price_basis = str(option.get("price_basis") or "").strip()
    gateway = str(option.get("gateway") or "").strip()

    if ticketing_model == "single_ticket_proven":
        return f"источник: единый защищённый билет{_provider_from(option)}"

    if (
        journey_scope == "two_one_way_pair"
        or ticketing_model == "separate_one_way_offers"
    ):
        return "источник: две отдельные односторонние выдачи — цена равна сумме плеч"

    if (
        source_type == "gateway_separate_ticket"
        or raw_ticketing == "separate_ticket_sum"
    ):
        gateway_text = f" через {gateway}" if gateway else ""
        return (
            f"источник: сборка из отдельных билетов{gateway_text}"
            f"{_provider_suffix(option)} — цена равна сумме плеч"
        )

    if source_type == "provider_full_route" or is_provider_aggregate_option(option):
        price_text_part = (
            "цена поставщика"
            if price_basis in ("", "provider_offer_price")
            else "цену проверить у поставщика"
        )
        return f"источник: полный маршрут{_provider_from(option)} — {price_text_part}"

    if source_type == RouteFamily.DIRECT_INVENTORY or max_connections == 0:
        return f"источник: прямой инвентарь{_provider_suffix(option)}"

    if (
        source_type == "assembled_separate_ticket"
        or ticketing_model == "separate_segments"
    ):
        return f"источник: сборка отдельных живых плеч{_provider_suffix(option)}"

    provider = provider_label(option)
    return f"источник: {provider}" if provider else "источник не указан"


def compact_price_text(option: dict[str, Any]) -> str:
    price = option.get("price") if isinstance(option.get("price"), dict) else {}
    amount = price.get("amount")
    if numeric_or_none(amount) is not None:
        return price_text(amount, price.get("currency"))
    raw = str(option.get("price_text") or "").strip()
    return re.sub(r"\bRUB\b", "₽", raw, flags=re.IGNORECASE) if raw else "цена н/д"


def baggage_piece_text(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    parts: list[str] = []
    if value.get("count") is not None:
        parts.append(f"{value.get('count')} мест")
    if value.get("weight") is not None:
        parts.append(f"{value.get('weight')} кг")
    if value.get("text"):
        parts.append(str(value.get("text")))
    return "/".join(parts) if parts else None


def catalog_caveat_codes(option: dict[str, Any], *, badges: list[str]) -> list[str]:
    """Коды предупреждений варианта. Порядок стабильный, дубликатов нет."""

    codes: list[str] = []
    for badge in ("single_pnr_unproven", "baggage_unknown", "self_transfer"):
        if badge in badges:
            codes.append(badge)
    codes.append("verify_on_booking_screen")
    return list(dict.fromkeys(codes))


def catalog_caveats(option: dict[str, Any], *, badges: list[str]) -> list[str]:
    """Тексты предупреждений. Дедупликация идёт по коду, а не по строке."""

    caveats = [
        CAVEAT_TEXTS[code]
        for code in catalog_caveat_codes(option, badges=badges)
        if code in CAVEAT_TEXTS
    ]
    note = option.get("self_transfer_note")
    if note and "self_transfer" in badges:
        caveats.insert(0, str(note))
    return list(dict.fromkeys(caveats))


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


def _segment_duration_minutes(segment: dict[str, Any]) -> int | None:
    for key in ("duration_min", "duration"):
        value = int_or_none(segment.get(key))
        if value is not None and value >= 0:
            return value
    return None


def segment_duration_clock_display(segment: dict[str, Any]) -> str:
    return duration_text(_segment_duration_minutes(segment))


def layover_minutes_display(value: Any) -> str:
    return duration_text(value)


def catalog_price_for_answer(price: dict[str, Any]) -> str:
    """Тот же формат, что и в структурном поле: одна цена — одно написание."""

    amount = price.get("amount")
    if numeric_or_none(amount) is not None:
        return price_text(amount, price.get("currency"))
    return str(price.get("display") or "цена н/д")


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


def _inline_catalog_caveat(item: dict[str, Any]) -> str | None:
    badges = item.get("badges") if isinstance(item.get("badges"), list) else []
    if "self_transfer" not in badges:
        return None
    for caveat in reversed(item.get("caveats") or []):
        value = str(caveat).strip()
        if value == _SELF_TRANSFER_CAVEAT:
            return value
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
    warning = _inline_catalog_caveat(item)
    if warning:
        price_line = f"{price_line} · {warning}"
    if body_lines:
        return [*body_lines, f"    {price_line}"]
    return [f"{item.get('number')}. вариант без детализации", f"    {price_line}"]


def render_catalog_answer(
    route: dict[str, Any],
    catalog: dict[str, Any],
    *,
    caveat_context: dict[str, Any],
) -> str:
    origin = route.get("origin") or "???"
    destination = route.get("destination") or "???"
    lines = [f"Нашёл варианты {origin}→{destination}."]
    rendered_items = [
        answer_display_lines_for_item(item)
        for item in catalog.get("items") or []
        if isinstance(item, dict)
    ]
    rendered_items = [item_lines for item_lines in rendered_items if item_lines]
    for index, rendered_item in enumerate(rendered_items):
        if index > 0:
            lines.append("")
        lines.extend(rendered_item)
    has_rendered_options = bool(rendered_items)
    if has_rendered_options:
        check_parts = [
            "Перед оплатой проверьте багаж, финальный тариф и правила обмена/возврата"
        ]
        if caveat_context.get("not_executed"):
            check_parts.append("покрытие неполное: не все live-проверки выполнены")
        if caveat_context.get("provider_failures"):
            check_parts.append("часть live-проверок упала")
        if caveat_context.get("source_boundaries"):
            check_parts.append("результат не доказывает варианты вне границ источников")
        checks = ["; ".join(check_parts) + "."]
    else:
        checks = [
            "Перед оплатой проверить багаж, финальный тариф и правила обмена/возврата.",
            "Единый тариф/сквозной багаж не подтверждены; текущий результат поставщика не доказывает наличие или отсутствие защищённого билета.",
        ]
        if caveat_context.get("not_executed"):
            checks.append("Coverage неполное: не все live-проверки выполнены.")
        if caveat_context.get("provider_failures"):
            checks.append(
                "часть live-проверок упала — повторить, если это влияет на выбор."
            )
    if checks and rendered_items:
        lines.append("")
    lines.extend(checks)
    return "\n".join(lines).strip()


def _render_no_viable_answer(
    route: dict[str, Any], *, caveat_context: dict[str, Any]
) -> str:
    origin = route.get("origin") or "???"
    destination = route.get("destination") or "???"
    lines = [f"Не нашёл пригодных вариантов {origin}→{destination}."]
    checks = [
        "не нашёл в выполненных live/probe источниках; это не доказательство отсутствия вне границ источника",
        "финальную цену, тариф, багаж и правила проверить на booking screen.",
    ]
    if caveat_context.get("not_executed"):
        checks.append("coverage неполное: не все live-проверки выполнены.")
    if caveat_context.get("provider_failures"):
        checks.append(
            "часть live-проверок упала — если это влияет на выбор, повторить поиск перед покупкой."
        )
    lines.append("")
    lines.append("**Проверить перед покупкой**")
    lines.extend(f"- {line}" for line in checks)
    return "\n".join(lines).strip()


def render_user_answer(answer: dict[str, Any], route: dict[str, Any]) -> str:
    """Render only from the already projected structured answer catalog."""

    catalog = answer.get("catalog") if isinstance(answer.get("catalog"), dict) else {}
    evidence = (
        answer.get("evidence_status")
        if isinstance(answer.get("evidence_status"), dict)
        else {}
    )
    required = (
        answer.get("required_caveats")
        if isinstance(answer.get("required_caveats"), dict)
        else {}
    )
    caveat_context = {
        "not_executed": [True]
        if int(evidence.get("not_executed_probe_count") or 0)
        else [],
        "provider_failures": [True]
        if int(evidence.get("provider_failure_count") or 0)
        else [],
        "source_boundaries": [True]
        if required.get("source_boundaries_included")
        else [],
    }
    route_contract = {
        "origin": route.get("origin"),
        "destination": route.get("destination"),
        "dates": route.get("dates") if isinstance(route.get("dates"), dict) else {},
    }
    if answer.get("answer_mode") == "catalog":
        return render_catalog_answer(
            route_contract,
            catalog,
            caveat_context=caveat_context,
        )
    return _render_no_viable_answer(route_contract, caveat_context=caveat_context)


__all__ = [
    "CAVEAT_TEXTS",
    "answer_display_lines_for_item",
    "answer_endpoint_display_label",
    "baggage_piece_text",
    "catalog_arrival_date_suffix",
    "catalog_caveat_codes",
    "catalog_caveats",
    "catalog_display_date",
    "catalog_display_time",
    "catalog_price_for_answer",
    "compact_price_text",
    "duration_text",
    "layover_minutes_display",
    "minutes_label",
    "price_label",
    "price_text",
    "render_answer_display_segment",
    "render_catalog_answer",
    "render_user_answer",
    "segment_duration_clock_display",
    "source_ticketing_note",
    "source_boundaries",
]
