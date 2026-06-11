from __future__ import annotations

from typing import Any

from ..contracts.registry import current_contract

AGENT_REPORT_SCHEMA_VERSION = current_contract("agent_report")["schema_version"]


def project_agent_report(flat_report: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "source_boundaries": flat_report.get("source_boundaries") or [],
        "hub_viability": flat_report.get("hub_viability") or [],
        "segment_searches": flat_report.get("segment_searches") or [],
        "provider_failures": flat_report.get("provider_failures") or [],
        "aggregate_controls": flat_report.get("aggregate_controls") or [],
        "coverage_diagnostics": flat_report.get("coverage_diagnostics") or {},
        "through_fare_checks": flat_report.get("through_fare_checks") or [],
        "rejected_pair_warnings": flat_report.get("rejected_pair_warnings") or [],
        "stop_policy": flat_report.get("stop_policy") or {},
        "stop_policy_diagnostics": flat_report.get("stop_policy_diagnostics") or {},
    }
    if "ru_priority_controls" in flat_report:
        evidence["ru_priority_controls"] = flat_report["ru_priority_controls"]
    if "date_window_inventory" in flat_report:
        evidence["date_window_inventory"] = flat_report["date_window_inventory"]

    frontier = {
        "status": flat_report.get("status") or {},
        "offer_graph": flat_report.get("offer_graph") or {},
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
        "diagnostics": diagnostics,
    }
