from __future__ import annotations

from typing import Any

from ..contracts.registry import current_contract

AGENT_REPORT_SCHEMA_VERSION = current_contract("agent_report")["schema_version"]


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _coverage_status(flat_report: dict[str, Any]) -> dict[str, Any]:
    diagnostics = (
        flat_report.get("coverage_diagnostics")
        if isinstance(flat_report.get("coverage_diagnostics"), dict)
        else {}
    )
    completeness = (
        diagnostics.get("completeness")
        if isinstance(diagnostics.get("completeness"), dict)
        else {}
    )
    not_executed = _list_value(diagnostics.get("not_executed_controls"))
    failed_controls = _list_value(diagnostics.get("failed_controls"))
    provider_failures = _list_value(flat_report.get("provider_failures"))
    not_supported = _list_value(diagnostics.get("not_supported_controls"))
    execution_complete = bool(
        completeness.get("all_planned_controls_have_terminal_state")
    )
    evidence_complete = execution_complete and not (
        not_executed or failed_controls or provider_failures
    )
    blocking_evidence: list[str] = []
    if not_executed:
        blocking_evidence.append("not_executed_controls")
    if failed_controls:
        blocking_evidence.append("failed_controls")
    if provider_failures:
        blocking_evidence.append("provider_failures")
    non_blocking_boundaries = ["not_supported_controls"] if not_supported else []
    return {
        "execution_complete": execution_complete,
        "evidence_complete": evidence_complete,
        "blocking_evidence": blocking_evidence,
        "non_blocking_boundaries": non_blocking_boundaries,
    }


def _answer_readiness(status: dict[str, Any]) -> str:
    if status["evidence_complete"]:
        return "answerable"
    if status["execution_complete"]:
        return "answerable_with_caveats"
    return "needs_more_evidence"


def _next_actions(
    flat_report: dict[str, Any], status: dict[str, Any]
) -> list[dict[str, Any]]:
    diagnostics = (
        flat_report.get("coverage_diagnostics")
        if isinstance(flat_report.get("coverage_diagnostics"), dict)
        else {}
    )
    route = (
        flat_report.get("route") if isinstance(flat_report.get("route"), dict) else {}
    )
    evidence_plan = (
        route.get("evidence_plan")
        if isinstance(route.get("evidence_plan"), dict)
        else {}
    )
    not_executed = _list_value(diagnostics.get("not_executed_controls"))
    failed_controls = _list_value(diagnostics.get("failed_controls"))
    provider_failures = _list_value(flat_report.get("provider_failures"))
    through_fare_checks = _list_value(flat_report.get("through_fare_checks"))
    actions: list[dict[str, Any]] = []

    if not_executed:
        current_limit = int(evidence_plan.get("max_segment_searches") or 300)
        actions.append(
            {
                "id": "rerun_with_larger_execution_budget",
                "reason": "not_executed_controls",
                "request_patch": {
                    "evidence": {
                        "max_segment_searches": max(
                            current_limit * 2, current_limit + len(not_executed)
                        ),
                        "no_live_cache": True,
                    }
                },
            }
        )
    if failed_controls or provider_failures:
        actions.append(
            {
                "id": "rerun_fresh_without_cache",
                "reason": "provider_failures_or_failed_controls",
                "request_patch": {"evidence": {"no_live_cache": True, "timeout": 90}},
            }
        )
    if through_fare_checks:
        actions.append(
            {
                "id": "verify_purchase_screen_or_airline_gds",
                "reason": "ticketing_or_through_fare_proof_required",
                "external_evidence_required": True,
            }
        )
    if not actions and status["evidence_complete"]:
        actions.append(
            {
                "id": "answer_from_canonical_rendered_text",
                "reason": "evidence_complete",
                "answer_path": current_contract("user_answer")["canonical_text_path"],
            }
        )
    return actions


def build_agent_guidance(flat_report: dict[str, Any]) -> dict[str, Any]:
    status = _coverage_status(flat_report)
    return {
        "primary_command": "search --request",
        "canonical_answer_path": current_contract("user_answer")["canonical_text_path"],
        "answer_readiness": _answer_readiness(status),
        "execution_complete": status["execution_complete"],
        "evidence_complete": status["evidence_complete"],
        "blocking_evidence": status["blocking_evidence"],
        "non_blocking_boundaries": status["non_blocking_boundaries"],
        "next_actions": _next_actions(flat_report, status),
    }


def project_agent_report(flat_report: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "source_boundaries": flat_report.get("source_boundaries") or [],
        "hub_viability": flat_report.get("hub_viability") or [],
        "segment_searches": flat_report.get("segment_searches") or [],
        "provider_failures": flat_report.get("provider_failures") or [],
        "primary_offer_results": flat_report.get("primary_offer_results") or [],
        "aggregate_controls": flat_report.get("aggregate_controls") or [],
        "coverage_diagnostics": flat_report.get("coverage_diagnostics") or {},
        "through_fare_checks": flat_report.get("through_fare_checks") or [],
        "rejected_pair_warnings": flat_report.get("rejected_pair_warnings") or [],
        "stop_policy": flat_report.get("stop_policy") or {},
        "stop_policy_diagnostics": flat_report.get("stop_policy_diagnostics") or {},
        "direct_flights": flat_report.get("direct_flights") or [],
    }
    if "ru_priority_controls" in flat_report:
        evidence["ru_priority_controls"] = flat_report["ru_priority_controls"]
    if "date_window_inventory" in flat_report:
        evidence["date_window_inventory"] = flat_report["date_window_inventory"]

    frontier = {
        "status": flat_report.get("status") or {},
        "offer_graph": flat_report.get("offer_graph") or {},
        "decision_frontier": flat_report.get("decision_frontier") or {},
        "recommended_options": flat_report.get("recommended_options") or [],
        "priority_options": flat_report.get("priority_options") or [],
    }
    diagnostics = {
        "display": flat_report.get("display") or {},
        "answer_lines": flat_report.get("answer_lines") or [],
        "human_answer": flat_report.get("human_answer") or {},
    }
    if "omitted_counts" in flat_report:
        diagnostics["omitted_counts"] = flat_report["omitted_counts"]

    return {
        "schema_version": AGENT_REPORT_SCHEMA_VERSION,
        "route": flat_report.get("route") or {},
        "evidence": evidence,
        "frontier": frontier,
        "user_answer": flat_report.get("user_answer") or {},
        "agent_guidance": flat_report.get("agent_guidance")
        or build_agent_guidance(flat_report),
        "diagnostics": diagnostics,
    }
