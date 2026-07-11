from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import (
    DEFAULT_COVERAGE_CONTROL_LIMIT,
    DEFAULT_CURRENCY,
    DEFAULT_GATEWAY_DISCOVERY_LIMIT,
    DEFAULT_GATEWAY_PROBE_BATCH_SIZE,
    DEFAULT_GATEWAY_PROBE_MAX_BATCHES,
    DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    DEFAULT_PROFILE,
    DEFAULT_ROUTING_STRATEGY,
    DEFAULT_SEARCH_WAVE_MAX_WAVES,
    DEFAULT_SEARCH_WAVE_PROBE_LIMIT,
    DEFAULT_SEARCH_WAVE_TOP_K,
    FLI_MCP_DEFAULT_URL,
    PRIORITY_ROUTE_CARRIERS,
    catalog_output_limits_from_mapping,
)
from ..domain.vocabulary import RoutingStrategy


@dataclass(frozen=True, slots=True)
class RouteOptions:
    origin: str
    destination: str
    depart_date: str
    return_date: str | None
    routing_strategy: str
    hubs: tuple[str, ...]
    origin_airports: tuple[str, ...]
    destination_airports: tuple[str, ...]
    max_airports_per_city: int
    max_connections: int | None
    tier2_max_connections: int | None
    date_window_end: str | None
    stop_policy: str
    min_same_airport_min: int
    min_cross_airport_min: int
    use_gateway_discovery_for_fallback_hubs: bool
    gateway_discovery_limit: int
    gateway_probe_batch_size: int
    gateway_probe_max_batches: int


@dataclass(frozen=True, slots=True)
class FilterOptions:
    only_carriers: tuple[str, ...]
    exclude_carriers: tuple[str, ...]
    prefer_carriers: tuple[str, ...]
    avoid_carriers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceOptions:
    provider_policy: str
    primary_offer_limit: int
    coverage_mode: str
    coverage_controls: tuple[str, ...]
    coverage_control_limit: int
    aggregate_control_limit: int
    aggregate_control_carriers: tuple[str, ...]
    max_segment_searches: int
    live_cache_ttl_seconds: int
    no_live_cache: bool
    segment_limit: int
    timeout: int
    outbound_second_leg_day_offsets: tuple[int, ...]
    return_second_leg_day_offsets: tuple[int, ...]
    search_wave_max_waves: int
    search_wave_probe_limit: int
    search_wave_top_k: int
    fail_fast: bool
    fli_mcp_url: str


