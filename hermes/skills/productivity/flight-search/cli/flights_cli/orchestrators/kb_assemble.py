from __future__ import annotations

import argparse
from datetime import date, timedelta
from typing import Any

from ..config import (
    DEFAULT_DIRECT_ROUTE_INDEX_TTL_SECONDS,
    DEFAULT_KB_ROUTE_OUTBOUND_SECOND_LEG_DAY_OFFSETS,
    DEFAULT_KB_ROUTE_RETURN_SECOND_LEG_DAY_OFFSETS,
    DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    PRIORITY_ASIA_HUB,
    PRIORITY_MOSCOW_GATEWAY,
    PRIORITY_PRIMARY_HUB,
    PRIORITY_ROUTE_CARRIERS,
    PRIORITY_SECONDARY_HUB,
    SUPPORTED_CURRENCIES,
)
from ..domain.airports import explicit_or_resolved_airports
from ..domain.normalize import normalize_carrier_code, normalize_profile, parse_iso_date
from ..errors import CliError
from ..execution.aggregate_control_runner import run_aggregate_controls
from ..execution.probe_dispatcher import dispatch_segment_probe, search_key
from ..execution.request_deduper import RequestDeduper
from ..execution.synthetic_control_runner import synthesize_moscow_gateway_control_results
from ..providers.kupibilet import fetch_kupibilet_search
from ..providers.route_intel import load_or_refresh_svx_route_index, svx_direct_route_index_summary
from ..services.agent_report import attach_agent_report
from ..services.assembly import assemble_direction, assemble_segment_results, direct_journeys, empty_assembled_result
from ..store import Store
from .route_graph import (
    coverage_controls_for_plan,
    resolve_route_graph_context,
    route_families_for_strategy,
    route_graph_from_segments,
    route_segment_key,
    route_segment_spec,
)

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


def plan_has_svx_direct_control(plan: dict[str, Any]) -> bool:
    for spec in plan.get("segments") or []:
        if not isinstance(spec, dict) or spec.get("leg") not in {"direct_outbound", "direct_return"}:
            continue
        if str(spec.get("origin") or "").upper() == "SVX" or str(spec.get("destination") or "").upper() == "SVX":
            return True
    return False


