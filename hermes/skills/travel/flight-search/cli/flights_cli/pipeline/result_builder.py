"""Сборка публичного ответа `flight_search_result.v1`.

Сборщик берёт три факта: запрос, выбранные варианты и журнал проб. Ни плана,
ни решения, ни свидетельства как объектов он не знает — раньше между ними и
ответом стояла диагностическая трасса, и публичные поля вычитывались обратно
из неё. Трассы больше нет, и вместе с ней нет второго представления цены,
длительности, пересадки и защиты билета.
"""

from __future__ import annotations

from typing import Any

from ..contracts.validation import validate_contract_payload
from ..reporting.answer_options import build_options
from ..reporting.answer_text import render_answer
from ..reporting.evidence import build_evidence
from .result_contract import (
    FlightSearchResult,
    SEARCH_RESULT_SCHEMA_VERSION,
    validate_flight_search_result,
)
from .search_request import SearchRequest


def build_flight_search_result(
    request: SearchRequest,
    frontier_options: list[dict[str, Any]],
    probe_ledger: Any,
    *,
    date_window: dict[str, Any] | None = None,
) -> FlightSearchResult:
    """Связать один прогон с публичным контрактом `.v1`."""

    echo = _request_echo(request)
    route = {
        "origin": echo["origin"],
        "destination": echo["destination"],
        "depart_date": echo["depart_date"],
        "return_date": echo.get("return_date"),
    }
    options = build_options(
        [option for option in frontier_options or [] if isinstance(option, dict)],
        round_trip=bool(route["return_date"]),
    )
    evidence = build_evidence(probe_ledger, date_window=date_window)
    result: FlightSearchResult = {
        "schema_version": SEARCH_RESULT_SCHEMA_VERSION,
        "request": echo,
        "route": route,
        "options": options,
        "evidence": evidence,
        "rendered_text": render_answer(route, options, evidence=evidence),
    }
    validate_contract_payload("search_result", result)
    validate_flight_search_result(result)
    return result


def _request_echo(request: SearchRequest) -> dict[str, Any]:
    """Канонический повтор входа берётся у самого запроса."""

    payload = request.to_payload()
    validate_contract_payload("search_request", payload)
    return payload


__all__ = ["build_flight_search_result"]
