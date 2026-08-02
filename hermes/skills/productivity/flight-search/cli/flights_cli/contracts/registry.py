from __future__ import annotations

from types import MappingProxyType
from typing import Any

_CURRENT_CONTRACTS: dict[str, dict[str, str]] = {
    "user_answer": {
        "schema_version": "flight_search_user_answer.v11",
        "schema_resource": "flight_search_user_answer.v11.schema.json",
        "public_path": "data.answer",
        "canonical_text_path": "data.answer.rendered_text",
        "status": "current_canonical_answer",
    },
    "search_request": {
        "schema_version": "flight_search_request.v3",
        "schema_resource": "flight_search_request.v3.schema.json",
        "status": "current_public_input",
    },
    "search_result": {
        "schema_version": "flight_search_result.v9",
        "schema_resource": "flight_search_result.v9.schema.json",
        "public_path": "data",
        "status": "current_public_contract",
    },
    "route_trace": {
        "schema_version": "flight_route_trace_diagnostic.v4",
        "schema_resource": "flight_route_trace_diagnostic.v4.schema.json",
        "public_path": "data.route_trace",
        "status": "diagnostic_trace_contract",
    },
    "search_plan": {
        "schema_version": "flight_search_plan.v5",
        "schema_resource": "flight_search_plan.v5.schema.json",
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
ROUTE_TRACE_SCHEMA_VERSION = _CURRENT_CONTRACTS["route_trace"]["schema_version"]


def current_contract(name: str) -> dict[str, Any]:
    try:
        return dict(CURRENT_CONTRACTS[name])
    except KeyError as exc:
        raise KeyError(f"Unknown flight-search contract: {name}") from exc
