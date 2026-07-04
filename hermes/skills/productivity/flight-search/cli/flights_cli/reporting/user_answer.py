from __future__ import annotations

from typing import Any

from ..config import catalog_output_limits_from_mapping
from .option_semantics import route_requested_round_trip
from .user_answer_absence import (
    gateway_coverage_summary,
    has_any_signal,
    render_no_viable_answer,
)
from .user_answer_catalog import (
    build_catalog_contract,
    infer_answer_mode,
    option_summary,
    priority_options_for_user_contract,
    render_catalog_answer,
    rendered_answer_lines,
)
from .user_answer_conflict import (
    build_constraint_conflict_payload,
    render_constraint_conflict_answer,
)
from .user_answer_contracts import (
    USER_ANSWER_SCHEMA_PACKAGE,
    USER_ANSWER_SCHEMA_RESOURCE,
    USER_ANSWER_SCHEMA_VERSION,
    has_ambiguous_provider_time_wording,
    has_combined_pair_time_fields,
    has_metadata_availability_claim,
    has_travel_time_without_itinerary_elapsed,
    has_two_one_way_phrase,
    has_unproven_ticketing_claim,
    label_text,
    load_user_answer_schema,
    normalized_ticketing_claim_text,
    normalized_time_label,
    summary_entries_for_answer,
    summary_label_text,
    user_answer_contract_semantic_errors,
    user_answer_validator,
    validate_catalog_semantics,
    validate_evidence_semantics,
    validate_metadata_availability_boundary,
    validate_provider_aggregate_semantics,
    validate_required_caveats,
    validate_round_trip_semantics,
    validate_stop_policy_semantics,
    validate_two_one_way_pair_semantics,
    validate_user_answer,
)
from .user_answer_lines import aircraft_display_label

__all__ = (
    "USER_ANSWER_SCHEMA_PACKAGE",
    "USER_ANSWER_SCHEMA_RESOURCE",
    "USER_ANSWER_SCHEMA_VERSION",
    "aircraft_display_label",
    "build_user_answer",
    "has_ambiguous_provider_time_wording",
    "has_combined_pair_time_fields",
    "has_metadata_availability_claim",
    "has_travel_time_without_itinerary_elapsed",
    "has_two_one_way_phrase",
    "has_unproven_ticketing_claim",
    "label_text",
    "load_user_answer_schema",
    "normalized_ticketing_claim_text",
    "normalized_time_label",
    "summary_entries_for_answer",
    "summary_label_text",
    "user_answer_contract_semantic_errors",
    "user_answer_validator",
    "validate_catalog_semantics",
    "validate_evidence_semantics",
    "validate_metadata_availability_boundary",
    "validate_provider_aggregate_semantics",
    "validate_required_caveats",
    "validate_round_trip_semantics",
    "validate_stop_policy_semantics",
    "validate_two_one_way_pair_semantics",
    "validate_user_answer",
)


