from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator

from ..contracts.registry import current_contract
from ..contracts.schema_errors import validation_error_detail
from ..domain.vocabulary import RouteFamily
from ..errors import CliError
from ..reporting.user_answer import validate_user_answer

AGENT_REPORT_SCHEMA_VERSION = current_contract("agent_report")["schema_version"]
AGENT_REPORT_SCHEMA_RESOURCE = current_contract("agent_report")["schema_resource"]
AGENT_REPORT_SCHEMA_PACKAGE = "flights_cli.contracts"

DETAILED_FLIGHT_NUMBER_RE = re.compile(
    r"\b(?=[A-Z0-9]{2}\s?\d{2,4}\b)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{2}\s?\d{2,4}\b",
    re.IGNORECASE,
)
DISPLAY_DATE_RE = re.compile(
    r"\b\d{2}(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b", re.IGNORECASE
)
TIME_RANGE_RE = re.compile(r"\b\d{1,2}:\d{2}\s*[-–—→]\s*\d{1,2}:\d{2}\b")
AIRPORT_TIME_ROUTE_RE = re.compile(
    r"\b[A-Z]{3}\s*(?:-|→|to)\s*[A-Z]{3}\b.*\b\d{1,2}:\d{2}\b"
)

RU_PRIORITY_BRANCHES = {
    "direct_destination_control": "direct_destination",
    "ist_primary_hub_control": "ist_primary_hub",
    "moscow_gateway_control": "moscow_gateway",
    "moscow_via_ist_secondary_control": "moscow_via_ist_secondary",
}
RU_PRIORITY_DECISIONS = {
    "direct_destination_viable",
    "ist_primary_viable",
    "moscow_gateway_viable",
    "moscow_via_ist_secondary_viable",
    "no_viable_ru_priority_control",
}
RU_PRIORITY_EXECUTION_STATES = {
    "executed",
    "executed_no_viable_result",
    "not_generated",
    "partial",
    "assembled_evidence",
    "skipped_better_options_available",
}

PUBLIC_REPORT_BANNED_TOP_LEVEL = {
    "diagnostics",
    "human_answer",
    "display",
    "answer_lines",
    "coverage_diagnostics",
    "provider_failures",
    "source_boundaries",
    "offer_graph",
    "recommended_options",
    "priority_options",
    "aggregate_controls",
    "segment_searches",
    "hub_viability",
    "primary_offer_results",
    "rejected_pair_warnings",
    "stop_policy_diagnostics",
}
PUBLIC_REPORT_BANNED_EVIDENCE_FIELDS = {
    "coverage_diagnostics",
    "segment_searches",
    "hub_viability",
    "primary_offer_results",
    "aggregate_controls",
    "rejected_pair_warnings",
    "stop_policy_diagnostics",
}
PUBLIC_REPORT_BANNED_FRONTIER_FIELDS = {
    "offer_graph",
    "recommended_options",
    "priority_options",
}

__all__ = [
    "AGENT_REPORT_SCHEMA_PACKAGE",
    "AGENT_REPORT_SCHEMA_RESOURCE",
    "AGENT_REPORT_SCHEMA_VERSION",
    "DETAILED_FLIGHT_NUMBER_RE",
    "DISPLAY_DATE_RE",
    "TIME_RANGE_RE",
    "AIRPORT_TIME_ROUTE_RE",
    "RU_PRIORITY_BRANCHES",
    "RU_PRIORITY_DECISIONS",
    "load_agent_report_schema",
    "agent_report_semantic_errors",
    "validate_agent_report",
]


def evidence_section(report: dict[str, Any]) -> dict[str, Any]:
    evidence = report.get("evidence")
    return evidence if isinstance(evidence, dict) else {}


def frontier_section(report: dict[str, Any]) -> dict[str, Any]:
    frontier = report.get("frontier")
    return frontier if isinstance(frontier, dict) else {}


