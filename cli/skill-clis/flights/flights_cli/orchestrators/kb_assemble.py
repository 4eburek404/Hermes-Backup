from __future__ import annotations

import argparse
from datetime import timedelta
from typing import Any

from ..config import DEFAULT_HUBS, DEFAULT_KB_ROUTE_OUTBOUND_SECOND_LEG_DAY_OFFSETS, DEFAULT_KB_ROUTE_RETURN_SECOND_LEG_DAY_OFFSETS, SUPPORTED_CURRENCIES
from ..domain.airports import explicit_or_resolved_airports
from ..domain.normalize import normalize_carrier_code, normalize_iata, normalize_profile, parse_iso_date
from ..errors import CliError
from ..providers.kupibilet import fetch_kupibilet_search, kupibilet_result_to_segment_result, kupibilet_segment_search_summary
from ..services.assembly import assemble_segment_results, empty_assembled_result
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
    hubs = [normalize_iata(hub, "hub") for hub in (args.hub or DEFAULT_HUBS)]
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

    def add_segment(direction: str, leg: str, dep_date: date, origin_code: str, dest_code: str) -> None:
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
            }
        )

    for origin_code in origin_airports:
        for hub in hubs:
            add_segment("outbound", "origin_to_hub", depart, origin_code, hub)
    for offset in outbound_second_offsets:
        leg_date = depart + timedelta(days=offset)
        for hub in hubs:
            for dest_code in destination_airports:
                add_segment("outbound", "hub_to_destination", leg_date, hub, dest_code)

    if ret:
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
    if any(hub in {"IST", "SAW"} for hub in hubs) and not {"IST", "SAW"}.issubset(set(hubs)):
        warnings.append("For Istanbul, include both --hub IST and --hub SAW when comparing airport systems.")

    return {
        "origin": origin.code,
        "destination": destination.code,
        "origin_airports": origin_airports,
        "destination_airports": destination_airports,
        "hubs": hubs,
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
    only_carriers = [normalize_carrier_code(code, "only-carrier") for code in (args.only_carrier or [])]
    segment_results: list[dict[str, Any]] = []
    searches: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for spec in plan["segments"]:
        try:
            result = fetch_kupibilet_search(
                spec["origin"],
                spec["destination"],
                parse_iso_date(spec["date"], "segment-date"),
                currency=plan["currency"],
                only_carriers=only_carriers,
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
        if segment_result["offers"]:
            segment_results.append(segment_result)

    assembled = assemble_segment_results(segment_results, args) if segment_results else empty_assembled_result(args)
    assembled["live_search"] = {
        "source": "Kupibilet frontend_search direct-only segment assembly",
        "note": "Live aggregate source; recheck price/seat availability and whether segments can be ticketed together before purchase.",
        "plan": {key: value for key, value in plan.items() if key != "segments"},
        "segment_searches": searches,
        "failure_count": len(failures),
        "failures": failures,
        "included_segment_result_count": min(len(segment_results), args.include_segment_results),
    }
    assembled["segment_results"] = segment_results[: args.include_segment_results]
    return assembled
