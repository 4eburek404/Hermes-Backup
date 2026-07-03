from __future__ import annotations

from typing import Any

from .formatting import minutes_label, price_label


def detail_stop_policy_selection(details: list[Any], limit: int = 5) -> dict[str, Any]:
    selected_two_stop_count = 0
    for detail in details[: max(0, limit)]:
        if not isinstance(detail, dict):
            continue
        ranked = detail.get("ranked") if isinstance(detail.get("ranked"), dict) else {}
        validation_summary = (
            ranked.get("validation_summary")
            if isinstance(ranked.get("validation_summary"), dict)
            else {}
        )
        try:
            max_connections = int(
                validation_summary.get("max_connections_per_journey") or 0
            )
        except (TypeError, ValueError):
            max_connections = 0
        if validation_summary.get("stop_tier") == "T2_TWO_STOP" or max_connections == 2:
            selected_two_stop_count += 1
    return {
        "source": "candidate_details",
        "selected_two_stop_option_count": selected_two_stop_count,
        "used_two_stop_tier": selected_two_stop_count > 0,
        "used_tier2_two_stop": selected_two_stop_count > 0,
    }


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


def candidate_options_from_details(
    details: list[Any], limit: int = 5
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for detail in details[: max(0, limit)]:
        if not isinstance(detail, dict):
            continue
        ranked = detail.get("ranked") if isinstance(detail.get("ranked"), dict) else {}
        candidate = (
            detail.get("candidate") if isinstance(detail.get("candidate"), dict) else {}
        )
        segments = []
        for journey in candidate.get("journeys") or []:
            if not isinstance(journey, dict):
                continue
            direction = str(journey.get("direction") or "")
            for segment in journey.get("segments") or []:
                if isinstance(segment, dict):
                    segments.append(segment_summary(segment, direction))
        risk = ranked.get("risk") if isinstance(ranked.get("risk"), dict) else {}
        validation_summary = (
            ranked.get("validation_summary")
            if isinstance(ranked.get("validation_summary"), dict)
            else {}
        )
        detail_status = "full" if segments else "missing"
        option = {
            "rank": ranked.get("rank") or detail.get("rank"),
            "id": ranked.get("id") or candidate.get("id"),
            "category": detail.get("category"),
            "reason": detail.get("reason"),
            "detail_status": detail.get("detail_status") or detail_status,
            "ok": ranked.get("ok"),
            "price": {
                "amount": ranked.get("price"),
                "currency": ranked.get("currency"),
            },
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
            "max_connections_per_journey": validation_summary.get(
                "max_connections_per_journey"
            ),
            "connections": [
                connection_summary(item)
                for item in ranked.get("connections") or []
                if isinstance(item, dict)
            ],
            "segments": segments,
            "ticketing_note": "Assume separate/self-transfer until the booking screen confirms protected through-ticketing and baggage.",
        }
        for key in (
            "source_type",
            "provider",
            "source_providers",
            "gateway",
            "covers_requested_trip",
            "journey_scope",
            "price_basis",
            "ticketing_model",
            "warnings",
            "selection_reasons",
            "evidence_sources",
        ):
            if key in candidate:
                option[key] = candidate.get(key)
        options.append(option)
    return options


def ranked_candidate_options(
    data: dict[str, Any], limit: int = 5
) -> list[dict[str, Any]]:
    details = (
        data.get("ranked_candidates")
        if isinstance(data.get("ranked_candidates"), list)
        else []
    )
    return candidate_options_from_details(details, limit=limit)


def priority_candidate_options(
    data: dict[str, Any], limit: int = 5
) -> list[dict[str, Any]]:
    details = (
        data.get("frontier_candidates")
        if isinstance(data.get("frontier_candidates"), list)
        else []
    )
    return candidate_options_from_details(details, limit=limit)


def decision_frontier_options(
    data: dict[str, Any], limit: int = 10
) -> list[dict[str, Any]]:
    live = data.get("live_search") if isinstance(data.get("live_search"), dict) else {}
    frontier = (
        live.get("decision_frontier")
        if isinstance(live.get("decision_frontier"), dict)
        else {}
    )
    if not frontier and isinstance(data.get("decision_frontier"), dict):
        frontier = data["decision_frontier"]
    options = frontier.get("options") if isinstance(frontier.get("options"), list) else []
    return [
        option_from_decision_frontier_item(item)
        for item in options[: max(0, limit)]
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
            segment for segment in journey.get("segments") or [] if isinstance(segment, dict)
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
        "detail_status": item.get("detail_status") or ("full" if segments else "missing"),
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
        "journey_pairing_model",
        "direction_pairing",
        "warnings",
        "selection_reasons",
        "evidence_sources",
    ):
        if key in item:
            option[key] = item.get(key)
    return option
