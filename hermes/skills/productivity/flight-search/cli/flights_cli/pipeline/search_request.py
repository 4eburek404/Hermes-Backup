from __future__ import annotations

from .options import LiveAssemblyOptions


class SearchRequest:
    """Read-only flat planner view backed by canonical assembly options.

    `LiveAssemblyOptions` owns the nested runtime state. This view preserves the
    established `flow.request.*` planner interface without copying those fields
    into a second mutable request object.
    """

    __slots__ = ("_options",)

    def __init__(self, options: LiveAssemblyOptions) -> None:
        object.__setattr__(self, "_options", options)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is read-only")

    @property
    def command_name(self) -> str:
        return self._options.command_name

    @property
    def origin(self) -> str:
        return self._options.route.origin

    @property
    def destination(self) -> str:
        return self._options.route.destination

    @property
    def depart_date(self) -> str:
        return self._options.route.depart_date

    @property
    def return_date(self) -> str | None:
        return self._options.route.return_date

    @property
    def currency(self) -> str:
        return self._options.currency

    @property
    def profile(self) -> str:
        return self._options.profile

    @property
    def ticketing(self) -> str:
        return self._options.ticketing

    @property
    def provider_policy(self) -> str:
        return self._options.evidence.provider_policy

    @property
    def primary_offer_limit(self) -> int:
        return self._options.evidence.primary_offer_limit

    @property
    def routing_strategy(self) -> str:
        return self._options.route.routing_strategy

    @property
    def hubs(self) -> tuple[str, ...]:
        return self._options.route.hubs

    @property
    def origin_airports(self) -> tuple[str, ...]:
        return self._options.route.origin_airports

    @property
    def destination_airports(self) -> tuple[str, ...]:
        return self._options.route.destination_airports

    @property
    def max_connections(self) -> int | None:
        return self._options.route.max_connections

    @property
    def tier2_max_connections(self) -> int | None:
        return self._options.route.tier2_max_connections

    @property
    def date_window_end(self) -> str | None:
        return self._options.route.date_window_end

    @property
    def max_segment_searches(self) -> int:
        return self._options.evidence.max_segment_searches

    @property
    def live_cache_ttl_seconds(self) -> int:
        return self._options.evidence.live_cache_ttl_seconds

    @property
    def no_live_cache(self) -> bool:
        return self._options.evidence.no_live_cache

    @property
    def aggregate_control_limit(self) -> int:
        return self._options.evidence.aggregate_control_limit

    @property
    def aggregate_control_carriers(self) -> tuple[str, ...]:
        return self._options.evidence.aggregate_control_carriers

    @property
    def coverage_mode(self) -> str:
        return self._options.evidence.coverage_mode

    @property
    def coverage_controls(self) -> tuple[str, ...]:
        return self._options.evidence.coverage_controls

    @property
    def coverage_control_limit(self) -> int:
        return self._options.evidence.coverage_control_limit

    @property
    def use_gateway_discovery_for_fallback_hubs(self) -> bool:
        return self._options.route.use_gateway_discovery_for_fallback_hubs

    @property
    def gateway_discovery_limit(self) -> int:
        return self._options.route.gateway_discovery_limit

    @property
    def gateway_probe_batch_size(self) -> int:
        return self._options.route.gateway_probe_batch_size

    @property
    def gateway_probe_max_batches(self) -> int:
        return self._options.route.gateway_probe_max_batches

    @property
    def only_carriers(self) -> tuple[str, ...]:
        return self._options.filters.only_carriers

    @property
    def exclude_carriers(self) -> tuple[str, ...]:
        return self._options.filters.exclude_carriers


def search_request_from_options(options: LiveAssemblyOptions) -> SearchRequest:
    return SearchRequest(options)
