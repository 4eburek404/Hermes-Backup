from __future__ import annotations

from typing import Any

OFFER_GRAPH_ALGORITHM = "unified_offer_graph.v1"


def build_offer_graph(report: dict[str, Any], plan: dict[str, Any], live: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Project the agent report into a single decision graph.

    This is intentionally a compact report-layer graph, not a raw provider dump:
    constraints define the request scope, evidence summarizes what was searched or
    still missing, and frontier lists the non-hidden options the agent must compare.
    """
    coverage_raw = report.get("coverage_diagnostics")
    coverage = coverage_raw if isinstance(coverage_raw, dict) else {}
    completeness = coverage.get("completeness") if isinstance(coverage.get("completeness"), dict) else {}
    route = report.get("route") if isinstance(report.get("route"), dict) else {}
    status = report.get("status") if isinstance(report.get("status"), dict) else {}
    provider_failures = report.get("provider_failures") if isinstance(report.get("provider_failures"), list) else []
    aggregate_controls = report.get("aggregate_controls") if isinstance(report.get("aggregate_controls"), list) else []
    missing_evidence = missing_evidence_controls(coverage)
    capability_boundaries = capability_boundary_controls(coverage)

    return {
        "algorithm": OFFER_GRAPH_ALGORITHM,
        "constraints": {
            "origin": route.get("origin") or plan.get("origin"),
            "destination": route.get("destination") or plan.get("destination"),
            "origin_airports": route.get("origin_airports") or plan.get("origin_airports") or [],
            "destination_airports": route.get("destination_airports") or plan.get("destination_airports") or [],
            "dates": route.get("dates") or plan.get("dates") or {},
            "profile": route.get("profile") or data.get("profile") or plan.get("profile"),
            "routing_strategy": route.get("routing_strategy") or plan.get("routing_strategy"),
            "provider_policy": route.get("provider_policy") or live.get("provider_policy"),
            "stop_policy": report.get("stop_policy") or {},
            "ticketing_assumption": "separate_or_unverified_until_purchase_screen",
        },
        "collection": {
            "mode": "progressive",
            "phases": collection_phases(live, coverage),
            "stop_reason": stop_reason(status, missing_evidence, provider_failures),
            "limits": coverage.get("limits") or {},
        },
        "evidence": {
            "coverage_mode": coverage.get("coverage_mode") or plan.get("coverage_mode") or "standard",
            "negative_evidence_type": coverage.get("negative_evidence_type") or "bounded_live_controls_only",
            "planned_control_count": int(completeness.get("planned_count") or len(coverage.get("planned_controls") or [])),
            "terminal_control_count": int(completeness.get("terminal_count") or 0),
            "searched_control_count": len(coverage.get("searched_controls") or []),
            "skipped_control_count": len(coverage.get("skipped_controls") or []),
            "failed_control_count": len(coverage.get("failed_controls") or []),
            "not_supported_control_count": len(capability_boundaries),
            "missing_evidence_count": len(missing_evidence),
            "provider_failure_count": len(provider_failures),
            "aggregate_control_count": len(aggregate_controls),
            "candidate_count": status.get("candidate_count"),
            "candidate_pool_truncated": bool(status.get("candidate_pool_truncated")),
        },
        "frontier": frontier_options(report),
        "missing_evidence": missing_evidence,
        "capability_boundaries": capability_boundaries,
        "truth_language": {
            "inventory_scope": "live_provider_returned_inventory",
            "absence_claim": "bounded_live_controls_only",
            "direct_wording": "нашёл все прямые, которые вернул live-поставщик",
            "negative_wording": "не нашёл в выполненных live/probe источниках; это не доказательство отсутствия вне границ источника",
            "capability_boundary_wording": "часть проверок не поддерживается текущим provider/source; это граница источника, не доказательство отсутствия рейса",
        },
    }


def collection_phases(live: dict[str, Any], coverage: dict[str, Any]) -> list[str]:
    phases = ["primary_segment_search"]
    planned = coverage.get("planned_controls") if isinstance(coverage.get("planned_controls"), list) else []
    if planned or live.get("aggregate_controls"):
        phases.append("targeted_controls")
    phases.extend(["coverage_diagnostics", "frontier_projection"])
    return phases


def stop_reason(status: dict[str, Any], missing_evidence: list[dict[str, Any]], provider_failures: list[dict[str, Any]]) -> str:
    if bool(status.get("candidate_pool_truncated")):
        return "candidate_pool_limit"
    if provider_failures:
        return "provider_failures_or_degraded_evidence"
    if missing_evidence:
        return "bounded_budget_or_not_executed_controls"
    return "bounded_terminal_controls"


def missing_evidence_controls(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for bucket in ("not_executed_controls", "failed_controls"):
        for item in coverage.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            projected = {
                "type": item.get("type"),
                "direction": item.get("direction"),
                "origin": item.get("origin"),
                "destination": item.get("destination"),
                "date": item.get("date"),
                "carrier": item.get("carrier"),
                "reason": item.get("reason") or item.get("execution_state") or item.get("status"),
                "provider": item.get("provider"),
                "cache_status": item.get("cache_status"),
                "probe_id": item.get("probe_id"),
            }
            missing.append({key: value for key, value in projected.items() if value is not None})
    return missing


def capability_boundary_controls(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    boundaries: list[dict[str, Any]] = []
    for item in coverage.get("not_supported_controls") or []:
        if not isinstance(item, dict):
            continue
        projected = {
            "type": item.get("type"),
            "direction": item.get("direction"),
            "origin": item.get("origin"),
            "destination": item.get("destination"),
            "date": item.get("date"),
            "carrier": item.get("carrier"),
            "reason": item.get("reason") or item.get("execution_state") or item.get("status"),
            "provider": item.get("provider"),
            "cache_status": item.get("cache_status"),
            "probe_id": item.get("probe_id"),
        }
        boundaries.append({key: value for key, value in projected.items() if value is not None})
    return boundaries


def frontier_options(report: dict[str, Any]) -> list[dict[str, Any]]:
    frontier: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in ("recommended_options", "priority_options"):
        options = report.get(source) if isinstance(report.get(source), list) else []
        for index, option in enumerate(options):
            if not isinstance(option, dict):
                continue
            option_id = str(option.get("id") or "").strip()
            if not option_id or option_id in seen:
                continue
            seen.add(option_id)
            role = frontier_role(option, source, index)
            item = {
                "option_id": option_id,
                "source": source,
                "role": role,
                "detail_status": option.get("detail_status") or "missing",
                "evidence_status": evidence_status_for_option(option),
                "price": option.get("price"),
                "price_text": option.get("price_text"),
                "elapsed_min": option.get("elapsed_min") or option.get("itinerary_elapsed_min") or option.get("flight_time_min"),
                "carriers": option.get("carriers") or [],
                "risk_grade": (option.get("risk") or {}).get("grade") if isinstance(option.get("risk"), dict) else None,
                "control_family": option.get("control_family"),
                "control_branch": option.get("control_branch"),
                "journey_scope": option.get("journey_scope"),
                "ticketing_model": option.get("ticketing_model"),
            }
            frontier.append({key: value for key, value in item.items() if value is not None})
    return frontier


def frontier_role(option: dict[str, Any], source: str, index: int) -> str:
    category = str(option.get("category") or "").strip()
    if source == "recommended_options" and index == 0:
        return category or "best_practical"
    if category:
        return category
    visibility_role = str(option.get("visibility_role") or "").strip()
    if visibility_role:
        return visibility_role
    return "ranked_candidate" if source == "recommended_options" else "priority_control"


def evidence_status_for_option(option: dict[str, Any]) -> str:
    if option.get("ticketing_model") == "provider_aggregate" or option.get("category") == "provider_aggregate_candidate":
        return "provider_aggregate_unverified_ticketing"
    detail_status = option.get("detail_status")
    if detail_status == "full":
        return "full"
    if detail_status == "summary_only":
        return "summary_only"
    return "missing"
