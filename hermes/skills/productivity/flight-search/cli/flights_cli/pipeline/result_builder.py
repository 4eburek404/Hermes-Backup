from __future__ import annotations

from typing import Any

from ..contracts.validation import validate_contract_payload
from ..errors import CliError
from ..reporting.coverage import CoverageSnapshot
from ..reporting.catalog_rendering import source_boundaries
from ..reporting.diagnostic_projection import build_projection_input
from ..reporting.frontier_projection import project_decision_frontier
from ..reporting.user_answer import UserAnswerInput, build_user_answer
from .result_contract import (
    FlightSearchResult,
    SEARCH_RESULT_SCHEMA_VERSION,
    validate_flight_search_result,
)
from .search_request import SearchRequest, normalize_search_request_payload


def build_result_projection(data: dict[str, Any]) -> dict[str, Any]:
    """Project request evidence and the existing decision frontier into result facts."""

    live = data.get("live_search") if isinstance(data.get("live_search"), dict) else {}
    plan = live.get("plan") if isinstance(live.get("plan"), dict) else {}
    route_plan = plan.get("route") if isinstance(plan.get("route"), dict) else plan
    decision_frontier = (
        data.get("decision_frontier")
        if isinstance(data.get("decision_frontier"), dict)
        else {}
    )
    frontier_projection = project_decision_frontier(decision_frontier)
    frontier_options = list(frontier_projection.options)
    decision_ids = list(frontier_projection.decision_option_ids)
    projected_ids = [str(item.get("id") or "") for item in frontier_options]
    if projected_ids != decision_ids:
        raise CliError(
            "result projection must preserve every SearchDecision option in order",
            error_type="contract_error",
            details={"decision_ids": decision_ids, "projected_ids": projected_ids},
        )
    primary_options = frontier_options[:1]
    alternative_options = frontier_options[1:]
    coverage_snapshot = CoverageSnapshot.from_live(live)
    route = {
        "origin": route_plan.get("origin"),
        "destination": route_plan.get("destination"),
        "origin_airports": route_plan.get("origin_airports") or [],
        "destination_airports": route_plan.get("destination_airports") or [],
        "dates": route_plan.get("dates") or {},
        "profile": route_plan.get("profile"),
        "routing_strategy": route_plan.get("routing_strategy"),
        "provider_policy": live.get("provider_policy")
        or route_plan.get("provider_policy"),
    }
    answer_input = UserAnswerInput(
        route=route,
        source_boundaries=source_boundaries(),
        coverage_snapshot=coverage_snapshot,
        primary_options=primary_options,
        alternative_options=alternative_options,
        stop_policy=dict(live.get("stop_policy") or {}),
        stop_policy_status=dict(live.get("stop_policy_status") or {}),
    )
    evidence: dict[str, Any] = {
        "source_boundaries": answer_input.source_boundaries,
        "coverage": coverage_snapshot.summary,
        "provider_failures": list(coverage_snapshot.provider_failures),
    }
    date_window_inventory = live.get("date_window_inventory")
    if isinstance(date_window_inventory, dict):
        evidence["date_window_inventory"] = date_window_inventory
    return {
        "route": route,
        "evidence": evidence,
        "frontier": frontier_projection.result_contract,
        "answer": build_user_answer(answer_input),
        "research_status": dict(live.get("research_status") or _empty_research_status()),
    }


def build_flight_search_result(
    request: dict[str, Any],
    projection: dict[str, Any],
    catalog_refresh: dict[str, Any] | None = None,
) -> FlightSearchResult:
    """Bind the single result projection to the stable public v10 contract."""

    refresh = catalog_refresh if isinstance(catalog_refresh, dict) else {}
    checked = refresh.get("checked") if isinstance(refresh.get("checked"), dict) else {}
    update = refresh.get("update") if isinstance(refresh.get("update"), dict) else {}
    evidence = dict(projection["evidence"])
    evidence["catalog_refresh"] = {
        "enabled": bool(refresh.get("enabled")),
        "refreshed": bool(refresh.get("refreshed")),
        "reason": str(refresh.get("reason") or "not_requested"),
        "checked_count": int(checked.get("checked_count") or 0),
        "stale_count": int(checked.get("stale_count") or 0),
        "updated_count": int(update.get("updated_count") or 0),
    }
    result: FlightSearchResult = {
        "schema_version": SEARCH_RESULT_SCHEMA_VERSION,
        "request": _canonical_request(request),
        "route": projection["route"],
        "evidence": evidence,
        "frontier": projection["frontier"],
        "answer": projection["answer"],
        "research_status": dict(
            projection.get("research_status") or _empty_research_status()
        ),
    }
    validate_contract_payload("search_result", result)
    validate_flight_search_result(result)
    return result


def _empty_research_status() -> dict[str, Any]:
    return {
        "needed": False,
        "evidence_incomplete": False,
        "eligible_direct": False,
        "convenient_signature_count": 0,
        "target_signature_count": 3,
        "audit": [],
    }


def _canonical_request(request: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_search_request_payload(request)
    validate_contract_payload("search_request", normalized)
    return SearchRequest._from_normalized_payload(normalized).to_payload()


__all__ = [
    "build_flight_search_result",
    "build_projection_input",
    "build_result_projection",
]
