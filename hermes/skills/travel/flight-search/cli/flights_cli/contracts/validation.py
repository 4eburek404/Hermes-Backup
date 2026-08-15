from __future__ import annotations

from datetime import datetime
import json
from functools import lru_cache
from importlib import resources
import re
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from ..errors import CliError
from ..domain.stop_policy import connection_count_for_segments
from ..reporting.catalog_rendering import render_user_answer
from .registry import current_contract


def validation_error_detail(error: ValidationError) -> dict[str, Any]:
    path = "$"
    if error.absolute_path:
        path += "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}"
            for part in error.absolute_path
        )
    return {"path": path, "message": error.message, "validator": error.validator}


@lru_cache(maxsize=None)
def load_contract_schema(contract_name: str) -> dict[str, Any]:
    contract = current_contract(contract_name)
    text = (
        resources.files("flights_cli.contracts")
        .joinpath(contract["schema_resource"])
        .read_text(encoding="utf-8")
    )
    schema = json.loads(text)
    Draft202012Validator.check_schema(schema)
    return schema


@lru_cache(maxsize=1)
def packaged_schema_registry() -> Registry:
    registry = Registry()
    root = resources.files("flights_cli.contracts")
    for resource in root.iterdir():
        if not resource.name.endswith(".schema.json"):
            continue
        schema = json.loads(resource.read_text(encoding="utf-8"))
        schema_id = schema.get("$id")
        if isinstance(schema_id, str) and schema_id:
            registry = registry.with_resource(schema_id, Resource.from_contents(schema))
    return registry


@lru_cache(maxsize=None)
def contract_validator(contract_name: str) -> Draft202012Validator:
    return Draft202012Validator(
        load_contract_schema(contract_name),
        format_checker=FormatChecker(),
        registry=packaged_schema_registry(),
    )


