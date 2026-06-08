from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .flow_decision import FlowDecision
from .search_request import SearchRequest


@dataclass(frozen=True, slots=True)
class EvidencePlan:
    """Typed internal evidence policy derived from legacy live-assemble flags."""

    provider_policy: str
    max_segment_searches: int
    live_cache_enabled: bool
    live_cache_ttl_seconds: int
    direct_route_intel_enabled: bool
    direct_route_index_ttl_seconds: int
    aggregate_control_limit: int
    aggregate_control_carriers: tuple[Any, ...]
    coverage_mode: str
    coverage_controls: tuple[Any, ...]
    coverage_control_limit: int
    include_segment_results: int


def _int_option(options: dict[str, Any], name: str, default: int) -> int:
    try:
        return int(options.get(name, default))
    except (TypeError, ValueError):
        return default


def _tuple_option(options: dict[str, Any], name: str) -> tuple[Any, ...]:
    value = options.get(name)
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def plan_evidence(request: SearchRequest, decision: FlowDecision) -> EvidencePlan:
    del decision
    options = dict(request.compatibility_options)
    direct_route_ttl = _int_option(options, "direct_route_index_ttl_seconds", 0)
    return EvidencePlan(
        provider_policy=request.provider_policy,
        max_segment_searches=_int_option(options, "max_segment_searches", 300),
        live_cache_enabled=not bool(options.get("no_live_cache", False)),
        live_cache_ttl_seconds=_int_option(options, "live_cache_ttl_seconds", 0),
        direct_route_intel_enabled=not bool(options.get("no_direct_route_intel", False)) and direct_route_ttl > 0,
        direct_route_index_ttl_seconds=direct_route_ttl,
        aggregate_control_limit=_int_option(options, "aggregate_control_limit", 0),
        aggregate_control_carriers=_tuple_option(options, "aggregate_control_carrier"),
        coverage_mode=str(options.get("coverage_mode") or "targeted"),
        coverage_controls=_tuple_option(options, "coverage_control"),
        coverage_control_limit=_int_option(options, "coverage_control_limit", 0),
        include_segment_results=_int_option(options, "include_segment_results", 0),
    )
