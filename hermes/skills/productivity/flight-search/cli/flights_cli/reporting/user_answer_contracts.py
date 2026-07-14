from __future__ import annotations

from datetime import datetime
import json
import re
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from ..contracts.registry import current_contract
from ..contracts.schema_errors import validation_error_detail
from ..errors import CliError


_USER_ANSWER_CONTRACT = current_contract("user_answer")
USER_ANSWER_SCHEMA_VERSION = _USER_ANSWER_CONTRACT["schema_version"]
USER_ANSWER_SCHEMA_RESOURCE = _USER_ANSWER_CONTRACT["schema_resource"]
USER_ANSWER_SCHEMA_PACKAGE = "flights_cli.contracts"


@lru_cache(maxsize=1)
def load_user_answer_schema() -> dict[str, Any]:
    text = (
        resources.files(USER_ANSWER_SCHEMA_PACKAGE)
        .joinpath(USER_ANSWER_SCHEMA_RESOURCE)
        .read_text(encoding="utf-8")
    )
    schema = json.loads(text)
    Draft202012Validator.check_schema(schema)
    return schema


@lru_cache(maxsize=1)
def user_answer_validator() -> Draft202012Validator:
    return Draft202012Validator(
        load_user_answer_schema(), format_checker=FormatChecker()
    )


def _error(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message, "validator": "semantic"}


