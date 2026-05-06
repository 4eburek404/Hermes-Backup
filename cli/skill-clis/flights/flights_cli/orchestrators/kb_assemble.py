from __future__ import annotations

import argparse
from datetime import timedelta
from typing import Any

from ..config import (
    DEFAULT_KB_ROUTE_OUTBOUND_SECOND_LEG_DAY_OFFSETS,
    DEFAULT_KB_ROUTE_RETURN_SECOND_LEG_DAY_OFFSETS,
    PRIORITY_MOSCOW_GATEWAY,
    PRIORITY_PRIMARY_HUB,
    PRIORITY_ROUTE_CARRIERS,
    PRIORITY_SECONDARY_HUB,
    SUPPORTED_CURRENCIES,
)
from ..domain.airports import explicit_or_resolved_airports
from ..domain.hubs import resolve_route_hubs, resolve_routing_strategy
from ..domain.normalize import currency_value, normalize_carrier_code, normalize_profile, parse_iso_date, price_value
from ..errors import CliError
from ..providers.kupibilet import fetch_kupibilet_search, kupibilet_result_to_segment_result, kupibilet_segment_search_summary
from ..services.assembly import assemble_direction, assemble_segment_results, empty_assembled_result
from ..store import Store

def normalize_day_offsets(values: list[int] | None, default: list[int], field: str) -> list[int]:
    raw_values = default if values is None else values
    offsets: list[int] = []
    for value in raw_values:
        try:
            offset = int(value)
        except (TypeError, ValueError) as exc:
            raise CliError(f"{field} must be an integer day offset, got {value!r}", error_type="validation_error") from exc
        if offset < 0 or offset > 7:
            raise CliError(f"{field} must be between 0 and 7 days, got {offset}", error_type="validation_error")
        if offset not in offsets:
            offsets.append(offset)
    return offsets


