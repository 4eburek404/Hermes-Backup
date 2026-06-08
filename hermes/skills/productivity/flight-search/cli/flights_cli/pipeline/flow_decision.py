from __future__ import annotations

from dataclasses import dataclass

from .search_request import SearchRequest


_RU_ROUTE_CODES = frozenset(
    {
        "AER",
        "DME",
        "IKT",
        "KZN",
        "LED",
        "MOW",
        "OVB",
        "SVO",
        "SVX",
        "UFA",
        "VKO",
    }
)


@dataclass(frozen=True, slots=True)
class FlowDecision:
    """Internal search-flow classification for legacy route assembly."""

    intent: str
    market: str
    evidence_requirement: str
    command_name: str
    route_mode: str
    provider_policy: str
    notes: tuple[str, ...] = ()


def _market_for(request: SearchRequest) -> str:
    origin_is_ru = request.origin in _RU_ROUTE_CODES
    destination_is_ru = request.destination in _RU_ROUTE_CODES
    if origin_is_ru and destination_is_ru:
        return "ru_domestic"
    if origin_is_ru or destination_is_ru:
        return "ru_touching_international"
    if request.provider_policy == "fli":
        return "global_non_ru"
    return "structurally_constrained"


def _intent_for(request: SearchRequest) -> str:
    if request.compatibility_options.get("aggregate_control_carrier") or request.compatibility_options.get("only_carrier"):
        return "carrier_or_airport_scope"
    return "route_recommendation"


def decide_flow(request: SearchRequest) -> FlowDecision:
    return FlowDecision(
        intent=_intent_for(request),
        market=_market_for(request),
        evidence_requirement="shopping_advisory",
        command_name=request.command_name,
        route_mode=request.route_mode,
        provider_policy=request.provider_policy,
        notes=("legacy_cli_compatibility_adapter",),
    )
