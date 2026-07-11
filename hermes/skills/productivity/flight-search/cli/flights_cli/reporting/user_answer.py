from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .option_semantics import route_requested_round_trip
from .user_answer_absence import (
    gateway_coverage_summary,
    render_no_viable_answer,
)
from .user_answer_catalog import (
    build_catalog_contract,
    infer_answer_mode,
    render_catalog_answer,
)
from .user_answer_contracts import (
    USER_ANSWER_SCHEMA_PACKAGE,
    USER_ANSWER_SCHEMA_RESOURCE,
    USER_ANSWER_SCHEMA_VERSION,
    load_user_answer_schema,
    user_answer_contract_semantic_errors,
    user_answer_validator,
    validate_user_answer,
)
from .user_answer_lines import aircraft_display_label

__all__ = (
    "USER_ANSWER_SCHEMA_PACKAGE",
    "USER_ANSWER_SCHEMA_RESOURCE",
    "USER_ANSWER_SCHEMA_VERSION",
    "aircraft_display_label",
    "build_user_answer",
    "render_user_answer",
    "load_user_answer_schema",
    "user_answer_contract_semantic_errors",
    "user_answer_validator",
    "validate_user_answer",
)


@dataclass(frozen=True, slots=True)
class UserAnswerInput:
    route: dict[str, Any]
    status: dict[str, Any]
    source_boundaries: list[dict[str, Any]]
    provider_failures: list[dict[str, Any]]
    primary_options: list[dict[str, Any]]
    alternative_options: list[dict[str, Any]]
    coverage_report: dict[str, Any]
    stop_policy: dict[str, Any]
    stop_policy_status: dict[str, Any]
    through_fare_checks: list[dict[str, Any]]
    truth_language: dict[str, Any] = field(default_factory=dict)


def render_user_answer(answer: dict[str, Any], route: dict[str, Any]) -> str:
    """Pure rendering from the validated structured answer catalog."""

    catalog = answer.get("catalog") if isinstance(answer.get("catalog"), dict) else {}
    evidence = (
        answer.get("evidence_status")
        if isinstance(answer.get("evidence_status"), dict)
        else {}
    )
    required = (
        answer.get("required_caveats")
        if isinstance(answer.get("required_caveats"), dict)
        else {}
    )
    caveat_context = {
        "not_executed": [True]
        if int(evidence.get("not_executed_control_count") or 0)
        else [],
        "provider_failures": [True]
        if int(evidence.get("provider_failure_count") or 0)
        else [],
        "source_boundaries": [True]
        if required.get("source_boundaries_included")
        else [],
        "through_fare_checks": [True]
        if int(evidence.get("through_fare_check_count") or 0)
        else [],
    }
    route_contract = {
        "origin": route.get("origin"),
        "destination": route.get("destination"),
        "dates": route.get("dates") if isinstance(route.get("dates"), dict) else {},
    }
    if answer.get("answer_mode") == "catalog":
        return render_catalog_answer(
            route_contract,
            catalog,
            caveat_context=caveat_context,
        )
    return render_no_viable_answer(route_contract, caveat_context=caveat_context)