def hub_viability_summary(plan: dict[str, Any], searches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_hub: dict[str, dict[str, Any]] = {
        hub: {
            "hub": hub,
            "viable": False,
            "total_offer_count": 0,
            "legs": {
                "origin_to_hub": {"offer_count": 0, "search_count": 0, "dates": []},
                "hub_to_destination": {"offer_count": 0, "search_count": 0, "dates": []},
                "destination_to_hub": {"offer_count": 0, "search_count": 0, "dates": []},
                "hub_to_origin": {"offer_count": 0, "search_count": 0, "dates": []},
            },
            "missing_legs": [],
        }
        for hub in plan["hubs"]
    }
    for search in searches:
        leg = search.get("leg")
        if leg == "origin_to_hub":
            hub = search.get("destination")
        elif leg == "hub_to_destination":
            hub = search.get("origin")
        elif leg == "destination_to_hub":
            hub = search.get("destination")
        elif leg == "hub_to_origin":
            hub = search.get("origin")
        else:
            continue
        if hub not in by_hub or leg not in by_hub[hub]["legs"]:
            continue
        leg_summary = by_hub[hub]["legs"][leg]
        leg_summary["search_count"] += 1
        leg_summary["offer_count"] += int(search.get("offer_count") or 0)
        date = search.get("date")
        if date and date not in leg_summary["dates"]:
            leg_summary["dates"].append(date)
        by_hub[hub]["total_offer_count"] += int(search.get("offer_count") or 0)

    required_legs = ["origin_to_hub", "hub_to_destination"]
    if plan["dates"].get("return"):
        required_legs += ["destination_to_hub", "hub_to_origin"]
    for item in by_hub.values():
        item["missing_legs"] = [
            leg
            for leg in required_legs
            if int(item["legs"][leg]["offer_count"]) <= 0
        ]
        item["viable"] = not item["missing_legs"]
    return sorted(by_hub.values(), key=lambda item: (not item["viable"], -int(item["total_offer_count"]), item["hub"]))


def segment_result_matches(result: dict[str, Any], direction: str, leg: str, origin: str, destination: str) -> bool:
    query = result.get("query") if isinstance(result.get("query"), dict) else {}
    return (
        result.get("direction") == direction
        and result.get("leg") == leg
        and str(query.get("origin") or "").upper() == origin
        and str(query.get("destination") or "").upper() == destination
    )


def direct_offer_count(segment_results: list[dict[str, Any]], direction: str, leg: str, origin: str, destination: str) -> int:
    return sum(
        len(result.get("offers") or [])
        for result in segment_results
        if segment_result_matches(result, direction, leg, origin, destination)
    )


def combined_offer(first: dict[str, Any], second: dict[str, Any], *, direction: str, leg: str, index: int) -> dict[str, Any] | None:
    first_arrival = str(first.get("arrival_airport") or first.get("destination") or "").upper()
    second_departure = str(second.get("departure_airport") or second.get("origin") or "").upper()
    if not first_arrival or first_arrival != second_departure:
        return None
    first_segments = [segment for segment in (first.get("segments") or []) if isinstance(segment, dict)]
    second_segments = [segment for segment in (second.get("segments") or []) if isinstance(segment, dict)]
    segments = first_segments + second_segments
    if len(segments) < 2:
        return None
    price = 0
    has_price = False
    for offer in (first, second):
        value = price_value(offer)
        if value is not None:
            price += value
            has_price = True
    currency = currency_value(first) or currency_value(second)
    return {
        "id": f"synthetic:{direction}:{leg}:{segments[0]['origin']}-{segments[-1]['destination']}:{index}",
        "direction": direction,
        "leg": leg,
        "query_origin": segments[0]["origin"],
        "query_destination": segments[-1]["destination"],
        "query_date": str(first.get("query_date") or ""),
        "origin": segments[0]["origin"],
        "destination": segments[-1]["destination"],
        "departure_airport": segments[0]["origin"],
        "arrival_airport": segments[-1]["destination"],
        "departure_at": segments[0].get("departure_at"),
        "arrival_at": segments[-1].get("arrival_at"),
        "price": price if has_price else None,
        "currency": currency,
        "carrier": segments[0].get("carrier"),
        "main_airline": segments[0].get("carrier"),
        "changes": 1,
        "duration_min": None,
        "source": "Kupibilet synthesized Moscow fallback",
        "segments": segments,
        "transfers": [],
        "internal_connection_count": max(0, len(segments) - 1),
        "synthetic": True,
        "source_offers": [
            {"id": first.get("id"), "origin": first.get("origin"), "destination": first.get("destination")},
            {"id": second.get("id"), "origin": second.get("origin"), "destination": second.get("destination")},
        ],
    }


def synthesize_priority_fallback_results(
    plan: dict[str, Any],
    segment_results: list[dict[str, Any]],
    directions: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if plan.get("routing_strategy") != "ru-priority":
        return [], []

    synthetic_results: list[dict[str, Any]] = []
    synthetic_searches: list[dict[str, Any]] = []

    def synthesize(
        *,
        direction: str,
        direct_leg: str,
        first_leg: str,
        second_leg: str,
        origin: str,
        gateway: str,
        destination: str,
    ) -> None:
        if direct_offer_count(segment_results, direction, direct_leg, origin, destination) > 0:
            return
        first_results = [
            result
            for result in segment_results
            if segment_result_matches(result, direction, first_leg, origin, gateway)
        ]
        second_results = [
            result
            for result in segment_results
            if segment_result_matches(result, direction, second_leg, gateway, destination)
        ]
        offers: list[dict[str, Any]] = []
        for first_result in first_results:
            for first_offer in first_result.get("offers") or []:
                if not isinstance(first_offer, dict):
                    continue
                for second_result in second_results:
                    for second_offer in second_result.get("offers") or []:
                        if not isinstance(second_offer, dict):
                            continue
                        offer = combined_offer(first_offer, second_offer, direction=direction, leg=direct_leg, index=len(offers) + 1)
                        if offer is not None:
                            offers.append(offer)
        if not offers:
            return
        query_date = str(offers[0].get("query_date") or "")
        synthetic_results.append(
            {
                "direction": direction,
                "leg": direct_leg,
                "query": {
                    "origin": origin,
                    "destination": destination,
                    "date": query_date,
                    "currency": plan["currency"],
                },
                "source_key": "synthetic_moscow_fallback",
                "source": "Kupibilet synthesized Moscow fallback",
                "raw_count": len(offers),
                "parse_errors": 0,
                "offers": offers,
                "synthetic": True,
            }
        )
        synthetic_searches.append(
            {
                "direction": direction,
                "leg": direct_leg,
                "origin": origin,
                "destination": destination,
                "date": query_date,
                "status": "synthetic",
                "route_family": "ist_svo_su_fallback",
                "offer_count": len(offers),
                "source_legs": [first_leg, second_leg],
            }
        )

    for origin in plan.get("origin_airports") or []:
        if (directions is None or "outbound" in directions) and origin != PRIORITY_MOSCOW_GATEWAY:
            synthesize(
                direction="outbound",
                direct_leg="origin_to_hub",
                first_leg="origin_to_gateway",
                second_leg="gateway_to_hub",
                origin=origin,
                gateway=PRIORITY_MOSCOW_GATEWAY,
                destination=PRIORITY_PRIMARY_HUB,
            )
        if (directions is None or "return" in directions) and plan["dates"].get("return") and origin != PRIORITY_MOSCOW_GATEWAY:
            synthesize(
                direction="return",
                direct_leg="hub_to_origin",
                first_leg="hub_to_gateway",
                second_leg="gateway_to_origin",
                origin=PRIORITY_PRIMARY_HUB,
                gateway=PRIORITY_MOSCOW_GATEWAY,
                destination=origin,
            )

    return synthetic_results, synthetic_searches


def build_kupibilet_route_segment_plan(args: argparse.Namespace, store: Store) -> dict[str, Any]:
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
    outbound_second_offsets = normalize_day_offsets(
        getattr(args, "outbound_second_leg_day_offset", None),
        DEFAULT_KB_ROUTE_OUTBOUND_SECOND_LEG_DAY_OFFSETS,
        "outbound-second-leg-day-offset",
    )
    return_second_offsets = normalize_day_offsets(
        getattr(args, "return_second_leg_day_offset", None),
        DEFAULT_KB_ROUTE_RETURN_SECOND_LEG_DAY_OFFSETS,
        "return-second-leg-day-offset",
    )

    segments: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    def add_segment(direction: str, leg: str, dep_date: date, origin_code: str, dest_code: str, **extra: Any) -> None:
        if origin_code == dest_code:
            return
        key = (direction, leg, origin_code, dest_code, dep_date.isoformat())
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
                "condition": "run only when origin->IST direct has no viable direct offers",
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
                route_family="ist_direct",
                priority=1,
                preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
            )
            if origin_code != PRIORITY_MOSCOW_GATEWAY:
                direct_key = {
                    "direction": "outbound",
                    "leg": "origin_to_hub",
                    "origin": origin_code,
                    "destination": PRIORITY_PRIMARY_HUB,
                }
                add_segment(
                    "outbound",
                    "origin_to_gateway",
                    depart,
                    origin_code,
                    PRIORITY_MOSCOW_GATEWAY,
                    route_family="ist_svo_su_fallback",
                    priority=2,
                    only_carriers=["SU"],
                    skip_if_offer_exists=direct_key,
                )
                add_segment(
                    "outbound",
                    "gateway_to_hub",
                    depart,
                    PRIORITY_MOSCOW_GATEWAY,
                    PRIORITY_PRIMARY_HUB,
                    route_family="ist_svo_su_fallback",
                    priority=2,
                    only_carriers=["SU"],
                    skip_if_offer_exists=direct_key,
                )
        for offset in outbound_second_offsets:
            leg_date = depart + timedelta(days=offset)
            for dest_code in destination_airports:
                add_segment(
                    "outbound",
                    "hub_to_destination",
                    leg_date,
                    PRIORITY_PRIMARY_HUB,
                    dest_code,
                    route_family="ist_shared_destination",
                    priority=1,
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
                priority=3,
                preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                skip_if_priority_ist_viable="outbound",
            )
        for offset in outbound_second_offsets:
            leg_date = depart + timedelta(days=offset)
            for dest_code in destination_airports:
                add_segment(
                    "outbound",
                    "hub_to_destination",
                    leg_date,
                    PRIORITY_SECONDARY_HUB,
                    dest_code,
                    route_family="dxb_direct",
                    priority=3,
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    skip_if_priority_ist_viable="outbound",
                )
    else:
        for origin_code in origin_airports:
            for hub in hubs:
                add_segment("outbound", "origin_to_hub", depart, origin_code, hub)
        for offset in outbound_second_offsets:
            leg_date = depart + timedelta(days=offset)
            for hub in hubs:
                for dest_code in destination_airports:
                    add_segment("outbound", "hub_to_destination", leg_date, hub, dest_code)

    if ret:
        if routing_strategy == "ru-priority":
            for dest_code in destination_airports:
                add_segment(
                    "return",
                    "destination_to_hub",
                    ret,
                    dest_code,
                    PRIORITY_PRIMARY_HUB,
                    route_family="ist_direct",
                    priority=1,
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                )
            for offset in return_second_offsets:
                leg_date = ret + timedelta(days=offset)
                for origin_code in origin_airports:
                    add_segment(
                        "return",
                        "hub_to_origin",
                        leg_date,
                        PRIORITY_PRIMARY_HUB,
                        origin_code,
                        route_family="ist_direct",
                        priority=1,
                        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    )
                    if origin_code != PRIORITY_MOSCOW_GATEWAY:
                        direct_key = {
                            "direction": "return",
                            "leg": "hub_to_origin",
                            "origin": PRIORITY_PRIMARY_HUB,
                            "destination": origin_code,
                        }
                        add_segment(
                            "return",
                            "hub_to_gateway",
                            leg_date,
                            PRIORITY_PRIMARY_HUB,
                            PRIORITY_MOSCOW_GATEWAY,
                            route_family="ist_svo_su_fallback",
                            priority=2,
                            only_carriers=["SU"],
                            skip_if_offer_exists=direct_key,
                        )
                        add_segment(
                            "return",
                            "gateway_to_origin",
                            leg_date,
                            PRIORITY_MOSCOW_GATEWAY,
                            origin_code,
                            route_family="ist_svo_su_fallback",
                            priority=2,
                            only_carriers=["SU"],
                            skip_if_offer_exists=direct_key,
                        )
            for dest_code in destination_airports:
                add_segment(
                    "return",
                    "destination_to_hub",
                    ret,
                    dest_code,
                    PRIORITY_SECONDARY_HUB,
                    route_family="dxb_direct",
                    priority=3,
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    skip_if_priority_ist_viable="return",
                )
            for offset in return_second_offsets:
                leg_date = ret + timedelta(days=offset)
                for origin_code in origin_airports:
                    add_segment(
                        "return",
                        "hub_to_origin",
                        leg_date,
                        PRIORITY_SECONDARY_HUB,
                        origin_code,
                        route_family="dxb_direct",
                        priority=3,
                        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                        skip_if_priority_ist_viable="return",
                    )
        else:
            for dest_code in destination_airports:
                for hub in hubs:
                    add_segment("return", "destination_to_hub", ret, dest_code, hub)
            for offset in return_second_offsets:
                leg_date = ret + timedelta(days=offset)
                for hub in hubs:
                    for origin_code in origin_airports:
                        add_segment("return", "hub_to_origin", leg_date, hub, origin_code)

    warnings = [
        "Kupibilet live segment assembly uses direct-only one-way searches; availability and price still require final booking-screen recheck.",
        "Assembled candidates are usually separate-ticket/self-transfer unless the booking site later confirms protected through-ticketing.",
    ]
    if routing_strategy == "ru-priority":
        warnings.append("Using ru-priority routing: IST direct first, SVO/SU fallback only if IST direct is empty, DXB only if IST has no usable assembled pair.")
    elif hub_source == "default":
        warnings.append("Using built-in hub list; pass --hub repeatedly to narrow live segment searches.")
    if hub_source == "manual" and any(hub in {"IST", "SAW"} for hub in hubs) and not {"IST", "SAW"}.issubset(set(hubs)):
        warnings.append("For Istanbul, include both --hub IST and --hub SAW when comparing airport systems.")

    return {
        "origin": origin.code,
        "destination": destination.code,
        "origin_airports": origin_airports,
        "destination_airports": destination_airports,
        "hubs": hubs,
        "hub_source": hub_source,
        "routing_strategy": routing_strategy,
        "route_families": route_families,
        "dates": {"depart": depart.isoformat(), "return": ret.isoformat() if ret else None},
        "currency": currency,
        "profile": profile,
        "ticketing": args.ticketing,
        "second_leg_day_offsets": {
            "outbound": outbound_second_offsets,
            "return": return_second_offsets if ret else [],
        },
        "segments": segments,
        "warnings": warnings,
        "metrics": {"segment_search_count": len(segments)},
    }


def run_kupibilet_route_assembly(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    plan = build_kupibilet_route_segment_plan(args, store)
    max_searches = max(1, int(args.max_segment_searches))
    if plan["metrics"]["segment_search_count"] > max_searches:
        raise CliError(
            f"planned {plan['metrics']['segment_search_count']} segment searches exceeds --max-segment-searches {max_searches}",
            error_type="validation_error",
            details={"planned": plan["metrics"]["segment_search_count"], "max_segment_searches": max_searches},
        )
    if plan.get("routing_strategy") == "ru-priority" and not getattr(args, "prefer_carrier", None):
        args.prefer_carrier = list(PRIORITY_ROUTE_CARRIERS)
    only_carriers = [normalize_carrier_code(code, "only-carrier") for code in (args.only_carrier or [])]
    segment_results: list[dict[str, Any]] = []
    searches: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    offer_counts: dict[tuple[str, str, str, str], int] = {}
    synthetic_fallback_done: set[str] = set()
    priority_ist_viability: dict[str, bool] = {}

    def search_key(spec: dict[str, Any]) -> tuple[str, str, str, str]:
        return (
            str(spec.get("direction") or ""),
            str(spec.get("leg") or ""),
            str(spec.get("origin") or "").upper(),
            str(spec.get("destination") or "").upper(),
        )

    def skipped_by_condition(spec: dict[str, Any]) -> dict[str, Any] | None:
        condition = spec.get("skip_if_offer_exists")
        if not isinstance(condition, dict):
            priority_direction = spec.get("skip_if_priority_ist_viable")
            if not priority_direction:
                return None
            direction = str(priority_direction)
            if not priority_ist_route_viable(direction):
                return None
            return {
                **spec,
                "status": "skipped",
                "reason": "priority_ist_route_viable",
                "offer_count": 0,
                "skipped_because": {
                    "direction": direction,
                    "hub": PRIORITY_PRIMARY_HUB,
                    "note": "DXB skipped because IST already produced a non-error assembled pair.",
                },
            }
        key = (
            str(condition.get("direction") or ""),
            str(condition.get("leg") or ""),
            str(condition.get("origin") or "").upper(),
            str(condition.get("destination") or "").upper(),
        )
        if int(offer_counts.get(key, 0)) <= 0:
            return None
        return {
            **spec,
            "status": "skipped",
            "reason": "direct_probe_has_offers",
            "offer_count": 0,
            "skipped_because": {
                "direction": key[0],
                "leg": key[1],
                "origin": key[2],
                "destination": key[3],
                "offer_count": offer_counts[key],
            },
        }

    def ensure_priority_fallback_synthesized(direction: str | None = None) -> None:
        directions = {"outbound", "return"} if direction is None else {direction}
        pending = directions - synthetic_fallback_done
        if not pending:
            return
        synthetic_fallback_done.update(pending)
        synthetic_results, synthetic_searches = synthesize_priority_fallback_results(plan, segment_results, directions=pending)
        segment_results.extend(synthetic_results)
        searches.extend(synthetic_searches)
        for search in synthetic_searches:
            key = (
                str(search.get("direction") or ""),
                str(search.get("leg") or ""),
                str(search.get("origin") or "").upper(),
                str(search.get("destination") or "").upper(),
            )
            offer_counts[key] = offer_counts.get(key, 0) + int(search.get("offer_count") or 0)

    def priority_ist_route_viable(direction: str) -> bool:
        if plan.get("routing_strategy") != "ru-priority":
            return False
        if direction in priority_ist_viability:
            return priority_ist_viability[direction]
        ensure_priority_fallback_synthesized(direction)
        if direction == "outbound":
            first_leg = "origin_to_hub"
            second_leg = "hub_to_destination"
        elif direction == "return":
            first_leg = "destination_to_hub"
            second_leg = "hub_to_origin"
        else:
            return False
        pairs, _ = assemble_direction(
            segment_results,
            first_leg,
            second_leg,
            direction,
            args.limit_per_pair,
            ticketing=args.ticketing,
            min_same_airport=args.min_same_airport_min,
            min_cross_airport=args.min_cross_airport_min,
            profile=args.profile,
        )
        viable = False
        for pair in pairs:
            offers = [offer for offer in (pair.get("offers") or []) if isinstance(offer, dict)]
            if len(offers) < 2:
                continue
            if str(offers[0].get("arrival_airport") or offers[0].get("destination") or "").upper() != PRIORITY_PRIMARY_HUB:
                continue
            if str(offers[1].get("departure_airport") or offers[1].get("origin") or "").upper() != PRIORITY_PRIMARY_HUB:
                continue
            if (pair.get("connection_quality") or {}).get("severity") != "error":
                viable = True
                break
        priority_ist_viability[direction] = viable
        return viable

    for spec in plan["segments"]:
        skipped = skipped_by_condition(spec)
        if skipped is not None:
            searches.append(skipped)
            continue
        spec_only_carriers = [
            normalize_carrier_code(code, "only-carrier")
            for code in (spec.get("only_carriers") or only_carriers)
        ]
        try:
            result = fetch_kupibilet_search(
                spec["origin"],
                spec["destination"],
                parse_iso_date(spec["date"], "segment-date"),
                currency=plan["currency"],
                only_carriers=spec_only_carriers,
                direct_only=True,
                limit=args.segment_limit,
                timeout=args.timeout,
            )
        except CliError as exc:
            failure = {**spec, "status": "error", "error": {"type": exc.error_type, "message": exc.message}}
            failures.append(failure)
            searches.append(failure)
            if args.fail_fast:
                raise
            continue
        segment_result = kupibilet_result_to_segment_result(result, direction=spec["direction"], leg=spec["leg"])
        searches.append(kupibilet_segment_search_summary(spec, result, segment_result))
        offer_counts[search_key(spec)] = offer_counts.get(search_key(spec), 0) + len(segment_result.get("offers") or [])
        if segment_result["offers"]:
            segment_results.append(segment_result)

    ensure_priority_fallback_synthesized()
    assembled = assemble_segment_results(segment_results, args) if segment_results else empty_assembled_result(args)
    assembled["live_search"] = {
        "source": "Kupibilet frontend_search direct-only segment assembly",
        "note": "Live aggregate source; recheck price/seat availability and whether segments can be ticketed together before purchase.",
        "plan": {key: value for key, value in plan.items() if key != "segments"},
        "segment_searches": searches,
        "hub_viability": hub_viability_summary(plan, searches),
        "failure_count": len(failures),
        "failures": failures,
        "included_segment_result_count": min(len(segment_results), args.include_segment_results),
    }
    assembled["segment_results"] = segment_results[: args.include_segment_results]
    return assembled
