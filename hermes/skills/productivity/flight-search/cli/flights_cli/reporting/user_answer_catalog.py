from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from ..domain.normalize import numeric_or_none
from ..domain.vocabulary import RouteFamily
from .option_semantics import direction_segments, option_direction
from .time_utils import (
    display_minutes_between as minutes_between_iso,
    integer_or_none as int_or_none,
)
from .user_answer_lines import answer_display_lines_for_item


def is_provider_aggregate_option(option: dict[str, Any]) -> bool:
    return str(option.get("category") or "") == "provider_aggregate_candidate" or str(
        option.get("id") or ""
    ).startswith("provider-aggregate:")


def option_source_type(option: dict[str, Any]) -> str | None:
    source_type = str(option.get("source_type") or "").strip()
    if source_type:
        return source_type
    if is_provider_aggregate_option(option):
        return "provider_full_route"
    return None


def option_provider_labels(option: dict[str, Any]) -> list[str]:
    raw = option.get("source_providers")
    providers: list[str] = []
    if isinstance(raw, list):
        providers.extend(str(item).strip() for item in raw if str(item).strip())
    provider = str(option.get("provider") or "").strip()
    if provider:
        providers.append(provider)
    return list(dict.fromkeys(providers))


def provider_label(option: dict[str, Any]) -> str:
    providers = option_provider_labels(option)
    return " + ".join(providers) if providers else "поставщика"


