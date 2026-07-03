from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain.vocabulary import (
    EvidenceClass,
    IntentClass,
    MarketClass,
    RoutingStrategy,
    RouteFamily,
)
from ..domain.route_access_profiles import (
    RouteAccessDecision,
    default_route_access_decision,
)
from .search_request import SearchRequest


@dataclass(frozen=True, slots=True)
class FlowDecision:
    """First-class runtime flow classification behind the canonical search path."""

    intent_class: str
    market_class: str
    evidence_class: str
    command_name: str
    route_mode: str
    provider_policy: str
    routing_strategy: str
    provider_plan: dict[str, Any]
    route_access_profile: str
    gateway_discovery_mode: str
    route_access_reasons: tuple[str, ...] = ()
    route_access_rule_id: str | None = None
    route_access_prior_set: str | None = None
    limitations: tuple[str, ...] = ()
    airport_scope: dict[str, Any] | None = None
    source_boundaries: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "intent_class": self.intent_class,
            "market_class": self.market_class,
            "evidence_class": self.evidence_class,
            "command_name": self.command_name,
            "route_mode": self.route_mode,
            "provider_policy": self.provider_policy,
            "routing_strategy": self.routing_strategy,
            "provider_plan": self.provider_plan,
            "route_access_profile": self.route_access_profile,
            "gateway_discovery_mode": self.gateway_discovery_mode,
            "route_access_reasons": list(self.route_access_reasons),
            "limitations": list(self.limitations),
            "source_boundaries": list(self.source_boundaries),
            "notes": list(self.notes),
        }
        if self.route_access_rule_id:
            payload["route_access_rule_id"] = self.route_access_rule_id
        if self.route_access_prior_set:
            payload["route_access_prior_set"] = self.route_access_prior_set
        if self.airport_scope is not None:
            payload["airport_scope"] = self.airport_scope
        return payload


def _is_direct_only(request: SearchRequest) -> bool:
    return request.max_connections == 0 and request.tier2_max_connections == 0


def _has_airport_scope(request: SearchRequest) -> bool:
    return bool(request.origin_airports or request.destination_airports)


def _has_carrier_scope(request: SearchRequest) -> bool:
    return bool(
        request.aggregate_control_carriers
        or request.only_carriers
        or request.exclude_carriers
        or request.constraint_only_carriers
        or request.constraint_preferred_carriers
    )


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


def market_class_for_resolved_route(
    store: Any,
    origin: Any,
    destination: Any,
    origin_airports: list[str] | tuple[str, ...] | None = None,
    destination_airports: list[str] | tuple[str, ...] | None = None,
) -> str:
    """Classify market from already-resolved locations/airports."""

    origin_country = str(getattr(origin, "country_code", None) or "").upper() or None
    destination_country = (
        str(getattr(destination, "country_code", None) or "").upper() or None
    )
    if not origin_country:
        countries = {_location_country(store, code) for code in (origin_airports or [])}
        countries.discard(None)
        if len(countries) == 1:
            origin_country = countries.pop()
    if not destination_country:
        countries = {
            _location_country(store, code) for code in (destination_airports or [])
        }
        countries.discard(None)
        if len(countries) == 1:
            destination_country = countries.pop()
    if origin_country == "RU" and destination_country == "RU":
        return MarketClass.RU_DOMESTIC
    if origin_country == "RU" or destination_country == "RU":
        return MarketClass.RU_TOUCHING_INTERNATIONAL
    if origin_country and destination_country:
        return MarketClass.GLOBAL_NON_RU
    return MarketClass.STRUCTURALLY_CONSTRAINED


def _intent_for(request: SearchRequest) -> str:
    command = request.command_name.replace("_", "-")
    if command.startswith("maint"):
        return IntentClass.MAINTENANCE
    if _is_direct_only(request):
        return IntentClass.DIRECT_INVENTORY
    if str(request.ticketing or "").lower() == "single":
        return IntentClass.TICKETING_PROOF
    if _has_carrier_scope(request) or _has_airport_scope(request):
        return IntentClass.CARRIER_OR_AIRPORT_SCOPE
    return IntentClass.ROUTE_RECOMMENDATION


