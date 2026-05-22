from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from ..errors import CliError

AGENT_REPORT_SCHEMA_VERSION = "agent_report.v1"
AGENT_REPORT_SCHEMA_RESOURCE = "agent_report.v1.schema.json"
AGENT_REPORT_SCHEMA_PACKAGE = "flights_cli.contracts"
DETAILED_FLIGHT_NUMBER_RE = re.compile(r"\b(?=[A-Z0-9]{2}\s?\d{2,4}\b)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{2}\s?\d{2,4}\b", re.IGNORECASE)
DISPLAY_DATE_RE = re.compile(r"\b\d{2}(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b", re.IGNORECASE)
TIME_RANGE_RE = re.compile(r"\b\d{1,2}:\d{2}\s*[-–—→]\s*\d{1,2}:\d{2}\b")
AIRPORT_TIME_ROUTE_RE = re.compile(r"\b[A-Z]{3}\s*(?:-|→|to)\s*[A-Z]{3}\b.*\b\d{1,2}:\d{2}\b")


@lru_cache(maxsize=1)
def load_agent_report_schema() -> dict[str, Any]:
    text = resources.files(AGENT_REPORT_SCHEMA_PACKAGE).joinpath(AGENT_REPORT_SCHEMA_RESOURCE).read_text(encoding="utf-8")
    schema = json.loads(text)
    Draft202012Validator.check_schema(schema)
    return schema


@lru_cache(maxsize=1)
def agent_report_validator() -> Draft202012Validator:
    return Draft202012Validator(load_agent_report_schema())


def validation_error_detail(error: ValidationError) -> dict[str, Any]:
    path = "$"
    if error.absolute_path:
        path += "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path)
    return {
        "path": path,
        "message": error.message,
        "validator": error.validator,
    }


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


def semantic_errors(report: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    answer_text = "\n".join(str(line).lower() for line in report.get("answer_lines") or [])

    if not report.get("answer_lines"):
        errors.append({"path": "$.answer_lines", "message": "answer_lines must not be empty", "validator": "semantic"})
    if not report.get("source_boundaries"):
        errors.append({"path": "$.source_boundaries", "message": "source_boundaries must not be empty", "validator": "semantic"})

    recommended = report.get("recommended_options") or []
    if recommended and not (recommended[0].get("segments") if isinstance(recommended[0], dict) else None):
        errors.append(
            {
                "path": "$.recommended_options[0].segments",
                "message": "first recommended option must include at least one segment",
                "validator": "semantic",
            }
        )
    if recommended and (recommended[0].get("segments") if isinstance(recommended[0], dict) else None):
        display = report.get("display") if isinstance(report.get("display"), dict) else {}
        if not str(display.get("text") or "").strip():
            errors.append(
                {
                    "path": "$.display.text",
                    "message": "display.text must render user-facing flight lines when recommended segments exist",
                    "validator": "semantic",
                }
            )

    summary_option_ids = {
        option.get("id")
        for collection_name in ("recommended_options", "priority_options")
        for option in (report.get(collection_name) or [])
        if isinstance(option, dict) and option.get("detail_status") == "summary_only"
    }
    display = report.get("display") if isinstance(report.get("display"), dict) else {}
    for index, display_option in enumerate(display.get("options") or []):
        if not isinstance(display_option, dict) or display_option.get("id") not in summary_option_ids:
            continue
        if any(has_detailed_flight_display_line(line) for line in display_lines(display_option)):
            errors.append(
                {
                    "path": f"$.display.options[{index}]",
                    "message": "summary_only display must not include detailed flight lines",
                    "validator": "semantic",
                }
            )

    if report.get("priority_options") and "priority" not in answer_text and "control" not in answer_text:
        errors.append(
            {
                "path": "$.answer_lines",
                "message": "answer_lines must surface priority/control options",
                "validator": "semantic",
            }
        )

    if report.get("through_fare_checks"):
        has_through_fare_signal = "through-fare" in answer_text or "through fare" in answer_text
        has_verify_signal = "verify" in answer_text or "verification" in answer_text
        if not has_through_fare_signal or not has_verify_signal:
            errors.append(
                {
                    "path": "$.answer_lines",
                    "message": "answer_lines must surface through-fare verification",
                    "validator": "semantic",
                }
            )

    if report.get("provider_failures") and "provider failure" not in answer_text and "failed" not in answer_text:
        errors.append(
            {
                "path": "$.answer_lines",
                "message": "answer_lines must surface provider failures",
                "validator": "semantic",
            }
        )

    stop_diagnostics = report.get("stop_policy_diagnostics") if isinstance(report.get("stop_policy_diagnostics"), dict) else {}
    for collection_name in ("recommended_options", "priority_options"):
        for index, option in enumerate(report.get(collection_name) or []):
            if not isinstance(option, dict):
                continue
            if option.get("stop_tier") == "T3_THREE_PLUS" or int(option.get("max_connections_per_journey") or 0) >= 3:
                errors.append(
                    {
                        "path": f"$.{collection_name}[{index}]",
                        "message": "agent_report must not surface three-plus-connection options",
                        "validator": "semantic",
                    }
                )
            if (option.get("stop_tier") == "T2_TWO_STOP" or int(option.get("max_connections_per_journey") or 0) == 2) and stop_diagnostics.get("used_two_stop_fallback") is not True:
                errors.append(
                    {
                        "path": f"$.{collection_name}[{index}]",
                        "message": "two-stop options require stop-policy fallback mode",
                        "validator": "semantic",
                    }
                )

    diagnostics = report.get("coverage_diagnostics") if isinstance(report.get("coverage_diagnostics"), dict) else {}
    completeness = diagnostics.get("completeness") if isinstance(diagnostics.get("completeness"), dict) else {}
    if completeness.get("planned_count") != completeness.get("terminal_count"):
        errors.append(
            {
                "path": "$.coverage_diagnostics.completeness",
                "message": "coverage completeness requires planned_count == terminal_count",
                "validator": "semantic",
            }
        )
    if completeness.get("all_planned_controls_have_terminal_state") is not True:
        errors.append(
            {
                "path": "$.coverage_diagnostics.completeness.all_planned_controls_have_terminal_state",
                "message": "coverage completeness requires every planned control to have a terminal state",
                "validator": "semantic",
            }
        )

    return errors


def validate_agent_report(report: dict[str, Any]) -> None:
    errors = sorted(agent_report_validator().iter_errors(report), key=lambda item: list(item.absolute_path))
    details = [validation_error_detail(error) for error in errors]
    details.extend(semantic_errors(report))
    if details:
        raise CliError(
            "agent_report failed contract validation",
            error_type="contract_error",
            details={
                "schema_version": report.get("schema_version"),
                "errors": details,
            },
        )
