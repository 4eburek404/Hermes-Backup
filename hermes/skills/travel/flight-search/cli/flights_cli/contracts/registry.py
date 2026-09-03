from __future__ import annotations

from types import MappingProxyType
from typing import Any

_CURRENT_CONTRACTS: dict[str, dict[str, str]] = {
    "search_request": {
        "schema_version": "flight_search_request.v1",
        "schema_resource": "flight_search_request.v1.schema.json",
        "status": "current_public_input",
    },
    "search_result": {
        "schema_version": "flight_search_result.v1",
        "schema_resource": "flight_search_result.v1.schema.json",
        "public_path": "data",
        "canonical_text_path": "data.rendered_text",
        "status": "current_public_contract",
    },
    "search_plan": {
        "schema_version": "flight_search_plan.v6",
        "schema_resource": "flight_search_plan.v6.schema.json",
        "public_path": "data.plan",
        "status": "diagnostic_plan_contract",
    },
    "offer_graph": {
        "schema_version": "flight_offer_graph.v1",
        "schema_resource": "flight_offer_graph.v1.schema.json",
        "public_path": "data.decision.offer_graph",
        "status": "diagnostic_graph_contract",
    },
}

CURRENT_CONTRACTS = MappingProxyType(_CURRENT_CONTRACTS)
# Устаревших схем в пакете больше нет: актуальные ни на чём не стоят.
LEGACY_SCHEMA_RESOURCES: frozenset[str] = frozenset()


def current_contract(name: str) -> dict[str, Any]:
    try:
        return dict(CURRENT_CONTRACTS[name])
    except KeyError as exc:
        raise KeyError(f"Unknown flight-search contract: {name}") from exc
