from __future__ import annotations

from typing import Any

from ..domain.stop_policy import BUSINESS_DEFAULT_STOP_POLICY, stop_policy_payload
from ..errors import CliError
from ..reporting.coverage import build_coverage_diagnostics, compact_coverage_summary
from ..reporting.source_boundaries import source_boundaries
from ..reporting.user_answer import UserAnswerInput, build_user_answer
from .decision_projection import decision_frontier_options


def provider_failure_summary(failure: dict[str, Any]) -> dict[str, Any]:
    error = failure.get("error") if isinstance(failure.get("error"), dict) else {}
    error_summary = {
        key: error.get(key)
        for key in (
            "type",
            "message",
            "classification",
            "retryable",
            "retry_after_seconds",
            "retry_after_parse_error",
            "http_status",
        )
        if key in error or key in {"type", "message"}
    }
    return {
        "direction": failure.get("direction"),
        "leg": failure.get("leg"),
        "origin": failure.get("origin"),
        "destination": failure.get("destination"),
        "date": failure.get("date"),
        "provider": failure.get("provider"),
        "cache_status": failure.get("cache_status"),
        "probe_id": failure.get("probe_id"),
        "error": error_summary,
    }


def provider_failures(live: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    return [
        provider_failure_summary(item)
        for item in (live.get("failures") or [])[: max(0, limit)]
        if isinstance(item, dict)
    ]


def result_frontier(decision_frontier: dict[str, Any]) -> dict[str, Any]:
    options = [
        option
        for option in decision_frontier.get("options") or []
        if isinstance(option, dict) and str(option.get("id") or "")
    ]
    coverage = (
        decision_frontier.get("coverage_summary")
        if isinstance(decision_frontier.get("coverage_summary"), dict)
        else {}
    )
    return {
        "schema_version": "flight_decision_frontier.result.v1",
        "option_ids": [str(option["id"]) for option in options],
        "coverage_summary": {
            key: int(coverage.get(key) or 0)
            for key in (
                "candidate_count",
                "acceptable_count",
                "selected_count",
                "rejected_count",
                "control_count",
            )
        },
    }


def _stop_policy_status(options: list[dict[str, Any]]) -> dict[str, Any]:
    connection_counts = [
        int(option.get("max_connections_per_journey") or 0) for option in options
    ]
    return {
        "policy": BUSINESS_DEFAULT_STOP_POLICY.name,
        "used_two_stop_tier": any(count == 2 for count in connection_counts),
        "three_plus_suppressed_count": 0,
        "garbage_options_hidden_from_answer": False,
    }


def build_result_projection(
    data: dict[str, Any], store: Any | None = None
) -> dict[str, Any]:
    """Project request evidence and the existing decision frontier into result facts."""

    del store
    live = data.get("live_search") if isinstance(data.get("live_search"), dict) else {}
    plan = live.get("plan") if isinstance(live.get("plan"), dict) else {}
    decision_frontier = (
        data.get("decision_frontier")
        if isinstance(data.get("decision_frontier"), dict)
        else {}
    )
    frontier_options = decision_frontier_options(data)
    decision_frontier = (
        data.get("decision_frontier")
        if isinstance(data.get("decision_frontier"), dict)
        else {}
    )
    decision_ids = [
        str(item.get("id") or "")
        for item in decision_frontier.get("options") or []
        if isinstance(item, dict)
    ]
    projected_ids = [str(item.get("id") or "") for item in frontier_options]
    if projected_ids != decision_ids:
        raise CliError(
            "result projection must preserve every SearchDecision option in order",
            error_type="contract_error",
            details={"decision_ids": decision_ids, "projected_ids": projected_ids},
        )
    primary_options = frontier_options[:1]
    alternative_options = frontier_options[1:]
    compact_failures = provider_failures(live)
    coverage_diagnostics = build_coverage_diagnostics(plan, live)
    coverage = compact_coverage_summary(coverage_diagnostics, compact_failures)
    route = {
        "origin": plan.get("origin"),
        "destination": plan.get("destination"),
        "origin_airports": plan.get("origin_airports") or [],
        "destination_airports": plan.get("destination_airports") or [],
        "dates": plan.get("dates") or {},
        "profile": data.get("profile") or plan.get("profile"),
        "routing_strategy": plan.get("routing_strategy"),
        "provider_policy": live.get("provider_policy"),
    }
    answer_input = UserAnswerInput(
        route=route,
        status={
            "direct_mode": {},
        },
        source_boundaries=source_boundaries(),
        provider_failures=compact_failures,
        primary_options=primary_options,
        alternative_options=alternative_options,
        coverage_report=coverage_diagnostics,
        stop_policy=stop_policy_payload(BUSINESS_DEFAULT_STOP_POLICY),
        stop_policy_status=_stop_policy_status(frontier_options),
    )
    evidence: dict[str, Any] = {
        "source_boundaries": answer_input.source_boundaries,
        "coverage": coverage,
        "provider_failures": compact_failures,
    }
    date_window_inventory = live.get("date_window_inventory")
    if isinstance(date_window_inventory, dict):
        evidence["date_window_inventory"] = date_window_inventory
    return {
        "route": route,
        "evidence": evidence,
        "frontier": result_frontier(decision_frontier),
        "answer": build_user_answer(answer_input),
    }
