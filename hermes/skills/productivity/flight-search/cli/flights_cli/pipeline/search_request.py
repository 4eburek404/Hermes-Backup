from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .options import LiveAssemblyOptions


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


def _route_mode(command_name: str) -> str:
    return "search_live"


def search_request_from_options(options: LiveAssemblyOptions) -> SearchRequest:
    compatibility_options: dict[str, Any] = {
        "routing_strategy": options.route.routing_strategy,
        "hub": options.route.hubs,
        "origin_airport": options.route.origin_airports,
        "destination_airport": options.route.destination_airports,
        "max_connections": options.route.max_connections,
        "date_window_end": options.route.date_window_end,
        "tier2_max_connections": options.route.tier2_max_connections,
        "max_segment_searches": options.evidence.max_segment_searches,
        "live_cache_ttl_seconds": options.evidence.live_cache_ttl_seconds,
        "no_live_cache": options.evidence.no_live_cache,
        "direct_route_index_ttl_seconds": options.evidence.direct_route_index_ttl_seconds,
        "no_direct_route_intel": options.evidence.no_direct_route_intel,
        "include_segment_results": options.output.include_segment_results,
        "aggregate_control_limit": options.evidence.aggregate_control_limit,
        "aggregate_control_carrier": options.evidence.aggregate_control_carriers,
        "coverage_mode": options.evidence.coverage_mode,
        "coverage_control": options.evidence.coverage_controls,
        "coverage_control_limit": options.evidence.coverage_control_limit,
        "only_carrier": options.filters.only_carriers,
        "exclude_carrier": options.filters.exclude_carriers,
        "prefer_carrier": options.filters.prefer_carriers,
        "avoid_carrier": options.filters.avoid_carriers,
    }
    return SearchRequest(
        command_name=options.command_name,
        route_mode=_route_mode(options.command_name),
        origin=options.route.origin,
        destination=options.route.destination,
        depart_date=options.route.depart_date,
        return_date=options.route.return_date,
        currency=options.currency,
        profile=options.profile,
        ticketing=options.ticketing,
        provider_policy=options.evidence.provider_policy,
        compatibility_options=compatibility_options,
    )
