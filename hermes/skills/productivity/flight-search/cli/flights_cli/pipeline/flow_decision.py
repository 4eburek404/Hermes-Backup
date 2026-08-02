from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain.vocabulary import MarketClass, RoutingStrategy, RouteFamily
from ..domain.route_access_profiles import (
    RouteAccessDecision,
    default_route_access_decision,
)
from .search_request import SearchRequest
from .direct_gate import is_direct_only


@dataclass(frozen=True, slots=True)
class FlowDecision:
    """First-class runtime flow classification behind the canonical search path."""

    market_class: str
    route_mode: str
    routing_strategy: str
    route_access_profile: str
    gateway_discovery_mode: str
    route_access_reasons: tuple[str, ...] = ()
    route_access_rule_id: str | None = None
    route_access_prior_set: str | None = None
    limitations: tuple[str, ...] = ()


def _has_airport_scope(request: SearchRequest) -> bool:
    return bool(request.origin_airports or request.destination_airports)


def _has_carrier_scope(request: SearchRequest) -> bool:
    return bool(request.only_carriers)


def _location_country(store: Any, code: str) -> str | None:
    normalized = str(code or "").upper()
    try:
        location = store.resolve_location(normalized)
    except Exception:
        location = None
    if location is not None and getattr(location, "country_code", None):
        return str(location.country_code or "").upper()
    airport = getattr(store, "airport_by_code", {}).get(normalized)
    if airport and airport.get("country_code"):
        return str(airport.get("country_code") or "").upper()
    city = getattr(store, "city_by_code", {}).get(normalized)
    if city and city.get("country_code"):
        return str(city.get("country_code") or "").upper()
    return None


def market_class_for_codes(store: Any, origin: str, destination: str) -> str:
    """Classify route market from catalog country metadata, not route-code lists."""

    origin_country = _location_country(store, origin)
    destination_country = _location_country(store, destination)
    return _market_class_from_country_codes(origin_country, destination_country)


def _market_class_from_country_codes(
    origin_country: str | None, destination_country: str | None
) -> str:
    if origin_country == "RU" and destination_country == "RU":
        return MarketClass.RU_DOMESTIC
    if origin_country == "RU" or destination_country == "RU":
        return MarketClass.RU_TOUCHING_INTERNATIONAL
    if origin_country and destination_country:
        return MarketClass.GLOBAL_NON_RU
    return MarketClass.STRUCTURALLY_CONSTRAINED


def route_access_decision_for_codes(
    store: Any,
    origin: str,
    destination: str,
    market_class: str,
) -> RouteAccessDecision:
    origin_country = _location_country(store, origin)
    destination_country = _location_country(store, destination)
    if hasattr(store, "route_access_profile_for_route"):
        return store.route_access_profile_for_route(
            market_class=market_class,
            origin_country=origin_country,
            destination_country=destination_country,
        )
    return default_route_access_decision(market_class)


def routing_strategy_for_market(request: SearchRequest, market_class: str) -> str:
    raw = str(request.routing_strategy or "auto").strip().lower()
    has_manual_hubs = bool(request.hubs)
    if raw != "auto":
        return raw
    if has_manual_hubs:
        return RoutingStrategy.HUB_LIST
    if market_class == MarketClass.RU_DOMESTIC:
        return RoutingStrategy.DOMESTIC_RU
    if market_class == MarketClass.RU_TOUCHING_INTERNATIONAL:
        return RoutingStrategy.RU_PRIORITY
    if market_class == MarketClass.GLOBAL_NON_RU:
        return RoutingStrategy.HUB_LIST
    return RoutingStrategy.HUB_LIST


def _route_mode(direct_only: bool, market_class: str, routing_strategy: str) -> str:
    if direct_only:
        return RouteFamily.DIRECT_INVENTORY
    if (
        market_class == MarketClass.RU_DOMESTIC
        and routing_strategy == RoutingStrategy.DOMESTIC_RU
    ):
        return RouteFamily.DOMESTIC_RU
    if routing_strategy == RoutingStrategy.RU_PRIORITY:
        return RouteFamily.RU_PRIORITY
    if routing_strategy == RoutingStrategy.HUB_LIST:
        return RouteFamily.HUB_LIST
    return routing_strategy.replace("-", "_")


def _limitations(
    request: SearchRequest, direct_only: bool, market_class: str, routing_strategy: str
) -> tuple[str, ...]:
    values: list[str] = []
    if (
        market_class == MarketClass.RU_TOUCHING_INTERNATIONAL
        and routing_strategy == RoutingStrategy.RU_PRIORITY
    ):
        values.append("ru_touching_market_uses_ru_priority_probes")
    if (
        market_class == MarketClass.GLOBAL_NON_RU
        and routing_strategy == RoutingStrategy.RU_PRIORITY
    ):
        values.append("global_non_ru_ru_priority_probes_require_explicit_scope")
    if market_class == MarketClass.STRUCTURALLY_CONSTRAINED:
        values.append("catalog_country_metadata_incomplete")
    if _has_carrier_scope(request) or _has_airport_scope(request):
        values.append("exact_scope_requires_live_probes")
    if direct_only:
        values.append("direct_inventory_requires_direct_only_probes")
    return tuple(dict.fromkeys(values))


def decide_flow(request: SearchRequest, store: Any | None = None) -> FlowDecision:
    if store is None:
        from ..store import Store

        store = Store()
    direct_only = is_direct_only(request)
    market_class = market_class_for_codes(store, request.origin, request.destination)
    route_access = route_access_decision_for_codes(
        store, request.origin, request.destination, market_class
    )
    routing_strategy = routing_strategy_for_market(request, market_class)
    route_mode = _route_mode(direct_only, market_class, routing_strategy)
    return FlowDecision(
        market_class=market_class,
        route_mode=route_mode,
        routing_strategy=routing_strategy,
        route_access_profile=route_access.route_access_profile,
        gateway_discovery_mode=route_access.gateway_discovery_mode,
        route_access_reasons=route_access.route_access_reasons,
        route_access_rule_id=route_access.matched_rule_id,
        route_access_prior_set=route_access.prior_set,
        limitations=_limitations(request, direct_only, market_class, routing_strategy),
    )
