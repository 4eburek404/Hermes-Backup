#!/usr/bin/env python3
"""Canonical itinerary JSON Schema contract for flight-calendar-ics.

This module is intentionally provider-agnostic: carrier/API/PDF-specific fields
belong in adapters, while this contract validates the normalized itinerary that
is ready for ICS generation.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SCHEMA_VERSION = "flight-calendar-ics-itinerary.v1"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "itinerary.v1.schema.json"
UTC = dt.timezone.utc
PLACEHOLDERS = {"", "tbd", "todo", "unknown", "none", "null", "n/a", "na", "?"}


def is_placeholder(value: Any) -> bool:
    return value is None or str(value).strip().lower() in PLACEHOLDERS


@lru_cache(maxsize=1)
def load_itinerary_schema() -> dict[str, Any]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - repository packaging guard
        raise ValueError(f"canonical itinerary schema is missing: {SCHEMA_PATH}") from exc
    if not isinstance(schema, dict):  # pragma: no cover - defensive guard
        raise ValueError("canonical itinerary schema root must be a JSON object")
    return schema


@lru_cache(maxsize=1)
def _validator() -> Any:
    try:
        from jsonschema import Draft202012Validator
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on runtime image
        raise ValueError("jsonschema package is required for canonical itinerary validation") from exc

    schema = load_itinerary_schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def normalize_legacy_itinerary(data: dict[str, Any]) -> dict[str, Any]:
    """Return a canonical-compatible copy of old itinerary JSON input.

    Older templates predated the explicit input-schema version. Keep those files
    usable by adding the version in memory, but do not remove unknown fields: the
    schema gate must still reject non-canonical payloads and typos.
    """
    if not isinstance(data, dict):
        raise ValueError("input JSON root must be an object")
    normalized = copy.deepcopy(data)
    normalized.setdefault("schema_version", SCHEMA_VERSION)
    return normalized


def _format_path(parts: Iterable[Any]) -> str:
    path = ""
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path = str(part) if not path else f"{path}.{part}"
    return path or "$"


def _safe_error_message(error: Any) -> str:
    path = _format_path(error.absolute_path)
    validator = getattr(error, "validator", "schema")
    if validator == "required":
        missing = re.findall(r"'([^']+)' is a required property", error.message)
        fields = ", ".join(missing) if missing else "required field"
        return f"{path}: missing required field(s): {fields}"
    if validator == "additionalProperties":
        unexpected = re.findall(r"'([^']+)'", error.message)
        fields = ", ".join(unexpected) if unexpected else "unknown field"
        return f"{path}: unknown field(s): {fields}"
    if validator == "type":
        expected = error.validator_value
        if isinstance(expected, list):
            expected_text = " or ".join(str(item) for item in expected)
        else:
            expected_text = str(expected)
        return f"{path}: expected {expected_text}"
    if validator == "pattern":
        return f"{path}: does not match the canonical pattern"
    if validator == "format":
        return f"{path}: invalid {error.validator_value} format"
    if validator == "minItems":
        return f"{path}: must contain at least {error.validator_value} item(s)"
    if validator == "uniqueItems":
        return f"{path}: must not contain duplicate items"
    if validator == "minimum":
        return f"{path}: must be greater than or equal to {error.validator_value}"
    if validator == "minLength":
        return f"{path}: must not be empty"
    if validator == "maxLength":
        return f"{path}: is too long"
    if validator == "const":
        return f"{path}: must equal the canonical schema version"
    if validator == "enum":
        return f"{path}: value is not allowed by the canonical contract"
    return f"{path}: violates schema rule {validator}"


def validate_itinerary_schema(data: dict[str, Any]) -> None:
    validator = _validator()
    errors = sorted(validator.iter_errors(data), key=lambda err: list(err.absolute_path))
    if errors:
        summary = "; ".join(_safe_error_message(error) for error in errors[:5])
        if len(errors) > 5:
            summary += f"; ... {len(errors) - 5} more"
        raise ValueError(f"itinerary schema validation failed: {summary}")


def _parse_local(value: Any, tzid: Any, path: str) -> dt.datetime:
    if is_placeholder(value):
        raise ValueError(f"{path}.local is required")
    if is_placeholder(tzid):
        raise ValueError(f"{path}.tz is required")
    raw = str(value).strip().replace(" ", "T", 1)
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{path}.local must be an ISO local datetime") from exc
    if parsed.tzinfo is not None:
        return parsed
    try:
        zone = ZoneInfo(str(tzid).strip())
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"{path}.tz is not a known IANA timezone") from exc
    return parsed.replace(tzinfo=zone)


def validate_itinerary_semantics(data: dict[str, Any]) -> None:
    flights = data.get("flights") or []
    for idx, flight in enumerate(flights):
        flight_path = f"flights[{idx}]"
        flight_number = flight.get("flight_number")
        if is_placeholder(flight_number):
            raise ValueError(f"{flight_path}.flight_number is required")
        dep = flight.get("departure") or {}
        arr = flight.get("arrival") or {}
        for endpoint_name, endpoint in (("departure", dep), ("arrival", arr)):
            endpoint_path = f"{flight_path}.{endpoint_name}"
            if is_placeholder(endpoint.get("airport")):
                raise ValueError(f"{endpoint_path}.airport is required")
            if is_placeholder(endpoint.get("local")):
                raise ValueError(f"{endpoint_path}.local is required")
            if is_placeholder(endpoint.get("tz")):
                raise ValueError(f"{endpoint_path}.tz is required")

        dep_dt = _parse_local(dep.get("local"), dep.get("tz"), f"{flight_path}.departure")
        arr_dt = _parse_local(arr.get("local"), arr.get("tz"), f"{flight_path}.arrival")
        if arr_dt.astimezone(UTC) <= dep_dt.astimezone(UTC):
            raise ValueError(f"{flight_path}: arrival must be after departure after timezone conversion")
