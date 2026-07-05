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
    include_segment_results: int
    catalog_limit: int
    direct_catalog_limit: int


@dataclass(frozen=True, slots=True)
class LiveAssemblyOptions:
    command_name: str
    route: RouteOptions
    filters: FilterOptions
    evidence: EvidenceOptions
    output: OutputOptions
    profile: str
    ticketing: str
    currency: str

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


def _upper_str_tuple(value: object) -> tuple[str, ...]:
    return tuple(str(item).strip().upper() for item in _as_tuple(value) if str(item))


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
    if value is None:
        return default
    return int(value)


def _optional_int_option(
    container: dict[str, Any], name: str, default: int | None = None
) -> int | None:
    value = container.get(name)
    if value is None:
        return default
    return int(value)


def _bool_option(container: dict[str, Any], name: str, default: bool = False) -> bool:
    value = container.get(name)
    if value is None:
        return default
    return bool(value)


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def search_request_to_options(payload: dict[str, Any]) -> LiveAssemblyOptions:
    route = _mapping(payload.get("route_options"))
    evidence = _mapping(payload.get("evidence"))
    filters = _mapping(payload.get("filters"))
    output = _mapping(payload.get("output"))
    output_limits = catalog_output_limits_from_mapping(output)
    return LiveAssemblyOptions(
        command_name="search",
        route=RouteOptions(
            origin=str(payload.get("origin") or "").upper(),
            destination=str(payload.get("destination") or "").upper(),
            depart_date=str(payload.get("depart_date") or ""),
            return_date=str(payload.get("return_date"))
            if payload.get("return_date")
            else None,
            routing_strategy=str(
                route.get("routing_strategy") or DEFAULT_ROUTING_STRATEGY
            ),
            hubs=_str_tuple(route.get("hubs")),
            origin_airports=_str_tuple(route.get("origin_airports")),
            destination_airports=_str_tuple(route.get("destination_airports")),
            max_airports_per_city=_int_option(route, "max_airports_per_city", 6),
            max_connections=_optional_int_option(route, "max_connections"),
            tier2_max_connections=_optional_int_option(route, "tier2_max_connections"),
            date_window_end=str(route.get("date_window_end"))
            if route.get("date_window_end")
            else None,
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
            aggregate_control_limit=_int_option(evidence, "aggregate_control_limit", 0),
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
                evidence, "search_wave_probe_limit", DEFAULT_SEARCH_WAVE_PROBE_LIMIT
            ),
            search_wave_top_k=_int_option(
                evidence, "search_wave_top_k", DEFAULT_SEARCH_WAVE_TOP_K
            ),
            fail_fast=_bool_option(evidence, "fail_fast", False),
            fli_mcp_url=str(evidence.get("fli_mcp_url") or FLI_MCP_DEFAULT_URL),
        ),
        output=OutputOptions(
            include_segment_results=_int_option(output, "include_segment_results", 0),
            catalog_limit=output_limits.catalog_limit,
            direct_catalog_limit=output_limits.direct_catalog_limit,
        ),
        profile=str(payload.get("profile") or DEFAULT_PROFILE),
        ticketing=str(payload.get("ticketing") or "separate"),
        currency=str(payload.get("currency") or DEFAULT_CURRENCY).upper(),
    )