@lru_cache(maxsize=1)
def load_agent_report_schema() -> dict[str, Any]:
    text = (
        resources.files(AGENT_REPORT_SCHEMA_PACKAGE)
        .joinpath(AGENT_REPORT_SCHEMA_RESOURCE)
        .read_text(encoding="utf-8")
    )
    schema = json.loads(text)
    Draft202012Validator.check_schema(schema)
    return schema


@lru_cache(maxsize=1)
def agent_report_validator() -> Draft202012Validator:
    return Draft202012Validator(load_agent_report_schema())


def has_metadata_availability_boundary(source_boundaries: list[Any]) -> bool:
    text = " ".join(str(item).lower() for item in source_boundaries)
    has_metadata_scope = "metadata" in text and ("static" in text or "catalog" in text)
    has_availability_boundary = "availability" in text or "absence" in text
    return has_metadata_scope and has_availability_boundary


def user_answer_semantic_errors(report: dict[str, Any]) -> list[dict[str, Any]]:
    user_answer = report.get("user_answer")
    if not isinstance(user_answer, dict):
        return []
    errors: list[dict[str, Any]] = []
    try:
        validate_user_answer(user_answer)
    except CliError as exc:
        for error in (exc.details or {}).get("errors") or []:
            if not isinstance(error, dict):
                continue
            detail = dict(error)
            path = str(detail.get("path") or "$")
            detail["path"] = "$.user_answer" + (
                path[1:] if path.startswith("$") else f".{path}"
            )
            errors.append(detail)
    return errors


def ru_priority_semantic_errors(report: dict[str, Any]) -> list[dict[str, Any]]:
    controls = evidence_section(report).get("ru_priority_controls")
    if controls is None or not isinstance(controls, dict):
        return []
    errors: list[dict[str, Any]] = []
    decision = controls.get("decision")
    if decision not in RU_PRIORITY_DECISIONS:
        errors.append(
            {
                "path": "$.evidence.ru_priority_controls.decision",
                "message": "ru_priority_controls.decision has invalid value",
                "validator": "semantic",
            }
        )
    required_fields = (
        "checked",
        "execution_state",
        "viable",
        "visible",
        "priority_option_id",
        "evidence_option_ids",
    )
    for control_key, branch in RU_PRIORITY_BRANCHES.items():
        branch_path = f"$.evidence.ru_priority_controls.{control_key}"
        branch_control = controls.get(control_key)
        if not isinstance(branch_control, dict):
            errors.append(
                {
                    "path": branch_path,
                    "message": f"{control_key} must be an object",
                    "validator": "semantic",
                }
            )
            continue
        for field in required_fields:
            if field not in branch_control:
                errors.append(
                    {
                        "path": f"{branch_path}.{field}",
                        "message": f"{control_key}.{field} is required",
                        "validator": "semantic",
                    }
                )
        if branch_control.get("execution_state") not in RU_PRIORITY_EXECUTION_STATES:
            errors.append(
                {
                    "path": f"{branch_path}.execution_state",
                    "message": f"{control_key}.execution_state has invalid value",
                    "validator": "semantic",
                }
            )
        if not isinstance(branch_control.get("evidence_option_ids"), list):
            errors.append(
                {
                    "path": f"{branch_path}.evidence_option_ids",
                    "message": f"{control_key}.evidence_option_ids must be a list",
                    "validator": "semantic",
                }
            )
        if branch_control.get("visible") is True and branch_control.get("viable") is not True:
            errors.append(
                {
                    "path": f"{branch_path}.visible",
                    "message": f"{control_key} cannot be visible when viable is false",
                    "validator": "semantic",
                }
            )
        if branch_control.get("visible") is True:
            visible_id = str(branch_control.get("priority_option_id") or "").strip()
            if not visible_id:
                errors.append(
                    {
                        "path": f"{branch_path}.priority_option_id",
                        "message": f"{control_key}.visible requires a non-empty priority_option_id",
                        "validator": "semantic",
                    }
                )
        if branch and controls.get("route_family") not in (None, RouteFamily.RU_PRIORITY):
            errors.append(
                {
                    "path": "$.evidence.ru_priority_controls.route_family",
                    "message": "ru_priority_controls.route_family has invalid value",
                    "validator": "semantic",
                }
            )
    return errors


