from __future__ import annotations

from types import MappingProxyType
from typing import Any

_CURRENT_CONTRACTS: dict[str, dict[str, str]] = {
    "agent_report": {
        "schema_version": "agent_report.v3",
        "schema_resource": "agent_report.v3.schema.json",
        "public_path": "data.agent_report",
        "status": "current_compat_contract",
    },
    "user_answer": {
        "schema_version": "flight_search_user_answer.v5",
        "schema_resource": "flight_search_user_answer.v5.schema.json",
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
        "schema_version": "flight_search_result.v2",
        "schema_resource": "flight_search_result.v2.schema.json",
        "status": "planned_new_root_output",
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

_DIAGNOSTIC_PROJECTIONS: dict[str, dict[str, str]] = {
    "human_answer_mirror": {
        "wire_version": "flight_human_answer.v1",
        "path": "data.agent_report.diagnostics.human_answer",
        "must_equal": "data.agent_report.user_answer.rendered_text",
        "status": "diagnostic_mirror_only",
    },
    "itinerary_display": {
        "wire_version": "flight_display.v1",
        "path": "data.agent_report.diagnostics.display",
        "status": "diagnostic_projection",
    },
    "summary_lines": {
        "path": "data.agent_report.diagnostics.answer_lines",
        "status": "diagnostic_projection",
    },
    "search_plan": {
        "wire_version": "flight_search_plan.v1",
        "path": "data.route_result.live_search.diagnostics.search_plan",
        "status": "diagnostic_projection",
    },
    "offer_graph": {
        "wire_version": "flight_offer_graph.v1",
        "path": "data.route_result.live_search.offer_graph",
        "status": "diagnostic_projection",
    },
}

CURRENT_CONTRACTS = MappingProxyType(_CURRENT_CONTRACTS)
DIAGNOSTIC_PROJECTIONS = MappingProxyType(_DIAGNOSTIC_PROJECTIONS)
REJECTED_CONTRACT_NAMES = frozenset({"user_output", "flight_search_final_answer"})


def current_contract(name: str) -> dict[str, Any]:
    try:
        return dict(CURRENT_CONTRACTS[name])
    except KeyError as exc:
        raise KeyError(f"Unknown flight-search contract: {name}") from exc


def diagnostic_projection(name: str) -> dict[str, Any]:
    try:
        return dict(DIAGNOSTIC_PROJECTIONS[name])
    except KeyError as exc:
        raise KeyError(f"Unknown flight-search diagnostic projection: {name}") from exc
