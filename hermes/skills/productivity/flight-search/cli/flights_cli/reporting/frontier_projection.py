from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .catalog_rendering import FRONTIER_TICKETING_NOTE, minutes_label, price_label


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


@dataclass(frozen=True, slots=True)
class FrontierProjection:
    options: tuple[dict[str, Any], ...]
    decision_option_ids: tuple[str, ...]
    result_contract: dict[str, Any]


def project_decision_frontier(
    decision_frontier: dict[str, Any],
) -> FrontierProjection:
    raw_options = [
        item
        for item in decision_frontier.get("options") or []
        if isinstance(item, dict) and str(item.get("id") or "")
    ]
    projected = tuple(option_from_decision_frontier_item(item) for item in raw_options)
    coverage = (
        decision_frontier.get("coverage_summary")
        if isinstance(decision_frontier.get("coverage_summary"), dict)
        else {}
    )
    option_ids = tuple(str(item["id"]) for item in raw_options)
    return FrontierProjection(
        options=projected,
        decision_option_ids=option_ids,
        result_contract={
            "schema_version": "flight_decision_frontier.result.v1",
            "option_ids": list(option_ids),
            "coverage_summary": {
                key: int(coverage.get(key) or 0)
                for key in (
                    "candidate_count",
                    "acceptable_count",
                    "selected_count",
                    "rejected_count",
                )
            },
        },
    )


def option_from_decision_frontier_item(item: dict[str, Any]) -> dict[str, Any]:
    segments: list[dict[str, Any]] = []
    max_connections = max(
        0,
        int(
            item.get("max_connections_per_journey")
            if item.get("max_connections_per_journey") is not None
            else item.get("connection_count") or 0
        ),
    )
    for journey in item.get("journeys") or []:
        if not isinstance(journey, dict):
            continue
        direction = str(journey.get("direction") or "")
        journey_segments = [
            segment
            for segment in journey.get("segments") or []
            if isinstance(segment, dict)
        ]
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
        "stop_tier": item.get("stop_tier"),
        "max_connections_per_journey": max_connections,
        "connections": [
            connection_summary(connection)
            for connection in item.get("connections") or []
            if isinstance(connection, dict)
        ],
        "segments": segments,
        "ticketing_note": FRONTIER_TICKETING_NOTE,
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
        "connection_assessment",
        "ticket_protection",
        "journey_pairing_model",
        "direction_pairing",
        "warnings",
        "selection_reasons",
        "evidence_sources",
    ):
        if key in item:
            option[key] = item.get(key)
    return option


__all__ = [
    "FrontierProjection",
    "connection_summary",
    "option_from_decision_frontier_item",
    "project_decision_frontier",
    "segment_summary",
]
