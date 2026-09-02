from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from ..config import (
    DEFAULT_CURRENCY,
    DEFAULT_GATEWAY_DISCOVERY_LIMIT,
    DEFAULT_GATEWAY_PROBE_BATCH_SIZE,
    DEFAULT_GATEWAY_PROBE_MAX_BATCHES,
    DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    DEFAULT_PROFILE,
    DEFAULT_ROUTING_STRATEGY,
    catalog_output_limits_from_mapping,
)
from ..domain.connection_policy import (
    DEFAULT_MIN_CROSS_AIRPORT_CONNECTION_MIN,
    DEFAULT_MIN_SAME_AIRPORT_CONNECTION_MIN,
)
from ..domain.normalize import parse_iso_date
from ..contracts.validation import validate_contract_payload
from ..errors import CliError


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
    min_same_airport_min: int
    min_cross_airport_min: int
    gateway_discovery_limit: int
    gateway_probe_batch_size: int
    gateway_probe_max_batches: int


@dataclass(frozen=True, slots=True)
class FilterOptions:
    only_carriers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceOptions:
    provider_policy: str
    primary_offer_limit: int
    max_segment_searches: int
    live_cache_ttl_seconds: int
    no_live_cache: bool
    segment_limit: int
    timeout: int
    fail_fast: bool


@dataclass(frozen=True, slots=True)
class OutputOptions:
    catalog_limit: int
    direct_catalog_limit: int


