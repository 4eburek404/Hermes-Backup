from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import (
    DEFAULT_COVERAGE_CONTROL_LIMIT,
    DEFAULT_CURRENCY,
    DEFAULT_DIRECT_ROUTE_INDEX_TTL_SECONDS,
    DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    DEFAULT_ROUTE_ASSEMBLE_LIMIT_PER_PAIR,
    DEFAULT_ROUTING_STRATEGY,
    FLI_MCP_DEFAULT_URL,
    PRIORITY_ROUTE_CARRIERS,
)


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


@dataclass(frozen=True, slots=True)
class FilterOptions:
    only_carriers: tuple[str, ...]
    exclude_carriers: tuple[str, ...]
    prefer_carriers: tuple[str, ...]
    avoid_carriers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceOptions:
    provider_policy: str
    coverage_mode: str
    coverage_controls: tuple[str, ...]
    coverage_control_limit: int
    aggregate_control_limit: int
    aggregate_control_carriers: tuple[str, ...]
    max_segment_searches: int
    live_cache_ttl_seconds: int
    no_live_cache: bool
    direct_route_index_ttl_seconds: int
    no_direct_route_intel: bool
    segment_limit: int
    timeout: int
    outbound_second_leg_day_offsets: tuple[int, ...]
    return_second_leg_day_offsets: tuple[int, ...]
    fail_fast: bool
    fli_mcp_url: str


@dataclass(frozen=True, slots=True)
class OutputOptions:
    agent_report: bool
    agent_brief: bool
    include_segment_results: int
    include_candidates: int
    include_ranked_candidates: int
    include_rejected_pairs: int
    include_filtered: int
    limit_per_pair: int
    candidate_pool_limit: int
    max_candidates: int
    max_reasons: int
    include_stop_policy_diagnostics: bool


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

    def effective_prefer_carriers(self, routing_strategy: str | None = None) -> tuple[str, ...]:
        carriers = list(self.filters.prefer_carriers)
        if str(routing_strategy or self.route.routing_strategy or "").lower() == "ru-priority":
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


def _int_tuple(value: object) -> tuple[int, ...]:
    return tuple(int(item) for item in _as_tuple(value))


