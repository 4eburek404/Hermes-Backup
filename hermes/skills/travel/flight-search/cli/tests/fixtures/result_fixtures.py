"""Общие фикстуры публичного результата `.v1`.

Строятся те же типизированные артефакты, что и в проде: свидетельство
прогона и решение. Промежуточной трассы, из которой раньше вычитывался
ответ, больше нет — значит и подделать её в тесте нельзя.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from flights_cli.pipeline.result_builder import build_flight_search_result
from flights_cli.pipeline.search_request import search_request_from_payload

# Дата фикстуры обязана быть будущей: канонический повтор входа строит сам
# SearchRequest, а он отвергает прошедшую дату вылета.
DEPART = (date.today() + timedelta(days=3)).isoformat()
NEXT_DAY = (date.today() + timedelta(days=4)).isoformat()

OUTBOUND_SEGMENTS = [
    {
        "flight_number": "SU1419",
        "carrier": "SU",
        "marketing_carrier": "SU",
        "operating_carrier": "SU",
        "origin": "SVX",
        "destination": "SVO",
        "departure_at": f"{DEPART}T06:00:00+05:00",
        "arrival_at": f"{DEPART}T06:40:00+03:00",
        "duration_min": 160,
    },
    {
        "flight_number": "SU232",
        "carrier": "SU",
        "marketing_carrier": "SU",
        "operating_carrier": "SU",
        "origin": "SVO",
        "destination": "DEL",
        "departure_at": f"{DEPART}T21:20:00+03:00",
        "arrival_at": f"{NEXT_DAY}T06:00:00+05:30",
        "duration_min": 370,
    },
]


def connecting_option(**overrides: Any) -> dict[str, Any]:
    """Вариант рубежа решения: SVX→SVO→DEL одним заказом провайдера."""

    option: dict[str, Any] = {
        "id": "candidate:primary_offer:kupibilet:svx-del",
        "provider": "kupibilet",
        "source_providers": ["kupibilet"],
        "price": 10000,
        "currency": "RUB",
        "journey_scope": "one_way",
        "ticketing_model": "provider_order_unverified",
        "ticket_protection": {
            "status": "unknown",
            "source": "provider_evidence_incomplete",
            "reasons": ["ticket_protection_unproven"],
        },
        "self_transfer": None,
        "detail_status": "full",
        "elapsed_min": 1410,
        "max_connections_per_journey": 1,
        "rank_key": [0, 0, 1, 0, 0, 0, 1, 0, 10000, 1410],
        "journeys": [{"direction": "outbound", "segments": OUTBOUND_SEGMENTS}],
        "connection_assessment": {
            "status": "valid",
            "comfort": "comfortable",
            "connections": [
                {
                    "airport": "SVO",
                    "journey_direction": "outbound",
                    "actual_min": 880,
                    "required_min": 120,
                    "comfort": "comfortable",
                    "status": "valid",
                }
            ],
        },
    }
    option.update(overrides)
    return option


DIRECT_SEGMENT = {
    "flight_number": "SU234",
    "carrier": "SU",
    "marketing_carrier": "SU",
    "operating_carrier": "SU",
    "origin": "SVX",
    "destination": "DEL",
    "departure_at": f"{DEPART}T06:00:00+05:00",
    "arrival_at": f"{DEPART}T12:00:00+05:30",
    "duration_min": 330,
}


def direct_option(**overrides: Any) -> dict[str, Any]:
    """Прямой рейс: защищать нечего, пересадок нет."""

    option = connecting_option(
        id="candidate:primary_offer:tutu:svx-del-direct",
        provider="tutu",
        source_providers=["tutu"],
        price=8043,
        elapsed_min=330,
        max_connections_per_journey=0,
        rank_key=[0, 0, 0, 0, 0, 0, 1, 0, 8043, 330],
        journeys=[{"direction": "outbound", "segments": [DIRECT_SEGMENT]}],
        connection_assessment={
            "status": "valid",
            "comfort": "unknown",
            "connections": [],
        },
    )
    option.update(overrides)
    return option


def probe_ledger(
    *,
    searched: list[str] | None = None,
    failed: list[dict[str, Any]] | None = None,
    not_executed: int = 0,
) -> dict[str, Any]:
    providers = ["kupibilet", "tutu"] if searched is None else searched
    failures = failed or []
    planned = [
        {"probe_id": f"probe-{index}", "provider": provider, "date": DEPART}
        for index, provider in enumerate(providers, start=1)
    ]
    planned.extend(
        {"probe_id": f"probe-failed-{index}", "provider": item.get("provider")}
        for index, item in enumerate(failures, start=1)
    )
    planned.extend(
        {"probe_id": f"probe-pending-{index}"} for index in range(1, not_executed + 1)
    )
    return {
        "planned_probes": planned,
        "searched_probes": [
            {"probe_id": f"probe-{index}", "provider": provider, "status": "ok"}
            for index, provider in enumerate(providers, start=1)
        ],
        "skipped_probes": [],
        "failed_probes": list(failures),
        "unsupported_probes": [],
        "not_executed_probes": [
            {"probe_id": f"probe-pending-{index}", "status": "not_executed"}
            for index in range(1, not_executed + 1)
        ],
        "deduped_probes": [],
    }


def request_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "schema_version": "flight_search_request.v1",
        "origin": "SVX",
        "destination": "DEL",
        "depart_date": DEPART,
        "return_date": None,
        "currency": "RUB",
    }
    payload.update(overrides)
    return payload


def valid_result(
    options: list[dict[str, Any]] | None = None,
    *,
    ledger: dict[str, Any] | None = None,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_flight_search_result(
        search_request_from_payload(request or request_payload()),
        options if options is not None else [connecting_option()],
        ledger if ledger is not None else probe_ledger(),
    )


__all__ = [
    "DEPART",
    "NEXT_DAY",
    "DIRECT_SEGMENT",
    "OUTBOUND_SEGMENTS",
    "connecting_option",
    "direct_option",
    "probe_ledger",
    "request_payload",
    "valid_result",
]