def build_user_answer(agent_report: dict[str, Any]) -> dict[str, Any]:
    diagnostics_raw = agent_report.get("coverage_diagnostics")
    diagnostics = diagnostics_raw if isinstance(diagnostics_raw, dict) else {}
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
    provider_failures = (
        agent_report.get("provider_failures")
        if isinstance(agent_report.get("provider_failures"), list)
        else []
    )
    through_fare_checks = (
        agent_report.get("through_fare_checks")
        if isinstance(agent_report.get("through_fare_checks"), list)
        else []
    )
    recommended = (
        agent_report.get("recommended_options")
        if isinstance(agent_report.get("recommended_options"), list)
        else []
    )
    priority = (
        agent_report.get("priority_options")
        if isinstance(agent_report.get("priority_options"), list)
        else []
    )
    route = (
        agent_report.get("route") if isinstance(agent_report.get("route"), dict) else {}
    )
    stop_policy = (
        agent_report.get("stop_policy")
        if isinstance(agent_report.get("stop_policy"), dict)
        else {}
    )
    stop_diagnostics = (
        agent_report.get("stop_policy_diagnostics")
        if isinstance(agent_report.get("stop_policy_diagnostics"), dict)
        else {}
    )
    offer_graph_raw = agent_report.get("offer_graph")
    offer_graph: dict[str, Any] = (
        offer_graph_raw if isinstance(offer_graph_raw, dict) else {}
    )
    truth_language_raw = offer_graph.get("truth_language")
    truth_language: dict[str, Any] = (
        truth_language_raw if isinstance(truth_language_raw, dict) else {}
    )
    two_stop_tier_used = bool(stop_diagnostics.get("used_two_stop_tier"))

    is_round_trip_request = route_requested_round_trip(route)
    status = (
        agent_report.get("status")
        if isinstance(agent_report.get("status"), dict)
        else {}
    )
    direct_mode = (
        status.get("direct_mode") if isinstance(status.get("direct_mode"), dict) else {}
    )
    output_limits = catalog_output_limits_from_mapping(
        status.get("output_limits")
        if isinstance(status.get("output_limits"), dict)
        else None
    )
    direct_mode_active = any(bool(value) for value in direct_mode.values())
    catalog = build_catalog_contract(
        recommended,
        priority,
        is_round_trip_request=is_round_trip_request,
        catalog_limit=output_limits.direct_catalog_limit
        if direct_mode_active
        else output_limits.catalog_limit,
        direct_mode=direct_mode_active,
    )
    constraint_conflict = build_constraint_conflict_payload(
        agent_report.get("constraint_conflict")
        if isinstance(agent_report.get("constraint_conflict"), dict)
        else None,
        is_round_trip_request=is_round_trip_request,
    )
    answer_mode = infer_answer_mode(
        is_round_trip_request=is_round_trip_request, options=catalog.get("items") or []
    )
    presentation = (
        catalog.get("presentation")
        if isinstance(catalog.get("presentation"), dict)
        else {}
    )
    try:
        catalog_max_items = int(
            presentation.get("max_items") or output_limits.catalog_limit
        )
    except (TypeError, ValueError):
        catalog_max_items = output_limits.catalog_limit
    alternative_limit = max(0, catalog_max_items - (1 if recommended else 0))
    route_contract = {
        "origin": route.get("origin"),
        "destination": route.get("destination"),
        "dates": route.get("dates") if isinstance(route.get("dates"), dict) else {},
    }
    gateway_summary = gateway_coverage_summary(agent_report)
    caveat_context = {
        "not_executed": not_executed,
        "provider_failures": provider_failures,
        "negative_wording": truth_language.get("negative_wording"),
    }
    if constraint_conflict is not None:
        answer_text = render_constraint_conflict_answer(
            route_contract,
            catalog,
            constraint_conflict,
            caveat_context=caveat_context,
            gateway_summary=gateway_summary,
        )
    elif answer_mode == "catalog":
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
    answer_lines = rendered_answer_lines(answer_text)
    answer_text_lower = answer_text.lower()
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
        "answerable_with_caveats"
        if constraint_conflict is not None
        else "answerable"
        if evidence_complete
        else "answerable_with_caveats"
        if execution_complete
        else "needs_more_evidence"
    )

    return {
        "schema_version": USER_ANSWER_SCHEMA_VERSION,
        "answer_mode": answer_mode,
        "constraint_conflict": constraint_conflict,
        "route": route_contract,
        "catalog": catalog,
        "primary_recommendation": option_summary(
            recommended[0] if recommended else None,
            is_round_trip_request=is_round_trip_request,
        ),
        "alternatives": [
            summary
            for summary in (
                option_summary(item, is_round_trip_request=is_round_trip_request)
                for item in priority_options_for_user_contract(
                    priority, limit=alternative_limit
                )
            )
            if summary is not None
        ],
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
            "source_boundaries_included": not bool(
                agent_report.get("source_boundaries")
            )
            or has_any_signal(
                answer_text_lower,
                (
                    "do not treat",
                    "не доказывает",
                    "не доказывают",
                    "не доказательство",
                    "not proof",
                    "does not prove",
                ),
            ),
            "coverage_incompleteness_acknowledged": not bool(not_executed)
            or has_any_signal(
                answer_text_lower,
                (
                    "coverage is incomplete",
                    "coverage непол",
                    "not_executed",
                    "не все live-проверки",
                    "неполное",
                ),
            ),
            "provider_failures_acknowledged": not bool(provider_failures)
            or has_any_signal(
                answer_text_lower,
                (
                    "provider failure",
                    "failed",
                    "live-проверок упала",
                    "live-проверки упали",
                ),
            ),
            "through_fare_verification_required": not bool(through_fare_checks)
            or has_any_signal(
                answer_text_lower,
                ("through-fare", "through fare", "сквозн", "единый тариф"),
            ),
            "purchase_screen_verification_required": has_any_signal(
                answer_text_lower,
                (
                    "booking screen",
                    "purchase-screen",
                    "purchase screen",
                    "final fare",
                    "финальн",
                ),
            ),
        },
        "rendered_text": answer_text,
        "answer_lines": answer_lines,
    }
