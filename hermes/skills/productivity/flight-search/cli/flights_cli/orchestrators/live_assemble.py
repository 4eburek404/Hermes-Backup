from __future__ import annotations

import argparse
from datetime import date, timedelta
from typing import Any

from ..config import (
    DEFAULT_DIRECT_ROUTE_INDEX_TTL_SECONDS,
    DEFAULT_KB_ROUTE_OUTBOUND_SECOND_LEG_DAY_OFFSETS,
    DEFAULT_KB_ROUTE_RETURN_SECOND_LEG_DAY_OFFSETS,
    DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    KUPIBILET_CITY_CODE_FIRST_AIRPORTS,
    MAX_DATE_WINDOW_DAYS,
    PRIORITY_ASIA_HUB,
    PRIORITY_MOSCOW_GATEWAY,
    PRIORITY_PRIMARY_HUB,
    PRIORITY_ROUTE_CARRIERS,
    PRIORITY_SECONDARY_HUB,
    SUPPORTED_CURRENCIES,
)
from ..domain.airports import explicit_or_resolved_airports
from ..domain.normalize import normalize_carrier_code, normalize_profile, parse_iso_date
from ..domain.vocabulary import Direction, Leg, MarketClass, RequiredControl, RouteFamily, RoutingStrategy
from ..errors import CliError
from ..execution.aggregate_control_runner import run_aggregate_controls
from ..execution.probe_dispatcher import dispatch_segment_probe, search_key
from ..execution.probe_intent import intent_from_control, intent_from_segment
from ..execution.probe_ledger import ProbeExecutionLedger
from ..execution.request_deduper import RequestDeduper
from ..execution.synthetic_control_runner import synthesize_moscow_gateway_control_results

from ..pipeline.search_pipeline import LiveRouteSearchFlow, build_live_route_search_flow
from ..providers.route_intel import load_or_refresh_svx_route_index, svx_direct_route_index_summary
from ..reporting.date_window_projector import build_date_window_inventory
from ..services.agent_report import attach_agent_report
from ..services.assembly import assemble_direction, assemble_segment_results, direct_journeys, empty_assembled_result
from ..store import Store
from .route_graph import (
    append_unique_route_segment,
    coverage_controls_for_plan,
    resolve_route_graph_context,
    route_families_for_strategy,
    route_graph_from_segments,
)

# Compatibility injection hook for older tests and callers that patch
# ``flights_cli.orchestrators.live_assemble.fetch_kupibilet_search``.
# Production keeps this as None so provider calls are resolved through the
# provider-port registry in ``execution.*``.
fetch_kupibilet_search: Any | None = None


def provider_policy_allows_kupibilet(policy: str | None) -> bool:
    normalized = str(policy or "kupibilet").strip().lower()
    return normalized in {"auto", "both", "kupibilet"}


def city_code_first_segment_options(
    *,
    city_code: str | None,
    airports: list[str],
    explicit: list[str] | None,
    provider_policy: str | None,
) -> list[tuple[str, dict[str, Any]]]:
    normalized_city = str(city_code or "").upper()
    if explicit or not provider_policy_allows_kupibilet(provider_policy):
        return [(code, {}) for code in airports]
    deferred_airports = [str(code).upper() for code in KUPIBILET_CITY_CODE_FIRST_AIRPORTS.get(normalized_city, [])]
    if not deferred_airports:
        return [(code, {}) for code in airports]

    options: list[tuple[str, dict[str, Any]]] = [
        (
            normalized_city,
            {
                "provider_request_strategy": "city_code_first",
                "provider_city_code": normalized_city,
                "provider_city_code_deferred_airports": deferred_airports,
            },
        )
    ]
    for code in airports:
        normalized_airport = str(code).upper()
        options.append(
            (
                normalized_airport,
                {
                    "provider_request_strategy": "city_code_deferred",
                    "provider_city_code": normalized_city,
                    "deferred_for_city_code_request": True,
                },
            )
        )
    return options


def provider_city_code_side(spec: dict[str, Any], side: str) -> bool:
    city_code = str(spec.get("provider_city_code") or "").upper()
    if not city_code:
        return False
    code = str(spec.get(side) or "").upper()
    deferred_airports = {str(item).upper() for item in KUPIBILET_CITY_CODE_FIRST_AIRPORTS.get(city_code, [])}
    return code == city_code or code in deferred_airports

def endpoint_group_code(spec: dict[str, Any], side: str) -> str:
    if provider_city_code_side(spec, side):
        return str(spec.get("provider_city_code") or "").upper()
    return str(spec.get(side) or "").upper()

