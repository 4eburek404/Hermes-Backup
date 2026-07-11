from __future__ import annotations

import re
from typing import Any

from ..domain.vocabulary import RouteFamily
from .catalog_order import ordered_user_options
from .option_semantics import direction_segments, option_direction
from .time_utils import (
    display_minutes_between as minutes_between_iso,
    integer_or_none as int_or_none,
)
from .user_answer_lines import (
    AGENT_DISPLAY_STYLE,
    agent_display_contract,
    agent_display_lines_for_item,
    answer_display_lines_for_item,
    numeric_or_none,
    render_direction_for_catalog,
)


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


def route_label(option: dict[str, Any]) -> str:
    segments = (
        option.get("segments") if isinstance(option.get("segments"), list) else []
    )
    if segments:
        first = next(
            (segment for segment in segments if isinstance(segment, dict)), None
        )
        last = next(
            (segment for segment in reversed(segments) if isinstance(segment, dict)),
            None,
        )
        if first and last and first.get("origin") and last.get("destination"):
            return f" {first.get('origin')}→{last.get('destination')}"
    return ""


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


def default_label(
    option: dict[str, Any],
    *,
    journey_scope: str,
    direction: str | None,
    is_primary: bool,
) -> str:
    price = str(option.get("price_text") or "price n/a")
    route = route_label(option)
    label_kind = "recommendation" if is_primary else "alternative"
    if journey_scope == "outbound_only":
        return f"One-way outbound {label_kind}{route}: {price}. Does not cover requested round trip."
    if journey_scope == "return_only":
        return f"One-way return {label_kind}{route}: {price}. Does not cover requested round trip."
    if journey_scope == "two_one_way_pair":
        return f"Two separate one-way offers{route}: {price}."
    if journey_scope == "round_trip":
        return f"Round-trip {label_kind}{route}: {price}."
    if direction == "return":
        return f"One-way return {label_kind}{route}: {price}."
    return f"One-way {label_kind}{route}: {price}."


def default_disclaimer(option: dict[str, Any], *, journey_scope: str) -> str | None:
    if journey_scope == "two_one_way_pair":
        return (
            "Two separate one-way offers; not proven as a single PNR, protected round-trip, "
            "baggage-through itinerary, through fare, or final fare. Sum of displayed one-way prices "
            "is arithmetic only, not booking-screen proof; verify ticketing, baggage, refund, and disruption protection on the booking screen."
        )
    if is_provider_aggregate_option(option):
        return "Provider aggregate offer; ticketing/protection, baggage handling, fare rules, and final fare require booking-screen verification."
    return None


def option_summary(
    option: dict[str, Any] | None,
    *,
    is_round_trip_request: bool = False,
    is_primary: bool = False,
) -> dict[str, Any] | None:
    if not isinstance(option, dict):
        return None
    risk = option.get("risk") if isinstance(option.get("risk"), dict) else {}
    segments = (
        option.get("segments") if isinstance(option.get("segments"), list) else []
    )
    explicit_max_connections = option.get("max_connections_per_journey")
    if explicit_max_connections is not None:
        max_connections = int(explicit_max_connections)
    else:
        direction_counts = [
            sum(
                1
                for segment in segments
                if isinstance(segment, dict) and segment.get("direction") == direction
            )
            for direction in ("outbound", "return")
        ]
        max_direction_segments = (
            max(direction_counts) if any(direction_counts) else len(segments)
        )
        max_connections = max(0, max_direction_segments - 1)
    journey_scope = infer_journey_scope(
        option, is_round_trip_request=is_round_trip_request
    )
    direction = option_direction(option)
    provider_aggregate = is_provider_aggregate_option(option)
    covers_requested_trip = option.get("covers_requested_trip")
    if not isinstance(covers_requested_trip, bool):
        covers_requested_trip = journey_scope in (
            "one_way",
            "round_trip",
            "two_one_way_pair",
        )
    directional_only = option.get("directional_only")
    if not isinstance(directional_only, bool):
        directional_only = provider_aggregate and journey_scope in (
            "one_way",
            "outbound_only",
            "return_only",
        )
    composed_of_directional_offers = bool(option.get("composed_of_directional_offers"))
    ticketing_model = canonical_ticketing_model(
        option, provider_aggregate=provider_aggregate
    )
    user_facing_label = str(
        option.get("user_facing_label")
        or option.get("label")
        or default_label(
            option,
            journey_scope=journey_scope,
            direction=direction,
            is_primary=is_primary,
        )
    )
    disclaimer = option.get("disclaimer") or default_disclaimer(
        option, journey_scope=journey_scope
    )
    summary = {
        "id": option.get("id"),
        "category": option.get("category"),
        "price_text": str(option.get("price_text") or "price n/a"),
        "elapsed": option.get("elapsed"),
        "risk_grade": risk.get("grade"),
        "segment_count": len(segments),
        "stop_tier": option.get("stop_tier"),
        "max_connections_per_journey": max_connections,
        "journey_scope": journey_scope,
        "covers_requested_trip": covers_requested_trip,
        "direction": direction,
        "directional_only": directional_only,
        "composed_of_directional_offers": composed_of_directional_offers,
        "ticketing_model": ticketing_model,
        "user_facing_label": user_facing_label,
    }
    for key in ("itinerary_elapsed_min", "flight_time_min", "layover_total_min"):
        if key in option:
            summary[key] = option.get(key)
    for key in ("outbound_time", "return_time"):
        value = option.get(key)
        if isinstance(value, dict):
            summary[key] = {
                "itinerary_elapsed_min": value.get("itinerary_elapsed_min"),
                "flight_time_min": value.get("flight_time_min"),
                "layover_total_min": value.get("layover_total_min"),
            }
    if disclaimer:
        summary["disclaimer"] = str(disclaimer)
    return summary


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


