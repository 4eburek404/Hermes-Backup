"""Варианты ответа `flight_search_result.v1`.

Один факт — одно поле. То, что раньше приезжало в шести кодировках —
`badges`, `caveats`, `protection`, `ticket_protection`, `ticketing_model` и
текст оговорки, — сведено к `ticketing` и `warnings`. Пересадка описана один
раз: `layovers` и `connection_assessment.connections` были двумя записями
одного и того же.

Два поля исчезли не как «неизвестные», а как неприменимые. У прямого
перелёта единым билетом нечего защищать, поэтому `single_pnr`,
`through_baggage` и `self_transfer` там просто отсутствуют — раньше он
получал `single_pnr_unproven` наравне со стыковочным. А `baggage` не
производит никто: ни один парсер провайдера не читает багаж, и объект из
четырёх полей всегда собирался из умолчаний. Осталось предупреждение
`baggage_unknown` — это правда, а не подстановка.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..domain.normalize import numeric_or_none, ordered_unique
from .time_utils import display_minutes_between, integer_or_none

# Словарь провайдерских моделей билета. Публичных значений три, и они
# отвечают на один вопрос: это один заказ провайдера или маршрут, собранный
# из отдельных предложений.
_PROVEN_MODELS = frozenset(
    {"single_pnr_proven", "single_ticket_proven", "protected_provider_order"}
)
_SINGLE_TICKET_MODELS = frozenset({"round_trip_single_ticket", "single_pnr"})
_PROVIDER_ORDER_MODELS = frozenset(
    {
        "provider_aggregate",
        "provider_offer_unverified",
        "provider_order_unverified",
        "round_trip_provider_order_unverified",
    }
)
_ASSEMBLED_MODELS = frozenset(
    {
        "gateway_separate_ticket",
        "separate_segments",
        "separate_ticket_sum",
        "separate_ticket_leg",
    }
)
_COMFORT_VALUES = frozenset({"comfortable", "acceptable", "long", "tight", "unknown"})


def build_options(
    frontier_options: list[dict[str, Any]], *, round_trip: bool
) -> list[dict[str, Any]]:
    """Спроецировать выбранные варианты решения в контракт ответа."""

    return [
        _option(source, number=number, round_trip=round_trip)
        for number, source in enumerate(
            [item for item in frontier_options if isinstance(item, dict)], start=1
        )
    ]


def _option(source: dict[str, Any], *, number: int, round_trip: bool) -> dict[str, Any]:
    assessment = (
        source.get("connection_assessment")
        if isinstance(source.get("connection_assessment"), dict)
        else {}
    )
    outbound = _leg(source, "outbound", assessment)
    inbound = _leg(source, "return", assessment)
    legs = [leg for leg in (outbound, inbound) if leg]
    flight_count = sum(len(leg["segments"]) for leg in legs)
    ticketing = _ticketing(source, flight_count=flight_count)
    price = source.get("price")
    return {
        "number": number,
        "id": str(source.get("id") or f"option-{number}"),
        "providers": _providers(source) or ["unknown"],
        "price": {
            "amount": numeric_or_none(price),
            "currency": str(source.get("currency") or "").upper(),
        },
        "journey_scope": "round_trip" if round_trip and inbound else "one_way",
        "ticketing": ticketing,
        "directions": {"outbound": outbound, "return": inbound},
        "rank_reason": _rank_reason(source),
        "warnings": _warnings(ticketing, legs),
    }


def _journey_segments(source: dict[str, Any], direction: str) -> list[dict[str, Any]]:
    for journey in source.get("journeys") or []:
        if not isinstance(journey, dict):
            continue
        if str(journey.get("direction") or "outbound") != direction:
            continue
        return [
            segment
            for segment in journey.get("segments") or []
            if isinstance(segment, dict)
        ]
    return []


def _leg(
    source: dict[str, Any], direction: str, assessment: dict[str, Any]
) -> dict[str, Any] | None:
    segments = _journey_segments(source, direction)
    if not segments:
        return None
    projected = [_segment(segment) for segment in segments]
    leg: dict[str, Any] = {
        "segments": projected,
        "duration_min": display_minutes_between(
            projected[0]["departure_at"], projected[-1]["arrival_at"]
        ),
    }
    connections = _connections(assessment, direction, projected)
    if connections:
        leg["connections"] = connections
    return leg


def _segment(segment: dict[str, Any]) -> dict[str, Any]:
    return {
        "flight_number": str(segment.get("flight_number") or "") or None,
        "carrier": str(
            segment.get("carrier")
            or segment.get("marketing_carrier")
            or segment.get("operating_carrier")
            or ""
        ).upper()
        or None,
        "origin": str(segment.get("origin") or "").upper(),
        "destination": str(segment.get("destination") or "").upper(),
        "departure_at": str(segment.get("departure_at") or ""),
        "arrival_at": str(segment.get("arrival_at") or ""),
        "duration_min": _segment_duration(segment),
        "departure_terminal": str(segment.get("departure_terminal") or "").strip()
        or None,
        "arrival_terminal": str(segment.get("arrival_terminal") or "").strip() or None,
    }


def _segment_duration(segment: dict[str, Any]) -> int | None:
    explicit = integer_or_none(segment.get("duration_min") or segment.get("duration"))
    if explicit is not None:
        return explicit
    try:
        departure = datetime.fromisoformat(str(segment["departure_at"]))
        arrival = datetime.fromisoformat(str(segment["arrival_at"]))
    except (KeyError, TypeError, ValueError):
        return None
    if departure.tzinfo is None or arrival.tzinfo is None:
        return None
    return int((arrival - departure).total_seconds() // 60)


def _connections(
    assessment: dict[str, Any], direction: str, segments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Пересадки плеча берутся из оценки, а недостающие — из самих рейсов.

    Оценка знает требуемый минимум, стыки между рейсами известны всегда.
    Раньше это были два независимых списка, и они умели расходиться.
    """

    scored = {
        str(item.get("airport") or "").upper(): item
        for item in assessment.get("connections") or []
        if isinstance(item, dict)
        and str(item.get("journey_direction") or "outbound") == direction
    }
    connections: list[dict[str, Any]] = []
    for arriving, departing in zip(segments, segments[1:]):
        airport = str(arriving["destination"] or departing["origin"] or "").upper()
        minutes = display_minutes_between(
            arriving["arrival_at"], departing["departure_at"]
        )
        item = scored.get(airport) or {}
        comfort = str(item.get("comfort") or "unknown")
        connection: dict[str, Any] = {
            "airport": airport,
            "minutes": integer_or_none(item.get("actual_min"))
            if integer_or_none(item.get("actual_min")) is not None
            else minutes,
            "comfort": comfort if comfort in _COMFORT_VALUES else "unknown",
        }
        required = integer_or_none(item.get("required_min"))
        if required is not None:
            connection["required_min"] = required
        connections.append(connection)
    return connections