def _int_option(container: dict[str, Any], name: str, default: int | None) -> int | None:
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
    return LiveAssemblyOptions(
        command_name="search",
        route=RouteOptions(
            origin=str(payload.get("origin") or "").upper(),
            destination=str(payload.get("destination") or "").upper(),
            depart_date=str(payload.get("depart_date") or ""),
            return_date=str(payload.get("return_date")) if payload.get("return_date") else None,
            routing_strategy=str(route.get("routing_strategy") or DEFAULT_ROUTING_STRATEGY),
            hubs=_str_tuple(route.get("hubs")),
            origin_airports=_str_tuple(route.get("origin_airports")),
            destination_airports=_str_tuple(route.get("destination_airports")),
            max_airports_per_city=int(route.get("max_airports_per_city") or 6),
            max_connections=_int_option(route, "max_connections", None),
            tier2_max_connections=_int_option(route, "tier2_max_connections", None),
            date_window_end=str(route.get("date_window_end")) if route.get("date_window_end") else None,
            stop_policy=str(route.get("stop_policy") or "business-default"),
            min_same_airport_min=int(route.get("min_same_airport_min") or 120),
            min_cross_airport_min=int(route.get("min_cross_airport_min") or 300),
        ),
        filters=FilterOptions(
            only_carriers=_str_tuple(filters.get("only_carriers")),
            exclude_carriers=_str_tuple(filters.get("exclude_carriers")),
            prefer_carriers=_str_tuple(filters.get("prefer_carriers")),
            avoid_carriers=_str_tuple(filters.get("avoid_carriers")),
        ),
        evidence=EvidenceOptions(
            provider_policy=str(payload.get("provider_policy") or "auto").lower(),
            coverage_mode=str(route.get("coverage_mode") or "targeted"),
            coverage_controls=_str_tuple(route.get("coverage_controls")),
            coverage_control_limit=int(route.get("coverage_control_limit") or DEFAULT_COVERAGE_CONTROL_LIMIT),
            aggregate_control_limit=int(evidence.get("aggregate_control_limit") or 0),
            aggregate_control_carriers=_str_tuple(evidence.get("aggregate_control_carriers")),
            max_segment_searches=int(evidence.get("max_segment_searches") or 300),
            live_cache_ttl_seconds=int(evidence.get("live_cache_ttl_seconds") or DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS),
            no_live_cache=_bool_option(evidence, "no_live_cache", False),
            direct_route_index_ttl_seconds=int(evidence.get("direct_route_index_ttl_seconds") or DEFAULT_DIRECT_ROUTE_INDEX_TTL_SECONDS),
            no_direct_route_intel=_bool_option(evidence, "no_direct_route_intel", False),
            segment_limit=int(evidence.get("segment_limit") or 30),
            timeout=int(evidence.get("timeout") or 60),
            outbound_second_leg_day_offsets=_int_tuple(evidence.get("outbound_second_leg_day_offsets")),
            return_second_leg_day_offsets=_int_tuple(evidence.get("return_second_leg_day_offsets")),
            fail_fast=_bool_option(evidence, "fail_fast", False),
            fli_mcp_url=str(evidence.get("fli_mcp_url") or FLI_MCP_DEFAULT_URL),
        ),
        output=OutputOptions(
            agent_report=True,
            agent_brief=_bool_option(output, "agent_brief", True),
            include_segment_results=int(output.get("include_segment_results") or 0),
            include_candidates=int(output.get("include_candidates") or 5),
            include_ranked_candidates=int(output.get("include_ranked_candidates") or 5),
            include_rejected_pairs=int(output.get("include_rejected_pairs") or 20),
            include_filtered=int(output.get("include_filtered") or 20),
            limit_per_pair=int(output.get("limit_per_pair") or DEFAULT_ROUTE_ASSEMBLE_LIMIT_PER_PAIR),
            candidate_pool_limit=int(output.get("candidate_pool_limit") or 5000),
            max_candidates=int(output.get("max_candidates") or 50),
            max_reasons=int(output.get("max_reasons") or 5),
            include_stop_policy_diagnostics=_bool_option(output, "include_stop_policy_diagnostics", False),
        ),
        profile=str(payload.get("profile") or "balanced"),
        ticketing=str(payload.get("ticketing") or "separate"),
        currency=str(payload.get("currency") or DEFAULT_CURRENCY).upper(),
    )


