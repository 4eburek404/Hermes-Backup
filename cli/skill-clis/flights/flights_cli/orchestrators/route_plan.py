from __future__ import annotations

import argparse
from typing import Any

from ..config import CACHE_NOTE, RISK_PROFILES, SINGLE_AIRPORT_NOTES, SUPPORTED_CURRENCIES
from ..domain.airports import airport_pair_risk, explicit_or_resolved_airports, explain_airport
from ..domain.normalize import normalize_iata, normalize_profile, parse_iso_date
from ..domain.routes import find_route_graph_candidates
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
    route_graph = None
    hub_source = "manual"
    if getattr(args, "auto_hubs", False):
        route_graph = find_route_graph_candidates(
            store,
            origin_airports,
            destination_airports,
            profile=profile,
            max_hubs=max(1, int(getattr(args, "max_auto_hubs", 10))),
        )
        graph_hubs = [candidate["hub"] for candidate in route_graph.get("one_stop_hubs", [])]
        manual_hubs = [normalize_iata(hub, "hub") for hub in (args.hub or [])]
        hubs = list(dict.fromkeys(graph_hubs + manual_hubs))
        hub_source = "routes_json"
        if manual_hubs:
            hub_source = "routes_json+manual"
    else:
        hubs = [normalize_iata(hub, "hub") for hub in (args.hub or [])]

    if not hubs:
        raise CliError("route hubs are required; pass --hub repeatedly or use --auto-hubs explicitly", error_type="validation_error")

    warnings: list[str] = [CACHE_NOTE]
    if destination.code == "LON":
        warnings.append("LON often returns empty in Travelpayouts; use specific London airports.")
    if origin.code == "LON":
        warnings.append("LON often returns empty in Travelpayouts; use specific London airports.")
    if any(hub in {"IST", "SAW"} for hub in hubs) and not {"IST", "SAW"}.issubset(set(hubs)):
        warnings.append("For Istanbul, query both IST and SAW when comparing hub options.")
    if "AYT" in hubs:
        warnings.append(SINGLE_AIRPORT_NOTES["AYT"])
    if route_graph:
        warnings.append("routes.json is a historical topology prior, not a current schedule source.")
        if route_graph.get("available") is False:
            warnings.append("routes.json is missing from cache; no automatic hubs were derived.")

    segments: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add_segment(direction: str, leg: str, dep_date: date, origin_code: str, dest_code: str) -> None:
        if origin_code == dest_code:
            return
        key = (direction, leg, origin_code, dest_code)
        if key in seen:
            return
        seen.add(key)
        segments.append(
            {
                "direction": direction,
                "leg": leg,
                "origin": origin_code,
                "destination": dest_code,
                "date": dep_date.isoformat(),
                "airport_pair_risk": airport_pair_risk(origin_code, dest_code),
                "request": compact_request_payload(
                    build_request_payload(origin_code, dest_code, dep_date, None, currency, args.direct_only)
                ),
                "command": segment_request_command(
                    origin_code,
                    dest_code,
                    dep_date,
                    currency=currency,
                    direct_only=args.direct_only,
                ),
            }
        )

    for origin_code in origin_airports:
        for hub in hubs:
            add_segment("outbound", "origin_to_hub", depart, origin_code, hub)
    for hub in hubs:
        for dest_code in destination_airports:
            add_segment("outbound", "hub_to_destination", depart, hub, dest_code)

    if ret:
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
        "dates": {"departure": depart.isoformat(), "return": ret.isoformat() if ret else None},
        "ticketing": args.ticketing,
        "profile": {
            "name": profile,
            "description": RISK_PROFILES[profile]["description"],
            "rank_order": RISK_PROFILES[profile]["rank_order"],
        },
        "segments": segments,
        "itinerary_families": itinerary_families,
        "route_graph": route_graph,
        "manual_links": {"aviasales": direct_links},
        "warnings": warnings,
        "metrics": {
            "without_cli": manual_ops,
            "with_cli": cli_ops,
            "segment_request_count": len(segments),
            "unique_airports_considered": sorted(set(origin_airports + destination_airports + hubs)),
            "profile_rank_order": RISK_PROFILES[profile]["rank_order"],
            "notes": [
                "Metrics are deterministic planning operations, not network fetch latency.",
                "The CLI does not call Travelpayouts during route plan.",
            ],
        },
    }
