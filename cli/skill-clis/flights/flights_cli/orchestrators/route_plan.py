from __future__ import annotations

import argparse
from typing import Any

from ..config import (
    CACHE_NOTE,
    PRIORITY_MOSCOW_GATEWAY,
    PRIORITY_PRIMARY_HUB,
    PRIORITY_ROUTE_CARRIERS,
    PRIORITY_SECONDARY_HUB,
    RISK_PROFILES,
    SINGLE_AIRPORT_NOTES,
    SUPPORTED_CURRENCIES,
)
from ..domain.airports import airport_pair_risk, explicit_or_resolved_airports, explain_airport
from ..domain.hubs import resolve_route_hubs, resolve_routing_strategy
from ..domain.normalize import normalize_profile, parse_iso_date
from ..errors import CliError
from ..providers.travelpayouts import aviasales_url, build_request_payload, compact_request_payload, segment_request_command
from ..services.validation import connection_rule
from ..store import Store

def build_route_plan(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    depart = parse_iso_date(args.depart_date, "depart-date")
    ret = parse_iso_date(args.return_date, "return-date") if args.return_date else None
    currency = args.currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise CliError(f"currency must be one of {', '.join(sorted(SUPPORTED_CURRENCIES))}", error_type="validation_error")
    profile = normalize_profile(getattr(args, "profile", "balanced"))

    origin = store.resolve_location(args.origin)
    destination = store.resolve_location(args.destination)

    origin_airports = explicit_or_resolved_airports(
        store, origin, args.origin_airport, role="origin", max_airports=args.max_airports_per_city
    )
    destination_airports = explicit_or_resolved_airports(
        store, destination, args.destination_airport, role="destination", max_airports=args.max_airports_per_city
    )
    try:
        routing_strategy = resolve_routing_strategy(getattr(args, "routing_strategy", None), args.hub)
    except ValueError as exc:
        raise CliError(str(exc), error_type="validation_error") from exc
    hubs, hub_source = resolve_route_hubs(args.hub)
    if routing_strategy == "ru-priority":
        hubs = [PRIORITY_PRIMARY_HUB, PRIORITY_SECONDARY_HUB]
        hub_source = "strategy"

    warnings: list[str] = [CACHE_NOTE]
    if routing_strategy == "ru-priority":
        warnings.append("Using ru-priority routing: IST direct first, SVO/SU fallback only if IST direct is empty, DXB only if IST has no usable assembled pair.")
    elif hub_source == "default":
        warnings.append("Using built-in hub list; pass --hub repeatedly to narrow the plan.")
    if destination.code == "LON":
        warnings.append("LON often returns empty in Travelpayouts; use specific London airports.")
    if origin.code == "LON":
        warnings.append("LON often returns empty in Travelpayouts; use specific London airports.")
    if hub_source == "manual" and any(hub in {"IST", "SAW"} for hub in hubs) and not {"IST", "SAW"}.issubset(set(hubs)):
        warnings.append("For Istanbul, query both IST and SAW when comparing hub options.")
    if "AYT" in hubs:
        warnings.append(SINGLE_AIRPORT_NOTES["AYT"])

    segments: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add_segment(
        direction: str,
        leg: str,
        dep_date: date,
        origin_code: str,
        dest_code: str,
        *,
        direct_only: bool | None = None,
        **extra: Any,
    ) -> None:
        if origin_code == dest_code:
            return
        key = (direction, leg, origin_code, dest_code)
        if key in seen:
            return
        seen.add(key)
        request_direct_only = args.direct_only if direct_only is None else direct_only
        segments.append(
            {
                "direction": direction,
                "leg": leg,
                "origin": origin_code,
                "destination": dest_code,
                "date": dep_date.isoformat(),
                "airport_pair_risk": airport_pair_risk(origin_code, dest_code),
                "request": compact_request_payload(
                    build_request_payload(origin_code, dest_code, dep_date, None, currency, request_direct_only)
                ),
                "command": segment_request_command(
                    origin_code,
                    dest_code,
                    dep_date,
                    currency=currency,
                    direct_only=request_direct_only,
                ),
                **extra,
            }
        )

    route_families: list[dict[str, Any]] = []
    if routing_strategy == "ru-priority":
        route_families = [
            {
                "id": "ist_direct",
                "priority": 1,
                "hub": PRIORITY_PRIMARY_HUB,
                "condition": "check first; use origin->IST direct when available",
                "preferred_carriers": list(PRIORITY_ROUTE_CARRIERS),
            },
            {
                "id": "ist_svo_su_fallback",
                "priority": 2,
                "hub": PRIORITY_PRIMARY_HUB,
                "via": [PRIORITY_MOSCOW_GATEWAY],
                "condition": "use only when origin->IST direct has no viable direct offers",
                "required_carriers": ["SU"],
                "preferred_carriers": list(PRIORITY_ROUTE_CARRIERS),
            },
            {
                "id": "dxb_direct",
                "priority": 3,
                "hub": PRIORITY_SECONDARY_HUB,
                "condition": "check only if IST does not produce a usable assembled pair; do not expand origin->DXB through Moscow",
                "preferred_carriers": list(PRIORITY_ROUTE_CARRIERS),
            },
        ]
        for origin_code in origin_airports:
            add_segment(
                "outbound",
                "origin_to_hub",
                depart,
                origin_code,
                PRIORITY_PRIMARY_HUB,
                direct_only=True,
                route_family="ist_direct",
                priority=1,
                condition="primary direct probe",
                preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
            )
            if origin_code != PRIORITY_MOSCOW_GATEWAY:
                add_segment(
                    "outbound",
                    "origin_to_gateway",
                    depart,
                    origin_code,
                    PRIORITY_MOSCOW_GATEWAY,
                    direct_only=True,
                    route_family="ist_svo_su_fallback",
                    priority=2,
                    condition="run only if origin->IST direct is empty",
                    only_carriers=["SU"],
                )
            add_segment(
                "outbound",
                "gateway_to_hub",
                depart,
                PRIORITY_MOSCOW_GATEWAY,
                PRIORITY_PRIMARY_HUB,
                direct_only=True,
                route_family="ist_svo_su_fallback",
                priority=2,
                condition="pairs with origin->SVO fallback",
                only_carriers=["SU"],
            )
        for dest_code in destination_airports:
            add_segment(
                "outbound",
                "hub_to_destination",
                depart,
                PRIORITY_PRIMARY_HUB,
                dest_code,
                direct_only=True,
                route_family="ist_shared_destination",
                priority=1,
                condition="needed for both IST direct and SVO fallback families",
                preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
            )
        for origin_code in origin_airports:
            add_segment(
                "outbound",
                "origin_to_hub",
                depart,
                origin_code,
                PRIORITY_SECONDARY_HUB,
                direct_only=True,
                route_family="dxb_direct",
                priority=3,
                condition="secondary direct-only fallback, only if IST assembled pair is not usable; no Moscow expansion",
                preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
            )
        for dest_code in destination_airports:
            add_segment(
                "outbound",
                "hub_to_destination",
                depart,
                PRIORITY_SECONDARY_HUB,
                dest_code,
                direct_only=True,
                route_family="dxb_direct",
                priority=3,
                condition="secondary direct-only fallback, only if IST assembled pair is not usable",
                preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
            )
    else:
        for origin_code in origin_airports:
            for hub in hubs:
                add_segment("outbound", "origin_to_hub", depart, origin_code, hub)
        for hub in hubs:
            for dest_code in destination_airports:
                add_segment("outbound", "hub_to_destination", depart, hub, dest_code)

    if ret:
        if routing_strategy == "ru-priority":
            for dest_code in destination_airports:
                add_segment(
                    "return",
                    "destination_to_hub",
                    ret,
                    dest_code,
                    PRIORITY_PRIMARY_HUB,
                    direct_only=True,
                    route_family="ist_direct",
                    priority=1,
                    condition="primary direct return probe",
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                )
            for origin_code in origin_airports:
                add_segment(
                    "return",
                    "hub_to_origin",
                    ret,
                    PRIORITY_PRIMARY_HUB,
                    origin_code,
                    direct_only=True,
                    route_family="ist_direct",
                    priority=1,
                    condition="use IST->origin direct when available",
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                )
                add_segment(
                    "return",
                    "hub_to_gateway",
                    ret,
                    PRIORITY_PRIMARY_HUB,
                    PRIORITY_MOSCOW_GATEWAY,
                    direct_only=True,
                    route_family="ist_svo_su_fallback",
                    priority=2,
                    condition="run only if IST->origin direct is empty",
                    only_carriers=["SU"],
                )
                if origin_code != PRIORITY_MOSCOW_GATEWAY:
                    add_segment(
                        "return",
                        "gateway_to_origin",
                        ret,
                        PRIORITY_MOSCOW_GATEWAY,
                        origin_code,
                        direct_only=True,
                        route_family="ist_svo_su_fallback",
                        priority=2,
                        condition="pairs with IST->SVO return fallback",
                        only_carriers=["SU"],
                    )
            for dest_code in destination_airports:
                add_segment(
                    "return",
                    "destination_to_hub",
                    ret,
                    dest_code,
                    PRIORITY_SECONDARY_HUB,
                    direct_only=True,
                    route_family="dxb_direct",
                    priority=3,
                    condition="secondary direct-only return fallback, only if IST assembled pair is not usable",
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                )
            for origin_code in origin_airports:
                add_segment(
                    "return",
                    "hub_to_origin",
                    ret,
                    PRIORITY_SECONDARY_HUB,
                    origin_code,
                    direct_only=True,
                    route_family="dxb_direct",
                    priority=3,
                    condition="secondary direct-only return fallback, only if IST assembled pair is not usable; no Moscow expansion",
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                )
        else:
            for dest_code in destination_airports:
                for hub in hubs:
                    add_segment("return", "destination_to_hub", ret, dest_code, hub)
            for hub in hubs:
                for origin_code in origin_airports:
                    add_segment("return", "hub_to_origin", ret, hub, origin_code)

    itinerary_families = []
    for hub in hubs:
        hub_info = explain_airport(store, hub)
        outbound_checks = [
            connection_rule(hub, hub, args.ticketing, args.min_same_airport_min, args.min_cross_airport_min)
        ]
        return_checks = outbound_checks if ret else []
        itinerary_families.append(
            {
                "hub": hub,
                "hub_info": hub_info,
                "outbound_airport_compatibility": outbound_checks,
                "return_airport_compatibility": return_checks,
            }
        )

    manual_ops = {
        "airport_expansions": 2,
        "hub_candidates": len(hubs),
        "segment_queries_to_prepare": len(segments),
        "airport_pair_risk_checks": len(segments),
        "route_family_compatibility_checks": len(hubs) * (2 if ret else 1),
        "manual_aviasales_links": len(origin_airports) * len(destination_airports),
    }
    cli_ops = {
        "route_plan_commands": 1,
        "generated_segment_commands": len(segments),
        "route_validate_command_after_results": 1,
        "airport_rules_embedded": True,
    }

    direct_links = [
        {
            "origin": origin_code,
            "destination": dest_code,
            "url": aviasales_url(origin_code, dest_code, depart, ret),
        }
        for origin_code in origin_airports
        for dest_code in destination_airports
    ]

    return {
        "origin": origin.to_dict(),
        "destination": destination.to_dict(),
        "origin_airports": origin_airports,
        "destination_airports": destination_airports,
        "hubs": hubs,
        "hub_source": hub_source,
        "routing_strategy": routing_strategy,
        "route_families": route_families,
        "dates": {"departure": depart.isoformat(), "return": ret.isoformat() if ret else None},
        "ticketing": args.ticketing,
        "profile": {
            "name": profile,
            "description": RISK_PROFILES[profile]["description"],
            "rank_order": RISK_PROFILES[profile]["rank_order"],
        },
        "segments": segments,
        "itinerary_families": itinerary_families,
        "manual_links": {"aviasales": direct_links},
        "warnings": warnings,
        "metrics": {
            "without_cli": manual_ops,
            "with_cli": cli_ops,
            "segment_request_count": len(segments),
            "unique_airports_considered": sorted(
                set(origin_airports + destination_airports + hubs)
                | {segment["origin"] for segment in segments}
                | {segment["destination"] for segment in segments}
            ),
            "profile_rank_order": RISK_PROFILES[profile]["rank_order"],
            "notes": [
                "Metrics are deterministic planning operations, not network fetch latency.",
                "The CLI does not call Travelpayouts during route plan.",
            ],
        },
    }