def _evidence_class_for(intent_class: str) -> str:
    if intent_class == IntentClass.MAINTENANCE:
        return EvidenceClass.DIAGNOSTIC_ONLY
    if intent_class == IntentClass.TICKETING_PROOF:
        return EvidenceClass.TICKETING_REQUIRED
    if intent_class in {
        IntentClass.DIRECT_INVENTORY,
        IntentClass.CARRIER_OR_AIRPORT_SCOPE,
    }:
        return EvidenceClass.ABSENCE_CLAIM
    return EvidenceClass.SHOPPING_ADVISORY


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


def _route_mode(intent_class: str, market_class: str, routing_strategy: str) -> str:
    if intent_class == IntentClass.DIRECT_INVENTORY:
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


def _provider_plan(
    request: SearchRequest, market_class: str, routing_strategy: str
) -> dict[str, Any]:
    policy = request.provider_policy
    default_provider = policy if policy in {"fli", "kupibilet", "tutu"} else "tutu"
    if policy == "auto":
        ru_touching_segments: list[str] = ["tutu", "kupibilet"]
        non_ru_segments: list[str] = ["tutu", "kupibilet", "fli"]
    elif policy == "fli":
        ru_touching_segments = []
        non_ru_segments = ["fli"]
    else:
        ru_touching_segments = [policy]
        non_ru_segments = [policy]
    return {
        "policy": policy,
        "default_provider": default_provider,
        "dispatch": {
            "ru_touching_segments": ru_touching_segments,
            "non_ru_segments": non_ru_segments,
        },
        "routing_strategy": routing_strategy,
        "ru_priority_controls": routing_strategy == RoutingStrategy.RU_PRIORITY,
    }


def _limitations(
    request: SearchRequest, intent_class: str, market_class: str, routing_strategy: str
) -> tuple[str, ...]:
    values: list[str] = []
    if (
        market_class == MarketClass.RU_TOUCHING_INTERNATIONAL
        and routing_strategy == RoutingStrategy.RU_PRIORITY
    ):
        values.append("ru_touching_market_uses_ru_priority_controls")
    if (
        market_class == MarketClass.GLOBAL_NON_RU
        and routing_strategy == RoutingStrategy.RU_PRIORITY
    ):
        values.append("global_non_ru_ru_priority_controls_require_explicit_scope")
    if (
        market_class == MarketClass.GLOBAL_NON_RU
        and request.provider_policy == "kupibilet"
    ):
        values.append("global_non_ru_with_ru_provider_override")
    if market_class == MarketClass.STRUCTURALLY_CONSTRAINED:
        values.append("catalog_country_metadata_incomplete")
    if intent_class == IntentClass.CARRIER_OR_AIRPORT_SCOPE:
        values.append("carrier_scope_requires_targeted_controls")
    if intent_class == IntentClass.DIRECT_INVENTORY:
        values.append("direct_inventory_requires_direct_only_controls")
    return tuple(dict.fromkeys(values))


def decide_flow(request: SearchRequest, store: Any | None = None) -> FlowDecision:
    if store is None:
        from ..store import Store

        store = Store()
    intent_class = _intent_for(request)
    market_class = market_class_for_codes(store, request.origin, request.destination)
    route_access = route_access_decision_for_codes(
        store, request.origin, request.destination, market_class
    )
    evidence_class = _evidence_class_for(intent_class)
    routing_strategy = routing_strategy_for_market(request, market_class)
    route_mode = _route_mode(intent_class, market_class, routing_strategy)
    return FlowDecision(
        intent_class=intent_class,
        market_class=market_class,
        evidence_class=evidence_class,
        command_name=request.command_name,
        route_mode=route_mode,
        provider_policy=request.provider_policy,
        routing_strategy=routing_strategy,
        provider_plan=_provider_plan(request, market_class, routing_strategy),
        route_access_profile=route_access.route_access_profile,
        gateway_discovery_mode=route_access.gateway_discovery_mode,
        route_access_reasons=route_access.route_access_reasons,
        route_access_rule_id=route_access.matched_rule_id,
        route_access_prior_set=route_access.prior_set,
        limitations=_limitations(request, intent_class, market_class, routing_strategy),
        source_boundaries=(
            "provider_empty_is_not_structural_absence",
            "ticketing_protection_requires_purchase_screen_or_airline_gds_evidence",
        ),
        notes=("canonical_search_request_adapter",),
    )
