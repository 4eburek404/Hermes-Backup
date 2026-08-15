from __future__ import annotations

from typing import Any, Mapping

from ..domain.stop_policy import stop_tier

_PROVEN_TICKETING_MODELS = frozenset(
    {
        "single_pnr_proven",
        "single_ticket_proven",
        "protected_provider_order",
    }
)
_NON_SELF_TRANSFER_MODELS = frozenset(
    {
        *_PROVEN_TICKETING_MODELS,
        "round_trip_single_ticket",
        "single_pnr",
    }
)
_PROVIDER_AGGREGATE_MODELS = frozenset(
    {
        "provider_aggregate",
        "provider_offer_unverified",
        "provider_order_unverified",
        "round_trip_provider_order_unverified",
    }
)
_SEPARATE_ONE_WAY_MODELS = frozenset({"one_way_sum", "separate_one_way_offers"})
_SEPARATE_SEGMENT_MODELS = frozenset(
    {"gateway_separate_ticket", "separate_segments", "separate_ticket_sum"}
)


def route_requested_round_trip(route: Mapping[str, Any] | None) -> bool:
    route_map = route if isinstance(route, Mapping) else {}
    dates = route_map.get("dates")
    if not isinstance(dates, dict):
        dates = {}
    return bool(dates.get("return") or dates.get("return_date"))


def option_direction(option: Mapping[str, Any] | None) -> str | None:
    option_map = option if isinstance(option, Mapping) else {}
    explicit = option_map.get("direction")
    if explicit in ("outbound", "return"):
        return str(explicit)
    option_id = str(option_map.get("id") or "")
    if option_id.startswith("provider-aggregate:outbound:"):
        return "outbound"
    if option_id.startswith("provider-aggregate:return:"):
        return "return"
    raw_segments = option_map.get("segments")
    segments = raw_segments if isinstance(raw_segments, list) else []
    directions = {
        str(segment.get("direction"))
        for segment in segments
        if isinstance(segment, dict) and segment.get("direction")
    }
    if len(directions) == 1:
        only = next(iter(directions))
        if only in ("outbound", "return"):
            return only
    return None


def direction_segments(
    option: Mapping[str, Any] | None, direction: str
) -> list[dict[str, Any]]:
    option_map = option if isinstance(option, Mapping) else {}
    return [
        segment
        for segment in option_map.get("segments") or []
        if isinstance(segment, dict)
        and str(segment.get("direction") or "") == direction
    ]


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


def resolve_ticket_semantics(
    option: dict[str, Any], *, provider_aggregate: bool
) -> dict[str, Any]:
    """Resolve catalog ticketing, protection, and self-transfer exactly once."""

    raw = str(option.get("ticketing_model") or "").strip()
    upstream = (
        option.get("ticket_protection")
        if isinstance(option.get("ticket_protection"), dict)
        else {}
    )
    upstream_status = str(upstream.get("status") or "unknown").strip().lower()
    if upstream_status not in {"protected", "unprotected", "unknown"}:
        upstream_status = "unknown"

    proven_model = raw in _PROVEN_TICKETING_MODELS or (
        raw in {"round_trip_single_ticket", "single_pnr"}
        and upstream_status == "protected"
    )
    non_self_transfer_model = raw in _NON_SELF_TRANSFER_MODELS
    separate_one_way = raw in _SEPARATE_ONE_WAY_MODELS
    separate_segments = raw in _SEPARATE_SEGMENT_MODELS

    if proven_model:
        ticketing_model = "single_ticket_proven"
    elif separate_one_way:
        ticketing_model = "separate_one_way_offers"
    elif separate_segments:
        ticketing_model = "separate_segments"
    elif raw in _PROVIDER_AGGREGATE_MODELS or raw in _NON_SELF_TRANSFER_MODELS:
        ticketing_model = "provider_aggregate"
    elif raw == "unknown":
        ticketing_model = "unknown"
    elif provider_aggregate:
        ticketing_model = "provider_aggregate"
    else:
        ticketing_model = "separate_segments"

    protection_status = upstream_status
    protection_source = str(upstream.get("source") or "provider_evidence_incomplete")
    protection_reasons = [
        str(item) for item in upstream.get("reasons") or [] if str(item).strip()
    ]
    if protection_status == "unknown" and not protection_reasons:
        protection_reasons = ["ticket_protection_unproven"]

    if protection_status == "protected":
        protection = {
            "single_pnr_status": "proven",
            "through_baggage_status": "proven",
            "self_transfer": False,
            "purchase_screen_verification_required": False,
        }
    elif protection_status == "unprotected":
        protection = {
            "single_pnr_status": "unproven",
            "through_baggage_status": "unproven",
            "self_transfer": True,
            "purchase_screen_verification_required": True,
        }
    elif non_self_transfer_model or option.get("self_transfer") is False:
        protection = {
            "single_pnr_status": "unknown",
            "through_baggage_status": "unknown",
            "self_transfer": False,
            "purchase_screen_verification_required": True,
        }
    else:
        protection = {
            "single_pnr_status": "unknown",
            "through_baggage_status": "unknown",
            "self_transfer": None,
            "purchase_screen_verification_required": True,
        }

    return {
        "ticketing_model": ticketing_model,
        "ticket_protection": {
            "status": protection_status,
            "source": protection_source,
            "reasons": protection_reasons,
        },
        "protection": protection,
    }


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
    if option.get("max_connections_per_journey") is not None and stop_tier(
        int(option.get("max_connections_per_journey") or 0)
    ) in {"T2_TWO_STOP", "T3_THREE_PLUS"}:
        badges.append("two_stop_or_more")
    badges.extend(
        str(value) for value in option.get("option_badges") or [] if str(value).strip()
    )
    return list(dict.fromkeys(badges))


__all__ = [
    "direction_segments",
    "infer_journey_scope",
    "is_provider_aggregate_option",
    "option_direction",
    "option_provider_labels",
    "option_source_type",
    "resolve_ticket_semantics",
    "risk_badges",
    "route_requested_round_trip",
]