def _segment_errors(
    segment: dict[str, Any], *, path: str
) -> tuple[list[dict[str, str]], tuple[datetime, datetime] | None]:
    errors: list[dict[str, str]] = []
    for field in ("origin", "destination"):
        if not re.fullmatch(r"[A-Z]{3}", str(segment.get(field) or "")):
            errors.append(_error(f"{path}.{field}", f"{field} must be an IATA code"))
    try:
        departure = datetime.fromisoformat(str(segment["departure_at"]))
        arrival = datetime.fromisoformat(str(segment["arrival_at"]))
        if departure.tzinfo is None or arrival.tzinfo is None:
            raise ValueError("UTC offset is required")
        if arrival < departure:
            raise ValueError("arrival precedes departure")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(_error(path, f"segment timestamps are invalid: {exc}"))
        return errors, None
    duration = segment.get("duration_min")
    if duration is not None and (not isinstance(duration, int) or duration < 0):
        errors.append(_error(f"{path}.duration_min", "duration must be non-negative"))
    elif duration is not None:
        expected_duration = int((arrival - departure).total_seconds() // 60)
        if duration != expected_duration:
            errors.append(
                _error(
                    f"{path}.duration_min",
                    "duration must match segment timestamps",
                )
            )
    return errors, (departure, arrival)


def user_answer_contract_semantic_errors(
    answer: dict[str, Any],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    catalog = answer.get("catalog") if isinstance(answer.get("catalog"), dict) else {}
    items = [item for item in catalog.get("items") or [] if isinstance(item, dict)]
    option_ids = [str(item.get("option_id") or "") for item in items]
    expected_primary = option_ids[0] if option_ids else None
    if answer.get("primary_option_id") != expected_primary:
        errors.append(
            _error("$.primary_option_id", "primary must be the first catalog option")
        )
    if answer.get("alternative_option_ids") != option_ids[1:]:
        errors.append(
            _error(
                "$.alternative_option_ids",
                "alternatives must preserve catalog order",
            )
        )
    if len(option_ids) != len(set(option_ids)):
        errors.append(_error("$.catalog.items", "catalog option IDs must be unique"))

    for item_index, item in enumerate(items):
        if item.get("number") != item_index + 1:
            errors.append(
                _error(
                    f"$.catalog.items[{item_index}].number",
                    "catalog numbering must be contiguous",
                )
            )
        directions = item.get("directions")
        directions = directions if isinstance(directions, dict) else {}
        for direction in ("outbound", "return"):
            detail = directions.get(direction)
            if not isinstance(detail, dict):
                continue
            segments = [
                segment
                for segment in detail.get("segments") or []
                if isinstance(segment, dict)
            ]
            layovers = [
                layover
                for layover in detail.get("layovers") or []
                if isinstance(layover, dict)
            ]
            parsed: list[tuple[datetime, datetime] | None] = []
            base = f"$.catalog.items[{item_index}].directions.{direction}"
            for segment_index, segment in enumerate(segments):
                segment_errors, times = _segment_errors(
                    segment, path=f"{base}.segments[{segment_index}]"
                )
                errors.extend(segment_errors)
                parsed.append(times)
            for segment_index, (previous, current) in enumerate(
                zip(segments, segments[1:])
            ):
                if previous.get("destination") != current.get("origin"):
                    errors.append(
                        _error(
                            f"{base}.segments[{segment_index + 1}].origin",
                            "segment continuity is broken",
                        )
                    )
                previous_times = parsed[segment_index]
                current_times = parsed[segment_index + 1]
                if previous_times is None or current_times is None:
                    continue
                expected = int(
                    (current_times[0] - previous_times[1]).total_seconds() // 60
                )
                actual = (
                    layovers[segment_index].get("duration_min")
                    if segment_index < len(layovers)
                    else None
                )
                airport = (
                    layovers[segment_index].get("airport")
                    if segment_index < len(layovers)
                    else None
                )
                if (
                    expected < 0
                    or actual != expected
                    or airport != previous.get("destination")
                ):
                    errors.append(
                        _error(
                            f"{base}.layovers[{segment_index}]",
                            "layover must match segment timestamps",
                        )
                    )
            if len(layovers) != max(0, len(segments) - 1):
                errors.append(
                    _error(
                        f"{base}.layovers",
                        "layover count must equal segment count minus one",
                    )
                )
            valid_times = [times for times in parsed if times is not None]
            if segments and len(valid_times) == len(segments):
                expected_elapsed = int(
                    (valid_times[-1][1] - valid_times[0][0]).total_seconds() // 60
                )
                if detail.get("elapsed_min") != expected_elapsed:
                    errors.append(
                        _error(
                            f"{base}.elapsed_min",
                            "elapsed duration must match direction timestamps",
                        )
                    )

    evidence = (
        answer.get("evidence_status")
        if isinstance(answer.get("evidence_status"), dict)
        else {}
    )
    planned = int(evidence.get("planned_control_count") or 0)
    terminal = int(evidence.get("terminal_control_count") or 0)
    if terminal > planned:
        errors.append(
            _error(
                "$.evidence_status.terminal_control_count",
                "terminal count cannot exceed planned count",
            )
        )
    if bool(evidence.get("execution_complete")) != (planned == terminal):
        errors.append(
            _error(
                "$.evidence_status.execution_complete",
                "execution_complete must match ledger counts",
            )
        )
    caveats = (
        answer.get("required_caveats")
        if isinstance(answer.get("required_caveats"), dict)
        else {}
    )
    required = ["source_boundaries_included", "purchase_screen_verification_required"]
    if int(evidence.get("not_executed_control_count") or 0):
        required.append("coverage_incompleteness_acknowledged")
    if int(evidence.get("provider_failure_count") or 0):
        required.append("provider_failures_acknowledged")
    for field in required:
        if caveats.get(field) is not True:
            errors.append(
                _error(f"$.required_caveats.{field}", "required caveat is missing")
            )
    return errors


def validate_user_answer(answer: dict[str, Any]) -> None:
    schema_errors = sorted(
        user_answer_validator().iter_errors(answer),
        key=lambda item: list(item.absolute_path),
    )
    details = [validation_error_detail(error) for error in schema_errors]
    details.extend(user_answer_contract_semantic_errors(answer))
    if details:
        raise CliError(
            "flight_search_user_answer failed contract validation",
            error_type="contract_error",
            details={"schema_version": answer.get("schema_version"), "errors": details},
        )