def argparse_args_to_options(args: Any) -> LiveAssemblyOptions:
    payload = {
        "origin": getattr(args, "origin", ""),
        "destination": getattr(args, "destination", ""),
        "depart_date": getattr(args, "depart_date", ""),
        "return_date": getattr(args, "return_date", None),
        "currency": getattr(args, "currency", DEFAULT_CURRENCY),
        "profile": getattr(args, "profile", "balanced"),
        "ticketing": getattr(args, "ticketing", "separate"),
        "provider_policy": getattr(args, "provider_policy", "auto"),
        "route_options": {
            "routing_strategy": getattr(args, "routing_strategy", DEFAULT_ROUTING_STRATEGY),
            "hubs": getattr(args, "hub", None),
            "origin_airports": getattr(args, "origin_airport", None),
            "destination_airports": getattr(args, "destination_airport", None),
            "max_airports_per_city": getattr(args, "max_airports_per_city", 6),
            "coverage_mode": getattr(args, "coverage_mode", "targeted"),
            "coverage_controls": getattr(args, "coverage_control", None),
            "coverage_control_limit": getattr(args, "coverage_control_limit", DEFAULT_COVERAGE_CONTROL_LIMIT),
            "min_same_airport_min": getattr(args, "min_same_airport_min", 120),
            "min_cross_airport_min": getattr(args, "min_cross_airport_min", 300),
            "stop_policy": getattr(args, "stop_policy", "business-default"),
            "date_window_end": getattr(args, "date_window_end", None),
            "max_connections": getattr(args, "max_connections", None),
            "tier2_max_connections": getattr(args, "tier2_max_connections", None),
        },
        "filters": {
            "only_carriers": getattr(args, "only_carrier", None),
            "exclude_carriers": getattr(args, "exclude_carrier", None),
            "prefer_carriers": getattr(args, "prefer_carrier", None),
            "avoid_carriers": getattr(args, "avoid_carrier", None),
        },
        "evidence": {
            "segment_limit": getattr(args, "segment_limit", 30),
            "timeout": getattr(args, "timeout", 60),
            "outbound_second_leg_day_offsets": getattr(args, "outbound_second_leg_day_offset", None),
            "return_second_leg_day_offsets": getattr(args, "return_second_leg_day_offset", None),
            "aggregate_control_limit": getattr(args, "aggregate_control_limit", 0),
            "aggregate_control_carriers": getattr(args, "aggregate_control_carrier", None),
            "max_segment_searches": getattr(args, "max_segment_searches", 300),
            "fail_fast": getattr(args, "fail_fast", False),
            "live_cache_ttl_seconds": getattr(args, "live_cache_ttl_seconds", DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS),
            "no_live_cache": getattr(args, "no_live_cache", False),
            "direct_route_index_ttl_seconds": getattr(args, "direct_route_index_ttl_seconds", DEFAULT_DIRECT_ROUTE_INDEX_TTL_SECONDS),
            "no_direct_route_intel": getattr(args, "no_direct_route_intel", False),
            "fli_mcp_url": getattr(args, "fli_mcp_url", FLI_MCP_DEFAULT_URL),
        },
        "output": {
            "include_stop_policy_diagnostics": getattr(args, "include_stop_policy_diagnostics", False),
            "limit_per_pair": getattr(args, "limit_per_pair", DEFAULT_ROUTE_ASSEMBLE_LIMIT_PER_PAIR),
            "candidate_pool_limit": getattr(args, "candidate_pool_limit", 5000),
            "max_candidates": getattr(args, "max_candidates", 50),
            "max_reasons": getattr(args, "max_reasons", 5),
            "include_candidates": getattr(args, "include_candidates", 5),
            "include_ranked_candidates": getattr(args, "include_ranked_candidates", 5),
            "include_rejected_pairs": getattr(args, "include_rejected_pairs", 20),
            "include_segment_results": getattr(args, "include_segment_results", 0),
            "agent_brief": getattr(args, "agent_brief", True),
            "include_filtered": getattr(args, "include_filtered", 20),
        },
    }
    options = search_request_to_options(payload)
    return LiveAssemblyOptions(
        command_name=str(getattr(args, "command_name", options.command_name) or options.command_name),
        route=options.route,
        filters=options.filters,
        evidence=options.evidence,
        output=OutputOptions(
            agent_report=bool(getattr(args, "agent_report", options.output.agent_report)),
            agent_brief=options.output.agent_brief,
            include_segment_results=options.output.include_segment_results,
            include_candidates=options.output.include_candidates,
            include_ranked_candidates=options.output.include_ranked_candidates,
            include_rejected_pairs=options.output.include_rejected_pairs,
            include_filtered=options.output.include_filtered,
            limit_per_pair=options.output.limit_per_pair,
            candidate_pool_limit=options.output.candidate_pool_limit,
            max_candidates=options.output.max_candidates,
            max_reasons=options.output.max_reasons,
            include_stop_policy_diagnostics=options.output.include_stop_policy_diagnostics,
        ),
        profile=options.profile,
        ticketing=options.ticketing,
        currency=options.currency,
    )
