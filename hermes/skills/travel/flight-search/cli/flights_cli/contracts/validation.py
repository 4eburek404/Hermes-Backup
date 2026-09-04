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


def _segment_errors(
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
    if duration is not None:
        expected_duration = int((arrival - departure).total_seconds() // 60)
        if duration != expected_duration:
            errors.append(
                _semantic_error(
                    f"{path}.duration_min", "duration must match segment timestamps"
                )
            )
    return errors, (departure, arrival)


def _leg_errors(
    leg: dict[str, Any],
    *,
    path: str,
    expected_origins: set[str],
    expected_destinations: set[str],
) -> tuple[list[dict[str, str]], int]:
    errors: list[dict[str, str]] = []
    segments = [
        segment for segment in leg.get("segments") or [] if isinstance(segment, dict)
    ]
    if not segments:
        errors.append(
            _semantic_error(f"{path}.segments", "a visible leg requires its flights")
        )
        return errors, 0
    if str(segments[0].get("origin") or "").upper() not in expected_origins:
        errors.append(
            _semantic_error(
                f"{path}.segments[0].origin", "leg origin does not match the request"
            )
        )
    if str(segments[-1].get("destination") or "").upper() not in expected_destinations:
        errors.append(
            _semantic_error(
                f"{path}.segments[-1].destination",
                "leg destination does not match the request",
            )
        )
    bounds: list[tuple[datetime, datetime] | None] = []
    for index, segment in enumerate(segments):
        segment_errors, window = _segment_errors(
            segment, path=f"{path}.segments[{index}]"
        )
        errors.extend(segment_errors)
        bounds.append(window)
    connections = leg.get("connections")
    if len(segments) == 1:
        if connections is not None:
            errors.append(
                _semantic_error(
                    f"{path}.connections",
                    "a single-flight leg cannot carry a connection",
                )
            )
        return errors, len(segments)
    if not isinstance(connections, list) or len(connections) != len(segments) - 1:
        errors.append(
            _semantic_error(
                f"{path}.connections",
                "every gap between two flights is described exactly once",
            )
        )
        return errors, len(segments)
    for index, connection in enumerate(connections):
        arriving, departing = segments[index], segments[index + 1]
        junction = str(arriving.get("destination") or "").upper()
        if str(connection.get("airport") or "").upper() != junction:
            errors.append(
                _semantic_error(
                    f"{path}.connections[{index}].airport",
                    "connection airport must be where the previous flight lands",
                )
            )
        if str(departing.get("origin") or "").upper() != junction:
            errors.append(
                _semantic_error(
                    f"{path}.segments[{index + 1}].origin",
                    "the next flight must depart where the previous one landed",
                )
            )
        before, after = bounds[index], bounds[index + 1]
        if before is None or after is None:
            continue
        minutes = int((after[0] - before[1]).total_seconds() // 60)
        if minutes < 0:
            errors.append(
                _semantic_error(
                    f"{path}.segments[{index + 1}].departure_at",
                    "the next flight cannot depart before the previous one lands",
                )
            )
        elif connection.get("minutes") != minutes:
            errors.append(
                _semantic_error(
                    f"{path}.connections[{index}].minutes",
                    "connection length must match the flights around it",
                )
            )
    return errors, len(segments)


_PROTECTION_FIELDS = ("single_pnr", "through_baggage", "self_transfer")
# Свойства пересадки: без стыка внутри плеча их не существует.
_TRANSFER_FIELDS = ("through_baggage", "self_transfer")


def flight_search_result_semantic_errors(
    result: dict[str, Any],
) -> list[dict[str, str]]:
    """Проверить то, чего схема не выражает: согласие полей между собой."""

    errors: list[dict[str, str]] = []
    request = result.get("request") if isinstance(result.get("request"), dict) else {}
    route = result.get("route") if isinstance(result.get("route"), dict) else {}
    evidence = (
        result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
    )
    options = [
        option for option in result.get("options") or [] if isinstance(option, dict)
    ]

    for field in ("origin", "destination", "depart_date", "return_date"):
        if route.get(field) != request.get(field):
            errors.append(
                _semantic_error(f"$.route.{field}", "route must repeat the request")
            )

    round_trip = bool(request.get("return_date"))
    request_currency = str(request.get("currency") or "").upper()
    origin_codes = {
        str(request.get("origin") or "").upper(),
        *(str(code).upper() for code in request.get("origin_airports") or []),
    }
    destination_codes = {
        str(request.get("destination") or "").upper(),
        *(str(code).upper() for code in request.get("destination_airports") or []),
    }
    searched = {str(provider) for provider in evidence.get("providers_searched") or []}

    seen_ids: set[str] = set()
    for index, option in enumerate(options):
        path = f"$.options[{index}]"
        if option.get("number") != index + 1:
            errors.append(
                _semantic_error(
                    f"{path}.number", "options are numbered from 1 in order"
                )
            )
        option_id = str(option.get("id") or "")
        if option_id in seen_ids:
            errors.append(_semantic_error(f"{path}.id", "option ids must be unique"))
        seen_ids.add(option_id)

        providers = {str(name) for name in option.get("providers") or []}
        unsearched = providers - searched
        if unsearched:
            errors.append(
                _semantic_error(
                    f"{path}.providers",
                    "an option cannot come from a provider that was never searched",
                )
            )
        price = option.get("price") if isinstance(option.get("price"), dict) else {}
        currency = str(price.get("currency") or "").upper()
        if request_currency and currency != request_currency:
            errors.append(
                _semantic_error(
                    f"{path}.price.currency", "currency does not match the request"
                )
            )

        directions = (
            option.get("directions")
            if isinstance(option.get("directions"), dict)
            else {}
        )
        inbound = directions.get("return")
        expected_scope = "round_trip" if round_trip else "one_way"
        if option.get("journey_scope") != expected_scope:
            errors.append(
                _semantic_error(
                    f"{path}.journey_scope", "journey scope must match the request"
                )
            )
        if round_trip and not isinstance(inbound, dict):
            errors.append(
                _semantic_error(
                    f"{path}.directions.return",
                    "a round-trip request is answered with both legs or not at all",
                )
            )
        if not round_trip and inbound is not None:
            errors.append(
                _semantic_error(
                    f"{path}.directions.return",
                    "a one-way request cannot be answered with a return leg",
                )
            )

        has_transfer = False
        for direction, expected_from, expected_to in (
            ("outbound", origin_codes, destination_codes),
            ("return", destination_codes, origin_codes),
        ):
            leg = directions.get(direction)
            if not isinstance(leg, dict):
                if direction == "outbound":
                    errors.append(
                        _semantic_error(
                            f"{path}.directions.outbound",
                            "a visible option requires its outbound flights",
                        )
                    )
                continue
            leg_errors, segment_count = _leg_errors(
                leg,
                path=f"{path}.directions.{direction}",
                expected_origins=expected_from,
                expected_destinations=expected_to,
            )
            errors.extend(leg_errors)
            has_transfer = has_transfer or segment_count > 1

        ticketing = (
            option.get("ticketing") if isinstance(option.get("ticketing"), dict) else {}
        )
        # Туда и обратно — два рейса, но не стык: везти багаж насквозь и
        # опаздывать на пересадку там негде.
        stated_transfer = [field for field in _TRANSFER_FIELDS if field in ticketing]
        if has_transfer and len(stated_transfer) != len(_TRANSFER_FIELDS):
            errors.append(
                _semantic_error(
                    f"{path}.ticketing",
                    "an option with a connection must state transfer protection",
                )
            )
        if not has_transfer and stated_transfer:
            errors.append(
                _semantic_error(
                    f"{path}.ticketing",
                    "an option without a connection has no transfer to protect",
                )
            )
        # Единый PNR — вопрос про число заказов, а не про стык: у собранного
        # маршрута он осмыслен и без пересадки.
        assembled = str(ticketing.get("model") or "") == "assembled"
        if (has_transfer or assembled) != ("single_pnr" in ticketing):
            errors.append(
                _semantic_error(
                    f"{path}.ticketing",
                    "single_pnr belongs to an option with a connection or "
                    "assembled from separate offers",
                )
            )

        warnings = {str(code) for code in option.get("warnings") or []}
        for field, value, code in (
            ("single_pnr", "unproven", "single_pnr_unproven"),
            ("through_baggage", "unproven", "through_baggage_unproven"),
            ("self_transfer", "yes", "self_transfer"),
        ):
            if (ticketing.get(field) == value) != (code in warnings):
                errors.append(
                    _semantic_error(
                        f"{path}.warnings",
                        f"{code} must agree with ticketing.{field}",
                    )
                )
        tight = any(
            connection.get("comfort") == "tight"
            for leg in directions.values()
            if isinstance(leg, dict)
            for connection in leg.get("connections") or []
            if isinstance(connection, dict)
        )
        if tight != ("tight_connection" in warnings):
            errors.append(
                _semantic_error(
                    f"{path}.warnings",
                    "tight_connection must agree with the connections shown",
                )
            )

    # Сверки rendered_text с повторным вызовом рендера здесь нет: она сравнивала
    # функцию с собственным выходом на том же входе и пропускала подделанный
    # текст. Проверка структуры остаётся, проверка строки — нет.
    return errors


def validate_flight_search_result(result: dict[str, Any]) -> None:
    errors = flight_search_result_semantic_errors(result)
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
    "validate_contract_payload",
    "validate_flight_search_result",
    "validation_error_detail",
]