def city_code_primary_keys_for_deferred_airport(spec: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    if not spec.get("deferred_for_city_code_request"):
        return []
    city_code = str(spec.get("provider_city_code") or "").upper()
    deferred_airports = {str(item).upper() for item in KUPIBILET_CITY_CODE_FIRST_AIRPORTS.get(city_code, [])}
    if not city_code or not deferred_airports:
        return []
    direction = str(spec.get("direction") or "")
    leg = str(spec.get("leg") or "")
    origin = str(spec.get("origin") or "").upper()
    destination = str(spec.get("destination") or "").upper()
    keys: list[tuple[str, str, str, str]] = []
    if origin in deferred_airports:
        keys.append((direction, leg, city_code, destination))
    if destination in deferred_airports:
        keys.append((direction, leg, origin, city_code))
    return keys


def deferred_airport_priority_sides(spec: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    sides: list[tuple[str, dict[str, Any]]] = []
    for side in ("origin", "destination"):
        metadata = spec.get(f"{side}_airport_priority")
        if not isinstance(metadata, dict):
            continue
        tier = int(metadata.get("tier") or 0)
        role = str(metadata.get("role") or "").lower()
        if tier > 1 or role == "deferred":
            sides.append((side, metadata))
    return sides


def preferred_keys_for_deferred_airport(spec: dict[str, Any], plan: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    keys: list[tuple[str, str, str, str]] = []
    for priority_side, deferred_metadata in deferred_airport_priority_sides(spec):
        city_code = str(deferred_metadata.get("city_code") or "").upper()
        deferred_tier = int(deferred_metadata.get("tier") or 0)
        if not city_code or deferred_tier <= 1:
            continue
        other_side = "destination" if priority_side == "origin" else "origin"
        other_group = endpoint_group_code(spec, other_side)
        for candidate in plan.get("segments") or []:
            if not isinstance(candidate, dict) or candidate is spec:
                continue
            if str(candidate.get("direction") or "") != str(spec.get("direction") or ""):
                continue
            if str(candidate.get("leg") or "") != str(spec.get("leg") or ""):
                continue
            if str(candidate.get("date") or "") != str(spec.get("date") or ""):
                continue
            if str(candidate.get("route_family") or "") != str(spec.get("route_family") or ""):
                continue
            candidate_metadata = candidate.get(f"{priority_side}_airport_priority")
            if not isinstance(candidate_metadata, dict):
                continue
            if str(candidate_metadata.get("city_code") or "").upper() != city_code:
                continue
            if int(candidate_metadata.get("tier") or 0) >= deferred_tier:
                continue
            if endpoint_group_code(candidate, other_side) != other_group:
                continue
            keys.append(search_key(candidate))
    return keys

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
        if not isinstance(spec, dict) or spec.get("leg") not in {Leg.DIRECT_OUTBOUND, Leg.DIRECT_RETURN}:
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
            StopBucket.TIER2: "direct-control live searches were kept because the official route index was unavailable.",
        }
    return index, svx_direct_route_index_summary(index, cache)


def hub_viability_summary(plan: dict[str, Any], searches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_hub: dict[str, dict[str, Any]] = {
        hub: {
            "hub": hub,
            "viable": False,
            "total_offer_count": 0,
            "legs": {
                Leg.ORIGIN_TO_HUB: {"offer_count": 0, "search_count": 0, "dates": []}, Leg.HUB_TO_DESTINATION: {"offer_count": 0, "search_count": 0, "dates": []}, Leg.DESTINATION_TO_HUB: {"offer_count": 0, "search_count": 0, "dates": []}, Leg.HUB_TO_ORIGIN: {"offer_count": 0, "search_count": 0, "dates": []},
            },
            "missing_legs": [],
        }
        for hub in plan["hubs"]
    }
    for search in searches:
        leg = search.get("leg")
        if leg == Leg.ORIGIN_TO_HUB:
            hub = search.get("destination")
        elif leg == Leg.HUB_TO_DESTINATION:
            hub = search.get("origin")
        elif leg == Leg.DESTINATION_TO_HUB:
            hub = search.get("destination")
        elif leg == Leg.HUB_TO_ORIGIN:
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

    required_legs = [Leg.ORIGIN_TO_HUB, Leg.HUB_TO_DESTINATION]
    if plan["dates"].get("return"):
        required_legs += [Leg.DESTINATION_TO_HUB, Leg.HUB_TO_ORIGIN]
    for item in by_hub.values():
        item["missing_legs"] = [
            leg
            for leg in required_legs
            if int(item["legs"][leg]["offer_count"]) <= 0
        ]
        item["viable"] = not item["missing_legs"]
    return sorted(by_hub.values(), key=lambda item: (not item["viable"], -int(item["total_offer_count"]), item["hub"]))

def resolve_date_window(args: argparse.Namespace, depart: date, ret: date | None, *, direct_only: bool) -> list[date]:
    """Expand route_options.date_window_end into bounded per-date direct inventory dates.

    This is the executable replacement for the manual per-date probe loop that
    references/direct-date-window.md used to describe in prose.
    """

    window_end_raw = getattr(args, "date_window_end", None)
    if not window_end_raw:
        return []
    window_end = parse_iso_date(str(window_end_raw), "date-window-end")
    if not direct_only:
        raise CliError(
            "date_window_end requires direct-only route options: set route_options.max_connections=0 and route_options.tier2_max_connections=0",
            error_type="validation_error",
        )
    if ret is not None:
        raise CliError(
            "date_window_end is a one-way direct inventory option; remove return_date or drop the window",
            error_type="validation_error",
        )
    if window_end < depart:
        raise CliError("date-window-end must be on or after depart-date", error_type="validation_error")
    window_days = (window_end - depart).days + 1
    if window_days > MAX_DATE_WINDOW_DAYS:
        raise CliError(
            f"date window spans {window_days} days; bound it to at most {MAX_DATE_WINDOW_DAYS} days",
            error_type="validation_error",
            details={"window_days": window_days, "max_days": MAX_DATE_WINDOW_DAYS},
        )
    return [depart + timedelta(days=offset) for offset in range(window_days)]

def build_live_route_segment_plan(args: argparse.Namespace, store: Store, *, flow: LiveRouteSearchFlow | None = None) -> dict[str, Any]:
    depart = parse_iso_date(args.depart_date, "depart-date")
    ret = parse_iso_date(args.return_date, "return-date") if args.return_date else None
    currency = args.currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise CliError(f"currency must be one of {', '.join(sorted(SUPPORTED_CURRENCIES))}", error_type="validation_error")
    profile = normalize_profile(getattr(args, "profile", "balanced"))
    if flow is None:
        flow = build_live_route_search_flow(args, store)
    direct_only = bool(flow.evidence_plan.direct_only)
    window_dates = resolve_date_window(args, depart, ret, direct_only=direct_only)

    origin = store.resolve_location(args.origin)
    destination = store.resolve_location(args.destination)
    origin_airports = explicit_or_resolved_airports(
        store, origin, args.origin_airport, role="origin", max_airports=args.max_airports_per_city
    )
    destination_airports = explicit_or_resolved_airports(
        store, destination, args.destination_airport, role="destination", max_airports=args.max_airports_per_city
    )
    provider_policy = str(getattr(args, "provider_policy", "kupibilet") or "kupibilet")
    origin_segment_options = city_code_first_segment_options(
        city_code=origin.code,
        airports=origin_airports,
        explicit=args.origin_airport,
        provider_policy=provider_policy,
    )
    destination_segment_options = city_code_first_segment_options(
        city_code=destination.code,
        airports=destination_airports,
        explicit=args.destination_airport,
        provider_policy=provider_policy,
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
    seen: set[tuple[str, ...]] = set()

    def add_live_segment(direction: str, leg: str, dep_date: date, origin_code: str, dest_code: str, **extra: Any) -> None:
        append_unique_route_segment(
            segments,
            seen,
            direction=direction,
            leg=leg,
            dep_date=dep_date,
            origin_code=origin_code,
            dest_code=dest_code,
            include_date=True,
            extra=extra,
        )

    route_families = route_families_for_strategy(routing_strategy, routing_profile)
    include_generic_direct_controls = flow.flow_decision.market_class == MarketClass.GLOBAL_NON_RU
    moscow_gateway_eligible = (
        routing_strategy == RoutingStrategy.RU_PRIORITY
        and str(origin.code or "").upper() != "MOW"
        and str(destination.code or "").upper() != "MOW"
    )
    gateway_segment_options: list[tuple[str, dict[str, Any]]] = []
    if moscow_gateway_eligible:
        gateway_segment_options = city_code_first_segment_options(
            city_code="MOW",
            airports=[str(code).upper() for code in KUPIBILET_CITY_CODE_FIRST_AIRPORTS.get("MOW", [PRIORITY_MOSCOW_GATEWAY])],
            explicit=None,
            provider_policy=provider_policy,
        )
    if direct_only:
        route_families = [
            {
                "id": RouteFamily.DIRECT_INVENTORY,
                "priority": 0,
                "condition": "direct-only request: search exact origin/destination airport pairs and do not assemble connecting fallback routes.",
            }
        ]
        for inventory_date in (window_dates or [depart]):
            for dest_code, dest_extra in destination_segment_options:
                for origin_code, origin_extra in origin_segment_options:
                    add_live_segment(
                        Direction.OUTBOUND,
                        Leg.DIRECT_OUTBOUND,
                        inventory_date,
                        origin_code,
                        dest_code,
                        route_family=RouteFamily.DIRECT_INVENTORY,
                        priority=0,
                        **{**origin_extra, **dest_extra},
                    )
    elif routing_strategy == RoutingStrategy.RU_PRIORITY:
        for dest_code, dest_extra in destination_segment_options:
            for origin_code, origin_extra in origin_segment_options:
                add_live_segment(Direction.OUTBOUND, Leg.DIRECT_OUTBOUND,
                    depart,
                    origin_code,
                    dest_code,
                    route_family="direct_control",
                    priority=0,
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    **{**origin_extra, **dest_extra},
                )
        if routing_profile == "asia-oceania":
            for origin_code in origin_airports:
                add_live_segment(Direction.OUTBOUND, Leg.ORIGIN_TO_HUB,
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
                    add_live_segment(Direction.OUTBOUND, Leg.HUB_TO_DESTINATION,
                        leg_date,
                        PRIORITY_ASIA_HUB,
                        dest_code,
                        route_family="svo_asia",
                        priority=1,
                        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    )
        for origin_code in origin_airports:
            add_live_segment(Direction.OUTBOUND, Leg.ORIGIN_TO_HUB,
                depart,
                origin_code,
                PRIORITY_PRIMARY_HUB,
                route_family="ist_direct",
                priority=2 if routing_profile == "asia-oceania" else 1,
                preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
            )
            if origin_code != PRIORITY_MOSCOW_GATEWAY:
                add_live_segment(Direction.OUTBOUND,
                    "origin_to_gateway",
                    depart,
                    origin_code,
                    PRIORITY_MOSCOW_GATEWAY,
                    route_family="moscow_gateway_control",
                    priority=3 if routing_profile == "asia-oceania" else 2,
                    only_carriers=["SU"],
                )
                add_live_segment(Direction.OUTBOUND,
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
                add_live_segment(Direction.OUTBOUND, Leg.HUB_TO_DESTINATION,
                    leg_date,
                    PRIORITY_PRIMARY_HUB,
                    dest_code,
                    route_family="ist_shared_destination",
                    priority=2 if routing_profile == "asia-oceania" else 1,
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                )
        for origin_code in origin_airports:
            add_live_segment(Direction.OUTBOUND, Leg.ORIGIN_TO_HUB,
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
                add_live_segment(Direction.OUTBOUND, Leg.HUB_TO_DESTINATION,
                    leg_date,
                    PRIORITY_SECONDARY_HUB,
                    dest_code,
                    route_family="dxb_direct",
                    priority=4 if routing_profile == "asia-oceania" else 3,
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    skip_if_priority_route_viable="outbound",
                )
        for gateway_code, gateway_extra in gateway_segment_options:
            for dest_code in destination_airports:
                add_live_segment(Direction.OUTBOUND,
                    "gateway_to_destination",
                    depart,
                    gateway_code,
                    dest_code,
                    route_family="moscow_gateway_control",
                    priority=3 if routing_profile == "asia-oceania" else 2,
                    **gateway_extra,
                )
    elif routing_strategy == RoutingStrategy.DOMESTIC_RU:
        for dest_code, dest_extra in destination_segment_options:
            for origin_code, origin_extra in origin_segment_options:
                add_live_segment(Direction.OUTBOUND, Leg.DIRECT_OUTBOUND,
                    depart,
                    origin_code,
                    dest_code,
                    route_family=RouteFamily.DOMESTIC_RU,
                    priority=0,
                    **{**origin_extra, **dest_extra},
                )
        for origin_code in origin_airports:
            for hub in hubs:
                add_live_segment(Direction.OUTBOUND, Leg.ORIGIN_TO_HUB, depart, origin_code, hub, route_family=RouteFamily.DOMESTIC_RU, priority=1)
        for offset in outbound_second_offsets:
            leg_date = depart + timedelta(days=offset)
            for hub in hubs:
                for dest_code in destination_airports:
                    add_live_segment(Direction.OUTBOUND, Leg.HUB_TO_DESTINATION, leg_date, hub, dest_code, route_family=RouteFamily.DOMESTIC_RU, priority=1)
    else:
        if include_generic_direct_controls:
            for dest_code, dest_extra in destination_segment_options:
                for origin_code, origin_extra in origin_segment_options:
                    add_live_segment(Direction.OUTBOUND, Leg.DIRECT_OUTBOUND,
                        depart,
                        origin_code,
                        dest_code,
                        route_family="direct_control",
                        priority=0,
                        **{**origin_extra, **dest_extra},
                    )
        for origin_code in origin_airports:
            for hub in hubs:
                add_live_segment(Direction.OUTBOUND, Leg.ORIGIN_TO_HUB, depart, origin_code, hub, route_family=RouteFamily.HUB_LIST, priority=1)
        for offset in outbound_second_offsets:
            leg_date = depart + timedelta(days=offset)
            for hub in hubs:
                for dest_code in destination_airports:
                    add_live_segment(Direction.OUTBOUND, Leg.HUB_TO_DESTINATION, leg_date, hub, dest_code, route_family=RouteFamily.HUB_LIST, priority=1)

    if ret:
        if direct_only:
            for dest_code, dest_extra in destination_segment_options:
                for origin_code, origin_extra in origin_segment_options:
                    add_live_segment(Direction.RETURN, Leg.DIRECT_RETURN,
                        ret,
                        dest_code,
                        origin_code,
                        route_family=RouteFamily.DIRECT_INVENTORY,
                        priority=0,
                        **{**dest_extra, **origin_extra},
                    )
        elif routing_strategy == RoutingStrategy.RU_PRIORITY:
            for dest_code, dest_extra in destination_segment_options:
                for origin_code, origin_extra in origin_segment_options:
                    add_live_segment(Direction.RETURN, Leg.DIRECT_RETURN,
                        ret,
                        dest_code,
                        origin_code,
                        route_family="direct_control",
                        priority=0,
                        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                        **{**dest_extra, **origin_extra},
                    )
            if routing_profile == "asia-oceania":
                for dest_code in destination_airports:
                    add_live_segment(Direction.RETURN, Leg.DESTINATION_TO_HUB,
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
                        add_live_segment(Direction.RETURN, Leg.HUB_TO_ORIGIN,
                            leg_date,
                            PRIORITY_ASIA_HUB,
                            origin_code,
                            route_family="svo_asia",
                            priority=1,
                            only_carriers=["SU"],
                            preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                        )
            for dest_code in destination_airports:
                add_live_segment(Direction.RETURN, Leg.DESTINATION_TO_HUB,
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
                    add_live_segment(Direction.RETURN, Leg.HUB_TO_ORIGIN,
                        leg_date,
                        PRIORITY_PRIMARY_HUB,
                        origin_code,
                        route_family="ist_direct",
                        priority=2 if routing_profile == "asia-oceania" else 1,
                        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    )
                    if origin_code != PRIORITY_MOSCOW_GATEWAY:
                        add_live_segment(Direction.RETURN,
                            "hub_to_gateway",
                            leg_date,
                            PRIORITY_PRIMARY_HUB,
                            PRIORITY_MOSCOW_GATEWAY,
                            route_family="moscow_gateway_control",
                            priority=3 if routing_profile == "asia-oceania" else 2,
                            only_carriers=["SU"],
                        )
                        add_live_segment(Direction.RETURN,
                            "gateway_to_origin",
                            leg_date,
                            PRIORITY_MOSCOW_GATEWAY,
                            origin_code,
                            route_family="moscow_gateway_control",
                            priority=3 if routing_profile == "asia-oceania" else 2,
                            only_carriers=["SU"],
                        )
            for dest_code in destination_airports:
                add_live_segment(Direction.RETURN, Leg.DESTINATION_TO_HUB,
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
                    add_live_segment(Direction.RETURN, Leg.HUB_TO_ORIGIN,
                        leg_date,
                        PRIORITY_SECONDARY_HUB,
                        origin_code,
                        route_family="dxb_direct",
                        priority=4 if routing_profile == "asia-oceania" else 3,
                        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                        skip_if_priority_route_viable="return",
                    )
            for gateway_code, gateway_extra in gateway_segment_options:
                for dest_code in destination_airports:
                    add_live_segment(Direction.RETURN,
                        "destination_to_gateway",
                        ret,
                        dest_code,
                        gateway_code,
                        route_family="moscow_gateway_control",
                        priority=3 if routing_profile == "asia-oceania" else 2,
                        **gateway_extra,
                    )
        elif routing_strategy == RoutingStrategy.DOMESTIC_RU:
            for dest_code, dest_extra in destination_segment_options:
                for origin_code, origin_extra in origin_segment_options:
                    add_live_segment(Direction.RETURN, Leg.DIRECT_RETURN,
                        ret,
                        dest_code,
                        origin_code,
                        route_family=RouteFamily.DOMESTIC_RU,
                        priority=0,
                        **{**dest_extra, **origin_extra},
                    )
            for dest_code in destination_airports:
                for hub in hubs:
                    add_live_segment(Direction.RETURN, Leg.DESTINATION_TO_HUB, ret, dest_code, hub, route_family=RouteFamily.DOMESTIC_RU, priority=1)
            for offset in return_second_offsets:
                leg_date = ret + timedelta(days=offset)
                for hub in hubs:
                    for origin_code in origin_airports:
                        add_live_segment(Direction.RETURN, Leg.HUB_TO_ORIGIN, leg_date, hub, origin_code, route_family=RouteFamily.DOMESTIC_RU, priority=1)
        else:
            if include_generic_direct_controls:
                for dest_code, dest_extra in destination_segment_options:
                    for origin_code, origin_extra in origin_segment_options:
                        add_live_segment(Direction.RETURN, Leg.DIRECT_RETURN,
                            ret,
                            dest_code,
                            origin_code,
                            route_family="direct_control",
                            priority=0,
                            **{**dest_extra, **origin_extra},
                        )
            for dest_code in destination_airports:
                for hub in hubs:
                    add_live_segment(Direction.RETURN, Leg.DESTINATION_TO_HUB, ret, dest_code, hub, route_family=RouteFamily.HUB_LIST, priority=1)
            for offset in return_second_offsets:
                leg_date = ret + timedelta(days=offset)
                for hub in hubs:
                    for origin_code in origin_airports:
                        add_live_segment(Direction.RETURN, Leg.HUB_TO_ORIGIN, leg_date, hub, origin_code, route_family=RouteFamily.HUB_LIST, priority=1)

    assembly_warning = (
        "KupiBilet live segment assembly uses direct-only one-way searches; availability and price still require final booking-screen recheck."
        if provider_policy.strip().lower() == "kupibilet"
        else "Provider-policy live assembly uses provider-selected direct-only one-way searches; availability and price still require final booking-screen recheck."
    )
    warnings = [
        assembly_warning,
        "Assembled candidates are usually separate-ticket/self-transfer unless the booking site later confirms protected through-ticketing.",
    ]
    if routing_strategy == RoutingStrategy.RU_PRIORITY:
        if routing_profile == "asia-oceania":
            warnings.append("Using geo-aware ru-priority routing: direct control, SVO as an independent Asia/Oceania hub, IST fallback, DXB only if priority routes are not usable.")
        else:
            warnings.append("Using ru-priority routing: direct control, IST direct first, SVO/Moscow gateway control even when direct exists, DXB only if priority routes are not usable.")
    elif routing_strategy == RoutingStrategy.DOMESTIC_RU:
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
        depart_dates=window_dates or None,
        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
        requested_controls=route_context.coverage_limits.get("requested_controls"),
        coverage_control_limit=route_context.coverage_limits.get("coverage_control_limit"),
    )
    if direct_only:
        coverage_controls = [control for control in coverage_controls if control.get("type") == RequiredControl.EXACT_AIRPORT_DIRECT]
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
        "coverage_limits": {
            **route_context.coverage_limits,
            "freshness_policy": flow.evidence_plan.freshness_policy,
            "required_controls": list(flow.evidence_plan.required_controls),
            "absence_taxonomy": list(flow.evidence_plan.absence_taxonomy),
            "missing_evidence": list(flow.evidence_plan.missing_evidence),
        },
        "direct_only": direct_only,
        "flow_decision": flow.flow_decision.to_dict(),
        "evidence_plan": flow.evidence_plan.to_dict(),
        "route_graph": route_graph,
        "route_families": route_families,
        "dates": {
            "depart": depart.isoformat(),
            "return": ret.isoformat() if ret else None,
            **({"window_end": window_dates[-1].isoformat()} if window_dates else {}),
        },
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


class LiveAssemblyRunner:
    """Stateful orchestrator for live route assembly.

    Created once per search; ``run()`` executes the full probe-assemble
    pipeline and returns the assembled result dict.
    """

    def __init__(self, args: argparse.Namespace, store: Store) -> None:
        self.args = args
        self.store = store
        # --- config (read-only after init) ---
        self.flow: LiveRouteSearchFlow
        self.plan: dict[str, Any]
        self.max_searches: int = 0
        self.only_carriers: list[str] = []
        self.cache_ttl_seconds: int = 0
        self.use_live_cache: bool = False
        self.provider_policy: str = ""
        self.direct_route_index: dict[str, Any] | None = None
        self.direct_route_intel: dict[str, Any] = {}
        # --- accumulators (mutated during run) ---
        self.segment_results: list[dict[str, Any]] = []
        self.searches: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []
        self.offer_counts: dict[tuple[str, str, str, str], int] = {}
        self.synthetic_moscow_control_done: set[str] = set()
        self.priority_route_viability: dict[str, bool] = {}
        # --- collaborators ---
        self.request_deduper = RequestDeduper()
        self.probe_ledger = ProbeExecutionLedger()

    def run(self) -> dict[str, Any]:
        args, store = self.args, self.store
        self.flow = build_live_route_search_flow(args, store)
        self.plan = build_live_route_segment_plan(args, store, flow=self.flow)
        self.max_searches = max(1, int(self.flow.evidence_plan.max_segment_searches))
        if self.plan["metrics"]["segment_search_count"] > self.max_searches:
            raise CliError(
                f"planned {self.plan['metrics']['segment_search_count']} segment searches exceeds --max-segment-searches {self.max_searches}",
                error_type="validation_error",
                details={"planned": self.plan["metrics"]["segment_search_count"], "max_segment_searches": self.max_searches},
            )
        if self.plan.get("routing_strategy") == RoutingStrategy.RU_PRIORITY and not getattr(args, "prefer_carrier", None):
            args.prefer_carrier = list(PRIORITY_ROUTE_CARRIERS)
        self.only_carriers = [normalize_carrier_code(code, "only-carrier") for code in (args.only_carrier or [])]
        self.cache_ttl_seconds = int(self.flow.evidence_plan.live_cache_ttl_seconds)
        self.use_live_cache = bool(self.flow.evidence_plan.live_cache_enabled)
        self.provider_policy = self.flow.evidence_plan.provider_policy
        self.direct_route_index, self.direct_route_intel = direct_route_intel_context(args, store, self.plan)
        self.request_deduper = RequestDeduper()
        self.probe_ledger = ProbeExecutionLedger()

        for spec in self.plan["segments"]:
            skipped = self._skipped_by_condition(spec)
            if skipped is not None:
                self.searches.append(skipped)
                self._record_segment_probe_summary(spec, skipped)
                continue
            for outcome in dispatch_segment_probe(
                spec=spec,
                plan=self.plan,
                args=args,
                store=store,
                only_carriers=self.only_carriers,
                cache_ttl_seconds=self.cache_ttl_seconds,
                use_live_cache=self.use_live_cache,
                provider_policy=self.provider_policy,
                kupibilet_fetcher=fetch_kupibilet_search,
                request_deduper=self.request_deduper,
            ):
                self.searches.append(outcome.summary)
                self._record_segment_probe_summary(spec, outcome.summary, provider_result=outcome.provider_result)
                if outcome.failure is not None:
                    self.failures.append(outcome.failure)
                    continue
                segment_result = outcome.segment_result
                if segment_result is None:
                    continue
                key = search_key(spec)
                self.offer_counts[key] = self.offer_counts.get(key, 0) + len(segment_result.get("offers") or [])
                if outcome.include_segment_result and segment_result["offers"]:
                    self.segment_results.append(segment_result)

        self._ensure_moscow_gateway_control_synthesized()
        date_window_inventory = build_date_window_inventory(self.plan, self.searches, self.segment_results)
        assembled = assemble_segment_results(self.segment_results, args) if self.segment_results else empty_assembled_result(args)
        aggregate_controls = run_aggregate_controls(args, self.plan, kupibilet_fetcher=fetch_kupibilet_search, probe_ledger=self.probe_ledger)
        for control in self.plan.get("coverage_controls") or []:
            if isinstance(control, dict) and control.get("type") == "city_pair_direct":
                self.probe_ledger.plan_intents([intent_from_control(control, provider=self.provider_policy)])
        self.probe_ledger.finalize_unexecuted()
        source_label = "Kupibilet frontend_search direct-only segment assembly"
        note = "Live aggregate source; recheck price/seat availability and whether segments can be ticketed together before purchase."
        if self.provider_policy != "kupibilet":
            source_label = "Provider-policy live segment assembly"
            note = "Kupibilet is used for Russia-touching segments; FLI MCP is used for non-Russia segments under auto policy. Recheck price/seat availability before purchase."
        assembled["live_search"] = {
            "source": source_label,
            "provider_policy": self.provider_policy,
            "note": note,
            "plan": {key: value for key, value in self.plan.items() if key != "segments"},
            "segment_searches": self.searches,
            "hub_viability": hub_viability_summary(self.plan, self.searches),
            "aggregate_controls": aggregate_controls,
            "probe_ledger": self.probe_ledger.to_coverage_diagnostics(self.plan),
            "direct_route_intelligence": self.direct_route_intel,
            "failure_count": len(self.failures),
            "failures": self.failures,
            "included_segment_result_count": min(len(self.segment_results), args.include_segment_results),
        }
        if date_window_inventory is not None:
            assembled["live_search"]["date_window_inventory"] = date_window_inventory
        assembled["segment_results"] = self.segment_results[: args.include_segment_results]
        return attach_agent_report(assembled, args, store)

    # --- skip-predicate methods ---

    def _skipped_by_offer_keys(
        self,
        spec: dict[str, Any],
        *,
        keys: list[tuple[str, str, str, str]],
        reason: str,
        note: str,
    ) -> dict[str, Any] | None:
        matched = [
            {
                "direction": key[0],
                "leg": key[1],
                "origin": key[2],
                "destination": key[3],
                "offer_count": self.offer_counts[key],
            }
            for key in keys
            if int(self.offer_counts.get(key, 0)) > 0
        ]
        if not matched:
            return None
        return {
            **spec,
            "status": "skipped",
            "reason": reason,
            "offer_count": 0,
            "skipped_because": {
                "matched_offer_counts": matched,
                "note": note,
            },
        }

    def _skipped_by_preferred_airport_tier(self, spec: dict[str, Any]) -> dict[str, Any] | None:
        return self._skipped_by_offer_keys(
            spec,
            keys=preferred_keys_for_deferred_airport(spec, self.plan),
            reason="preferred_airport_tier_has_offers",
            note="Fallback airport tier was deferred because a preferred airport tier already produced accepted offers.",
        )

    def _skipped_by_city_code_primary(self, spec: dict[str, Any]) -> dict[str, Any] | None:
        return self._skipped_by_offer_keys(
            spec,
            keys=city_code_primary_keys_for_deferred_airport(spec),
            reason="city_code_request_has_offers",
            note="Exact airport deferred probe was skipped because the provider city-code request already produced accepted offers.",
        )

    def _skipped_by_condition(self, spec: dict[str, Any]) -> dict[str, Any] | None:
        direct_skip = self._skipped_by_direct_route_intel(spec)
        if direct_skip is not None:
            return direct_skip
        preferred_skip = self._skipped_by_preferred_airport_tier(spec)
        if preferred_skip is not None:
            return preferred_skip
        city_code_skip = self._skipped_by_city_code_primary(spec)
        if city_code_skip is not None:
            return city_code_skip
        condition = spec.get("skip_if_offer_exists")
        if not isinstance(condition, dict):
            priority_direction = spec.get("skip_if_priority_route_viable")
            if not priority_direction:
                return None
            direction = str(priority_direction)
            if not self._priority_route_viable(direction):
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
        if int(self.offer_counts.get(key, 0)) <= 0:
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
                "offer_count": self.offer_counts[key],
            },
        }

    def _skipped_by_direct_route_intel(self, spec: dict[str, Any]) -> dict[str, Any] | None:
        if self.direct_route_index is None or spec.get("leg") not in {Leg.DIRECT_OUTBOUND, Leg.DIRECT_RETURN}:
            return None
        direct_route_index = self.direct_route_index
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

    def _priority_route_viable(self, direction: str) -> bool:
        if self.plan.get("routing_strategy") != RoutingStrategy.RU_PRIORITY:
            return False
        if direction in self.priority_route_viability:
            return self.priority_route_viability[direction]
        self._ensure_moscow_gateway_control_synthesized(direction)
        if direction == Direction.OUTBOUND:
            first_leg = Leg.ORIGIN_TO_HUB
            second_leg = Leg.HUB_TO_DESTINATION
            direct_leg = Leg.DIRECT_OUTBOUND
        elif direction == Direction.RETURN:
            first_leg = Leg.DESTINATION_TO_HUB
            second_leg = Leg.HUB_TO_ORIGIN
            direct_leg = Leg.DIRECT_RETURN
        else:
            return False
        direct = direct_journeys(self.segment_results, direct_leg, direction, self.args.limit_per_pair)
        if direct:
            self.priority_route_viability[direction] = True
            return True
        pairs, _ = assemble_direction(
            self.segment_results,
            first_leg,
            second_leg,
            direction,
            self.args.limit_per_pair,
            ticketing=self.args.ticketing,
            min_same_airport=self.args.min_same_airport_min,
            min_cross_airport=self.args.min_cross_airport_min,
            profile=self.args.profile,
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
        self.priority_route_viability[direction] = viable
        return viable

    def _ensure_moscow_gateway_control_synthesized(self, direction: str | None = None) -> None:
        directions = {"outbound", "return"} if direction is None else {direction}
        pending = directions - self.synthetic_moscow_control_done
        if not pending:
            return
        self.synthetic_moscow_control_done.update(pending)
        synthetic_results, synthetic_searches = synthesize_moscow_gateway_control_results(
            self.plan, self.segment_results, directions=pending,
        )
        self.segment_results.extend(synthetic_results)
        self.searches.extend(synthetic_searches)
        for search in synthetic_searches:
            key = (
                str(search.get("direction") or ""),
                str(search.get("leg") or ""),
                str(search.get("origin") or "").upper(),
                str(search.get("destination") or "").upper(),
            )
            self.offer_counts[key] = self.offer_counts.get(key, 0) + int(search.get("offer_count") or 0)

    def _record_segment_probe_summary(
        self,
        spec: dict[str, Any],
        summary: dict[str, Any],
        *,
        provider_result: Any | None = None,
    ) -> None:
        intent_spec = {**spec, "only_carriers": spec.get("only_carriers") or self.only_carriers}
        intent = intent_from_segment(intent_spec, provider=summary.get("provider"), probe_id=summary.get("probe_id"))
        status = summary.get("status")
        if status == "deduped":
            self.probe_ledger.record_deduped(intent, original_probe_id=summary.get("original_probe_id"))
            return
        self.probe_ledger.plan_intents([intent])
        if provider_result is not None:
            self.probe_ledger.record_provider_result(intent, provider_result)
            return
        if status == "skipped":
            self.probe_ledger.record_skipped(intent, reason=summary.get("reason"))
            return
        if status == "error":
            self.probe_ledger.record_failed(intent, provider=summary.get("provider"), error=summary.get("error"))
            return
        if status == "not_supported":
            self.probe_ledger.record_not_supported(intent, provider=summary.get("provider"), reason=summary.get("reason"))
            return
        self.probe_ledger.record_searched(
            intent,
            status=status or "ok",
            provider=summary.get("provider"),
            offer_count=summary.get("offer_count", 0),
            cache_status=summary.get("cache_status"),
        )


def run_live_route_assembly(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return LiveAssemblyRunner(args, store).run()