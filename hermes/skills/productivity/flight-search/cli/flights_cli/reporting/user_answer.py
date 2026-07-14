from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .option_semantics import route_requested_round_trip
from .user_answer_catalog import (
    build_catalog_contract,
    infer_answer_mode,
    render_catalog_answer,
)
from .user_answer_contracts import (
    USER_ANSWER_SCHEMA_VERSION,
    validate_user_answer,
)

__all__ = (
    "UserAnswerInput",
    "build_user_answer",
    "render_user_answer",
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


def _render_no_viable_answer(
    route: dict[str, Any], *, caveat_context: dict[str, Any]
) -> str:
    origin = route.get("origin") or "???"
    destination = route.get("destination") or "???"
    lines = [f"Не нашёл пригодных вариантов {origin}→{destination}."]
    checks = [
        "не нашёл в выполненных live/probe источниках; это не доказательство отсутствия вне границ источника",
        "финальную цену, тариф, багаж и правила проверить на booking screen.",
    ]
    if caveat_context.get("not_executed"):
        checks.append("coverage неполное: не все live-проверки выполнены.")
    if caveat_context.get("provider_failures"):
        checks.append(
            "часть live-проверок упала — если это влияет на выбор, повторить поиск перед покупкой."
        )
    lines.append("")
    lines.append("**Проверить перед покупкой**")
    lines.extend(f"- {line}" for line in checks)
    return "\n".join(lines).strip()


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
        if int(evidence.get("not_executed_probe_count") or 0)
        else [],
        "provider_failures": [True]
        if int(evidence.get("provider_failure_count") or 0)
        else [],
        "source_boundaries": [True]
        if required.get("source_boundaries_included")
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
    return _render_no_viable_answer(route_contract, caveat_context=caveat_context)


def build_user_answer(answer_input: UserAnswerInput) -> dict[str, Any]:
    diagnostics = answer_input.coverage_report
    completeness = (
        diagnostics.get("completeness")
        if isinstance(diagnostics.get("completeness"), dict)
        else {}
    )
    not_executed_raw = diagnostics.get("not_executed_probes")
    not_executed = not_executed_raw if isinstance(not_executed_raw, list) else []
    failed_probes_raw = diagnostics.get("failed_probes")
    failed_probes = failed_probes_raw if isinstance(failed_probes_raw, list) else []
    not_supported_raw = diagnostics.get("unsupported_probes")
    not_supported = not_supported_raw if isinstance(not_supported_raw, list) else []
    provider_failures = answer_input.provider_failures
    recommended = answer_input.primary_options
    priority = answer_input.alternative_options
    route = answer_input.route
    stop_policy = answer_input.stop_policy
    stop_diagnostics = answer_input.stop_policy_status
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
    execution_complete = bool(
        completeness.get("all_planned_probes_have_terminal_state")
    )
    blocking_evidence = []
    if not_executed:
        blocking_evidence.append("not_executed_probes")
    if failed_probes:
        blocking_evidence.append("failed_probes")
    if provider_failures:
        blocking_evidence.append("provider_failures")
    non_blocking_boundaries = ["unsupported_probes"] if not_supported else []
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
            "planned_probe_count": int(completeness.get("planned_count") or 0),
            "terminal_probe_count": int(completeness.get("terminal_count") or 0),
            "not_executed_probe_count": len(not_executed),
            "failed_probe_count": len(failed_probes),
            "unsupported_probe_count": len(not_supported),
            "provider_failure_count": len(provider_failures),
            "blocking_evidence": blocking_evidence,
            "non_blocking_boundaries": non_blocking_boundaries,
        },
        "required_caveats": {
            "source_boundaries_included": True,
            "coverage_incompleteness_acknowledged": True,
            "provider_failures_acknowledged": True,
            "purchase_screen_verification_required": True,
        },
    }
    answer["rendered_text"] = render_user_answer(answer, route_contract)
    return answer