def catalog_segment(segment: dict[str, Any]) -> dict[str, Any]:
    return {
        "flight_number": str(
            segment.get("flight_number") or segment.get("carrier") or ""
        )
        or None,
        "carrier": str(
            segment.get("carrier")
            or segment.get("marketing_carrier")
            or segment.get("carrier_name")
            or ""
        )
        or None,
        "origin": str(segment.get("origin") or "") or None,
        "destination": str(segment.get("destination") or "") or None,
        "departure_terminal": str(segment.get("departure_terminal") or "").strip()
        or None,
        "arrival_terminal": str(segment.get("arrival_terminal") or "").strip() or None,
        "departure_at": str(segment.get("departure_at") or "") or None,
        "arrival_at": str(segment.get("arrival_at") or "") or None,
        "aircraft_code": str(
            segment.get("aircraft_code") or segment.get("aircraft") or ""
        )
        or None,
        "duration_min": int_or_none(segment.get("duration_min")),
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
        "render_line": render_direction_for_catalog(segments, direction),
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
    disclaimer = option.get("disclaimer") or option.get("ticketing_note")
    if disclaimer:
        caveats.append(str(disclaimer))
    if "single_pnr_unproven" in badges:
        caveats.append("single PNR/protection not proven; verify on booking screen")
    if "baggage_unknown" in badges:
        caveats.append("baggage unknown until fare/package verification")
    if "self_transfer" in badges:
        caveats.append(
            "Самостоятельная пересадка: единый PNR и защита стыковки не подтверждены."
        )
        if option.get("self_transfer_note"):
            caveats.append(str(option["self_transfer_note"]))
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
        "agent_display": {
            "style": AGENT_DISPLAY_STYLE,
            "lines": [],
            "text": "",
        },
        "render_line": "",
        "evidence_refs": [],
    }
    item["agent_display"] = agent_display_contract(item)
    item["render_line"] = render_catalog_item(item)
    return item


def catalog_options(
    recommended: list[Any],
    priority: list[Any],
    *,
    limit: int,
    is_round_trip_request: bool = False,
) -> list[dict[str, Any]]:
    return ordered_user_options(
        recommended or [],
        priority or [],
        limit=limit,
        is_round_trip_request=is_round_trip_request,
    )


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
    requested_limit = max(1, int(catalog_limit))
    catalog_limit = (
        max(1, len(recommended))
        if direct_mode
        else max(requested_limit, len(recommended))
    )
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


def render_catalog_item(item: dict[str, Any]) -> str:
    agent_display = (
        item.get("agent_display") if isinstance(item.get("agent_display"), dict) else {}
    )
    text = str(agent_display.get("text") or "").strip()
    if text:
        return text
    return "\n".join(agent_display_lines_for_item(item))


def render_catalog_answer(
    route: dict[str, Any],
    catalog: dict[str, Any],
    *,
    caveat_context: dict[str, Any],
    gateway_summary: str | None = None,
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
    if gateway_summary:
        if has_rendered_options:
            lines.append("")
        lines.append(gateway_summary)
    negative_wording = str(caveat_context.get("negative_wording") or "").strip()
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
        if caveat_context.get("through_fare_checks"):
            check_parts.append("единый тариф проверить отдельно")
        checks = ["; ".join(check_parts) + "."]
    else:
        checks = [
            "Перед оплатой проверить багаж, финальный тариф и правила обмена/возврата.",
            "Единый тариф/сквозной багаж не подтверждены; текущий результат поставщика не доказывает наличие или отсутствие защищённого билета.",
        ]
        if negative_wording and negative_wording not in checks:
            checks.append(negative_wording)
        if caveat_context.get("not_executed"):
            checks.append("Coverage неполное: не все live-проверки выполнены.")
        if caveat_context.get("provider_failures"):
            checks.append(
                "часть live-проверок упала — повторить, если это влияет на выбор."
            )
    if checks and (rendered_items or gateway_summary):
        lines.append("")
    lines.extend(checks)
    return "\n".join(lines).strip()


def is_two_one_way_pair_option(option: dict[str, Any]) -> bool:
    return (
        option.get("journey_scope") == "two_one_way_pair"
        or option.get("composed_of_directional_offers") is True
    )


def priority_options_for_user_contract(
    priority: list[Any], *, limit: int = 5, is_round_trip_request: bool = False
) -> list[dict[str, Any]]:
    dict_priority = [item for item in priority if isinstance(item, dict)]
    selected = ordered_user_options(
        [],
        dict_priority,
        limit=max(0, limit),
        is_round_trip_request=is_round_trip_request,
    )
    pair = next(
        (item for item in dict_priority if is_two_one_way_pair_option(item)), None
    )
    if pair is not None:
        selected = ordered_user_options(
            [],
            [*selected, pair],
            limit=len(selected) + 1,
            is_round_trip_request=is_round_trip_request,
        )
    return selected


def rendered_answer_lines(rendered_text: str) -> list[str]:
    return [line for line in rendered_text.splitlines() if line.strip()]