def canonical_ticketing_model(
    option: dict[str, Any], *, provider_aggregate: bool
) -> str:
    raw = str(option.get("ticketing_model") or "").strip()
    if raw in (
        "single_ticket_proven",
        "provider_aggregate",
        "separate_one_way_offers",
        "separate_segments",
        "unknown",
    ):
        return raw
    if raw in ("provider_order_unverified", "provider_offer_unverified"):
        return "provider_aggregate"
    if raw in ("separate_ticket_sum", "gateway_separate_ticket"):
        return "separate_segments"
    if raw == "metasearch_redirect_unknown":
        return "unknown"
    if provider_aggregate:
        return "provider_aggregate"
    return "separate_segments"


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
    has_fli_source = any(
        item.lower() == "fli" for item in option_provider_labels(option)
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
        provider_text = (
            f" ({provider}; FLI/metasearch для non-RU плеча)"
            if has_fli_source
            else f" ({provider})"
        )
        return (
            f"источник: separate-ticket сборка{gateway_text}{provider_text}; "
            "цена - сумма отдельных плеч; "
            "единый PNR, сквозной багаж и защита пересадки не подтверждены"
        )

    if raw_ticketing == "metasearch_redirect_unknown" or (
        has_fli_source and source_type != "provider_full_route"
    ):
        return (
            f"источник: FLI/metasearch для non-RU плеча ({provider}); "
            "финальный тариф и ticketing проверить у redirect-поставщика"
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


def infer_journey_scope(option: dict[str, Any], *, is_round_trip_request: bool) -> str:
    explicit = option.get("journey_scope")
    if explicit == "two_one_way_pair":
        return "two_one_way_pair"
    direction = option_direction(option)
    if is_provider_aggregate_option(option):
        if is_round_trip_request:
            return "return_only" if direction == "return" else "outbound_only"
        return "one_way"
    if is_round_trip_request:
        return "round_trip"
    return "one_way"


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


def price_contract(option: dict[str, Any]) -> dict[str, Any]:
    price = option.get("price") if isinstance(option.get("price"), dict) else {}
    source = (
        "provider_aggregate"
        if is_provider_aggregate_option(option)
        else "live_provider"
    )
    confidence = "medium" if is_provider_aggregate_option(option) else "high"
    return {
        "amount": numeric_or_none(price.get("amount")),
        "currency": str(price.get("currency") or "").upper() or None,
        "display": compact_price_text(option),
        "source": source,
        "confidence": confidence,
    }


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


def baggage_contract(option: dict[str, Any]) -> dict[str, str]:
    checked = baggage_piece_text(option.get("baggage"))
    cabin = baggage_piece_text(
        option.get("hand_luggage") or option.get("cabin_baggage")
    )
    source = "provider_offer" if checked or cabin else "unknown"
    confidence = "medium" if checked or cabin else "unknown"
    return {
        "checked": checked or "unknown",
        "cabin": cabin or "unknown",
        "source": source,
        "confidence": confidence,
    }


def protection_contract(option: dict[str, Any]) -> dict[str, Any]:
    if option.get("self_transfer") is True:
        return {
            "single_pnr_status": "unproven",
            "through_baggage_status": "unproven",
            "self_transfer": True,
            "purchase_screen_verification_required": True,
        }
    if option.get("self_transfer") is False:
        return {
            "single_pnr_status": "unknown",
            "through_baggage_status": "unknown",
            "self_transfer": False,
            "purchase_screen_verification_required": True,
        }
    ticketing_model = str(
        option.get("ticketing_model")
        or (
            "provider_aggregate"
            if is_provider_aggregate_option(option)
            else "separate_segments"
        )
    )
    if ticketing_model == "single_ticket_proven":
        return {
            "single_pnr_status": "proven",
            "through_baggage_status": "proven",
            "self_transfer": False,
            "purchase_screen_verification_required": False,
        }
    if ticketing_model in ("separate_segments", "separate_one_way_offers"):
        return {
            "single_pnr_status": "unproven",
            "through_baggage_status": "unproven",
            "self_transfer": True,
            "purchase_screen_verification_required": True,
        }
    return {
        "single_pnr_status": "unknown",
        "through_baggage_status": "unknown",
        "self_transfer": None,
        "purchase_screen_verification_required": True,
    }


def _catalog_segment_duration(segment: dict[str, Any]) -> int | None:
    explicit = int_or_none(segment.get("duration_min") or segment.get("duration"))
    if explicit is not None:
        return explicit
    try:
        departure = datetime.fromisoformat(str(segment["departure_at"]))
        arrival = datetime.fromisoformat(str(segment["arrival_at"]))
    except (KeyError, TypeError, ValueError):
        return None
    if departure.tzinfo is None or arrival.tzinfo is None:
        return None
    return int((arrival - departure).total_seconds() // 60)


def catalog_segment(segment: dict[str, Any]) -> dict[str, Any]:
    return {
        "flight_number": str(segment.get("flight_number") or "") or None,
        "carrier": str(
            segment.get("carrier")
            or segment.get("marketing_carrier")
            or segment.get("carrier_name")
            or ""
        )
        or None,
        "origin": str(segment.get("origin") or "") or None,
        "destination": str(segment.get("destination") or "") or None,
        "origin_label": str(segment.get("origin_label") or segment.get("origin") or "")
        or None,
        "destination_label": str(
            segment.get("destination_label") or segment.get("destination") or ""
        )
        or None,
        "departure_terminal": str(segment.get("departure_terminal") or "").strip()
        or None,
        "arrival_terminal": str(segment.get("arrival_terminal") or "").strip() or None,
        "departure_at": str(segment.get("departure_at") or "") or None,
        "arrival_at": str(segment.get("arrival_at") or "") or None,
        "aircraft_code": str(
            segment.get("aircraft_code") or segment.get("aircraft") or ""
        )
        or None,
        "duration_min": _catalog_segment_duration(segment),
    }


def direction_layovers(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    layovers: list[dict[str, Any]] = []
    for previous, current in zip(segments, segments[1:]):
        layovers.append(
            {
                "airport": previous.get("destination") or current.get("origin"),
                "duration_min": minutes_between_iso(
                    previous.get("arrival_at"), current.get("departure_at")
                ),
            }
        )
    return layovers


def direction_elapsed(
    option: dict[str, Any], direction: str, segments: list[dict[str, Any]]
) -> int | None:
    key = "outbound_time" if direction == "outbound" else "return_time"
    value = option.get(key)
    if isinstance(value, dict):
        known = int_or_none(value.get("itinerary_elapsed_min"))
        if known is not None:
            return known
    if segments:
        return minutes_between_iso(
            segments[0].get("departure_at"), segments[-1].get("arrival_at")
        )
    return int_or_none(option.get("itinerary_elapsed_min") or option.get("elapsed_min"))


def direction_contract(option: dict[str, Any], direction: str) -> dict[str, Any] | None:
    segments = direction_segments(option, direction)
    if not segments and option_direction(option) not in (direction, None):
        return None
    if not segments and option.get("journey_scope") == "round_trip":
        return None
    detail_status = str(
        option.get("detail_status") or ("full" if segments else "summary_only")
    )
    if detail_status not in ("full", "summary_only", "missing"):
        detail_status = "summary_only"
    catalog_segments = [catalog_segment(segment) for segment in segments]
    return {
        "detail_status": detail_status if catalog_segments else "summary_only",
        "segments": catalog_segments,
        "layovers": direction_layovers(catalog_segments),
        "elapsed_min": direction_elapsed(option, direction, catalog_segments),
    }


def risk_badges(
    option: dict[str, Any],
    *,
    ticketing_model: str,
    baggage: dict[str, str],
    protection: dict[str, Any],
) -> list[str]:
    badges: list[str] = []
    if ticketing_model == "provider_aggregate":
        badges.append("provider_aggregate")
    if ticketing_model == "separate_one_way_offers":
        badges.append("separate_one_way_offers")
    if ticketing_model == "separate_segments":
        badges.append("separate_segments")
    if protection.get("single_pnr_status") != "proven":
        badges.append("single_pnr_unproven")
    if protection.get("through_baggage_status") != "proven":
        badges.append("through_baggage_unproven")
    if protection.get("self_transfer") is True:
        badges.append("self_transfer")
    if baggage.get("checked") == "unknown":
        badges.append("baggage_unknown")
    if option.get("directional_only") is True:
        badges.append("directional_only")
    if (
        option.get("max_connections_per_journey") is not None
        and int(option.get("max_connections_per_journey") or 0) >= 2
    ):
        badges.append("two_stop_or_more")
    badges.extend(
        str(value) for value in option.get("option_badges") or [] if str(value).strip()
    )
    return list(dict.fromkeys(badges))


def catalog_caveats(option: dict[str, Any], *, badges: list[str]) -> list[str]:
    caveats: list[str] = []
    ticket_protection = (
        option.get("ticket_protection")
        if isinstance(option.get("ticket_protection"), dict)
        else {}
    )
    disclaimer = option.get("disclaimer") or option.get("ticketing_note")
    if disclaimer:
        caveats.append(str(disclaimer))
    if "single_pnr_unproven" in badges:
        caveats.append("single PNR/protection not proven; verify on booking screen")
    if "baggage_unknown" in badges:
        caveats.append("baggage unknown until fare/package verification")
    if "self_transfer" in badges:
        caveats.append(
            "Отдельные билеты: при задержке первого рейса следующий сегмент не защищён."
        )
        if option.get("self_transfer_note"):
            caveats.append(str(option["self_transfer_note"]))
    elif ticket_protection.get("status") == "unprotected":
        caveats.append(
            "Отдельные билеты: при задержке первого рейса следующий сегмент не защищён."
        )
    return list(dict.fromkeys(caveats))


def catalog_item(
    option: dict[str, Any], *, number: int, is_round_trip_request: bool
) -> dict[str, Any]:
    journey_scope = infer_journey_scope(
        option, is_round_trip_request=is_round_trip_request
    )
    provider_aggregate = is_provider_aggregate_option(option)
    ticketing_model = canonical_ticketing_model(
        option, provider_aggregate=provider_aggregate
    )
    baggage = baggage_contract(option)
    protection = protection_contract({**option, "ticketing_model": ticketing_model})
    badges = risk_badges(
        option, ticketing_model=ticketing_model, baggage=baggage, protection=protection
    )
    outbound = direction_contract(option, "outbound")
    inbound = direction_contract(option, "return")
    explicit_max_connections = option.get("max_connections_per_journey")
    if explicit_max_connections is not None:
        max_connections = int(explicit_max_connections)
    else:
        direction_counts = [
            sum(
                1
                for segment in (
                    option.get("segments")
                    if isinstance(option.get("segments"), list)
                    else []
                )
                if isinstance(segment, dict) and segment.get("direction") == direction
            )
            for direction in ("outbound", "return")
        ]
        max_direction_segments = (
            max(direction_counts)
            if any(direction_counts)
            else len(option.get("segments") or [])
        )
        max_connections = max(0, max_direction_segments - 1)
    caveats = catalog_caveats(option, badges=badges)
    source_note = source_ticketing_note(
        option,
        journey_scope=journey_scope,
        ticketing_model=ticketing_model,
        max_connections=max_connections,
    )
    if source_note:
        caveats = list(dict.fromkeys([source_note, *caveats]))
    item: dict[str, Any] = {
        "number": number,
        "option_id": str(option.get("id") or f"option-{number}"),
        "covers_requested_trip": bool(
            option.get("covers_requested_trip")
            if isinstance(option.get("covers_requested_trip"), bool)
            else journey_scope in ("one_way", "round_trip", "two_one_way_pair")
        ),
        "journey_scope": journey_scope,
        "ticketing_model": ticketing_model,
        "detail_status": str(
            option.get("detail_status")
            or ("full" if option.get("segments") else "summary_only")
        ),
        "total_price": price_contract(option),
        "directions": {"outbound": outbound, "return": inbound},
        "baggage": baggage,
        "protection": protection,
        "connection_assessment": (
            dict(option["connection_assessment"])
            if isinstance(option.get("connection_assessment"), dict)
            else {"status": "unknown", "comfort": "unknown", "connections": []}
        ),
        "ticket_protection": (
            dict(option["ticket_protection"])
            if isinstance(option.get("ticket_protection"), dict)
            else {
                "status": "unknown",
                "source": "provider_evidence_incomplete",
                "reasons": ["ticket_protection_unproven"],
            }
        ),
        "risk": {
            **(option.get("risk") if isinstance(option.get("risk"), dict) else {}),
            **(
                {"self_transfer_source": option.get("self_transfer_source")}
                if option.get("self_transfer_source")
                else {}
            ),
            **(
                {"self_transfer_note": option.get("self_transfer_note")}
                if option.get("self_transfer_note")
                else {}
            ),
        },
        "badges": badges,
        "caveats": caveats,
        "evidence_refs": [],
    }
    return item


def catalog_options(
    recommended: list[Any],
    priority: list[Any],
    *,
    limit: int,
    is_round_trip_request: bool = False,
) -> list[dict[str, Any]]:
    del is_round_trip_request
    return [
        option
        for option in [*(recommended or []), *(priority or [])]
        if isinstance(option, dict)
    ][: max(0, limit)]


def infer_answer_mode(
    *, is_round_trip_request: bool, options: list[dict[str, Any]]
) -> str:
    if not options:
        return "no_viable_options"
    return "catalog"


def build_catalog_contract(
    recommended: list[Any],
    priority: list[Any],
    *,
    is_round_trip_request: bool,
    catalog_limit: int,
    direct_mode: bool = False,
) -> dict[str, Any]:
    del direct_mode
    requested_limit = max(1, int(catalog_limit))
    catalog_limit = max(requested_limit, len(recommended) + len(priority))
    options = catalog_options(
        recommended,
        priority,
        limit=catalog_limit,
        is_round_trip_request=is_round_trip_request,
    )
    return {
        "presentation": {
            "style": "numbered_inline_itinerary_v1",
            "language": "ru",
            "max_items": catalog_limit,
        },
        "items": [
            catalog_item(
                option, number=index, is_round_trip_request=is_round_trip_request
            )
            for index, option in enumerate(options, start=1)
        ],
    }


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
