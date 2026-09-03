"""Публичный тип результата и точка входа в его проверку."""

from __future__ import annotations

from typing import Any, TypedDict

from ..contracts.registry import current_contract
from ..contracts.validation import (
    flight_search_result_semantic_errors,
    validate_flight_search_result,
)


SEARCH_RESULT_SCHEMA_VERSION = current_contract("search_result")["schema_version"]


class FlightSearchResult(TypedDict):
    schema_version: str
    request: dict[str, Any]
    route: dict[str, Any]
    options: list[dict[str, Any]]
    evidence: dict[str, Any]
    rendered_text: str


__all__ = [
    "FlightSearchResult",
    "SEARCH_RESULT_SCHEMA_VERSION",
    "flight_search_result_semantic_errors",
    "validate_flight_search_result",
]
