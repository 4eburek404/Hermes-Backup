from __future__ import annotations

import argparse
from datetime import date, timedelta
from typing import Any

from ..config import (
    DEFAULT_KB_ROUTE_OUTBOUND_SECOND_LEG_DAY_OFFSETS,
    DEFAULT_KB_ROUTE_RETURN_SECOND_LEG_DAY_OFFSETS,
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
from ..domain.normalize import normalize_profile, parse_iso_date
from ..domain.vocabulary import Direction, Leg, MarketClass, RequiredControl, RouteFamily, RoutingStrategy
from ..errors import CliError
from ..execution.synthetic_control_runner import synthesize_moscow_gateway_control_results
from ..pipeline.search_pipeline import LiveRouteSearchFlow, build_live_route_search_flow
from ..store import Store
from .live_assembly_runner import (
    LiveAssemblyRunner,
    city_code_primary_keys_for_deferred_airport,
    direct_route_intel_context,
    endpoint_group_code,
    fetch_kupibilet_search,
    hub_viability_summary,
    plan_has_svx_direct_control,
    preferred_keys_for_deferred_airport,
    provider_city_code_side,
)
from .route_graph import (
    append_unique_route_segment,
    coverage_controls_for_plan,
    resolve_route_graph_context,
    route_families_for_strategy,
    route_graph_from_segments,
)

# Re-export fetch_kupibilet_search for backward compatibility.
# Tests and callers that patch ``flights_cli.orchestrators.live_assemble.fetch_kupibilet_search``
# should now patch ``flights_cli.orchestrators.live_assembly_runner.fetch_kupibilet_search``
# instead, because LiveAssemblyRunner reads the hook from its own module.
# The re-export here is kept so that ``from live_assemble import fetch_kupibilet_search``
# still works for any code that imported it before the split.


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


def run_live_route_assembly(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    return LiveAssemblyRunner(args, store, plan_builder=build_live_route_segment_plan).run()