from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from ..errors import CliError

USER_ANSWER_SCHEMA_VERSION = "flight_search_user_answer.v1"
USER_ANSWER_SCHEMA_RESOURCE = "flight_search_user_answer.v1.schema.json"
USER_ANSWER_SCHEMA_PACKAGE = "flights_cli.contracts"


@lru_cache(maxsize=1)
def load_user_answer_schema() -> dict[str, Any]:
    text = resources.files(USER_ANSWER_SCHEMA_PACKAGE).joinpath(USER_ANSWER_SCHEMA_RESOURCE).read_text(encoding="utf-8")
    schema = json.loads(text)
    Draft202012Validator.check_schema(schema)
    return schema


@lru_cache(maxsize=1)
def user_answer_validator() -> Draft202012Validator:
    return Draft202012Validator(load_user_answer_schema())


def validation_error_detail(error: ValidationError) -> dict[str, Any]:
    path = "$"
    if error.absolute_path:
        path += "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path)
    return {"path": path, "message": error.message, "validator": error.validator}


def option_summary(option: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(option, dict):
        return None
    risk = option.get("risk") if isinstance(option.get("risk"), dict) else {}
    segments = option.get("segments") if isinstance(option.get("segments"), list) else []
    max_connections = int(option.get("max_connections_per_journey") if option.get("max_connections_per_journey") is not None else max(0, len(segments) - 1))
    return {
        "id": option.get("id"),
        "category": option.get("category"),
        "price_text": str(option.get("price_text") or "price n/a"),
        "elapsed": option.get("elapsed"),
        "risk_grade": risk.get("grade"),
        "segment_count": len(segments),
        "stop_tier": option.get("stop_tier"),
        "max_connections_per_journey": max_connections,
    }


def build_user_answer_contract(agent_report: dict[str, Any]) -> dict[str, Any]:
    diagnostics = agent_report.get("coverage_diagnostics") if isinstance(agent_report.get("coverage_diagnostics"), dict) else {}
    completeness = diagnostics.get("completeness") if isinstance(diagnostics.get("completeness"), dict) else {}
    not_executed = diagnostics.get("not_executed_controls") if isinstance(diagnostics.get("not_executed_controls"), list) else []
    provider_failures = agent_report.get("provider_failures") if isinstance(agent_report.get("provider_failures"), list) else []
    through_fare_checks = agent_report.get("through_fare_checks") if isinstance(agent_report.get("through_fare_checks"), list) else []
    answer_lines = [str(line) for line in agent_report.get("answer_lines") or [] if str(line)]
    answer_text = "\n".join(answer_lines).lower()
    recommended = agent_report.get("recommended_options") if isinstance(agent_report.get("recommended_options"), list) else []
    priority = agent_report.get("priority_options") if isinstance(agent_report.get("priority_options"), list) else []
    route = agent_report.get("route") if isinstance(agent_report.get("route"), dict) else {}
    stop_policy = agent_report.get("stop_policy") if isinstance(agent_report.get("stop_policy"), dict) else {}
    stop_diagnostics = agent_report.get("stop_policy_diagnostics") if isinstance(agent_report.get("stop_policy_diagnostics"), dict) else {}
    two_stop_fallback_used = bool(stop_diagnostics.get("used_two_stop_fallback"))

    return {
        "schema_version": USER_ANSWER_SCHEMA_VERSION,
        "route": {
            "origin": route.get("origin"),
            "destination": route.get("destination"),
            "dates": route.get("dates") if isinstance(route.get("dates"), dict) else {},
        },
        "primary_recommendation": option_summary(recommended[0] if recommended else None),
        "alternatives": [summary for summary in (option_summary(item) for item in priority[:5]) if summary is not None],
        "stop_policy_status": {
            "policy": str(stop_policy.get("name") or stop_diagnostics.get("policy") or "business_default"),
            "max_reported_connections": 2 if two_stop_fallback_used else int(stop_policy.get("preferred_max_connections") or 1),
            "two_stop_fallback_used": two_stop_fallback_used,
            "three_plus_suppressed_count": int(stop_diagnostics.get("three_plus_suppressed_count") or 0),
            "garbage_options_suppressed": bool(stop_diagnostics.get("garbage_options_hidden_from_answer")),
        },
        "evidence_status": {
            "coverage_complete": bool(completeness.get("all_planned_controls_have_terminal_state")),
            "planned_control_count": int(completeness.get("planned_count") or 0),
            "terminal_control_count": int(completeness.get("terminal_count") or 0),
            "not_executed_control_count": len(not_executed),
            "provider_failure_count": len(provider_failures),
            "through_fare_check_count": len(through_fare_checks),
        },
        "required_caveats": {
            "source_boundaries_included": bool(agent_report.get("source_boundaries")) and "do not treat" in answer_text,
            "coverage_incompleteness_acknowledged": not bool(not_executed) or "coverage is incomplete" in answer_text or "not_executed" in answer_text,
            "provider_failures_acknowledged": not bool(provider_failures) or "provider failure" in answer_text or "failed" in answer_text,
            "through_fare_verification_required": not bool(through_fare_checks) or "through-fare" in answer_text or "through fare" in answer_text,
            "purchase_screen_verification_required": "booking screen" in answer_text or "purchase-screen" in answer_text or "final fare" in answer_text,
        },
        "answer_lines": answer_lines,
    }


def semantic_errors(answer: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    evidence = answer.get("evidence_status") if isinstance(answer.get("evidence_status"), dict) else {}
    caveats = answer.get("required_caveats") if isinstance(answer.get("required_caveats"), dict) else {}
    stop_status = answer.get("stop_policy_status") if isinstance(answer.get("stop_policy_status"), dict) else {}
    summaries = [answer.get("primary_recommendation")] + list(answer.get("alternatives") or [])
    summaries = [item for item in summaries if isinstance(item, dict)]

    if evidence.get("planned_control_count") != evidence.get("terminal_control_count") and evidence.get("coverage_complete"):
        errors.append({"path": "$.evidence_status.coverage_complete", "message": "coverage_complete cannot be true when planned and terminal counts differ", "validator": "semantic"})
    if int(evidence.get("not_executed_control_count") or 0) > 0 and caveats.get("coverage_incompleteness_acknowledged") is not True:
        errors.append({"path": "$.required_caveats.coverage_incompleteness_acknowledged", "message": "final answer must acknowledge incomplete coverage when controls are not_executed", "validator": "semantic"})
    if int(evidence.get("provider_failure_count") or 0) > 0 and caveats.get("provider_failures_acknowledged") is not True:
        errors.append({"path": "$.required_caveats.provider_failures_acknowledged", "message": "final answer must acknowledge provider failures", "validator": "semantic"})
    if int(evidence.get("through_fare_check_count") or 0) > 0 and caveats.get("through_fare_verification_required") is not True:
        errors.append({"path": "$.required_caveats.through_fare_verification_required", "message": "final answer must require through-fare verification", "validator": "semantic"})
    if caveats.get("source_boundaries_included") is not True:
        errors.append({"path": "$.required_caveats.source_boundaries_included", "message": "final answer must include source-boundary caveats", "validator": "semantic"})
    if caveats.get("purchase_screen_verification_required") is not True:
        errors.append({"path": "$.required_caveats.purchase_screen_verification_required", "message": "final answer must require booking or purchase-screen verification", "validator": "semantic"})
    if any(item.get("stop_tier") == "T3_THREE_PLUS" or int(item.get("max_connections_per_journey") or 0) >= 3 for item in summaries):
        errors.append({"path": "$.primary_recommendation", "message": "final answer must not report three-plus-connection options", "validator": "semantic"})
    if any(item.get("stop_tier") == "T2_TWO_STOP" or int(item.get("max_connections_per_journey") or 0) == 2 for item in summaries):
        if stop_status.get("two_stop_fallback_used") is not True:
            errors.append({"path": "$.alternatives", "message": "two-stop options require explicit two-stop fallback status", "validator": "semantic"})
    return errors


def validate_user_answer_contract(answer: dict[str, Any]) -> None:
    errors = sorted(user_answer_validator().iter_errors(answer), key=lambda item: list(item.absolute_path))
    details = [validation_error_detail(error) for error in errors]
    details.extend(semantic_errors(answer))
    if details:
        raise CliError(
            "flight_search_user_answer failed contract validation",
            error_type="contract_error",
            details={"schema_version": answer.get("schema_version"), "errors": details},
        )
