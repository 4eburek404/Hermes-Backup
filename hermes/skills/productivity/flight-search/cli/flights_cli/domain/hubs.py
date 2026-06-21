from __future__ import annotations

from ..config import DEFAULT_ROUTE_HUBS, DEFAULT_ROUTING_STRATEGY, ROUTING_STRATEGIES
from .normalize import normalize_iata
from .vocabulary import RoutingStrategy


def resolve_route_hubs(values: list[str] | None) -> tuple[list[str], str]:
    manual_hubs = [normalize_iata(hub, "hub") for hub in (values or [])]
    if manual_hubs:
        return list(dict.fromkeys(manual_hubs)), "manual"
    return list(DEFAULT_ROUTE_HUBS), "default"


def resolve_routing_strategy(value: str | None, hub_values: list[str] | None) -> str:
    raw = (value or DEFAULT_ROUTING_STRATEGY).strip().lower()
    if raw not in ROUTING_STRATEGIES:
        available = ", ".join(sorted(ROUTING_STRATEGIES))
        raise ValueError(f"routing strategy must be one of {available}")
    if raw == "auto":
        return RoutingStrategy.HUB_LIST if hub_values else RoutingStrategy.RU_PRIORITY
    return raw