def banned_field_errors(report: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for key in sorted(PUBLIC_REPORT_BANNED_TOP_LEVEL & set(report)):
        errors.append(
            {
                "path": f"$.{key}",
                "message": f"{key} is not part of agent_report.v4",
                "validator": "semantic",
            }
        )
    evidence = evidence_section(report)
    for key in sorted(PUBLIC_REPORT_BANNED_EVIDENCE_FIELDS & set(evidence)):
        errors.append(
            {
                "path": f"$.evidence.{key}",
                "message": f"evidence.{key} is not part of compact agent_report.v4",
                "validator": "semantic",
            }
        )
    frontier = frontier_section(report)
    for key in sorted(PUBLIC_REPORT_BANNED_FRONTIER_FIELDS & set(frontier)):
        errors.append(
            {
                "path": f"$.frontier.{key}",
                "message": f"frontier.{key} is not part of agent_report.v4",
                "validator": "semantic",
            }
        )
    return errors


def coverage_guidance_errors(report: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = evidence_section(report)
    coverage = evidence.get("coverage") if isinstance(evidence.get("coverage"), dict) else {}
    completeness = (
        coverage.get("completeness")
        if isinstance(coverage.get("completeness"), dict)
        else {}
    )
    agent_guidance = (
        report.get("agent_guidance")
        if isinstance(report.get("agent_guidance"), dict)
        else {}
    )
    blocking_evidence = (
        coverage.get("blocking_evidence")
        if isinstance(coverage.get("blocking_evidence"), list)
        else []
    )
    non_blocking_boundaries = (
        coverage.get("non_blocking_boundaries")
        if isinstance(coverage.get("non_blocking_boundaries"), list)
        else []
    )
    execution_complete = bool(
        completeness.get("all_planned_controls_have_terminal_state")
    )
    evidence_complete = execution_complete and not blocking_evidence
    expected = {
        "execution_complete": execution_complete,
        "evidence_complete": evidence_complete,
        "blocking_evidence": blocking_evidence,
        "non_blocking_boundaries": non_blocking_boundaries,
    }
    errors: list[dict[str, Any]] = []
    for key, value in expected.items():
        if agent_guidance.get(key) != value:
            errors.append(
                {
                    "path": f"$.agent_guidance.{key}",
                    "message": f"agent_guidance.{key} must match compact coverage",
                    "validator": "semantic",
                }
            )
    return errors


def source_boundary_errors(report: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = evidence_section(report)
    source_boundaries = (
        evidence.get("source_boundaries")
        if isinstance(evidence.get("source_boundaries"), list)
        else []
    )
    if not source_boundaries:
        return [
            {
                "path": "$.evidence.source_boundaries",
                "message": "evidence.source_boundaries must not be empty",
                "validator": "semantic",
            }
        ]
    if not has_metadata_availability_boundary(source_boundaries):
        return [
            {
                "path": "$.evidence.source_boundaries",
                "message": "evidence.source_boundaries must state that static catalog metadata is not flight availability or absence evidence",
                "validator": "semantic",
            }
        ]
    return []


def agent_report_semantic_errors(report: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    errors.extend(banned_field_errors(report))
    errors.extend(source_boundary_errors(report))
    errors.extend(coverage_guidance_errors(report))
    errors.extend(ru_priority_semantic_errors(report))
    errors.extend(user_answer_semantic_errors(report))
    return errors


def validate_agent_report(report: dict[str, Any]) -> None:
    errors = sorted(
        agent_report_validator().iter_errors(report),
        key=lambda item: list(item.absolute_path),
    )
    details = [validation_error_detail(error) for error in errors]
    details.extend(agent_report_semantic_errors(report))
    if details:
        raise CliError(
            "agent_report failed contract validation",
            error_type="contract_error",
            details={
                "schema_version": report.get("schema_version"),
                "errors": details,
            },
        )
