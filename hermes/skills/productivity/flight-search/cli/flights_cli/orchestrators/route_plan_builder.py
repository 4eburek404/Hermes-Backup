"""Segment fallback planner behind the legacy RoutePlanBuilder API.

The public class name still says RoutePlanBuilder for compatibility. Its
current responsibility is the fallback segment plan consumed by live execution
and dry diagnostics. Primary full-route offer queries belong in
SearchPlan.primary_offer_queries, not in this legacy segment planner.
"""

from __future__ import annotations

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
    SUPPORTED_CURRENCIES,
)
from ..domain.airports import explicit_or_resolved_airports
from ..domain.normalize import normalize_profile, parse_iso_date
from ..domain.vocabulary import (
    Direction,
    Leg,
    MarketClass,
    RequiredControl,
    RouteFamily,
    RoutingStrategy,
)
from ..errors import CliError
from ..pipeline.options import LiveAssemblyOptions
from ..pipeline.search_pipeline import LiveRouteSearchFlow, build_live_route_search_flow
from ..store import Store

from .route_graph import (
    append_unique_route_segment,
    complete_route_families,
    coverage_controls_for_plan,
    resolve_route_graph_context,
    route_families_for_strategy,
    route_graph_from_segments,
)


# ---------------------------------------------------------------------------
# Planner-only helper functions
# ---------------------------------------------------------------------------


def provider_policy_allows_kupibilet(policy: str | None) -> bool:
    normalized = str(policy or "kupibilet").strip().lower()
    return normalized in {"auto", "kupibilet"}


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
    deferred_airports = [
        str(code).upper()
        for code in KUPIBILET_CITY_CODE_FIRST_AIRPORTS.get(normalized_city, [])
    ]
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


def normalize_day_offsets(
    values: list[int] | None, default: list[int], field: str
) -> list[int]:
    raw_values = default if values is None else values
    offsets: list[int] = []
    for value in raw_values:
        try:
            offset = int(value)
        except (TypeError, ValueError) as exc:
            raise CliError(
                f"{field} must be an integer day offset, got {value!r}",
                error_type="validation_error",
            ) from exc
        if offset < 0 or offset > 7:
            raise CliError(
                f"{field} must be between 0 and 7 days, got {offset}",
                error_type="validation_error",
            )
        if offset not in offsets:
            offsets.append(offset)
    return offsets


def resolve_date_window(
    options: LiveAssemblyOptions, depart: date, ret: date | None, *, direct_only: bool
) -> list[date]:
    """Expand route_options.date_window_end into bounded per-date direct inventory dates.

    This is the executable replacement for the manual per-date probe loop that
    references/direct-date-window.md used to describe in prose.
    """

    window_end_raw = options.route.date_window_end
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
        raise CliError(
            "date-window-end must be on or after depart-date",
            error_type="validation_error",
        )
    window_days = (window_end - depart).days + 1
    if window_days > MAX_DATE_WINDOW_DAYS:
        raise CliError(
            f"date window spans {window_days} days; bound it to at most {MAX_DATE_WINDOW_DAYS} days",
            error_type="validation_error",
            details={"window_days": window_days, "max_days": MAX_DATE_WINDOW_DAYS},
        )
    return [depart + timedelta(days=offset) for offset in range(window_days)]


# ---------------------------------------------------------------------------
# RoutePlanBuilder (legacy name for the segment fallback planner)
# ---------------------------------------------------------------------------