def direct_route_intel_context(args: argparse.Namespace, store: Store, plan: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if bool(getattr(args, "no_direct_route_intel", False)):
        return None, {"enabled": False, "available": False, "reason": "disabled_by_flag"}
    ttl_seconds = int(getattr(args, "direct_route_index_ttl_seconds", DEFAULT_DIRECT_ROUTE_INDEX_TTL_SECONDS))
    if ttl_seconds <= 0:
        return None, {"enabled": False, "available": False, "reason": "disabled_by_ttl"}
    if not plan_has_svx_direct_control(plan):
        return None, {"enabled": False, "available": False, "reason": "no_supported_svx_direct_control"}
    try:
        known_airports = set(store.airport_by_code)
        index, cache = load_or_refresh_svx_route_index(
            ttl_seconds=ttl_seconds,
            timeout=int(getattr(args, "timeout", 20)),
            known_airports=known_airports or None,
            cache_dir=store.cache_dir / "route_intel",
        )
    except CliError as exc:
        return None, {
            "enabled": True,
            "available": False,
            "reason": "route_index_unavailable",
            "error": {"type": exc.error_type, "message": exc.message},
            "fallback": "direct-control live searches were kept because the official route index was unavailable.",
        }
    return index, svx_direct_route_index_summary(index, cache)


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
    route_context = resolve_route_graph_context(args, store, origin, destination, origin_airports, destination_airports)
    routing_strategy = route_context.routing_strategy
    hubs = route_context.hubs
    hub_source = route_context.hub_source
    routing_profile = route_context.routing_profile
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
        spec = route_segment_spec(direction, leg, dep_date, origin_code, dest_code, **extra)
        key = route_segment_key(spec, include_date=True)
        if key in seen:
            return
        seen.add(key)
        segments.append(spec)

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
                    only_carriers=["SU"],
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                )
            for offset in outbound_second_offsets:
                leg_date = depart + timedelta(days=offset)
                for dest_code in destination_airports:
                    add_segment(
                        "outbound",
                        "hub_to_destination",
                        leg_date,
                        PRIORITY_ASIA_HUB,
                        dest_code,
                        route_family="svo_asia",
                        priority=1,
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
                    only_carriers=["SU"],
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
                    priority=2 if routing_profile == "asia-oceania" else 1,
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
                preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                skip_if_priority_route_viable="outbound",
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
                    priority=4 if routing_profile == "asia-oceania" else 3,
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    skip_if_priority_route_viable="outbound",
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
                )
        for origin_code in origin_airports:
            for hub in hubs:
                add_segment("outbound", "origin_to_hub", depart, origin_code, hub, route_family="domestic_ru", priority=1)
        for offset in outbound_second_offsets:
            leg_date = depart + timedelta(days=offset)
            for hub in hubs:
                for dest_code in destination_airports:
                    add_segment("outbound", "hub_to_destination", leg_date, hub, dest_code, route_family="domestic_ru", priority=1)
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
                for origin_code in origin_airports:
                    add_segment(
                        "return",
                        "direct_return",
                        ret,
                        dest_code,
                        origin_code,
                        route_family="direct_control",
                        priority=0,
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
                        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    )
                for offset in return_second_offsets:
                    leg_date = ret + timedelta(days=offset)
                    for origin_code in origin_airports:
                        add_segment(
                            "return",
                            "hub_to_origin",
                            leg_date,
                            PRIORITY_ASIA_HUB,
                            origin_code,
                            route_family="svo_asia",
                            priority=1,
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
                        priority=2 if routing_profile == "asia-oceania" else 1,
                        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    )
                    if origin_code != PRIORITY_MOSCOW_GATEWAY:
                        add_segment(
                            "return",
                            "hub_to_gateway",
                            leg_date,
                            PRIORITY_PRIMARY_HUB,
                            PRIORITY_MOSCOW_GATEWAY,
                            route_family="moscow_gateway_control",
                            priority=3 if routing_profile == "asia-oceania" else 2,
                            only_carriers=["SU"],
                        )
                        add_segment(
                            "return",
                            "gateway_to_origin",
                            leg_date,
                            PRIORITY_MOSCOW_GATEWAY,
                            origin_code,
                            route_family="moscow_gateway_control",
                            priority=3 if routing_profile == "asia-oceania" else 2,
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
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    skip_if_priority_route_viable="return",
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
                        priority=4 if routing_profile == "asia-oceania" else 3,
                        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                        skip_if_priority_route_viable="return",
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
                    )
            for dest_code in destination_airports:
                for hub in hubs:
                    add_segment("return", "destination_to_hub", ret, dest_code, hub, route_family="domestic_ru", priority=1)
            for offset in return_second_offsets:
                leg_date = ret + timedelta(days=offset)
                for hub in hubs:
                    for origin_code in origin_airports:
                        add_segment("return", "hub_to_origin", leg_date, hub, origin_code, route_family="domestic_ru", priority=1)
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
        if routing_profile == "asia-oceania":
            warnings.append("Using geo-aware ru-priority routing: direct control, SVO as an independent Asia/Oceania hub, IST fallback, DXB only if priority routes are not usable.")
        else:
            warnings.append("Using ru-priority routing: direct control, IST direct first, SVO/Moscow gateway control even when direct exists, DXB only if priority routes are not usable.")
    elif routing_strategy == "domestic-ru":
        warnings.append("Using domestic-RU routing: direct domestic controls first, Moscow airports only as bounded fallback; international hubs are excluded by default.")
    elif hub_source == "default":
        warnings.append("Using built-in hub list; pass --hub repeatedly to narrow live segment searches.")
    if hub_source == "manual" and any(hub in {"IST", "SAW"} for hub in hubs) and not {"IST", "SAW"}.issubset(set(hubs)):
        warnings.append("For Istanbul, include both --hub IST and --hub SAW when comparing airport systems.")

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
        "origin": origin.code,
        "destination": destination.code,
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
    synthetic_moscow_control_done: set[str] = set()
    priority_route_viability: dict[str, bool] = {}
    cache_ttl_seconds = int(getattr(args, "live_cache_ttl_seconds", DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS))
    use_live_cache = not bool(getattr(args, "no_live_cache", False))
    provider_policy = str(getattr(args, "provider_policy", "kupibilet") or "kupibilet")
    direct_route_index, direct_route_intel = direct_route_intel_context(args, store, plan)
    request_deduper = RequestDeduper()


    def skipped_by_condition(spec: dict[str, Any]) -> dict[str, Any] | None:
        direct_skip = skipped_by_direct_route_intel(spec)
        if direct_skip is not None:
            return direct_skip
        condition = spec.get("skip_if_offer_exists")
        if not isinstance(condition, dict):
            priority_direction = spec.get("skip_if_priority_route_viable")
            if not priority_direction:
                return None
            direction = str(priority_direction)
            if not priority_route_viable(direction):
                return None
            return {
                **spec,
                "status": "skipped",
                "reason": "priority_route_viable",
                "offer_count": 0,
                "skipped_because": {
                    "direction": direction,
                    "note": "DXB skipped because direct/SVO/IST priority routing already produced a non-error journey.",
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

    def skipped_by_direct_route_intel(spec: dict[str, Any]) -> dict[str, Any] | None:
        if direct_route_index is None or spec.get("leg") not in {"direct_outbound", "direct_return"}:
            return None
        routes = direct_route_index.get("routes") if isinstance(direct_route_index.get("routes"), dict) else {}
        origin = str(spec.get("origin") or "").upper()
        destination = str(spec.get("destination") or "").upper()
        if origin == "SVX":
            route_set = {str(code).upper() for code in (routes.get("outbound") or [])}
            checked_airport = destination
        elif destination == "SVX":
            route_set = {str(code).upper() for code in (routes.get("return") or [])}
            checked_airport = origin
        else:
            return None
        if checked_airport in route_set:
            return None
        return {
            **spec,
            "status": "skipped",
            "reason": "direct_route_schedule_negative",
            "offer_count": 0,
            "skipped_because": {
                "checked_airport": checked_airport,
                "airport": "SVX",
                "source": direct_route_index.get("source"),
                "fetched_at": direct_route_index.get("fetched_at"),
                "note": "Official SVX seasonal schedule has no direct route for this exact airport pair; hub routing is still checked.",
            },
        }

    def ensure_moscow_gateway_control_synthesized(direction: str | None = None) -> None:
        directions = {"outbound", "return"} if direction is None else {direction}
        pending = directions - synthetic_moscow_control_done
        if not pending:
            return
        synthetic_moscow_control_done.update(pending)
        synthetic_results, synthetic_searches = synthesize_moscow_gateway_control_results(plan, segment_results, directions=pending)
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

    def priority_route_viable(direction: str) -> bool:
        if plan.get("routing_strategy") != "ru-priority":
            return False
        if direction in priority_route_viability:
            return priority_route_viability[direction]
        ensure_moscow_gateway_control_synthesized(direction)
        if direction == "outbound":
            first_leg = "origin_to_hub"
            second_leg = "hub_to_destination"
            direct_leg = "direct_outbound"
        elif direction == "return":
            first_leg = "destination_to_hub"
            second_leg = "hub_to_origin"
            direct_leg = "direct_return"
        else:
            return False
        direct = direct_journeys(segment_results, direct_leg, direction, args.limit_per_pair)
        if direct:
            priority_route_viability[direction] = True
            return True
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
            hub = str(offers[0].get("arrival_airport") or offers[0].get("destination") or "").upper()
            next_origin = str(offers[1].get("departure_airport") or offers[1].get("origin") or "").upper()
            if hub != next_origin or hub == PRIORITY_SECONDARY_HUB:
                continue
            if (pair.get("connection_quality") or {}).get("severity") != "error":
                viable = True
                break
        priority_route_viability[direction] = viable
        return viable

    for spec in plan["segments"]:
        skipped = skipped_by_condition(spec)
        if skipped is not None:
            searches.append(skipped)
            continue
        for outcome in dispatch_segment_probe(
            spec=spec,
            plan=plan,
            args=args,
            store=store,
            only_carriers=only_carriers,
            cache_ttl_seconds=cache_ttl_seconds,
            use_live_cache=use_live_cache,
            provider_policy=provider_policy,
            kupibilet_fetcher=fetch_kupibilet_search,
            request_deduper=request_deduper,
        ):
            searches.append(outcome.summary)
            if outcome.failure is not None:
                failures.append(outcome.failure)
                continue
            segment_result = outcome.segment_result
            if segment_result is None:
                continue
            offer_counts[search_key(spec)] = offer_counts.get(search_key(spec), 0) + len(segment_result.get("offers") or [])
            if outcome.include_segment_result and segment_result["offers"]:
                segment_results.append(segment_result)

    ensure_moscow_gateway_control_synthesized()
    assembled = assemble_segment_results(segment_results, args) if segment_results else empty_assembled_result(args)
    source_label = "Kupibilet frontend_search direct-only segment assembly"
    note = "Live aggregate source; recheck price/seat availability and whether segments can be ticketed together before purchase."
    if provider_policy != "kupibilet":
        source_label = "Provider-policy live segment assembly"
        note = "Kupibilet is used for Russia-touching segments; FLI MCP is used for non-Russia segments under auto policy. Recheck price/seat availability before purchase."
    assembled["live_search"] = {
        "source": source_label,
        "provider_policy": provider_policy,
        "note": note,
        "plan": {key: value for key, value in plan.items() if key != "segments"},
        "segment_searches": searches,
        "hub_viability": hub_viability_summary(plan, searches),
        "aggregate_controls": run_aggregate_controls(args, plan, kupibilet_fetcher=fetch_kupibilet_search),
        "direct_route_intelligence": direct_route_intel,
        "failure_count": len(failures),
        "failures": failures,
        "included_segment_result_count": min(len(segment_results), args.include_segment_results),
    }
    assembled["segment_results"] = segment_results[: args.include_segment_results]
    return attach_agent_report(assembled, args, store)
