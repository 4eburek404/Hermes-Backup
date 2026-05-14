from __future__ import annotations

from typing import Any

from .formatting import minutes_label, price_label


def segment_summary(segment: dict[str, Any], direction: str | None = None) -> dict[str, Any]:
    return {
        "direction": direction,
        "flight_number": segment.get("flight_number"),
        "carrier": segment.get("carrier") or segment.get("operating_carrier") or segment.get("marketing_carrier"),
        "marketing_carrier": segment.get("marketing_carrier"),
        "operating_carrier": segment.get("operating_carrier"),
        "origin": segment.get("origin"),
        "destination": segment.get("destination"),
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


def candidate_options_from_details(details: list[Any], limit: int = 5) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for detail in details[: max(0, limit)]:
        if not isinstance(detail, dict):
            continue
        ranked = detail.get("ranked") if isinstance(detail.get("ranked"), dict) else {}
        candidate = detail.get("candidate") if isinstance(detail.get("candidate"), dict) else {}
        segments = []
        for journey in candidate.get("journeys") or []:
            if not isinstance(journey, dict):
                continue
            direction = str(journey.get("direction") or "")
            for segment in journey.get("segments") or []:
                if isinstance(segment, dict):
                    segments.append(segment_summary(segment, direction))
        risk = ranked.get("risk") if isinstance(ranked.get("risk"), dict) else {}
        validation_summary = ranked.get("validation_summary") if isinstance(ranked.get("validation_summary"), dict) else {}
        detail_status = "full" if segments else "missing"
        options.append(
            {
                "rank": ranked.get("rank") or detail.get("rank"),
                "id": ranked.get("id") or candidate.get("id"),
                "category": detail.get("category"),
                "reason": detail.get("reason"),
                "detail_status": detail.get("detail_status") or detail_status,
                "ok": ranked.get("ok"),
                "price": {"amount": ranked.get("price"), "currency": ranked.get("currency")},
                "price_text": price_label(ranked.get("price"), ranked.get("currency")),
                "elapsed_min": ranked.get("elapsed_min"),
                "elapsed": minutes_label(ranked.get("elapsed_min")),
                "carriers": ranked.get("carriers") or [],
                "risk": {
                    "score": risk.get("score"),
                    "grade": risk.get("grade"),
                    "reject": risk.get("reject"),
                    "top_reasons": risk.get("top_reasons") or [],
                },
                "validation_summary": ranked.get("validation_summary"),
                "stop_tier": validation_summary.get("stop_tier"),
                "max_connections_per_journey": validation_summary.get("max_connections_per_journey"),
                "connections": [connection_summary(item) for item in ranked.get("connections") or [] if isinstance(item, dict)],
                "segments": segments,
                "ticketing_note": "Assume separate/self-transfer until the booking screen confirms protected through-ticketing and baggage.",
            }
        )
    return options


def ranked_candidate_options(data: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    details = data.get("ranked_candidates") if isinstance(data.get("ranked_candidates"), list) else []
    return candidate_options_from_details(details, limit=limit)


def priority_candidate_options(data: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    details = data.get("frontier_candidates") if isinstance(data.get("frontier_candidates"), list) else []
    return candidate_options_from_details(details, limit=limit)