class RoutePlanBuilder:
    """Builds the segment fallback plan from typed options and store.

    This class is a structural extraction of the former
    ``build_live_route_segment_plan`` function.  It preserves
    behaviour exactly — the ``build`` method body is a copy-paste
    of the original function body.

    Keep this class focused on fallback segment probes. New primary through-offer
    planning should be represented by ``SearchPlan.primary_offer_queries``.
    """

    def __init__(
        self,
        options: LiveAssemblyOptions,
        store: Store,
        *,
        flow: LiveRouteSearchFlow | None = None,
    ) -> None:
        self._options = options
        self._store = store

        origin_airports_arg = list(options.route.origin_airports) or None
        destination_airports_arg = list(options.route.destination_airports) or None

        self.depart = parse_iso_date(options.route.depart_date, "depart-date")
        self.ret = (
            parse_iso_date(options.route.return_date, "return-date")
            if options.route.return_date
            else None
        )
        self.currency = options.currency.upper()
        if self.currency not in SUPPORTED_CURRENCIES:
            raise CliError(
                f"currency must be one of {', '.join(sorted(SUPPORTED_CURRENCIES))}",
                error_type="validation_error",
            )
        self.profile = normalize_profile(options.profile)
        self.flow = (
            flow if flow is not None else build_live_route_search_flow(options, store)
        )
        self.direct_only = bool(self.flow.evidence_plan.direct_only)
        self.window_dates = resolve_date_window(
            options, self.depart, self.ret, direct_only=self.direct_only
        )

        self.origin = store.resolve_location(options.route.origin)
        self.destination = store.resolve_location(options.route.destination)
        self.origin_airports = explicit_or_resolved_airports(
            store,
            self.origin,
            origin_airports_arg,
            role="origin",
            max_airports=options.route.max_airports_per_city,
        )
        self.destination_airports = explicit_or_resolved_airports(
            store,
            self.destination,
            destination_airports_arg,
            role="destination",
            max_airports=options.route.max_airports_per_city,
        )
        self.provider_policy = str(options.evidence.provider_policy or "kupibilet")
        self.origin_segment_options = city_code_first_segment_options(
            city_code=self.origin.code,
            airports=self.origin_airports,
            explicit=origin_airports_arg,
            provider_policy=self.provider_policy,
        )
        self.destination_segment_options = city_code_first_segment_options(
            city_code=self.destination.code,
            airports=self.destination_airports,
            explicit=destination_airports_arg,
            provider_policy=self.provider_policy,
        )
        self.route_context = resolve_route_graph_context(
            options,
            store,
            self.origin,
            self.destination,
            self.origin_airports,
            self.destination_airports,
        )
        self.routing_strategy = self.route_context.routing_strategy
        self.hubs = self.route_context.hubs
        self.hub_source = self.route_context.hub_source
        self.routing_profile = self.route_context.routing_profile
        self.use_gateway_discovery_for_fallback_hubs = bool(
            options.route.use_gateway_discovery_for_fallback_hubs
        )
        self._include_imperative_primary_hub = not (
            self.routing_strategy == RoutingStrategy.RU_PRIORITY
            and self.use_gateway_discovery_for_fallback_hubs
        )
        if not self._include_imperative_primary_hub:
            self.hubs = [hub for hub in self.hubs if hub != PRIORITY_PRIMARY_HUB]
        self.outbound_second_offsets = normalize_day_offsets(
            list(options.evidence.outbound_second_leg_day_offsets) or None,
            DEFAULT_KB_ROUTE_OUTBOUND_SECOND_LEG_DAY_OFFSETS,
            "outbound-second-leg-day-offset",
        )
        self.return_second_offsets = normalize_day_offsets(
            list(options.evidence.return_second_leg_day_offsets) or None,
            DEFAULT_KB_ROUTE_RETURN_SECOND_LEG_DAY_OFFSETS,
            "return-second-leg-day-offset",
        )

        self.segments: list[dict[str, Any]] = []
        self._seen: set[tuple[str, ...]] = set()

        self.route_families = route_families_for_strategy(
            self.routing_strategy, self.routing_profile
        )
        if not self._include_imperative_primary_hub:
            self.route_families = [
                family
                for family in self.route_families
                if family.get("id") not in {"ist_direct", "ist_shared_destination"}
            ]
        self._include_generic_direct_controls = (
            self.flow.flow_decision.market_class == MarketClass.GLOBAL_NON_RU
        )
        endpoint_airports = {
            *(code.upper() for code in self.origin_airports),
            *(code.upper() for code in self.destination_airports),
        }
        self._connection_hubs = [
            hub for hub in self.hubs if hub.upper() not in endpoint_airports
        ]
        self._moscow_gateway_eligible = (
            self.routing_strategy == RoutingStrategy.RU_PRIORITY
            and str(self.origin.code or "").upper() != "MOW"
            and str(self.destination.code or "").upper() != "MOW"
        )
        self._gateway_segment_options: list[tuple[str, dict[str, Any]]] = []
        if self._moscow_gateway_eligible:
            self._gateway_segment_options = city_code_first_segment_options(
                city_code="MOW",
                airports=[
                    str(code).upper()
                    for code in KUPIBILET_CITY_CODE_FIRST_AIRPORTS.get(
                        "MOW", [PRIORITY_MOSCOW_GATEWAY]
                    )
                ],
                explicit=None,
                provider_policy=self.provider_policy,
            )

    def _add_segment(
        self,
        direction: str,
        leg: str,
        dep_date: date,
        origin_code: str,
        dest_code: str,
        **extra: Any,
    ) -> None:
        append_unique_route_segment(
            self.segments,
            self._seen,
            direction=direction,
            leg=leg,
            dep_date=dep_date,
            origin_code=origin_code,
            dest_code=dest_code,
            include_date=True,
            extra=extra,
        )

    def build(self) -> dict[str, Any]:
        self._build_outbound()
        if self.ret:
            self._build_return()
        return self._build_result()

    def _build_outbound(self) -> None:
        if self.direct_only:
            self._build_outbound_direct_only()
        elif self.routing_strategy == RoutingStrategy.RU_PRIORITY:
            self._build_outbound_ru_priority()
        elif self.routing_strategy == RoutingStrategy.DOMESTIC_RU:
            self._build_outbound_domestic_ru()
        else:
            self._build_outbound_hub_list()

    def _build_return(self) -> None:
        if self.direct_only:
            self._build_return_direct_only()
        elif self.routing_strategy == RoutingStrategy.RU_PRIORITY:
            self._build_return_ru_priority()
        elif self.routing_strategy == RoutingStrategy.DOMESTIC_RU:
            self._build_return_domestic_ru()
        else:
            self._build_return_hub_list()

    def _build_outbound_direct_only(self) -> None:
        self.route_families = [
            {
                "id": RouteFamily.DIRECT_INVENTORY,
                "priority": 0,
                "condition": "direct-only request: search exact origin/destination airport pairs and do not assemble connecting fallback routes.",
            }
        ]
        for inventory_date in self.window_dates or [self.depart]:
            for dest_code, dest_extra in self.destination_segment_options:
                for origin_code, origin_extra in self.origin_segment_options:
                    self._add_segment(
                        Direction.OUTBOUND,
                        Leg.DIRECT_OUTBOUND,
                        inventory_date,
                        origin_code,
                        dest_code,
                        route_family=RouteFamily.DIRECT_INVENTORY,
                        priority=0,
                        **{**origin_extra, **dest_extra},
                    )

    def _build_outbound_ru_priority(self) -> None:
        for dest_code, dest_extra in self.destination_segment_options:
            for origin_code, origin_extra in self.origin_segment_options:
                self._add_segment(
                    Direction.OUTBOUND,
                    Leg.DIRECT_OUTBOUND,
                    self.depart,
                    origin_code,
                    dest_code,
                    route_family="direct_control",
                    priority=0,
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    **{**origin_extra, **dest_extra},
                )
        if self.routing_profile == "asia-oceania":
            for origin_code in self.origin_airports:
                self._add_segment(
                    Direction.OUTBOUND,
                    Leg.ORIGIN_TO_HUB,
                    self.depart,
                    origin_code,
                    PRIORITY_ASIA_HUB,
                    route_family="svo_asia",
                    priority=1,
                    only_carriers=["SU"],
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                )
            for offset in self.outbound_second_offsets:
                leg_date = self.depart + timedelta(days=offset)
                for dest_code in self.destination_airports:
                    self._add_segment(
                        Direction.OUTBOUND,
                        Leg.HUB_TO_DESTINATION,
                        leg_date,
                        PRIORITY_ASIA_HUB,
                        dest_code,
                        route_family="svo_asia",
                        priority=1,
                        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    )
        for origin_code in self.origin_airports:
            if self._include_imperative_primary_hub:
                self._add_segment(
                    Direction.OUTBOUND,
                    Leg.ORIGIN_TO_HUB,
                    self.depart,
                    origin_code,
                    PRIORITY_PRIMARY_HUB,
                    route_family="ist_direct",
                    priority=2 if self.routing_profile == "asia-oceania" else 1,
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                )
            if origin_code != PRIORITY_MOSCOW_GATEWAY:
                self._add_segment(
                    Direction.OUTBOUND,
                    "origin_to_gateway",
                    self.depart,
                    origin_code,
                    PRIORITY_MOSCOW_GATEWAY,
                    route_family="moscow_gateway_control",
                    priority=3 if self.routing_profile == "asia-oceania" else 2,
                    only_carriers=["SU"],
                )
                if self._include_imperative_primary_hub:
                    self._add_segment(
                        Direction.OUTBOUND,
                        "gateway_to_hub",
                        self.depart,
                        PRIORITY_MOSCOW_GATEWAY,
                        PRIORITY_PRIMARY_HUB,
                        route_family="moscow_gateway_control",
                        priority=3 if self.routing_profile == "asia-oceania" else 2,
                        only_carriers=["SU"],
                    )
        if self._include_imperative_primary_hub:
            for offset in self.outbound_second_offsets:
                leg_date = self.depart + timedelta(days=offset)
                for dest_code in self.destination_airports:
                    self._add_segment(
                        Direction.OUTBOUND,
                        Leg.HUB_TO_DESTINATION,
                        leg_date,
                        PRIORITY_PRIMARY_HUB,
                        dest_code,
                        route_family="ist_shared_destination",
                        priority=2 if self.routing_profile == "asia-oceania" else 1,
                        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    )
        for gateway_code, gateway_extra in self._gateway_segment_options:
            for dest_code in self.destination_airports:
                self._add_segment(
                    Direction.OUTBOUND,
                    "gateway_to_destination",
                    self.depart,
                    gateway_code,
                    dest_code,
                    route_family="moscow_gateway_control",
                    priority=3 if self.routing_profile == "asia-oceania" else 2,
                    **gateway_extra,
                )

    def _build_outbound_domestic_ru(self) -> None:
        for dest_code, dest_extra in self.destination_segment_options:
            for origin_code, origin_extra in self.origin_segment_options:
                self._add_segment(
                    Direction.OUTBOUND,
                    Leg.DIRECT_OUTBOUND,
                    self.depart,
                    origin_code,
                    dest_code,
                    route_family=RouteFamily.DOMESTIC_RU,
                    priority=0,
                    **{**origin_extra, **dest_extra},
                )
        for origin_code in self.origin_airports:
            for hub in self._connection_hubs:
                self._add_segment(
                    Direction.OUTBOUND,
                    Leg.ORIGIN_TO_HUB,
                    self.depart,
                    origin_code,
                    hub,
                    route_family=RouteFamily.DOMESTIC_RU,
                    priority=1,
                )
        for offset in self.outbound_second_offsets:
            leg_date = self.depart + timedelta(days=offset)
            for hub in self._connection_hubs:
                for dest_code in self.destination_airports:
                    self._add_segment(
                        Direction.OUTBOUND,
                        Leg.HUB_TO_DESTINATION,
                        leg_date,
                        hub,
                        dest_code,
                        route_family=RouteFamily.DOMESTIC_RU,
                        priority=1,
                    )

    def _build_outbound_hub_list(self) -> None:
        if self._include_generic_direct_controls:
            for dest_code, dest_extra in self.destination_segment_options:
                for origin_code, origin_extra in self.origin_segment_options:
                    self._add_segment(
                        Direction.OUTBOUND,
                        Leg.DIRECT_OUTBOUND,
                        self.depart,
                        origin_code,
                        dest_code,
                        route_family="direct_control",
                        priority=0,
                        **{**origin_extra, **dest_extra},
                    )
        for origin_code in self.origin_airports:
            for hub in self.hubs:
                self._add_segment(
                    Direction.OUTBOUND,
                    Leg.ORIGIN_TO_HUB,
                    self.depart,
                    origin_code,
                    hub,
                    route_family=RouteFamily.HUB_LIST,
                    priority=1,
                )
        for offset in self.outbound_second_offsets:
            leg_date = self.depart + timedelta(days=offset)
            for hub in self.hubs:
                for dest_code in self.destination_airports:
                    self._add_segment(
                        Direction.OUTBOUND,
                        Leg.HUB_TO_DESTINATION,
                        leg_date,
                        hub,
                        dest_code,
                        route_family=RouteFamily.HUB_LIST,
                        priority=1,
                    )

    def _build_return_direct_only(self) -> None:
        for dest_code, dest_extra in self.destination_segment_options:
            for origin_code, origin_extra in self.origin_segment_options:
                self._add_segment(
                    Direction.RETURN,
                    Leg.DIRECT_RETURN,
                    self.ret,
                    dest_code,
                    origin_code,
                    route_family=RouteFamily.DIRECT_INVENTORY,
                    priority=0,
                    **{**dest_extra, **origin_extra},
                )

    def _build_return_ru_priority(self) -> None:
        for dest_code, dest_extra in self.destination_segment_options:
            for origin_code, origin_extra in self.origin_segment_options:
                self._add_segment(
                    Direction.RETURN,
                    Leg.DIRECT_RETURN,
                    self.ret,
                    dest_code,
                    origin_code,
                    route_family="direct_control",
                    priority=0,
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    **{**dest_extra, **origin_extra},
                )
        if self.routing_profile == "asia-oceania":
            for dest_code in self.destination_airports:
                self._add_segment(
                    Direction.RETURN,
                    Leg.DESTINATION_TO_HUB,
                    self.ret,
                    dest_code,
                    PRIORITY_ASIA_HUB,
                    route_family="svo_asia",
                    priority=1,
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                )
            for offset in self.return_second_offsets:
                leg_date = self.ret + timedelta(days=offset)
                for origin_code in self.origin_airports:
                    self._add_segment(
                        Direction.RETURN,
                        Leg.HUB_TO_ORIGIN,
                        leg_date,
                        PRIORITY_ASIA_HUB,
                        origin_code,
                        route_family="svo_asia",
                        priority=1,
                        only_carriers=["SU"],
                        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    )
        if self._include_imperative_primary_hub:
            for dest_code in self.destination_airports:
                self._add_segment(
                    Direction.RETURN,
                    Leg.DESTINATION_TO_HUB,
                    self.ret,
                    dest_code,
                    PRIORITY_PRIMARY_HUB,
                    route_family="ist_direct",
                    priority=2 if self.routing_profile == "asia-oceania" else 1,
                    preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                )
        for offset in self.return_second_offsets:
            leg_date = self.ret + timedelta(days=offset)
            for origin_code in self.origin_airports:
                if self._include_imperative_primary_hub:
                    self._add_segment(
                        Direction.RETURN,
                        Leg.HUB_TO_ORIGIN,
                        leg_date,
                        PRIORITY_PRIMARY_HUB,
                        origin_code,
                        route_family="ist_direct",
                        priority=2 if self.routing_profile == "asia-oceania" else 1,
                        preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
                    )
                if origin_code != PRIORITY_MOSCOW_GATEWAY:
                    if self._include_imperative_primary_hub:
                        self._add_segment(
                            Direction.RETURN,
                            "hub_to_gateway",
                            leg_date,
                            PRIORITY_PRIMARY_HUB,
                            PRIORITY_MOSCOW_GATEWAY,
                            route_family="moscow_gateway_control",
                            priority=3 if self.routing_profile == "asia-oceania" else 2,
                            only_carriers=["SU"],
                        )
                    self._add_segment(
                        Direction.RETURN,
                        "gateway_to_origin",
                        leg_date,
                        PRIORITY_MOSCOW_GATEWAY,
                        origin_code,
                        route_family="moscow_gateway_control",
                        priority=3 if self.routing_profile == "asia-oceania" else 2,
                        only_carriers=["SU"],
                    )
        for gateway_code, gateway_extra in self._gateway_segment_options:
            for dest_code in self.destination_airports:
                self._add_segment(
                    Direction.RETURN,
                    "destination_to_gateway",
                    self.ret,
                    dest_code,
                    gateway_code,
                    route_family="moscow_gateway_control",
                    priority=3 if self.routing_profile == "asia-oceania" else 2,
                    **gateway_extra,
                )

    def _build_return_domestic_ru(self) -> None:
        for dest_code, dest_extra in self.destination_segment_options:
            for origin_code, origin_extra in self.origin_segment_options:
                self._add_segment(
                    Direction.RETURN,
                    Leg.DIRECT_RETURN,
                    self.ret,
                    dest_code,
                    origin_code,
                    route_family=RouteFamily.DOMESTIC_RU,
                    priority=0,
                    **{**dest_extra, **origin_extra},
                )
        for dest_code in self.destination_airports:
            for hub in self._connection_hubs:
                self._add_segment(
                    Direction.RETURN,
                    Leg.DESTINATION_TO_HUB,
                    self.ret,
                    dest_code,
                    hub,
                    route_family=RouteFamily.DOMESTIC_RU,
                    priority=1,
                )
        for offset in self.return_second_offsets:
            leg_date = self.ret + timedelta(days=offset)
            for hub in self._connection_hubs:
                for origin_code in self.origin_airports:
                    self._add_segment(
                        Direction.RETURN,
                        Leg.HUB_TO_ORIGIN,
                        leg_date,
                        hub,
                        origin_code,
                        route_family=RouteFamily.DOMESTIC_RU,
                        priority=1,
                    )

    def _build_return_hub_list(self) -> None:
        if self._include_generic_direct_controls:
            for dest_code, dest_extra in self.destination_segment_options:
                for origin_code, origin_extra in self.origin_segment_options:
                    self._add_segment(
                        Direction.RETURN,
                        Leg.DIRECT_RETURN,
                        self.ret,
                        dest_code,
                        origin_code,
                        route_family="direct_control",
                        priority=0,
                        **{**dest_extra, **origin_extra},
                    )
        for dest_code in self.destination_airports:
            for hub in self.hubs:
                self._add_segment(
                    Direction.RETURN,
                    Leg.DESTINATION_TO_HUB,
                    self.ret,
                    dest_code,
                    hub,
                    route_family=RouteFamily.HUB_LIST,
                    priority=1,
                )
        for offset in self.return_second_offsets:
            leg_date = self.ret + timedelta(days=offset)
            for hub in self.hubs:
                for origin_code in self.origin_airports:
                    self._add_segment(
                        Direction.RETURN,
                        Leg.HUB_TO_ORIGIN,
                        leg_date,
                        hub,
                        origin_code,
                        route_family=RouteFamily.HUB_LIST,
                        priority=1,
                    )

    def _build_result(self) -> dict[str, Any]:
        assembly_warning = (
            "KupiBilet live segment assembly uses direct-only one-way searches; availability and price still require final booking-screen recheck."
            if self.provider_policy.strip().lower() == "kupibilet"
            else "Provider-policy live assembly uses provider-selected direct-only one-way searches; availability and price still require final booking-screen recheck."
        )
        warnings = [
            assembly_warning,
            "Assembled candidates are usually separate-ticket/self-transfer unless the booking site later confirms protected through-ticketing.",
        ]
        if self.routing_strategy == RoutingStrategy.RU_PRIORITY:
            if self.routing_profile == "asia-oceania":
                if self._include_imperative_primary_hub:
                    warnings.append(
                        "Using geo-aware ru-priority routing: direct control, SVO as an independent Asia/Oceania hub, IST fallback; secondary fallback hubs are gateway discovery candidates only."
                    )
                else:
                    warnings.append(
                        "Using geo-aware ru-priority routing: direct control and SVO/Moscow controls; primary and secondary bridge gateways are gateway discovery candidates only."
                    )
            else:
                if self._include_imperative_primary_hub:
                    warnings.append(
                        "Using ru-priority routing: direct control, IST direct first, SVO/Moscow gateway control even when direct exists; secondary fallback hubs are gateway discovery candidates only."
                    )
                else:
                    warnings.append(
                        "Using ru-priority routing: direct control and SVO/Moscow gateway control; bridge gateways are gateway discovery candidates only."
                    )
        elif self.routing_strategy == RoutingStrategy.DOMESTIC_RU:
            warnings.append(
                "Using domestic-RU routing: direct domestic controls first, Moscow airports only as bounded fallback; international hubs are excluded by default."
            )
        elif self.hub_source == "default":
            warnings.append(
                "Using built-in hub list; pass --hub repeatedly to narrow live segment searches."
            )
        if (
            self.hub_source == "manual"
            and any(hub in {"IST", "SAW"} for hub in self.hubs)
            and not {"IST", "SAW"}.issubset(set(self.hubs))
        ):
            warnings.append(
                "For Istanbul, include both --hub IST and --hub SAW when comparing airport systems."
            )

        coverage_controls = coverage_controls_for_plan(
            coverage_mode=self.route_context.coverage_mode,
            origin_code=str(self.origin.code).upper(),
            destination_code=str(self.destination.code).upper(),
            origin_airports=self.origin_airports,
            destination_airports=self.destination_airports,
            depart=self.depart,
            ret=self.ret,
            depart_dates=self.window_dates or None,
            preferred_carriers=list(PRIORITY_ROUTE_CARRIERS),
            requested_controls=self.route_context.coverage_limits.get(
                "requested_controls"
            ),
            coverage_control_limit=self.route_context.coverage_limits.get(
                "coverage_control_limit"
            ),
        )
        if self.direct_only:
            coverage_controls = [
                control
                for control in coverage_controls
                if control.get("type") == RequiredControl.EXACT_AIRPORT_DIRECT
            ]
        route_graph = route_graph_from_segments(
            routing_strategy=self.routing_strategy,
            routing_profile=self.routing_profile,
            hubs=self.hubs,
            origin_airports=self.origin_airports,
            destination_airports=self.destination_airports,
            segments=self.segments,
        )
        route_families = complete_route_families(
            self.route_families, route_graph["families"]
        )

        return {
            "origin": self.origin.code,
            "destination": self.destination.code,
            "origin_airports": self.origin_airports,
            "destination_airports": self.destination_airports,
            "hubs": self.hubs,
            "hub_source": self.hub_source,
            "routing_strategy": self.routing_strategy,
            "routing_profile": self.routing_profile,
            "airport_scope": self.route_context.airport_scope,
            "coverage_mode": self.route_context.coverage_mode,
            "coverage_controls": coverage_controls,
            "coverage_limits": {
                **self.route_context.coverage_limits,
                "freshness_policy": self.flow.evidence_plan.freshness_policy,
                "required_controls": list(self.flow.evidence_plan.required_controls),
                "absence_taxonomy": list(self.flow.evidence_plan.absence_taxonomy),
                "missing_evidence": list(self.flow.evidence_plan.missing_evidence),
            },
            "direct_only": self.direct_only,
            "flow_decision": self.flow.flow_decision.to_dict(),
            "evidence_plan": self.flow.evidence_plan.to_dict(),
            "route_graph": route_graph,
            "route_families": route_families,
            "dates": {
                "depart": self.depart.isoformat(),
                "return": self.ret.isoformat() if self.ret else None,
                **(
                    {"window_end": self.window_dates[-1].isoformat()}
                    if self.window_dates
                    else {}
                ),
            },
            "currency": self.currency,
            "profile": self.profile,
            "ticketing": self._options.ticketing,
            "second_leg_day_offsets": {
                "outbound": self.outbound_second_offsets,
                "return": self.return_second_offsets if self.ret else [],
            },
            "segments": self.segments,
            "warnings": warnings,
            "metrics": {"segment_search_count": len(self.segments)},
        }
