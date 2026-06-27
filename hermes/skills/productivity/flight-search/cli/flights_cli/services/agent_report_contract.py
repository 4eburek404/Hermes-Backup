from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator
from ..contracts.schema_errors import validation_error_detail
from ..domain.vocabulary import RouteFamily
from ..errors import CliError

from ..reporting.agent_report_projector import (
    AGENT_REPORT_SCHEMA_VERSION,
)  # re-exported for test_agent_report_contract
from ..reporting.user_answer import validate_user_answer

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
    "validate_agent_report",
]

AGENT_REPORT_SCHEMA_RESOURCE = "agent_report.v2.schema.json"
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


def evidence_section(report: dict[str, Any]) -> dict[str, Any]:
    evidence = report.get("evidence")
    return evidence if isinstance(evidence, dict) else {}


def frontier_section(report: dict[str, Any]) -> dict[str, Any]:
    frontier = report.get("frontier")
    return frontier if isinstance(frontier, dict) else {}


def diagnostics_section(report: dict[str, Any]) -> dict[str, Any]:
    diagnostics = report.get("diagnostics")
    return diagnostics if isinstance(diagnostics, dict) else {}


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


def display_lines(display_option: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    raw_lines = display_option.get("lines")
    if isinstance(raw_lines, list):
        lines.extend(str(line) for line in raw_lines)
    text = display_option.get("text")
    if isinstance(text, str):
        lines.extend(text.splitlines())
    return lines


def has_detailed_flight_display_line(line: str) -> bool:
    stripped = line.strip()
    lowered = stripped.lower()
    if lowered.startswith("пересадка") or lowered.startswith("layover"):
        return True
    if DETAILED_FLIGHT_NUMBER_RE.search(stripped):
        return True
    if DISPLAY_DATE_RE.search(stripped) and TIME_RANGE_RE.search(stripped):
        return True
    if AIRPORT_TIME_ROUTE_RE.search(stripped):
        return True
    if "борт " in lowered and "в полете" in lowered:
        return True
    return False


def ru_priority_semantic_errors(report: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = evidence_section(report)
    controls = evidence.get("ru_priority_controls")
    if controls is None:
        return []
    errors: list[dict[str, Any]] = []
    if not isinstance(controls, dict):
        return errors
    decision = controls.get("decision")
    if decision not in RU_PRIORITY_DECISIONS:
        errors.append(
            {
                "path": "$.evidence.ru_priority_controls.decision",
                "message": "ru_priority_controls.decision has invalid value",
                "validator": "semantic",
            }
        )

    frontier = frontier_section(report)
    priority_options = (
        frontier.get("priority_options")
        if isinstance(frontier.get("priority_options"), list)
        else []
    )
    priority_by_id = {
        str(option.get("id")): option
        for option in priority_options
        if isinstance(option, dict)
        and isinstance(option.get("id"), str)
        and str(option.get("id")).strip()
    }
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
        execution_state = branch_control.get("execution_state")
        if execution_state not in RU_PRIORITY_EXECUTION_STATES:
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

        visible = branch_control.get("visible") is True
        viable = branch_control.get("viable") is True
        if visible and not viable:
            errors.append(
                {
                    "path": f"{branch_path}.visible",
                    "message": f"{control_key} cannot be visible when viable is false",
                    "validator": "semantic",
                }
            )
        priority_option_id = branch_control.get("priority_option_id")
        priority_option_id_is_present = isinstance(priority_option_id, str) and bool(
            priority_option_id.strip()
        )
        if visible and not priority_option_id_is_present:
            errors.append(
                {
                    "path": f"{branch_path}.priority_option_id",
                    "message": f"{control_key}.visible requires a non-empty priority_option_id",
                    "validator": "semantic",
                }
            )
            continue
        if not priority_option_id_is_present:
            continue
        option = priority_by_id.get(priority_option_id)
        if option is None:
            errors.append(
                {
                    "path": f"{branch_path}.priority_option_id",
                    "message": f"{control_key}.priority_option_id must reference priority_options",
                    "validator": "semantic",
                }
            )
            continue
        if option.get("control_family") != RouteFamily.RU_PRIORITY:
            errors.append(
                {
                    "path": f"$.frontier.priority_options[{priority_option_id}].control_family",
                    "message": "visible RU-priority option must have control_family=ru_priority",
                    "validator": "semantic",
                }
            )
        if option.get("control_branch") != branch:
            errors.append(
                {
                    "path": f"$.frontier.priority_options[{priority_option_id}].control_branch",
                    "message": f"visible RU-priority option must have control_branch={branch}",
                    "validator": "semantic",
                }
            )
        if option.get("visibility_role") != "priority_control":
            errors.append(
                {
                    "path": f"$.frontier.priority_options[{priority_option_id}].visibility_role",
                    "message": "visible RU-priority option must have visibility_role=priority_control",
                    "validator": "semantic",
                }
            )
    return errors


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
    diagnostics = diagnostics_section(report)
    human_answer = (
        diagnostics.get("human_answer")
        if isinstance(diagnostics.get("human_answer"), dict)
        else {}
    )
    if str(user_answer.get("rendered_text") or "") != str(
        human_answer.get("text") or ""
    ):
        errors.append(
            {
                "path": "$.diagnostics.human_answer.text",
                "message": "diagnostics.human_answer.text must mirror canonical user_answer.rendered_text",
                "validator": "semantic",
            }
        )
    return errors


def has_metadata_availability_boundary(source_boundaries: list[Any]) -> bool:
    text = " ".join(str(item).lower() for item in source_boundaries)
    has_metadata_scope = "metadata" in text and ("static" in text or "catalog" in text)
    has_availability_boundary = "availability" in text or "absence" in text
    return has_metadata_scope and has_availability_boundary


def agent_report_semantic_errors(report: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = evidence_section(report)
    frontier = frontier_section(report)
    diagnostics_payload = diagnostics_section(report)
    errors: list[dict[str, Any]] = []
    if not diagnostics_payload.get("answer_lines"):
        errors.append(
            {
                "path": "$.diagnostics.answer_lines",
                "message": "diagnostics.answer_lines must not be empty",
                "validator": "semantic",
            }
        )
    source_boundaries = (
        evidence.get("source_boundaries")
        if isinstance(evidence.get("source_boundaries"), list)
        else []
    )
    if not source_boundaries:
        errors.append(
            {
                "path": "$.evidence.source_boundaries",
                "message": "evidence.source_boundaries must not be empty",
                "validator": "semantic",
            }
        )
    elif not has_metadata_availability_boundary(source_boundaries):
        errors.append(
            {
                "path": "$.evidence.source_boundaries",
                "message": "evidence.source_boundaries must state that static catalog metadata is not flight availability or absence evidence",
                "validator": "semantic",
            }
        )

    recommended = frontier.get("recommended_options") or []
    if recommended and not (
        recommended[0].get("segments") if isinstance(recommended[0], dict) else None
    ):
        errors.append(
            {
                "path": "$.frontier.recommended_options[0].segments",
                "message": "first recommended option must include at least one segment",
                "validator": "semantic",
            }
        )
    if recommended and (
        recommended[0].get("segments") if isinstance(recommended[0], dict) else None
    ):
        display = (
            diagnostics_payload.get("display")
            if isinstance(diagnostics_payload.get("display"), dict)
            else {}
        )
        if not str(display.get("text") or "").strip():
            errors.append(
                {
                    "path": "$.diagnostics.display.text",
                    "message": "diagnostics.display.text must render user-facing flight lines when recommended segments exist",
                    "validator": "semantic",
                }
            )

    summary_option_ids = {
        option.get("id")
        for collection_name in ("recommended_options", "priority_options")
        for option in (frontier.get(collection_name) or [])
        if isinstance(option, dict) and option.get("detail_status") == "summary_only"
    }
    display = (
        diagnostics_payload.get("display")
        if isinstance(diagnostics_payload.get("display"), dict)
        else {}
    )
    for index, display_option in enumerate(display.get("options") or []):
        if (
            not isinstance(display_option, dict)
            or display_option.get("id") not in summary_option_ids
        ):
            continue
        if any(
            has_detailed_flight_display_line(line)
            for line in display_lines(display_option)
        ):
            errors.append(
                {
                    "path": f"$.diagnostics.display.options[{index}]",
                    "message": "summary_only display must not include detailed flight lines",
                    "validator": "semantic",
                }
            )

    stop_diagnostics = (
        evidence.get("stop_policy_diagnostics")
        if isinstance(evidence.get("stop_policy_diagnostics"), dict)
        else {}
    )
    for collection_name in ("recommended_options", "priority_options"):
        for index, option in enumerate(frontier.get(collection_name) or []):
            if not isinstance(option, dict):
                continue
            if (
                option.get("stop_tier") == "T3_THREE_PLUS"
                or int(option.get("max_connections_per_journey") or 0) >= 3
            ):
                errors.append(
                    {
                        "path": f"$.frontier.{collection_name}[{index}]",
                        "message": "agent_report must not surface three-plus-connection options",
                        "validator": "semantic",
                    }
                )
            if (
                option.get("stop_tier") == "T2_TWO_STOP"
                or int(option.get("max_connections_per_journey") or 0) == 2
            ) and stop_diagnostics.get("used_two_stop_tier") is not True:
                errors.append(
                    {
                        "path": f"$.frontier.{collection_name}[{index}]",
                        "message": "two-stop options require stop-policy tier2 mode",
                        "validator": "semantic",
                    }
                )

    diagnostics = (
        evidence.get("coverage_diagnostics")
        if isinstance(evidence.get("coverage_diagnostics"), dict)
        else {}
    )
    control_bucket_states = {
        "planned_controls": "planned",
        "searched_controls": "searched",
        "skipped_controls": "skipped",
        "failed_controls": "failed",
        "not_supported_controls": "not_supported",
        "not_executed_controls": "not_executed",
        "deduped_controls": "deduped",
    }
    for required_key in (*control_bucket_states.keys(), "completeness"):
        if required_key not in diagnostics:
            errors.append(
                {
                    "path": f"$.evidence.coverage_diagnostics.{required_key}",
                    "message": f"coverage_diagnostics requires canonical {required_key}",
                    "validator": "semantic",
                }
            )
            continue
        if required_key in control_bucket_states and not isinstance(
            diagnostics.get(required_key), list
        ):
            errors.append(
                {
                    "path": f"$.evidence.coverage_diagnostics.{required_key}",
                    "message": f"coverage_diagnostics.{required_key} must be a list",
                    "validator": "semantic",
                }
            )
    for bucket, expected_state in control_bucket_states.items():
        controls = diagnostics.get(bucket)
        if not isinstance(controls, list):
            continue
        for index, control in enumerate(controls):
            if not isinstance(control, dict):
                errors.append(
                    {
                        "path": f"$.evidence.coverage_diagnostics.{bucket}[{index}]",
                        "message": f"coverage_diagnostics.{bucket}[{index}] must be an object",
                        "validator": "semantic",
                    }
                )
                continue
            state = control.get("execution_state")
            if state is not None and state != expected_state:
                errors.append(
                    {
                        "path": f"$.evidence.coverage_diagnostics.{bucket}[{index}].execution_state",
                        "message": f"{bucket} entries must have execution_state={expected_state}",
                        "validator": "semantic",
                    }
                )
            status = control.get("status")
            if (
                status is not None
                and expected_state
                in {"failed", "not_supported", "not_executed", "deduped"}
                and status != expected_state
            ):
                errors.append(
                    {
                        "path": f"$.evidence.coverage_diagnostics.{bucket}[{index}].status",
                        "message": f"{bucket} entries with status must use status={expected_state}",
                        "validator": "semantic",
                    }
                )
    completeness = (
        diagnostics.get("completeness")
        if isinstance(diagnostics.get("completeness"), dict)
        else {}
    )
    if completeness.get("planned_count") != completeness.get("terminal_count"):
        errors.append(
            {
                "path": "$.evidence.coverage_diagnostics.completeness",
                "message": "coverage completeness requires planned_count == terminal_count",
                "validator": "semantic",
            }
        )
    if completeness.get("all_planned_controls_have_terminal_state") is not True:
        errors.append(
            {
                "path": "$.evidence.coverage_diagnostics.completeness.all_planned_controls_have_terminal_state",
                "message": "coverage completeness requires every planned control to have a terminal state",
                "validator": "semantic",
            }
        )
    agent_guidance = (
        report.get("agent_guidance")
        if isinstance(report.get("agent_guidance"), dict)
        else {}
    )
    not_executed_controls = (
        diagnostics.get("not_executed_controls")
        if isinstance(diagnostics.get("not_executed_controls"), list)
        else []
    )
    failed_controls = (
        diagnostics.get("failed_controls")
        if isinstance(diagnostics.get("failed_controls"), list)
        else []
    )
    not_supported_controls = (
        diagnostics.get("not_supported_controls")
        if isinstance(diagnostics.get("not_supported_controls"), list)
        else []
    )
    provider_failures = (
        evidence.get("provider_failures")
        if isinstance(evidence.get("provider_failures"), list)
        else []
    )
    guidance_execution_complete = bool(
        completeness.get("all_planned_controls_have_terminal_state")
    )
    guidance_blocking_evidence: list[str] = []
    if not_executed_controls:
        guidance_blocking_evidence.append("not_executed_controls")
    if failed_controls:
        guidance_blocking_evidence.append("failed_controls")
    if provider_failures:
        guidance_blocking_evidence.append("provider_failures")
    guidance_evidence_complete = (
        guidance_execution_complete and not guidance_blocking_evidence
    )
    expected_boundaries = ["not_supported_controls"] if not_supported_controls else []
    if agent_guidance.get("execution_complete") != guidance_execution_complete:
        errors.append(
            {
                "path": "$.agent_guidance.execution_complete",
                "message": "agent_guidance.execution_complete must match coverage diagnostics",
                "validator": "semantic",
            }
        )
    if agent_guidance.get("evidence_complete") != guidance_evidence_complete:
        errors.append(
            {
                "path": "$.agent_guidance.evidence_complete",
                "message": "agent_guidance.evidence_complete must reflect blocking evidence",
                "validator": "semantic",
            }
        )
    if agent_guidance.get("blocking_evidence") != guidance_blocking_evidence:
        errors.append(
            {
                "path": "$.agent_guidance.blocking_evidence",
                "message": "agent_guidance.blocking_evidence must match missing/degraded evidence buckets",
                "validator": "semantic",
            }
        )
    if agent_guidance.get("non_blocking_boundaries") != expected_boundaries:
        errors.append(
            {
                "path": "$.agent_guidance.non_blocking_boundaries",
                "message": "agent_guidance.non_blocking_boundaries must match provider capability boundaries",
                "validator": "semantic",
            }
        )

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
