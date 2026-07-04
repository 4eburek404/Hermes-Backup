from __future__ import annotations

from types import MappingProxyType
from typing import Any

_CURRENT_CONTRACTS: dict[str, dict[str, str]] = {
    "agent_report": {
        "schema_version": "agent_report.v4",
        "schema_resource": "agent_report.v4.schema.json",
        "public_path": "data.agent_report",
        "status": "current_public_contract",
    },
    "user_answer": {
        "schema_version": "flight_search_user_answer.v6",
        "schema_resource": "flight_search_user_answer.v6.schema.json",
        "public_path": "data.agent_report.user_answer",
        "canonical_text_path": "data.agent_report.user_answer.rendered_text",
        "status": "current_canonical_answer",
    },
    "search_request": {
        "schema_version": "flight_search_request.v1",
        "schema_resource": "flight_search_request.v1.schema.json",
        "status": "planned_new_root_input",
    },
    "search_result": {
        "schema_version": "flight_search_result.v3",
        "schema_resource": "flight_search_result.v3.schema.json",
        "public_path": "data",
        "status": "current_public_contract",
    },
    "search_plan": {
        "schema_version": "flight_search_plan.v1",
        "schema_resource": "flight_search_plan.v1.schema.json",
        "public_path": "data.route_result.live_search.diagnostics.search_plan",
        "status": "diagnostic_plan_contract",
    },
    "offer_graph": {
        "schema_version": "flight_offer_graph.v1",
        "schema_resource": "flight_offer_graph.v1.schema.json",
        "public_path": "data.route_result.live_search.offer_graph",
        "status": "diagnostic_graph_contract",
    },
}

CURRENT_CONTRACTS = MappingProxyType(_CURRENT_CONTRACTS)
REJECTED_CONTRACT_NAMES = frozenset({"user_output", "flight_search_final_answer"})


def current_contract(name: str) -> dict[str, Any]:
    try:
        return dict(CURRENT_CONTRACTS[name])
    except KeyError as exc:
        raise KeyError(f"Unknown flight-search contract: {name}") from exc
