from __future__ import annotations

from dataclasses import dataclass, field

from .options import LiveAssemblyOptions


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """Typed internal request extracted from canonical search assembly options.

    The public wire contract is flight_search_request.v1; this dataclass keeps the
    runtime assembly pipeline explicit after argparse/request-file adaptation.
    """

    command_name: str
    origin: str
    destination: str
    depart_date: str
    return_date: str | None
    currency: str
    profile: str
    ticketing: str
    provider_policy: str
    primary_offer_limit: int
    routing_strategy: str
    hubs: tuple[str, ...] = field(default_factory=tuple)
    origin_airports: tuple[str, ...] = field(default_factory=tuple)
    destination_airports: tuple[str, ...] = field(default_factory=tuple)
    max_connections: int | None = None
    tier2_max_connections: int | None = None
    date_window_end: str | None = None
    max_segment_searches: int = 300
    live_cache_ttl_seconds: int = 0
    no_live_cache: bool = False
    include_segment_results: int = 0
    aggregate_control_limit: int = 0
    aggregate_control_carriers: tuple[str, ...] = field(default_factory=tuple)
    coverage_mode: str = "targeted"
    coverage_controls: tuple[str, ...] = field(default_factory=tuple)
    coverage_control_limit: int = 0
    use_gateway_discovery_for_fallback_hubs: bool = False
    gateway_discovery_limit: int = 3
    gateway_probe_batch_size: int = 2
    gateway_probe_max_batches: int = 2
    only_carriers: tuple[str, ...] = field(default_factory=tuple)
    exclude_carriers: tuple[str, ...] = field(default_factory=tuple)


def search_request_from_options(options: LiveAssemblyOptions) -> SearchRequest:
    return SearchRequest(
        command_name=options.command_name,
        origin=options.route.origin,
        destination=options.route.destination,
        depart_date=options.route.depart_date,
        return_date=options.route.return_date,
        currency=options.currency,
        profile=options.profile,
        ticketing=options.ticketing,
        provider_policy=options.evidence.provider_policy,
        primary_offer_limit=options.evidence.primary_offer_limit,
        routing_strategy=options.route.routing_strategy,
        hubs=options.route.hubs,
        origin_airports=options.route.origin_airports,
        destination_airports=options.route.destination_airports,
        max_connections=options.route.max_connections,
        tier2_max_connections=options.route.tier2_max_connections,
        date_window_end=options.route.date_window_end,
        max_segment_searches=options.evidence.max_segment_searches,
        live_cache_ttl_seconds=options.evidence.live_cache_ttl_seconds,
        no_live_cache=options.evidence.no_live_cache,
        include_segment_results=options.output.include_segment_results,
        aggregate_control_limit=options.evidence.aggregate_control_limit,
        aggregate_control_carriers=options.evidence.aggregate_control_carriers,
        coverage_mode=options.evidence.coverage_mode,
        coverage_controls=options.evidence.coverage_controls,
        coverage_control_limit=options.evidence.coverage_control_limit,
        use_gateway_discovery_for_fallback_hubs=(
            options.route.use_gateway_discovery_for_fallback_hubs
        ),
        gateway_discovery_limit=options.route.gateway_discovery_limit,
        gateway_probe_batch_size=options.route.gateway_probe_batch_size,
        gateway_probe_max_batches=options.route.gateway_probe_max_batches,
        only_carriers=options.filters.only_carriers,
        exclude_carriers=options.filters.exclude_carriers,
    )
