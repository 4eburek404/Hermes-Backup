from __future__ import annotations

from datetime import datetime
from typing import Any

from ..domain.normalize import numeric_or_none
from .catalog_semantics import (
    direction_segments,
    infer_journey_scope,
    is_provider_aggregate_option,
    option_direction,
    option_has_transfer,
    option_transfer_topology,
    resolve_ticket_semantics,
    risk_badges,
)
from .catalog_rendering import (
    baggage_piece_text,
    catalog_caveats,
    compact_price_text,
    source_ticketing_note,
)
from .time_utils import (
    display_minutes_between as minutes_between_iso,
    integer_or_none as int_or_none,
)


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


def catalog_item(
    option: dict[str, Any], *, number: int, is_round_trip_request: bool
) -> dict[str, Any]:
    journey_scope = infer_journey_scope(
        option, is_round_trip_request=is_round_trip_request
    )
    provider_aggregate = is_provider_aggregate_option(option)
    transfer_topology = option_transfer_topology(option)
    ticket_semantics = resolve_ticket_semantics(
        option,
        provider_aggregate=provider_aggregate,
        transfer_topology=transfer_topology,
    )
    ticketing_model = str(ticket_semantics["ticketing_model"])
    ticket_protection = dict(ticket_semantics["ticket_protection"])
    protection = dict(ticket_semantics["protection"])
    baggage = baggage_contract(option)
    badges = risk_badges(
        option, ticketing_model=ticketing_model, baggage=baggage, protection=protection
    )
    outbound = direction_contract(option, "outbound")
    inbound = direction_contract(option, "return")
    max_connections = max(0, int(option.get("max_connections_per_journey") or 0))
    caveats = catalog_caveats(option, badges=badges)
    source_note = source_ticketing_note(
        option,
        journey_scope=journey_scope,
        ticketing_model=ticketing_model,
        max_connections=max_connections,
        has_transfer=option_has_transfer(transfer_topology),
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
        "ticket_protection": ticket_protection,
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
) -> list[dict[str, Any]]:
    return [
        option
        for option in [*(recommended or []), *(priority or [])]
        if isinstance(option, dict)
    ][: max(0, limit)]


def infer_answer_mode(*, options: list[dict[str, Any]]) -> str:
    if not options:
        return "no_viable_options"
    return "catalog"


def build_catalog_contract(
    recommended: list[Any],
    priority: list[Any],
    *,
    is_round_trip_request: bool,
    catalog_limit: int,
) -> dict[str, Any]:
    requested_limit = max(1, int(catalog_limit))
    catalog_limit = max(requested_limit, len(recommended) + len(priority))
    options = catalog_options(
        recommended,
        priority,
        limit=catalog_limit,
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


__all__ = [
    "baggage_contract",
    "build_catalog_contract",
    "catalog_item",
    "catalog_options",
    "catalog_segment",
    "direction_contract",
    "direction_elapsed",
    "direction_layovers",
    "infer_answer_mode",
    "price_contract",
]
