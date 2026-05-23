from __future__ import annotations

import argparse
from datetime import date
from typing import Any

from ..config import (
    CACHE_NOTE,
    PRIORITY_ASIA_HUB,
    PRIORITY_MOSCOW_GATEWAY,
    PRIORITY_PRIMARY_HUB,
    PRIORITY_ROUTE_CARRIERS,
    PRIORITY_SECONDARY_HUB,
    RISK_PROFILES,
    SINGLE_AIRPORT_NOTES,
    SUPPORTED_CURRENCIES,
)
from ..domain.airports import airport_pair_risk, airport_priority_metadata, explicit_or_resolved_airports, explain_airport
from ..domain.normalize import normalize_carrier_code, normalize_profile, parse_iso_date
from ..errors import CliError
from ..adapters.providers.registry import providers_for_segment
from ..services.validation import connection_rule
from ..store import Store
from .route_graph import (
    coverage_controls_for_plan,
    resolve_route_graph_context,
    route_families_for_strategy,
    route_graph_from_segments,
    route_segment_key,
    route_segment_spec,
)


def segment_code_metadata(origin_code: str, dest_code: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    origin_priority = airport_priority_metadata(origin_code)
    destination_priority = airport_priority_metadata(dest_code)
    if origin_priority:
        metadata["origin_airport_priority"] = origin_priority
    if destination_priority:
        metadata["destination_airport_priority"] = destination_priority
    return metadata


def live_segment_command(spec: dict[str, Any], store: Store, currency: str, limit: int = 30) -> str:
    provider = providers_for_segment(spec, store, "auto")[0]
    origin = str(spec["origin"]).upper()
    destination = str(spec["destination"]).upper()
    date_text = str(spec["date"])
    carriers = [
        normalize_carrier_code(code, "only-carrier")
        for code in (spec.get("only_carriers") or [])
    ]
    if provider == "fli":
        parts = [
            "flights",
            "--json",
            "fli-search",
            origin,
            destination,
            "--depart-date",
            date_text,
            "--currency",
            currency,
            "--direct-only",
            "--limit",
            str(limit),
        ]
    else:
        parts = [
            "flights",
            "--json",
            "kb-search",
            origin,
            destination,
            "--depart-date",
            date_text,
            "--currency",
            currency,
            "--direct-only",
            "--limit",
            str(limit),
        ]
    for carrier in carriers:
        parts.extend(["--only-carrier", carrier])
    return " ".join(parts)


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
    route_context = resolve_route_graph_context(args, store, origin, destination, origin_airports, destination_airports)
    routing_strategy = route_context.routing_strategy
    hubs = route_context.hubs
    hub_source = route_context.hub_source
    routing_profile = route_context.routing_profile

    warnings: list[str] = [CACHE_NOTE]
    if routing_strategy == "ru-priority":
        if routing_profile == "asia-oceania":
            warnings.append("Using geo-aware ru-priority routing: direct control, SVO as an independent Asia/Oceania hub, IST fallback, DXB only if priority routes are not usable.")
        else:
            warnings.append("Using ru-priority routing: direct control, IST direct first, SVO/Moscow gateway control even when direct exists, DXB only if priority routes are not usable.")
    elif routing_strategy == "domestic-ru":
        warnings.append("Using domestic-RU routing: direct domestic controls first, Moscow airports only as bounded fallback; international hubs are excluded by default.")
    elif hub_source == "default":
        warnings.append("Using built-in hub list; pass --hub repeatedly to narrow the plan.")
    if destination.code == "LON":
        warnings.append("LON is broad and provider-dependent; use specific London airports for decision-grade checks.")
    if origin.code == "LON":
        warnings.append("LON is broad and provider-dependent; use specific London airports for decision-grade checks.")
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
        **extra: Any,
    ) -> None:
        if origin_code == dest_code:
            return
        spec = route_segment_spec(direction, leg, dep_date, origin_code, dest_code, **segment_code_metadata(origin_code, dest_code), **extra)
        key = route_segment_key(spec, include_date=False)
        if key in seen:
            return
        seen.add(key)
        segments.append(
            {
                **spec,
                "airport_pair_risk": airport_pair_risk(origin_code, dest_code),
                "provider_policy": "auto",
                "command": live_segment_command(spec, store, currency),
            }
        )

    route_families = route_families_for_strategy(routing_strategy, routing_profile)
    if routing_strategy == "ru-priority":
        for origin_code in origin_airports:
            for dest_code in destination_airports:
                add_segment(
                    "outbound",
                    "direct_outbound",
                    depart,
                    origin_code,
                    dest_code,
                    route_family="direct_control",
                    priority=0,
                    condition="direct exact-airport control",
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                )
        if routing_profile == "asia-oceania":
            for origin_code in origin_airports:
                add_segment(
                    "outbound",
                    "origin_to_hub",
                    depart,
                    origin_code,
                    PRIORITY_ASIA_HUB,
                    route_family="svo_asia",
                    priority=1,
                    condition="primary Asia/Oceania hub",
                    only_carriers=["SU"],
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                )
            for dest_code in destination_airports:
                add_segment(
                    "outbound",
                    "hub_to_destination",
                    depart,
                    PRIORITY_ASIA_HUB,
                    dest_code,
                    route_family="svo_asia",
                    priority=1,
                    condition="primary Asia/Oceania hub",
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                )
        for origin_code in origin_airports:
            add_segment(
                "outbound",
                "origin_to_hub",
                depart,
                origin_code,
                PRIORITY_PRIMARY_HUB,
                route_family="ist_direct",
                priority=2 if routing_profile == "asia-oceania" else 1,
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
                    route_family="moscow_gateway_control",
                    priority=3 if routing_profile == "asia-oceania" else 2,
                    condition="Moscow/SVO control; run even if origin->IST direct exists",
                    only_carriers=["SU"],
                )
            add_segment(
                "outbound",
                "gateway_to_hub",
                depart,
                PRIORITY_MOSCOW_GATEWAY,
                PRIORITY_PRIMARY_HUB,
                route_family="moscow_gateway_control",
                priority=3 if routing_profile == "asia-oceania" else 2,
                condition="pairs with origin->SVO Moscow control",
                only_carriers=["SU"],
            )
        for dest_code in destination_airports:
            add_segment(
                "outbound",
                "hub_to_destination",
                depart,
                PRIORITY_PRIMARY_HUB,
                dest_code,
                route_family="ist_shared_destination",
                priority=2 if routing_profile == "asia-oceania" else 1,
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
                route_family="dxb_direct",
                priority=4 if routing_profile == "asia-oceania" else 3,
                condition="secondary direct-only fallback, only if priority routes are not usable; no Moscow expansion",
                preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
            )
        for dest_code in destination_airports:
            add_segment(
                "outbound",
                "hub_to_destination",
                depart,
                PRIORITY_SECONDARY_HUB,
                dest_code,
                route_family="dxb_direct",
                priority=4 if routing_profile == "asia-oceania" else 3,
                condition="secondary direct-only fallback, only if priority routes are not usable",
                preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
            )
    elif routing_strategy == "domestic-ru":
        for origin_code in origin_airports:
            for dest_code in destination_airports:
                add_segment(
                    "outbound",
                    "direct_outbound",
                    depart,
                    origin_code,
                    dest_code,
                    route_family="domestic_ru",
                    priority=0,
                    condition="domestic direct control",
                )
        for origin_code in origin_airports:
            for hub in hubs:
                add_segment("outbound", "origin_to_hub", depart, origin_code, hub, route_family="domestic_ru", priority=1)
        for hub in hubs:
            for dest_code in destination_airports:
                add_segment("outbound", "hub_to_destination", depart, hub, dest_code, route_family="domestic_ru", priority=1)
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
                for origin_code in origin_airports:
                    add_segment(
                        "return",
                        "direct_return",
                        ret,
                        dest_code,
                        origin_code,
                        route_family="direct_control",
                        priority=0,
                        condition="direct exact-airport return control",
                        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    )
            if routing_profile == "asia-oceania":
                for dest_code in destination_airports:
                    add_segment(
                        "return",
                        "destination_to_hub",
                        ret,
                        dest_code,
                        PRIORITY_ASIA_HUB,
                        route_family="svo_asia",
                        priority=1,
                        condition="primary Asia/Oceania return hub",
                        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    )
                for origin_code in origin_airports:
                    add_segment(
                        "return",
                        "hub_to_origin",
                        ret,
                        PRIORITY_ASIA_HUB,
                        origin_code,
                        route_family="svo_asia",
                        priority=1,
                        condition="primary Asia/Oceania return hub",
                        only_carriers=["SU"],
                        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    )
            for dest_code in destination_airports:
                add_segment(
                    "return",
                    "destination_to_hub",
                    ret,
                    dest_code,
                    PRIORITY_PRIMARY_HUB,
                    route_family="ist_direct",
                    priority=2 if routing_profile == "asia-oceania" else 1,
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
                    route_family="ist_direct",
                    priority=2 if routing_profile == "asia-oceania" else 1,
                    condition="use IST->origin direct when available",
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                )
                add_segment(
                    "return",
                    "hub_to_gateway",
                    ret,
                    PRIORITY_PRIMARY_HUB,
                    PRIORITY_MOSCOW_GATEWAY,
                    route_family="moscow_gateway_control",
                    priority=3 if routing_profile == "asia-oceania" else 2,
                    condition="Moscow/SVO return control; run even if IST->origin direct exists",
                    only_carriers=["SU"],
                )
                if origin_code != PRIORITY_MOSCOW_GATEWAY:
                    add_segment(
                        "return",
                        "gateway_to_origin",
                        ret,
                        PRIORITY_MOSCOW_GATEWAY,
                        origin_code,
                        route_family="moscow_gateway_control",
                        priority=3 if routing_profile == "asia-oceania" else 2,
                        condition="pairs with IST->SVO Moscow return control",
                        only_carriers=["SU"],
                    )
            for dest_code in destination_airports:
                add_segment(
                    "return",
                    "destination_to_hub",
                    ret,
                    dest_code,
                    PRIORITY_SECONDARY_HUB,
                    route_family="dxb_direct",
                    priority=4 if routing_profile == "asia-oceania" else 3,
                    condition="secondary direct-only return fallback, only if priority routes are not usable",
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                )
            for origin_code in origin_airports:
                add_segment(
                    "return",
                    "hub_to_origin",
                    ret,
                    PRIORITY_SECONDARY_HUB,
                    origin_code,
                    route_family="dxb_direct",
                    priority=4 if routing_profile == "asia-oceania" else 3,
                    condition="secondary direct-only return fallback, only if priority routes are not usable; no Moscow expansion",
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                )
        elif routing_strategy == "domestic-ru":
            for dest_code in destination_airports:
                for origin_code in origin_airports:
                    add_segment(
                        "return",
                        "direct_return",
                        ret,
                        dest_code,
                        origin_code,
                        route_family="domestic_ru",
                        priority=0,
                        condition="domestic direct return control",
                    )
            for dest_code in destination_airports:
                for hub in hubs:
                    add_segment(
                        "return",
                        "destination_to_hub",
                        ret,
                        dest_code,
                        hub,
                        route_family="domestic_ru",
                        priority=1,
                    )
            for hub in hubs:
                for origin_code in origin_airports:
                    add_segment(
                        "return",
                        "hub_to_origin",
                        ret,
                        hub,
                        origin_code,
                        route_family="domestic_ru",
                        priority=1,
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
    }
    cli_ops = {
        "route_plan_commands": 1,
        "generated_segment_commands": len(segments),
        "route_validate_command_after_results": 1,
        "airport_rules_embedded": True,
    }

    coverage_controls = coverage_controls_for_plan(
        coverage_mode=route_context.coverage_mode,
        origin_code=str(origin.code).upper(),
        destination_code=str(destination.code).upper(),
        origin_airports=origin_airports,
        destination_airports=destination_airports,
        depart=depart,
        ret=ret,
        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
        requested_controls=route_context.coverage_limits.get("requested_controls"),
        coverage_control_limit=route_context.coverage_limits.get("coverage_control_limit"),
    )
    route_graph = route_graph_from_segments(
        routing_strategy=routing_strategy,
        routing_profile=routing_profile,
        hubs=hubs,
        origin_airports=origin_airports,
        destination_airports=destination_airports,
        segments=segments,
    )

    return {
        "origin": origin.to_dict(),
        "destination": destination.to_dict(),
        "origin_airports": origin_airports,
        "destination_airports": destination_airports,
        "hubs": hubs,
        "hub_source": hub_source,
        "routing_strategy": routing_strategy,
        "routing_profile": routing_profile,
        "airport_scope": route_context.airport_scope,
        "coverage_mode": route_context.coverage_mode,
        "coverage_controls": coverage_controls,
        "coverage_limits": route_context.coverage_limits,
        "route_graph": route_graph,
        "route_families": route_families,
        "dates": {
            "depart": depart.isoformat(),
            "departure": depart.isoformat(),
            "return": ret.isoformat() if ret else None,
        },
        "second_leg_day_offsets": {
            "outbound": [0],
            "return": [0] if ret else [],
            "mode": "dry_plan_same_day_only",
            "note": "Dry route plan models same-day second legs; live assembly may expand second-leg offsets.",
        },
        "ticketing": args.ticketing,
        "profile": {
            "name": profile,
            "description": RISK_PROFILES[profile]["description"],
            "rank_order": RISK_PROFILES[profile]["rank_order"],
        },
        "segments": segments,
        "itinerary_families": itinerary_families,
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
                "The CLI does not call retired Travelpayouts price APIs during route plan.",
            ],
        },
    }
