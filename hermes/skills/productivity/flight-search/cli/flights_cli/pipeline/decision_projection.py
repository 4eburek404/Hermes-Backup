from __future__ import annotations

from typing import Any

from ..reporting.formatting import minutes_label, price_label


def segment_summary(
    segment: dict[str, Any], direction: str | None = None
) -> dict[str, Any]:
    return {
        "direction": direction,
        "flight_number": segment.get("flight_number"),
        "carrier": segment.get("carrier")
        or segment.get("operating_carrier")
        or segment.get("marketing_carrier"),
        "marketing_carrier": segment.get("marketing_carrier"),
        "operating_carrier": segment.get("operating_carrier"),
        "origin": segment.get("origin"),
        "destination": segment.get("destination"),
        "departure_terminal": segment.get("departure_terminal"),
        "arrival_terminal": segment.get("arrival_terminal"),
        "departure_at": segment.get("departure_at"),
        "arrival_at": segment.get("arrival_at"),
        "aircraft_code": segment.get("aircraft_code") or segment.get("aircraft"),
        "duration_min": segment.get("duration_min") or segment.get("duration"),
    }


def connection_summary(connection: dict[str, Any]) -> dict[str, Any]:
    risk = connection.get("risk") if isinstance(connection.get("risk"), dict) else {}
    return {
        "direction": connection.get("journey_direction"),
        "arrival_airport": connection.get("arrival_airport"),
        "departure_airport": connection.get("departure_airport"),
        "status": connection.get("status"),
        "severity": connection.get("severity"),
        "actual_min": connection.get("actual_min"),
        "actual": minutes_label(connection.get("actual_min")),
        "required_min": connection.get("required_min"),
        "required": minutes_label(connection.get("required_min")),
        "risk": {
            "score": risk.get("score"),
            "grade": risk.get("grade"),
            "reasons": risk.get("reasons") or [],
        },
        "tradeoffs": connection.get("tradeoffs") or [],
    }


def decision_frontier_options(data: dict[str, Any]) -> list[dict[str, Any]]:
    live = data.get("live_search") if isinstance(data.get("live_search"), dict) else {}
    frontier = (
        live.get("decision_frontier")
        if isinstance(live.get("decision_frontier"), dict)
        else {}
    )
    if not frontier and isinstance(data.get("decision_frontier"), dict):
        frontier = data["decision_frontier"]
    options = (
        frontier.get("options") if isinstance(frontier.get("options"), list) else []
    )
    return [
        option_from_decision_frontier_item(item)
        for item in options
        if isinstance(item, dict)
    ]


def option_from_decision_frontier_item(item: dict[str, Any]) -> dict[str, Any]:
    segments: list[dict[str, Any]] = []
    max_connections = int(item.get("connection_count") or 0)
    for journey in item.get("journeys") or []:
        if not isinstance(journey, dict):
            continue
        direction = str(journey.get("direction") or "")
        journey_segments = [
            segment
            for segment in journey.get("segments") or []
            if isinstance(segment, dict)
        ]
        max_connections = max(max_connections, max(0, len(journey_segments) - 1))
        for segment in journey_segments:
            segments.append(segment_summary(segment, direction))

    price_amount = item.get("price")
    currency = item.get("currency")
    risk_score = item.get("connection_risk_score")
    option = {
        "rank": item.get("rank"),
        "id": item.get("id"),
        "category": item.get("category") or "decision_frontier_option",
        "reason": ", ".join(str(value) for value in item.get("selection_reasons") or [])
        or None,
        "detail_status": item.get("detail_status")
        or ("full" if segments else "missing"),
        "ok": True,
        "price": {"amount": price_amount, "currency": currency},
        "price_text": price_label(price_amount, currency),
        "elapsed_min": item.get("elapsed_min")
        or item.get("duration_min")
        or item.get("total_duration_min"),
        "elapsed": minutes_label(
            item.get("elapsed_min")
            or item.get("duration_min")
            or item.get("total_duration_min")
        ),
        "carriers": sorted(
            {
                str(segment.get("carrier") or "").strip()
                for segment in segments
                if str(segment.get("carrier") or "").strip()
            }
        ),
        "risk": {
            "score": risk_score,
            "grade": "unknown",
            "reject": False,
            "top_reasons": [],
        },
        "validation_summary": {
            "ok": True,
            "max_connections_per_journey": max_connections,
            **(
                item.get("validation_summary")
                if isinstance(item.get("validation_summary"), dict)
                else {}
            ),
        },
        "stop_tier": (
            item.get("validation_summary", {}).get("stop_tier")
            if isinstance(item.get("validation_summary"), dict)
            else None
        ),
        "max_connections_per_journey": max_connections,
        "connections": [
            connection_summary(connection)
            for connection in item.get("connections") or []
            if isinstance(connection, dict)
        ],
        "segments": segments,
        "ticketing_note": "Verify final fare, baggage, ticket protection, and purchase-screen rules before booking.",
    }
    for key in (
        "source_type",
        "provider",
        "source_providers",
        "gateway",
        "gateways",
        "covers_requested_trip",
        "journey_scope",
        "price_basis",
        "ticketing_model",
        "self_transfer",
        "self_transfer_note",
        "self_transfer_source",
        "journey_pairing_model",
        "direction_pairing",
        "warnings",
        "selection_reasons",
        "evidence_sources",
    ):
        if key in item:
            option[key] = item.get(key)
    return option
