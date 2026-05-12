from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from ..errors import CliError

AGENT_REPORT_SCHEMA_VERSION = "agent_report.v1"
AGENT_REPORT_SCHEMA_RESOURCE = "agent_report.v1.schema.json"
AGENT_REPORT_SCHEMA_PACKAGE = "flights_cli.contracts"


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


def _option_stop_connections(option: Any) -> int | None:
    connections = option.get("max_connections_per_journey") if isinstance(option, dict) else None
    if isinstance(connections, int):
        return connections
    return None


def _is_stop_tier(option: Any, tier: str) -> bool:
    return isinstance(option, dict) and option.get("stop_tier") == tier


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

    options = list(report.get("recommended_options") or []) + list(report.get("priority_options") or [])
    preferred_tiers = {"t0_direct", "t1_one_stop"}
    has_preferred = any(
        str(option.get("stop_tier") or "").lower() in preferred_tiers
        or (_option_stop_connections(option) is not None and _option_stop_connections(option) <= 1)
        for option in options
        if isinstance(option, dict)
    )
    has_three_plus = any(
        _is_stop_tier(option, "T3_THREE_PLUS")
        or (_option_stop_connections(option) is not None and _option_stop_connections(option) >= 3)
        for option in options
        if isinstance(option, dict)
    )
    if has_three_plus:
        errors.append(
            {
                "path": "$.recommended_options, $.priority_options",
                "message": "agent_report options must not include 3+ connection itineraries in normal mode",
                "validator": "semantic",
            }
        )

    has_two_stop = any(
        _is_stop_tier(option, "T2_TWO_STOP")
        or (_option_stop_connections(option) is not None and _option_stop_connections(option) == 2)
        for option in options
        if isinstance(option, dict)
    )
    diagnostics = report.get("stop_policy_diagnostics") if isinstance(report.get("stop_policy_diagnostics"), dict) else {}
    used_fallback = bool(diagnostics.get("used_fallback_two_stop") or diagnostics.get("used_two_stop_fallback"))
    if has_preferred and has_two_stop and not used_fallback:
        errors.append(
            {
                "path": "$.recommended_options, $.priority_options",
                "message": "two-stop options should not be reported when preferred-tier candidates are present",
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
