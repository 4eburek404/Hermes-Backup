from __future__ import annotations

from typing import Any, TypedDict

from ..errors import CliError
from ..reporting.user_answer import render_user_answer
from ..reporting.user_answer_contracts import user_answer_contract_semantic_errors


class FlightSearchResult(TypedDict):
    schema_version: str
    request: dict[str, Any]
    route: dict[str, Any]
    evidence: dict[str, Any]
    frontier: dict[str, Any]
    answer: dict[str, Any]


def _semantic_error(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message, "validator": "semantic"}


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
        "planned_control_count": completeness.get("planned_count"),
        "terminal_control_count": completeness.get("terminal_count"),
        "not_executed_control_count": counts.get("not_executed_controls"),
        "failed_control_count": counts.get("failed_controls"),
        "not_supported_control_count": counts.get("not_supported_controls"),
        "provider_failure_count": len(evidence.get("provider_failures") or []),
        "through_fare_check_count": len(evidence.get("through_fare_checks") or []),
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
