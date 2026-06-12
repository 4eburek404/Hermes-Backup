from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    limitations: tuple[str, ...] = ()
    airport_scope: dict[str, Any] | None = None
    source_boundaries: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def intent(self) -> str:
        """Compatibility alias for older internal callers/tests."""

        return self.intent_class

    @property
    def market(self) -> str:
        """Compatibility alias for older internal callers/tests."""

        return self.market_class

    @property
    def evidence_requirement(self) -> str:
        """Compatibility alias for older internal callers/tests."""

        return self.evidence_class

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
            "limitations": list(self.limitations),
            "source_boundaries": list(self.source_boundaries),
            "notes": list(self.notes),
            # Legacy names stay in the structured seam until downstream reports
            # no longer need to read old keys.
            "intent": self.intent_class,
            "market": self.market_class,
            "evidence_requirement": self.evidence_class,
        }
        if self.airport_scope is not None:
            payload["airport_scope"] = self.airport_scope
        return payload


def _as_tuple(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def _is_direct_only(request: SearchRequest) -> bool:
    options = request.compatibility_options
    return options.get("max_connections") == 0 and options.get("fallback_max_connections") == 0


def _has_airport_scope(request: SearchRequest) -> bool:
    options = request.compatibility_options
    return bool(_as_tuple(options.get("origin_airport")) or _as_tuple(options.get("destination_airport")))


def _has_carrier_scope(request: SearchRequest) -> bool:
    options = request.compatibility_options
    return bool(
        _as_tuple(options.get("aggregate_control_carrier"))
        or _as_tuple(options.get("only_carrier"))
        or _as_tuple(options.get("prefer_carrier"))
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
    if origin_country == "RU" and destination_country == "RU":
        return "ru_domestic"
    if origin_country == "RU" or destination_country == "RU":
        return "ru_touching_international"
    if origin_country and destination_country:
        return "global_non_ru"
    return "structurally_constrained"


def market_class_for_resolved_route(
    store: Any,
    origin: Any,
    destination: Any,
    origin_airports: list[str] | tuple[str, ...] | None = None,
    destination_airports: list[str] | tuple[str, ...] | None = None,
) -> str:
    """Classify market from already-resolved locations/airports."""

    origin_country = str(getattr(origin, "country_code", None) or "").upper() or None
    destination_country = str(getattr(destination, "country_code", None) or "").upper() or None
    if not origin_country:
        countries = {_location_country(store, code) for code in (origin_airports or [])}
        countries.discard(None)
        if len(countries) == 1:
            origin_country = countries.pop()
    if not destination_country:
        countries = {_location_country(store, code) for code in (destination_airports or [])}
        countries.discard(None)
        if len(countries) == 1:
            destination_country = countries.pop()
    if origin_country == "RU" and destination_country == "RU":
        return "ru_domestic"
    if origin_country == "RU" or destination_country == "RU":
        return "ru_touching_international"
    if origin_country and destination_country:
        return "global_non_ru"
    return "structurally_constrained"


def _intent_for(request: SearchRequest) -> str:
    command = request.command_name.replace("_", "-")
    if command.startswith("maint"):
        return "maintenance"
    if _is_direct_only(request):
        return "direct_inventory"
    if str(request.ticketing or "").lower() in {"single", "protected", "through", "single_pnr"}:
        return "ticketing_proof"
    if _has_carrier_scope(request) or _has_airport_scope(request):
        return "carrier_or_airport_scope"
    return "route_recommendation"


def _evidence_class_for(intent_class: str) -> str:
    if intent_class == "maintenance":
        return "diagnostic_only"
    if intent_class == "ticketing_proof":
        return "ticketing_required"
    if intent_class in {"direct_inventory", "carrier_or_airport_scope"}:
        return "absence_claim"
    return "shopping_advisory"


def routing_strategy_for_market(request: SearchRequest, market_class: str) -> str:
    raw = str(request.compatibility_options.get("routing_strategy") or "auto").strip().lower()
    has_manual_hubs = bool(_as_tuple(request.compatibility_options.get("hub")))
    if raw != "auto":
        return raw
    if has_manual_hubs:
        return "hub-list"
    if market_class == "ru_domestic":
        return "domestic-ru"
    if market_class == "ru_touching_international":
        return "ru-priority"
    if market_class == "global_non_ru":
        return "hub-list"
    return "hub-list"


def _route_mode(intent_class: str, market_class: str, routing_strategy: str) -> str:
    if intent_class == "direct_inventory":
        return "direct_inventory"
    if market_class == "ru_domestic" and routing_strategy == "domestic-ru":
        return "domestic_ru"
    if routing_strategy == "ru-priority":
        return "ru_priority"
    if routing_strategy == "hub-list":
        return "hub_list"
    return routing_strategy.replace("-", "_")


def _provider_plan(request: SearchRequest, market_class: str, routing_strategy: str) -> dict[str, Any]:
    policy = request.provider_policy
    if policy == "fli":
        default_provider = "fli"
    elif policy == "kupibilet":
        default_provider = "kupibilet"
    elif market_class == "global_non_ru":
        default_provider = "fli"
    else:
        default_provider = "kupibilet"
    return {
        "policy": policy,
        "default_provider": default_provider,
        "dispatch": {
            "ru_touching_segments": "kupibilet" if policy in {"auto", "both", "kupibilet"} else policy,
            "non_ru_segments": "fli" if policy in {"auto", "both", "fli"} else policy,
        },
        "routing_strategy": routing_strategy,
        "ru_priority_controls": routing_strategy == "ru-priority",
    }


def _limitations(request: SearchRequest, intent_class: str, market_class: str, routing_strategy: str) -> tuple[str, ...]:
    values: list[str] = []
    if market_class == "ru_touching_international" and routing_strategy == "ru-priority":
        values.append("ru_touching_market_uses_ru_priority_controls")
    if market_class == "global_non_ru" and routing_strategy == "ru-priority":
        values.append("global_non_ru_ru_priority_controls_require_explicit_scope")
    if market_class == "global_non_ru" and request.provider_policy == "kupibilet":
        values.append("global_non_ru_with_ru_provider_override")
    if market_class == "structurally_constrained":
        values.append("catalog_country_metadata_incomplete")
    if intent_class == "carrier_or_airport_scope":
        values.append("carrier_scope_requires_targeted_controls")
    if intent_class == "direct_inventory":
        values.append("direct_inventory_requires_direct_only_controls")
    return tuple(dict.fromkeys(values))


def decide_flow(request: SearchRequest, store: Any | None = None) -> FlowDecision:
    if store is None:
        from ..store import Store

        store = Store()
    intent_class = _intent_for(request)
    market_class = market_class_for_codes(store, request.origin, request.destination)
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
        limitations=_limitations(request, intent_class, market_class, routing_strategy),
        source_boundaries=(
            "provider_empty_is_not_structural_absence",
            "ticketing_protection_requires_purchase_screen_or_airline_gds_evidence",
        ),
        notes=("canonical_search_request_adapter",),
    )