@dataclass(frozen=True, slots=True)
class RouteHypothesisInput:
    """A caller-supplied airport sequence, not provider evidence."""

    airports: tuple[str, ...]
    source: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> RouteHypothesisInput:
        return cls(
            airports=_str_tuple(payload.get("airports")),
            source=str(payload.get("source") or ""),
        )

    def to_payload(self) -> dict[str, Any]:
        return {"airports": list(self.airports), "source": self.source}


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """Canonical immutable input consumed only by SearchPlanBuilder."""

    route: RouteOptions
    filters: FilterOptions
    evidence: EvidenceOptions
    output: OutputOptions
    profile: str
    currency: str
    route_hypotheses: tuple[RouteHypothesisInput, ...] = ()

    @classmethod
    def _from_normalized_payload(cls, payload: dict[str, Any]) -> SearchRequest:
        """Build from a payload already normalized at the input boundary."""

        route = _mapping(payload.get("route_options"))
        evidence = _mapping(payload.get("evidence"))
        filters = _mapping(payload.get("filters"))
        output = _mapping(payload.get("output"))
        output_limits = catalog_output_limits_from_mapping(output)
        return cls(
            route=RouteOptions(
                origin=str(payload.get("origin") or ""),
                destination=str(payload.get("destination") or ""),
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
                min_same_airport_min=_int_option(
                    route,
                    "min_same_airport_min",
                    DEFAULT_MIN_SAME_AIRPORT_CONNECTION_MIN,
                ),
                min_cross_airport_min=_int_option(
                    route,
                    "min_cross_airport_min",
                    DEFAULT_MIN_CROSS_AIRPORT_CONNECTION_MIN,
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
            ),
            evidence=EvidenceOptions(
                provider_policy=str(payload.get("provider_policy") or "auto"),
                primary_offer_limit=max(
                    output_limits.catalog_limit, output_limits.direct_catalog_limit
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
                fail_fast=_bool_option(evidence, "fail_fast", False),
            ),
            output=OutputOptions(
                catalog_limit=output_limits.catalog_limit,
                direct_catalog_limit=output_limits.direct_catalog_limit,
            ),
            profile=str(payload.get("profile") or DEFAULT_PROFILE),
            currency=str(payload.get("currency") or DEFAULT_CURRENCY),
            route_hypotheses=tuple(
                RouteHypothesisInput.from_payload(item)
                for item in payload.get("route_hypotheses") or []
                if isinstance(item, dict)
            ),
        )

    def to_payload(self) -> dict[str, Any]:
        """Return the canonical wire projection after Python defaults are applied."""

        return {
            "schema_version": "flight_search_request.v4",
            "origin": self.route.origin,
            "destination": self.route.destination,
            "depart_date": self.route.depart_date,
            "return_date": self.route.return_date,
            "currency": self.currency,
            "profile": self.profile,
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
                "min_same_airport_min": self.route.min_same_airport_min,
                "min_cross_airport_min": self.route.min_cross_airport_min,
                "gateway_discovery_limit": self.route.gateway_discovery_limit,
                "gateway_probe_batch_size": self.route.gateway_probe_batch_size,
                "gateway_probe_max_batches": self.route.gateway_probe_max_batches,
            },
            "filters": {
                "only_carriers": list(self.filters.only_carriers),
            },
            "evidence": {
                "segment_limit": self.evidence.segment_limit,
                "timeout": self.evidence.timeout,
                "max_segment_searches": self.evidence.max_segment_searches,
                "fail_fast": self.evidence.fail_fast,
                "live_cache_ttl_seconds": self.evidence.live_cache_ttl_seconds,
                "no_live_cache": self.evidence.no_live_cache,
            },
            "output": {
                "catalog_limit": self.output.catalog_limit,
                "direct_catalog_limit": self.output.direct_catalog_limit,
            },
            "route_hypotheses": [
                hypothesis.to_payload() for hypothesis in self.route_hypotheses
            ],
        }

    def effective_only_carriers(self) -> tuple[str, ...]:
        return _unique_strs(self.filters.only_carriers)

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


def normalize_search_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Canonical casing/default normalization for the public request payload."""

    normalized = dict(payload)
    version = str(normalized.get("schema_version") or "flight_search_request.v3")
    if version in {"flight_search_request.v3", "flight_search_request.v4"}:
        normalized["schema_version"] = "flight_search_request.v4"
    for name in ("origin", "destination", "currency"):
        if name in normalized:
            normalized[name] = str(normalized[name]).upper()
    if "provider_policy" in normalized:
        normalized["provider_policy"] = str(normalized["provider_policy"]).lower()
    route_value = normalized.get("route_options")
    if isinstance(route_value, dict):
        route = dict(route_value)
        for name in ("hubs", "origin_airports", "destination_airports"):
            if isinstance(route.get(name), list):
                route[name] = [str(item).upper() for item in route[name]]
        if "routing_strategy" in route:
            route["routing_strategy"] = str(route["routing_strategy"]).lower()
        normalized["route_options"] = route
    filters_value = normalized.get("filters")
    if isinstance(filters_value, dict):
        filters = dict(filters_value)
        if isinstance(filters.get("only_carriers"), list):
            filters["only_carriers"] = [
                str(item).upper() for item in filters["only_carriers"]
            ]
        normalized["filters"] = filters
    hypotheses = normalized.get("route_hypotheses")
    if hypotheses is None:
        normalized["route_hypotheses"] = []
    elif isinstance(hypotheses, list):
        normalized["route_hypotheses"] = [
            {
                **item,
                "airports": [str(code).upper() for code in item.get("airports") or []],
                "source": str(item.get("source") or "").lower(),
            }
            for item in hypotheses
            if isinstance(item, dict)
        ]
    return normalized


def validate_search_request_semantics(request: SearchRequest) -> None:
    depart = parse_iso_date(request.depart_date, "depart-date")
    if request.origin == request.destination:
        raise ValueError("origin and destination must differ")
    if request.return_date:
        return_date = parse_iso_date(request.return_date, "return-date")
        if return_date < depart:
            raise ValueError("return-date must be on or after depart-date")
    if request.date_window_end:
        window_end = parse_iso_date(request.date_window_end, "date-window-end")
        if window_end < depart:
            raise ValueError("date-window-end must be on or after depart-date")
        if request.return_date:
            raise ValueError("date-window-end cannot be combined with return-date")
    if (
        request.max_connections is not None
        and request.tier2_max_connections is not None
        and request.tier2_max_connections < request.max_connections
    ):
        raise ValueError("tier2-max-connections must not be below max-connections")
    origin_scope = {request.origin, *request.origin_airports}
    destination_scope = {request.destination, *request.destination_airports}
    signatures: set[tuple[str, ...]] = set()
    for hypothesis in request.route_hypotheses:
        airports = hypothesis.airports
        if not 3 <= len(airports) <= 5:
            raise ValueError("route-hypothesis must contain 3 to 5 airports")
        if any(not re.fullmatch(r"[A-Z]{3}", airport) for airport in airports):
            raise ValueError("route-hypothesis airports must be exact IATA codes")
        if len(set(airports)) != len(airports):
            raise ValueError("route-hypothesis must not contain airport cycles")
        if airports[0] not in origin_scope or airports[-1] not in destination_scope:
            raise ValueError("route-hypothesis endpoints must be within route scope")
        if airports in signatures:
            raise ValueError("route-hypotheses must be unique")
        signatures.add(airports)


def is_direct_only(request: "SearchRequest") -> bool:
    """Запрос «только прямые»: пересадки запрещены на обоих ярусах."""
    return request.max_connections == 0 and request.tier2_max_connections == 0


def search_request_from_payload(payload: dict[str, Any]) -> SearchRequest:
    normalized = normalize_search_request_payload(payload)
    validate_contract_payload(
        "search_request", normalized, error_type="validation_error"
    )
    request = SearchRequest._from_normalized_payload(normalized)
    try:
        validate_search_request_semantics(request)
    except ValueError as exc:
        raise CliError(str(exc), error_type="validation_error") from exc
    return request