def build_user_answer(answer_input: UserAnswerInput) -> dict[str, Any]:
    diagnostics = answer_input.coverage_report
    completeness = (
        diagnostics.get("completeness")
        if isinstance(diagnostics.get("completeness"), dict)
        else {}
    )
    not_executed_raw = diagnostics.get("not_executed_controls")
    not_executed = not_executed_raw if isinstance(not_executed_raw, list) else []
    failed_controls_raw = diagnostics.get("failed_controls")
    failed_controls = (
        failed_controls_raw if isinstance(failed_controls_raw, list) else []
    )
    not_supported_raw = diagnostics.get("not_supported_controls")
    not_supported = not_supported_raw if isinstance(not_supported_raw, list) else []
    provider_failures = answer_input.provider_failures
    through_fare_checks = answer_input.through_fare_checks
    recommended = answer_input.primary_options
    priority = answer_input.alternative_options
    route = answer_input.route
    stop_policy = answer_input.stop_policy
    stop_diagnostics = answer_input.stop_policy_status
    truth_language = answer_input.truth_language
    two_stop_tier_used = bool(stop_diagnostics.get("used_two_stop_tier"))

    is_round_trip_request = route_requested_round_trip(route)
    status = answer_input.status if isinstance(answer_input.status, dict) else {}
    direct_mode = (
        status.get("direct_mode") if isinstance(status.get("direct_mode"), dict) else {}
    )
    selected_option_count = len(recommended) + len(priority)
    catalog = build_catalog_contract(
        recommended,
        priority,
        is_round_trip_request=is_round_trip_request,
        catalog_limit=max(1, selected_option_count),
        direct_mode=any(bool(value) for value in direct_mode.values()),
    )
    answer_mode = infer_answer_mode(
        is_round_trip_request=is_round_trip_request, options=catalog.get("items") or []
    )
    route_contract = {
        "origin": route.get("origin"),
        "destination": route.get("destination"),
        "dates": route.get("dates") if isinstance(route.get("dates"), dict) else {},
    }
    gateway_summary = gateway_coverage_summary(diagnostics)
    caveat_context = {
        "not_executed": not_executed,
        "provider_failures": provider_failures,
        "source_boundaries": answer_input.source_boundaries,
        "through_fare_checks": through_fare_checks,
        "negative_wording": truth_language.get("negative_wording"),
    }
    if answer_mode == "catalog":
        answer_text = render_catalog_answer(
            route_contract,
            catalog,
            caveat_context=caveat_context,
            gateway_summary=gateway_summary,
        )
    else:
        answer_text = render_no_viable_answer(
            route_contract,
            caveat_context=caveat_context,
            gateway_summary=gateway_summary,
        )
    execution_complete = bool(
        completeness.get("all_planned_controls_have_terminal_state")
    )
    blocking_evidence = []
    if not_executed:
        blocking_evidence.append("not_executed_controls")
    if failed_controls:
        blocking_evidence.append("failed_controls")
    if provider_failures:
        blocking_evidence.append("provider_failures")
    non_blocking_boundaries = ["not_supported_controls"] if not_supported else []
    evidence_complete = execution_complete and not blocking_evidence
    answerability = (
        "answerable"
        if evidence_complete
        else "answerable_with_caveats"
        if execution_complete
        else "needs_more_evidence"
    )

    catalog_ids = [
        str(item.get("option_id") or "")
        for item in catalog.get("items") or []
        if isinstance(item, dict) and str(item.get("option_id") or "")
    ]
    answer = {
        "schema_version": USER_ANSWER_SCHEMA_VERSION,
        "answer_mode": answer_mode,
        "catalog": catalog,
        "primary_option_id": catalog_ids[0] if catalog_ids else None,
        "alternative_option_ids": catalog_ids[1:],
        "stop_policy_status": {
            "policy": str(
                stop_policy.get("name")
                or stop_diagnostics.get("policy")
                or "business_default"
            ),
            "max_reported_connections": 2
            if two_stop_tier_used
            else int(stop_policy.get("preferred_max_connections") or 1),
            "two_stop_tier_used": two_stop_tier_used,
            "three_plus_suppressed_count": int(
                stop_diagnostics.get("three_plus_suppressed_count") or 0
            ),
            "garbage_options_suppressed": bool(
                stop_diagnostics.get("garbage_options_hidden_from_answer")
            ),
        },
        "evidence_status": {
            "coverage_complete": evidence_complete,
            "execution_complete": execution_complete,
            "evidence_complete": evidence_complete,
            "answerability": answerability,
            "planned_control_count": int(completeness.get("planned_count") or 0),
            "terminal_control_count": int(completeness.get("terminal_count") or 0),
            "not_executed_control_count": len(not_executed),
            "failed_control_count": len(failed_controls),
            "not_supported_control_count": len(not_supported),
            "provider_failure_count": len(provider_failures),
            "through_fare_check_count": len(through_fare_checks),
            "blocking_evidence": blocking_evidence,
            "non_blocking_boundaries": non_blocking_boundaries,
        },
        "required_caveats": {
            "source_boundaries_included": True,
            "coverage_incompleteness_acknowledged": True,
            "provider_failures_acknowledged": True,
            "through_fare_verification_required": True,
            "purchase_screen_verification_required": True,
        },
        "rendered_text": answer_text,
    }
    answer["rendered_text"] = render_user_answer(answer, route_contract)
    return answer