@dataclass(frozen=True, slots=True)
class OutputOptions:
    catalog_limit: int
    direct_catalog_limit: int


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """Canonical immutable request used by planning and execution."""

    route: RouteOptions
    filters: FilterOptions
    evidence: EvidenceOptions
    output: OutputOptions
    profile: str
    ticketing: str
    currency: str
    command_name: str = "search"

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> SearchRequest:
        route = _mapping(payload.get("route_options"))
        evidence = _mapping(payload.get("evidence"))
        filters = _mapping(payload.get("filters"))
        output = _mapping(payload.get("output"))
        output_limits = catalog_output_limits_from_mapping(output)
        return cls(
            route=RouteOptions(
                origin=str(payload.get("origin") or "").upper(),
                destination=str(payload.get("destination") or "").upper(),
                depart_date=str(payload.get("depart_date") or ""),
                return_date=(
                    str(payload.get("return_date"))
                    if payload.get("return_date")
                    else None
                ),
                routing_strategy=str(
                    route.get("routing_strategy") or DEFAULT_ROUTING_STRATEGY
                ),
                hubs=_str_tuple(route.get("hubs")),
                origin_airports=_str_tuple(route.get("origin_airports")),
                destination_airports=_str_tuple(route.get("destination_airports")),
                max_airports_per_city=_int_option(route, "max_airports_per_city", 6),
                max_connections=_optional_int_option(route, "max_connections"),
                tier2_max_connections=_optional_int_option(
                    route, "tier2_max_connections"
                ),
                date_window_end=(
                    str(route.get("date_window_end"))
                    if route.get("date_window_end")
                    else None
                ),
                stop_policy=str(route.get("stop_policy") or "business-default"),
                min_same_airport_min=_int_option(route, "min_same_airport_min", 120),
                min_cross_airport_min=_int_option(route, "min_cross_airport_min", 300),
                use_gateway_discovery_for_fallback_hubs=_bool_option(
                    route, "use_gateway_discovery_for_fallback_hubs", False
                ),
                gateway_discovery_limit=_int_option(
                    route,
                    "gateway_discovery_limit",
                    DEFAULT_GATEWAY_DISCOVERY_LIMIT,
                ),
                gateway_probe_batch_size=_int_option(
                    route,
                    "gateway_probe_batch_size",
                    DEFAULT_GATEWAY_PROBE_BATCH_SIZE,
                ),
                gateway_probe_max_batches=_int_option(
                    route,
                    "gateway_probe_max_batches",
                    DEFAULT_GATEWAY_PROBE_MAX_BATCHES,
                ),
            ),
            filters=FilterOptions(
                only_carriers=_str_tuple(filters.get("only_carriers")),
                exclude_carriers=_str_tuple(filters.get("exclude_carriers")),
                prefer_carriers=_str_tuple(filters.get("prefer_carriers")),
                avoid_carriers=_str_tuple(filters.get("avoid_carriers")),
            ),
            evidence=EvidenceOptions(
                provider_policy=str(payload.get("provider_policy") or "auto").lower(),
                primary_offer_limit=max(
                    output_limits.catalog_limit, output_limits.direct_catalog_limit
                ),
                coverage_mode=str(route.get("coverage_mode") or "targeted"),
                coverage_controls=_str_tuple(route.get("coverage_controls")),
                coverage_control_limit=_int_option(
                    route, "coverage_control_limit", DEFAULT_COVERAGE_CONTROL_LIMIT
                ),
                aggregate_control_limit=_int_option(
                    evidence, "aggregate_control_limit", 0
                ),
                aggregate_control_carriers=_str_tuple(
                    evidence.get("aggregate_control_carriers")
                ),
                max_segment_searches=_int_option(evidence, "max_segment_searches", 300),
                live_cache_ttl_seconds=_int_option(
                    evidence,
                    "live_cache_ttl_seconds",
                    DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
                ),
                no_live_cache=_bool_option(evidence, "no_live_cache", False),
                segment_limit=_int_option(evidence, "segment_limit", 30),
                timeout=_int_option(evidence, "timeout", 60),
                outbound_second_leg_day_offsets=_int_tuple(
                    evidence.get("outbound_second_leg_day_offsets")
                ),
                return_second_leg_day_offsets=_int_tuple(
                    evidence.get("return_second_leg_day_offsets")
                ),
                search_wave_max_waves=_int_option(
                    evidence, "search_wave_max_waves", DEFAULT_SEARCH_WAVE_MAX_WAVES
                ),
                search_wave_probe_limit=_int_option(
                    evidence,
                    "search_wave_probe_limit",
                    DEFAULT_SEARCH_WAVE_PROBE_LIMIT,
                ),
                search_wave_top_k=_int_option(
                    evidence, "search_wave_top_k", DEFAULT_SEARCH_WAVE_TOP_K
                ),
                fail_fast=_bool_option(evidence, "fail_fast", False),
                fli_mcp_url=str(evidence.get("fli_mcp_url") or FLI_MCP_DEFAULT_URL),
            ),
            output=OutputOptions(
                catalog_limit=output_limits.catalog_limit,
                direct_catalog_limit=output_limits.direct_catalog_limit,
            ),
            profile=str(payload.get("profile") or DEFAULT_PROFILE),
            ticketing=str(payload.get("ticketing") or "separate"),
            currency=str(payload.get("currency") or DEFAULT_CURRENCY).upper(),
        )

    def to_payload(self) -> dict[str, Any]:
        """Return the canonical wire projection after Python defaults are applied."""

        return {
            "schema_version": "flight_search_request.v1",
            "origin": self.route.origin,
            "destination": self.route.destination,
            "depart_date": self.route.depart_date,
            "return_date": self.route.return_date,
            "currency": self.currency,
            "profile": self.profile,
            "ticketing": self.ticketing,
            "provider_policy": self.evidence.provider_policy,
            "route_options": {
                "routing_strategy": self.route.routing_strategy,
                "hubs": list(self.route.hubs),
                "origin_airports": list(self.route.origin_airports),
                "destination_airports": list(self.route.destination_airports),
                "max_airports_per_city": self.route.max_airports_per_city,
                "max_connections": self.route.max_connections,
                "tier2_max_connections": self.route.tier2_max_connections,
                "date_window_end": self.route.date_window_end,
                "stop_policy": self.route.stop_policy,
                "min_same_airport_min": self.route.min_same_airport_min,
                "min_cross_airport_min": self.route.min_cross_airport_min,
                "use_gateway_discovery_for_fallback_hubs": (
                    self.route.use_gateway_discovery_for_fallback_hubs
                ),
                "gateway_discovery_limit": self.route.gateway_discovery_limit,
                "gateway_probe_batch_size": self.route.gateway_probe_batch_size,
                "gateway_probe_max_batches": self.route.gateway_probe_max_batches,
                "coverage_mode": self.evidence.coverage_mode,
                "coverage_controls": list(self.evidence.coverage_controls),
                "coverage_control_limit": self.evidence.coverage_control_limit,
            },
            "filters": {
                "only_carriers": list(self.filters.only_carriers),
                "exclude_carriers": list(self.filters.exclude_carriers),
                "prefer_carriers": list(self.filters.prefer_carriers),
                "avoid_carriers": list(self.filters.avoid_carriers),
            },
            "evidence": {
                "segment_limit": self.evidence.segment_limit,
                "timeout": self.evidence.timeout,
                "outbound_second_leg_day_offsets": list(
                    self.evidence.outbound_second_leg_day_offsets
                ),
                "return_second_leg_day_offsets": list(
                    self.evidence.return_second_leg_day_offsets
                ),
                "search_wave_max_waves": self.evidence.search_wave_max_waves,
                "search_wave_probe_limit": self.evidence.search_wave_probe_limit,
                "search_wave_top_k": self.evidence.search_wave_top_k,
                "aggregate_control_limit": self.evidence.aggregate_control_limit,
                "aggregate_control_carriers": list(
                    self.evidence.aggregate_control_carriers
                ),
                "max_segment_searches": self.evidence.max_segment_searches,
                "fail_fast": self.evidence.fail_fast,
                "live_cache_ttl_seconds": self.evidence.live_cache_ttl_seconds,
                "no_live_cache": self.evidence.no_live_cache,
                "fli_mcp_url": self.evidence.fli_mcp_url,
            },
            "output": {
                "catalog_limit": self.output.catalog_limit,
                "direct_catalog_limit": self.output.direct_catalog_limit,
            },
        }

    def effective_only_carriers(self) -> tuple[str, ...]:
        return _unique_strs(self.filters.only_carriers)

    def effective_prefer_carriers(
        self, routing_strategy: str | None = None
    ) -> tuple[str, ...]:
        carriers = list(_unique_strs(self.filters.prefer_carriers))
        if (
            str(routing_strategy or self.route.routing_strategy or "").lower()
            == RoutingStrategy.RU_PRIORITY
        ):
            for carrier in PRIORITY_ROUTE_CARRIERS:
                if carrier not in carriers:
                    carriers.append(carrier)
        return tuple(carriers)

    @property
    def origin(self) -> str:
        return self.route.origin

    @property
    def destination(self) -> str:
        return self.route.destination

    @property
    def depart_date(self) -> str:
        return self.route.depart_date

    @property
    def return_date(self) -> str | None:
        return self.route.return_date

    @property
    def provider_policy(self) -> str:
        return self.evidence.provider_policy

    @property
    def primary_offer_limit(self) -> int:
        return self.evidence.primary_offer_limit

    @property
    def routing_strategy(self) -> str:
        return self.route.routing_strategy

    @property
    def hubs(self) -> tuple[str, ...]:
        return self.route.hubs

    @property
    def origin_airports(self) -> tuple[str, ...]:
        return self.route.origin_airports

    @property
    def destination_airports(self) -> tuple[str, ...]:
        return self.route.destination_airports

    @property
    def max_connections(self) -> int | None:
        return self.route.max_connections

    @property
    def tier2_max_connections(self) -> int | None:
        return self.route.tier2_max_connections

    @property
    def date_window_end(self) -> str | None:
        return self.route.date_window_end

    @property
    def max_segment_searches(self) -> int:
        return self.evidence.max_segment_searches

    @property
    def live_cache_ttl_seconds(self) -> int:
        return self.evidence.live_cache_ttl_seconds

    @property
    def no_live_cache(self) -> bool:
        return self.evidence.no_live_cache

    @property
    def aggregate_control_limit(self) -> int:
        return self.evidence.aggregate_control_limit

    @property
    def aggregate_control_carriers(self) -> tuple[str, ...]:
        return self.evidence.aggregate_control_carriers

    @property
    def coverage_mode(self) -> str:
        return self.evidence.coverage_mode

    @property
    def coverage_controls(self) -> tuple[str, ...]:
        return self.evidence.coverage_controls

    @property
    def coverage_control_limit(self) -> int:
        return self.evidence.coverage_control_limit

    @property
    def use_gateway_discovery_for_fallback_hubs(self) -> bool:
        return self.route.use_gateway_discovery_for_fallback_hubs

    @property
    def gateway_discovery_limit(self) -> int:
        return self.route.gateway_discovery_limit

    @property
    def gateway_probe_batch_size(self) -> int:
        return self.route.gateway_probe_batch_size

    @property
    def gateway_probe_max_batches(self) -> int:
        return self.route.gateway_probe_max_batches

    @property
    def only_carriers(self) -> tuple[str, ...]:
        return self.filters.only_carriers

    @property
    def exclude_carriers(self) -> tuple[str, ...]:
        return self.filters.exclude_carriers


def _as_tuple(value: object) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def _str_tuple(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in _as_tuple(value) if str(item))


def _unique_strs(*values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for group in values:
        for item in group:
            text = str(item).strip().upper()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
    return tuple(result)


def _int_tuple(value: object) -> tuple[int, ...]:
    return tuple(int(item) for item in _as_tuple(value))


def _int_option(container: dict[str, Any], name: str, default: int) -> int:
    value = container.get(name)
    return default if value is None else int(value)


def _optional_int_option(
    container: dict[str, Any], name: str, default: int | None = None
) -> int | None:
    value = container.get(name)
    return default if value is None else int(value)


def _bool_option(container: dict[str, Any], name: str, default: bool = False) -> bool:
    value = container.get(name)
    return default if value is None else bool(value)


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