def contract_validation_errors(
    contract_name: str, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    errors = sorted(
        contract_validator(contract_name).iter_errors(payload),
        key=lambda error: list(error.path),
    )
    return [validation_error_detail(error) for error in errors]


def validate_contract_payload(
    contract_name: str, payload: dict[str, Any], *, error_type: str = "contract_error"
) -> None:
    errors = contract_validation_errors(contract_name, payload)
    if errors:
        contract = current_contract(contract_name)
        raise CliError(
            f"{contract['schema_version']} failed contract validation",
            error_type=error_type,
            details={
                "schema_version": contract["schema_version"],
                "errors": errors[:10],
            },
        )


def _semantic_error(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message, "validator": "semantic"}


def _user_answer_segment_errors(
    segment: dict[str, Any], *, path: str
) -> tuple[list[dict[str, str]], tuple[datetime, datetime] | None]:
    errors: list[dict[str, str]] = []
    for field in ("origin", "destination"):
        if not re.fullmatch(r"[A-Z]{3}", str(segment.get(field) or "")):
            errors.append(
                _semantic_error(f"{path}.{field}", f"{field} must be an IATA code")
            )
    try:
        departure = datetime.fromisoformat(str(segment["departure_at"]))
        arrival = datetime.fromisoformat(str(segment["arrival_at"]))
        if departure.tzinfo is None or arrival.tzinfo is None:
            raise ValueError("UTC offset is required")
        if arrival < departure:
            raise ValueError("arrival precedes departure")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(_semantic_error(path, f"segment timestamps are invalid: {exc}"))
        return errors, None
    duration = segment.get("duration_min")
    if duration is not None and (not isinstance(duration, int) or duration < 0):
        errors.append(
            _semantic_error(f"{path}.duration_min", "duration must be non-negative")
        )
    elif duration is not None:
        expected_duration = int((arrival - departure).total_seconds() // 60)
        if duration != expected_duration:
            errors.append(
                _semantic_error(
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
            _semantic_error(
                "$.primary_option_id", "primary must be the first catalog option"
            )
        )
    if answer.get("alternative_option_ids") != option_ids[1:]:
        errors.append(
            _semantic_error(
                "$.alternative_option_ids",
                "alternatives must preserve catalog order",
            )
        )
    if len(option_ids) != len(set(option_ids)):
        errors.append(
            _semantic_error("$.catalog.items", "catalog option IDs must be unique")
        )

    for item_index, item in enumerate(items):
        if item.get("number") != item_index + 1:
            errors.append(
                _semantic_error(
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
                segment_errors, times = _user_answer_segment_errors(
                    segment, path=f"{base}.segments[{segment_index}]"
                )
                errors.extend(segment_errors)
                parsed.append(times)
            for segment_index, (previous, current) in enumerate(
                zip(segments, segments[1:])
            ):
                if previous.get("destination") != current.get("origin"):
                    errors.append(
                        _semantic_error(
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
                        _semantic_error(
                            f"{base}.layovers[{segment_index}]",
                            "layover must match segment timestamps",
                        )
                    )
            if len(layovers) != connection_count_for_segments(segments):
                errors.append(
                    _semantic_error(
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
                        _semantic_error(
                            f"{base}.elapsed_min",
                            "elapsed duration must match direction timestamps",
                        )
                    )

    evidence = (
        answer.get("evidence_status")
        if isinstance(answer.get("evidence_status"), dict)
        else {}
    )
    planned = int(evidence.get("planned_probe_count") or 0)
    terminal = int(evidence.get("terminal_probe_count") or 0)
    if terminal > planned:
        errors.append(
            _semantic_error(
                "$.evidence_status.terminal_probe_count",
                "terminal count cannot exceed planned count",
            )
        )
    if bool(evidence.get("execution_complete")) != (planned == terminal):
        errors.append(
            _semantic_error(
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
    if int(evidence.get("not_executed_probe_count") or 0):
        required.append("coverage_incompleteness_acknowledged")
    if int(evidence.get("provider_failure_count") or 0):
        required.append("provider_failures_acknowledged")
    for field in required:
        if caveats.get(field) is not True:
            errors.append(
                _semantic_error(
                    f"$.required_caveats.{field}", "required caveat is missing"
                )
            )
    return errors


def flight_search_result_semantic_errors(
    result: dict[str, Any],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    request = result.get("request") if isinstance(result.get("request"), dict) else {}
    route = result.get("route") if isinstance(result.get("route"), dict) else {}
    evidence = (
        result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
    )
    frontier = (
        result.get("frontier") if isinstance(result.get("frontier"), dict) else {}
    )
    answer = result.get("answer") if isinstance(result.get("answer"), dict) else {}

    if route.get("origin") != request.get("origin"):
        errors.append(_semantic_error("$.route.origin", "route must match request"))
    if route.get("destination") != request.get("destination"):
        errors.append(
            _semantic_error("$.route.destination", "route must match request")
        )
    request_dates = (request.get("depart_date"), request.get("return_date"))
    route_dates = route.get("dates") if isinstance(route.get("dates"), dict) else {}
    if (route_dates.get("depart"), route_dates.get("return")) != request_dates:
        errors.append(
            _semantic_error("$.route.dates", "route dates must match request")
        )

    catalog = answer.get("catalog") if isinstance(answer.get("catalog"), dict) else {}
    items = [item for item in catalog.get("items") or [] if isinstance(item, dict)]
    catalog_ids = [str(item.get("option_id") or "") for item in items]
    frontier_ids = [str(value) for value in frontier.get("option_ids") or []]
    if catalog_ids != frontier_ids:
        errors.append(
            _semantic_error(
                "$.answer.catalog.items",
                "catalog IDs and order must exactly match SearchDecision frontier",
            )
        )

    request_currency = str(request.get("currency") or "").upper()
    round_trip = bool(request.get("return_date"))
    origin_codes = {
        str(route.get("origin") or "").upper(),
        *(str(code).upper() for code in route.get("origin_airports") or []),
    }
    destination_codes = {
        str(route.get("destination") or "").upper(),
        *(str(code).upper() for code in route.get("destination_airports") or []),
    }
    for index, item in enumerate(items):
        path = f"$.answer.catalog.items[{index}]"
        price = (
            item.get("total_price") if isinstance(item.get("total_price"), dict) else {}
        )
        currency = str(price.get("currency") or "").upper()
        if currency and request_currency and currency != request_currency:
            errors.append(
                _semantic_error(f"{path}.total_price.currency", "currency mismatch")
            )
        directions = (
            item.get("directions") if isinstance(item.get("directions"), dict) else {}
        )
        if not isinstance(directions.get("outbound"), dict):
            errors.append(
                _semantic_error(
                    f"{path}.directions.outbound",
                    "visible option requires outbound segment details",
                )
            )
        if round_trip and not isinstance(directions.get("return"), dict):
            errors.append(
                _semantic_error(
                    f"{path}.directions.return",
                    "round-trip option requires return segment details",
                )
            )
        for direction, expected_origins, expected_destinations in (
            ("outbound", origin_codes, destination_codes),
            ("return", destination_codes, origin_codes),
        ):
            detail = directions.get(direction)
            if not isinstance(detail, dict):
                continue
            segments = [
                segment
                for segment in detail.get("segments") or []
                if isinstance(segment, dict)
            ]
            if not segments:
                errors.append(
                    _semantic_error(
                        f"{path}.directions.{direction}.segments",
                        "visible option requires complete segment details",
                    )
                )
                continue
            if str(segments[0].get("origin") or "").upper() not in expected_origins:
                errors.append(
                    _semantic_error(
                        f"{path}.directions.{direction}.segments[0].origin",
                        "direction origin does not match request",
                    )
                )
            if (
                str(segments[-1].get("destination") or "").upper()
                not in expected_destinations
            ):
                errors.append(
                    _semantic_error(
                        f"{path}.directions.{direction}.segments[-1].destination",
                        "direction destination does not match request",
                    )
                )

    coverage = (
        evidence.get("coverage") if isinstance(evidence.get("coverage"), dict) else {}
    )
    counts = coverage.get("counts") if isinstance(coverage.get("counts"), dict) else {}
    completeness = (
        coverage.get("completeness")
        if isinstance(coverage.get("completeness"), dict)
        else {}
    )
    evidence_status = (
        answer.get("evidence_status")
        if isinstance(answer.get("evidence_status"), dict)
        else {}
    )
    expected_counts = {
        "planned_probe_count": completeness.get("planned_count"),
        "terminal_probe_count": completeness.get("terminal_count"),
        "not_executed_probe_count": counts.get("not_executed_probes"),
        "failed_probe_count": counts.get("failed_probes"),
        "unsupported_probe_count": counts.get("unsupported_probes"),
        "provider_failure_count": counts.get("failed_probes"),
    }
    for field, expected in expected_counts.items():
        if evidence_status.get(field) != expected:
            errors.append(
                _semantic_error(
                    f"$.answer.evidence_status.{field}",
                    "evidence count does not match frozen evidence",
                )
            )

    rendered = render_user_answer(answer, route)
    if answer.get("rendered_text") != rendered:
        errors.append(
            _semantic_error(
                "$.answer.rendered_text",
                "rendered_text must equal the pure render of structured catalog facts",
            )
        )
    return errors


def validate_user_answer(answer: dict[str, Any]) -> None:
    details = contract_validation_errors("user_answer", answer)
    details.extend(user_answer_contract_semantic_errors(answer))
    if details:
        raise CliError(
            "flight_search_user_answer failed contract validation",
            error_type="contract_error",
            details={"schema_version": answer.get("schema_version"), "errors": details},
        )


def validate_flight_search_result(result: dict[str, Any]) -> None:
    answer = result.get("answer") if isinstance(result.get("answer"), dict) else {}
    errors = user_answer_contract_semantic_errors(answer)
    errors.extend(flight_search_result_semantic_errors(result))
    if errors:
        raise CliError(
            "flight_search_result failed semantic validation",
            error_type="contract_error",
            details={"schema_version": result.get("schema_version"), "errors": errors},
        )


__all__ = [
    "contract_validation_errors",
    "contract_validator",
    "flight_search_result_semantic_errors",
    "load_contract_schema",
    "packaged_schema_registry",
    "user_answer_contract_semantic_errors",
    "validate_contract_payload",
    "validate_flight_search_result",
    "validate_user_answer",
    "validation_error_detail",
]
