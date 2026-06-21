from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any, Mapping

from ._shared import as_tuple


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """Typed internal request extracted from canonical search assembly options.

    The public wire contract is flight_search_request.v1; this dataclass keeps the
    runtime assembly pipeline explicit after argparse/request-file adaptation.
    """

    command_name: str
    route_mode: str
    origin: str
    destination: str
    depart_date: str
    return_date: str | None
    currency: str
    profile: str
    ticketing: str
    provider_policy: str
    compatibility_options: Mapping[str, Any] = field(default_factory=dict)


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _route_mode(command_name: str) -> str:
    return "live_assemble"


def _default_provider_policy(command_name: str) -> str:
    return "auto"


def search_request_from_live_args(args: argparse.Namespace) -> SearchRequest:
    command_name = str(getattr(args, "command_name", "search") or "search")
    provider_policy = str(
        getattr(args, "provider_policy", None) or _default_provider_policy(command_name)
    ).strip().lower()
    compatibility_options: dict[str, Any] = {
        "routing_strategy": str(getattr(args, "routing_strategy", "auto") or "auto"),
        "hub": as_tuple(getattr(args, "hub", None)),
        "origin_airport": as_tuple(getattr(args, "origin_airport", None)),
        "destination_airport": as_tuple(getattr(args, "destination_airport", None)),
        "max_connections": getattr(args, "max_connections", None),
        "date_window_end": getattr(args, "date_window_end", None),
        "tier2_max_connections": getattr(args, "tier2_max_connections", None),
        "max_segment_searches": _as_int(getattr(args, "max_segment_searches", 300), 300),
        "live_cache_ttl_seconds": _as_int(getattr(args, "live_cache_ttl_seconds", 0), 0),
        "no_live_cache": bool(getattr(args, "no_live_cache", False)),
        "direct_route_index_ttl_seconds": _as_int(getattr(args, "direct_route_index_ttl_seconds", 0), 0),
        "no_direct_route_intel": bool(getattr(args, "no_direct_route_intel", False)),
        "include_segment_results": _as_int(getattr(args, "include_segment_results", 0), 0),
        "aggregate_control_limit": _as_int(getattr(args, "aggregate_control_limit", 0), 0),
        "aggregate_control_carrier": as_tuple(getattr(args, "aggregate_control_carrier", None)),
        "coverage_mode": str(getattr(args, "coverage_mode", "targeted") or "targeted"),
        "coverage_control": as_tuple(getattr(args, "coverage_control", None)),
        "coverage_control_limit": _as_int(getattr(args, "coverage_control_limit", 0), 0),
        "only_carrier": as_tuple(getattr(args, "only_carrier", None)),
        "prefer_carrier": as_tuple(getattr(args, "prefer_carrier", None)),
    }
    return SearchRequest(
        command_name=command_name,
        route_mode=_route_mode(command_name),
        origin=str(getattr(args, "origin", "") or "").upper(),
        destination=str(getattr(args, "destination", "") or "").upper(),
        depart_date=str(getattr(args, "depart_date", "") or ""),
        return_date=str(getattr(args, "return_date")) if getattr(args, "return_date", None) else None,
        currency=str(getattr(args, "currency", "RUB") or "RUB").upper(),
        profile=str(getattr(args, "profile", "balanced") or "balanced"),
        ticketing=str(getattr(args, "ticketing", "separate") or "separate"),
        provider_policy=provider_policy,
        compatibility_options=compatibility_options,
    )
