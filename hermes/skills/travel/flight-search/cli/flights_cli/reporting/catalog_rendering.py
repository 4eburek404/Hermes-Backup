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
FRONTIER_TICKETING_NOTE = (
    "Verify final fare, baggage, ticket protection, and purchase-screen rules "
    "before booking."
)
PROVIDER_SHOPPING_EVIDENCE_NOTE = (
    "Provider offers are shopping evidence; verify final fare, baggage, and "
    "ticket protection on the booking screen."
)


def source_boundaries() -> list[str]:
    """Render the stable human-readable evidence boundaries."""

    return [
        "Segment assembly prices direct one-way legs and does not construct GDS, airline through-fares, or guaranteed single-PNR fares.",
        "KupiBilet full-route offers can reveal provider-assembled itineraries, but ticket protection, baggage, fare rules, and final price still require booking-screen verification.",
        "Static city, airport, route, carrier, and aircraft catalogs are metadata only and cannot prove flight availability or absence.",
        "Cached or non-live price-source absence is not negative evidence.",
        "Provider failures are source availability failures, not route absence evidence.",
    ]


def minutes_label(value: Any) -> str | None:
    if value is None:
        return None
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return None
    hours, mins = divmod(max(0, minutes), 60)
    if hours and mins:
        return f"{hours}h{mins:02d}"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def price_label(amount: Any, currency: Any) -> str:
    if amount is None:
        return "price n/a"
    try:
        number = int(amount)
    except (TypeError, ValueError):
        return f"{amount} {currency or ''}".strip()
    return f"{number:,} {currency or ''}".replace(",", " ").strip()


def provider_label(option: dict[str, Any]) -> str:
    providers = option_provider_labels(option)
    return " + ".join(providers) if providers else "поставщика"


def source_ticketing_note(
    option: dict[str, Any],
    *,
    journey_scope: str,
    ticketing_model: str,
    max_connections: int,
) -> str:
    source_type = option_source_type(option)
    raw_ticketing = str(option.get("ticketing_model") or "").strip()
    price_basis = str(option.get("price_basis") or "").strip()
    provider = provider_label(option)
    gateway = str(option.get("gateway") or "").strip()

    if ticketing_model == "single_ticket_proven":
        return (
            f"источник: единый защищённый билет от {provider}; "
            "финальный тариф и условия багажа проверить на booking screen"
        )

    if (
        journey_scope == "two_one_way_pair"
        or ticketing_model == "separate_one_way_offers"
    ):
        return (
            "источник: две отдельные one-way выдачи; "
            "цена - сумма отдельных one-way; "
            "единый PNR, сквозной багаж и защищённый round-trip не подтверждены"
        )

    if (
        source_type == "gateway_separate_ticket"
        or raw_ticketing == "separate_ticket_sum"
    ):
        gateway_text = f" через {gateway}" if gateway else ""
        provider_text = f" ({provider})"
        return (
            f"источник: separate-ticket сборка{gateway_text}{provider_text}; "
            "цена - сумма отдельных плеч; "
            "единый PNR, сквозной багаж и защита пересадки не подтверждены"
        )

    if source_type == "provider_full_route" or is_provider_aggregate_option(option):
        price_text = (
            "цена поставщика"
            if price_basis in ("", "provider_offer_price")
            else "цену проверить у поставщика"
        )
        return (
            f"источник: полный маршрут от {provider}; {price_text}; "
            "единый PNR, сквозной багаж и защита пересадки не подтверждены"
        )

    if source_type == RouteFamily.DIRECT_INVENTORY or max_connections == 0:
        return (
            f"источник: прямой инвентарь ({provider}); "
            "финальный тариф и багаж проверить на booking screen"
        )

    if (
        source_type == "assembled_separate_ticket"
        or ticketing_model == "separate_segments"
    ):
        return (
            f"источник: сборка отдельных live-плеч ({provider}); "
            "единый PNR, сквозной багаж и защита пересадки не подтверждены"
        )

    return (
        f"источник: {provider}; "
        "ticketing/protection, багаж и финальный тариф проверить на booking screen"
    )


def compact_price_text(option: dict[str, Any]) -> str:
    price = option.get("price") if isinstance(option.get("price"), dict) else {}
    amount = numeric_or_none(price.get("amount"))
    currency = str(price.get("currency") or "").upper()
    if amount is not None:
        rendered = (
            f"{int(amount):,}".replace(",", " ")
            if float(amount).is_integer()
            else str(amount)
        )
        if currency == "RUB":
            return f"{rendered} ₽"
        if currency:
            return f"{rendered} {currency}"
        return rendered
    raw = str(option.get("price_text") or "").strip()
    return re.sub(r"\bRUB\b", "₽", raw, flags=re.IGNORECASE) if raw else "цена н/д"


def baggage_piece_text(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    parts: list[str] = []
    if value.get("count") is not None:
        parts.append(f"{value.get('count')}pc")
    if value.get("weight") is not None:
        parts.append(f"{value.get('weight')}kg")
    if value.get("text"):
        parts.append(str(value.get("text")))
    return "/".join(parts) if parts else None


def catalog_caveats(option: dict[str, Any], *, badges: list[str]) -> list[str]:
    caveats: list[str] = []
    disclaimer = option.get("disclaimer") or option.get("ticketing_note")
    if disclaimer:
        caveats.append(str(disclaimer))
    if "single_pnr_unproven" in badges:
        caveats.append("single PNR/protection not proven; verify on booking screen")
    if "baggage_unknown" in badges:
        caveats.append("baggage unknown until fare/package verification")
    if "self_transfer" in badges:
        if option.get("self_transfer_note"):
            caveats.append(str(option["self_transfer_note"]))
        caveats.append(_SELF_TRANSFER_CAVEAT)
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
    "FRONTIER_TICKETING_NOTE",
    "answer_display_lines_for_item",
    "answer_endpoint_display_label",
    "baggage_piece_text",
    "catalog_arrival_date_suffix",
    "catalog_caveats",
    "catalog_display_date",
    "catalog_display_time",
    "catalog_price_for_answer",
    "compact_price_text",
    "layover_minutes_display",
    "minutes_label",
    "price_label",
    "PROVIDER_SHOPPING_EVIDENCE_NOTE",
    "render_answer_display_segment",
    "render_catalog_answer",
    "render_user_answer",
    "segment_duration_clock_display",
    "source_ticketing_note",
    "source_boundaries",
]
