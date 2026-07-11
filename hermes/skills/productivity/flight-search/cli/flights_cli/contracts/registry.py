from __future__ import annotations

from types import MappingProxyType
from typing import Any

_CURRENT_CONTRACTS: dict[str, dict[str, str]] = {
    "user_answer": {
        "schema_version": "flight_search_user_answer.v8",
        "schema_resource": "flight_search_user_answer.v8.schema.json",
        "public_path": "data.answer",
        "canonical_text_path": "data.answer.rendered_text",
        "status": "current_canonical_answer",
    },
    "search_request": {
        "schema_version": "flight_search_request.v1",
        "schema_resource": "flight_search_request.v1.schema.json",
        "status": "planned_new_root_input",
    },
    "search_result": {
        "schema_version": "flight_search_result.v6",
        "schema_resource": "flight_search_result.v6.schema.json",
        "public_path": "data",
        "status": "current_public_contract",
    },
    "route_trace": {
        "schema_version": "flight_route_trace_diagnostic.v2",
        "schema_resource": "flight_route_trace_diagnostic.v2.schema.json",
        "public_path": "data.route_trace",
        "status": "diagnostic_trace_contract",
    },
    "search_plan": {
        "schema_version": "flight_search_plan.v2",
        "schema_resource": "flight_search_plan.v2.schema.json",
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


def current_contract(name: str) -> dict[str, Any]:
    try:
        return dict(CURRENT_CONTRACTS[name])
    except KeyError as exc:
        raise KeyError(f"Unknown flight-search contract: {name}") from exc