def _ticketing(source: dict[str, Any], *, flight_count: int) -> dict[str, Any]:
    raw = str(source.get("ticketing_model") or "").strip()
    upstream = (
        source.get("ticket_protection")
        if isinstance(source.get("ticket_protection"), dict)
        else {}
    )
    status = str(upstream.get("status") or "unknown").strip().lower()
    if status not in {"protected", "unprotected", "unknown"}:
        status = "unknown"
    proven = raw in _PROVEN_MODELS or (
        raw in _SINGLE_TICKET_MODELS and status == "protected"
    )
    if raw in _ASSEMBLED_MODELS:
        model = "assembled"
    elif proven or raw in _PROVIDER_ORDER_MODELS or raw in _SINGLE_TICKET_MODELS:
        model = "provider_order"
    else:
        model = "unknown"
    ticketing: dict[str, Any] = {"model": model}
    if flight_count < 2:
        # Защищать нечего: один рейс не может распасться на два билета.
        return ticketing
    ticketing["single_pnr"] = "proven" if status == "protected" else "unproven"
    ticketing["through_baggage"] = "proven" if status == "protected" else "unproven"
    if status == "unprotected":
        ticketing["self_transfer"] = "yes"
    elif (
        status == "protected"
        or raw in _SINGLE_TICKET_MODELS
        or source.get("self_transfer") is False
    ):
        ticketing["self_transfer"] = "no"
    else:
        ticketing["self_transfer"] = "unknown"
    return ticketing


def _providers(source: dict[str, Any]) -> list[str]:
    raw = source.get("source_providers")
    names = (
        [str(item).strip() for item in raw if str(item).strip()]
        if isinstance(raw, list)
        else []
    )
    provider = str(source.get("provider") or "").strip()
    if provider:
        names.append(provider)
    return ordered_unique(names)


def _warnings(ticketing: dict[str, Any], legs: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if ticketing.get("single_pnr") == "unproven":
        warnings.append("single_pnr_unproven")
    if ticketing.get("through_baggage") == "unproven":
        warnings.append("through_baggage_unproven")
    if ticketing.get("self_transfer") == "yes":
        warnings.append("self_transfer")
    if any(
        connection.get("comfort") == "tight"
        for leg in legs
        for connection in leg.get("connections") or []
    ):
        warnings.append("tight_connection")
    # Багаж не читает ни один парсер провайдера, поэтому предупреждение
    # безусловно. Появится источник — здесь появится условие.
    warnings.append("baggage_unknown")
    warnings.append("verify_on_booking_screen")
    return warnings


def _rank_reason(source: dict[str, Any]) -> dict[str, Any]:
    """Причину ранга считает слой решения — здесь она только проецируется."""

    reason = source.get("rank_reason")
    if not isinstance(reason, dict) or not reason.get("code"):
        return {"code": "top_ranked", "detail_min": None}
    detail = integer_or_none(reason.get("detail_min"))
    return {"code": str(reason["code"]), "detail_min": detail}


__all__ = ["build_options"]
