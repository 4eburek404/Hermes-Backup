from __future__ import annotations

import argparse
from typing import Any

from ..config import LEISURE_HUBS, LOW_COST_CARRIERS, RISK_PROFILES
from ..domain.airports import airport_group
from ..domain.carriers import segment_carriers
from ..domain.normalize import clamp_score, is_reject_score, normalize_iata, normalize_profile, normalize_transfer, normalize_transfers, price_value, risk_grade
from ..domain.stop_metrics import stop_metrics_from_normalized
from ..domain.time import is_night_time, minutes_between, parse_iso_datetime, validation_elapsed_minutes
from ..errors import CliError

def connection_rule(
    arrival_airport: str,
    departure_airport: str,
    ticketing: str,
    min_same_airport: int,
    min_cross_airport: int,
    actual_minutes: int | None = None,
) -> dict[str, Any]:
    arrival = arrival_airport.upper()
    departure = departure_airport.upper()
    same_airport = arrival == departure
    arrival_group = airport_group(arrival)
    departure_group = airport_group(departure)
    same_group = bool(arrival_group and departure_group and arrival_group["key"] == departure_group["key"])

    if ticketing == "single":
        required = 60 if same_airport else min_cross_airport
    elif same_airport:
        required = min_same_airport
    elif same_group:
        required = min_cross_airport
    else:
        required = min_cross_airport

    severity = "ok"
    status = "compatible"
    notes: list[str] = []
    if not same_airport:
        if same_group:
            status = "ground_transfer_required"
            severity = "warn"
            notes.append(f"{arrival} to {departure} requires airport change inside {arrival_group['label']}.")
        else:
            status = "airport_mismatch"
            severity = "error"
            notes.append(f"Arrival airport {arrival} does not match next departure airport {departure}.")

    if actual_minutes is not None:
        if actual_minutes < 0:
            status = "invalid_time_order"
            severity = "error"
            notes.append("Next departure is before previous arrival.")
        elif actual_minutes < required:
            severity = "error"
            status = "too_short"
            notes.append(f"Connection is {actual_minutes} min, below required {required} min.")

    return {
        "arrival_airport": arrival,
        "departure_airport": departure,
        "same_airport": same_airport,
        "same_multi_airport_system": same_group,
        "ticketing": ticketing,
        "required_min": required,
        "actual_min": actual_minutes,
        "status": status,
        "severity": severity,
        "notes": notes,
    }


def connection_risk_points(
    rule: dict[str, Any],
    prev_segment: dict[str, Any],
    next_segment: dict[str, Any],
    profile: str,
) -> dict[str, Any]:
    config = RISK_PROFILES[profile]
    score = 0
    reasons: list[dict[str, Any]] = []
    actual = rule.get("actual_min")
    required = int(rule.get("required_min") or 0)

    def add(code: str, points: int, message: str) -> None:
        nonlocal score
        if points <= 0:
            return
        score += points
        reasons.append({"code": code, "points": points, "message": message})

    if rule["status"] == "invalid_time_order":
        add("invalid_time_order", 100, "Next departure is before previous arrival.")
    elif rule["status"] == "airport_mismatch" and not rule["same_multi_airport_system"]:
        add("airport_mismatch", 92, "Connection changes to an unrelated airport.")
    elif actual is None:
        add("missing_connection_time", config["missing_time_penalty"], "Connection time is unknown.")
    elif actual < required:
        short_by = required - actual
        add(
            "too_short_connection",
            min(100, int(config["too_short_penalty"]) + min(18, short_by // 15)),
            f"Connection is {actual} min, below required {required} min.",
        )
    elif not rule["same_airport"]:
        base = int(config["cross_airport_base"])
        if rule["same_multi_airport_system"]:
            add("cross_airport_transfer", base, "Ground transfer between airports is required.")
        else:
            add("airport_change", max(base, 55), "Arrival airport differs from next departure airport.")

    if actual is not None and actual >= required and rule["same_airport"]:
        ideal_min = int(config["ideal_same_min"])
        if actual < ideal_min:
            add("below_ideal_buffer", min(18, max(3, (ideal_min - actual) // 10)), "Connection is valid but below ideal buffer.")

    return {
        "score": clamp_score(score),
        "grade": risk_grade(clamp_score(score)),
        "reasons": reasons,
    }


def connection_tradeoffs(rule: dict[str, Any], prev_segment: dict[str, Any], next_segment: dict[str, Any]) -> list[dict[str, Any]]:
    actual = rule.get("actual_min")
    if not isinstance(actual, int) or actual < 0:
        return []
    arrival = str(prev_segment.get("arrival_at") or "")
    departure = str(next_segment.get("departure_at") or "")
    arrival_airport = str(rule.get("arrival_airport") or "")
    departure_airport = str(rule.get("departure_airport") or "")
    parsed_arrival = parse_iso_datetime(arrival)
    parsed_departure = parse_iso_datetime(departure)
    crosses_calendar_date = bool(parsed_arrival and parsed_departure and parsed_departure.date() > parsed_arrival.date())
    touches_night = is_night_time(arrival) or is_night_time(departure)

    tradeoffs: list[dict[str, Any]] = []
    if actual >= 8 * 60:
        tradeoffs.append(
            {
                "code": "long_wait",
                "actual_min": actual,
                "arrival_airport": arrival_airport,
                "departure_airport": departure_airport,
                "message": f"Long wait of {actual // 60}h{actual % 60:02d}; show as a trade-off, not an automatic risk penalty.",
            }
        )
    if actual >= 6 * 60 and (crosses_calendar_date or touches_night):
        tradeoffs.append(
            {
                "code": "overnight_wait",
                "actual_min": actual,
                "arrival_airport": arrival_airport,
                "departure_airport": departure_airport,
                "message": "Overnight wait; show explicitly and compare alternatives, but do not demote solely for overnight timing.",
            }
        )
    return tradeoffs


def segment_risk_points(segment: dict[str, Any], profile: str) -> dict[str, Any]:
    config = RISK_PROFILES[profile]
    score = 0
    reasons: list[dict[str, Any]] = []

    def add(code: str, points: int, message: str) -> None:
        nonlocal score
        if points <= 0:
            return
        score += points
        reasons.append({"code": code, "points": points, "message": message})

    origin = str(segment.get("origin") or "").upper()
    destination = str(segment.get("destination") or "").upper()
    for airport in (origin, destination):
        if airport in LEISURE_HUBS:
            add("leisure_hub", int(config["leisure_hub_penalty"]), f"{airport} is a leisure/charter-heavy hub.")
        airport_penalty = dict(config["unpreferred_airport_penalty"]).get(airport, 0)
        add("profile_airport_penalty", int(airport_penalty), f"{airport} is less preferred for profile {profile}.")

    lowcost = sorted(segment_carriers(segment) & LOW_COST_CARRIERS)
    if lowcost:
        add("lowcost_carrier", int(config["lowcost_penalty"]), f"Low-cost/leisure carrier signal: {', '.join(lowcost)}.")

    transfer_after = segment.get("transfer_after")
    if isinstance(transfer_after, dict):
        transfer_at = str(transfer_after.get("at") or destination or "").upper()
        if transfer_after.get("visa_required"):
            add(
                "visa_required_transfer",
                int(config["visa_transfer_penalty"]),
                f"Internal transfer at {transfer_at} reports visa_required=true.",
            )
        if transfer_after.get("night_transfer"):
            add(
                "api_night_transfer",
                int(config["api_night_transfer_penalty"]),
                f"Internal transfer at {transfer_at} is marked as a night transfer by provider.",
            )
        duration_seconds = transfer_after.get("duration_seconds")
        if isinstance(duration_seconds, int) and duration_seconds >= 8 * 3600:
            hours = duration_seconds // 3600
            add(
                "long_internal_transfer",
                int(config["long_internal_transfer_penalty"]),
                f"Internal transfer at {transfer_at} is about {hours}h.",
            )

    return {
        "score": clamp_score(score),
        "grade": risk_grade(clamp_score(score)),
        "reasons": reasons,
    }


def score_itinerary(validation: dict[str, Any], source: dict[str, Any], profile: str) -> dict[str, Any]:
    segments = validation["segments"]
    connection_scores = []
    segment_scores = []
    components: list[dict[str, Any]] = []
    total = 0

    for connection in validation["connections"]:
        prev_index, next_index = connection["between_segments"]
        risk = connection_risk_points(connection, segments[prev_index], segments[next_index], profile)
        tradeoffs = connection_tradeoffs(connection, segments[prev_index], segments[next_index])
        connection_scores.append({**connection, "risk": risk, "tradeoffs": tradeoffs})
        total += risk["score"]
        for reason in risk["reasons"]:
            components.append({"scope": "connection", "between_segments": [prev_index, next_index], **reason})

    for segment in segments:
        risk = segment_risk_points(segment, profile)
        segment_scores.append({"index": segment["index"], "origin": segment["origin"], "destination": segment["destination"], "risk": risk})
        total += risk["score"]
        for reason in risk["reasons"]:
            components.append({"scope": "segment", "segment": segment["index"], **reason})

    if validation["violations"]:
        total = max(total, 86)

    score = clamp_score(total)
    price = price_value(source)
    elapsed = validation_elapsed_minutes(validation)
    return {
        "profile": profile,
        "profile_description": RISK_PROFILES[profile]["description"],
        "score": score,
        "grade": risk_grade(score),
        "reject": is_reject_score(score),
        "price": price,
        "elapsed_min": elapsed,
        "connection_scores": connection_scores,
        "segment_scores": segment_scores,
        "components": components,
        "rank_key": rank_key(profile, score, price, elapsed),
    }


def normalize_input_segments(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized_segments: list[dict[str, Any]] = []
    journeys_out: list[dict[str, Any]] = []

    def normalize_segment(seg: dict[str, Any], journey_index: int, direction: str | None) -> dict[str, Any]:
        index = len(normalized_segments)
        origin = normalize_iata(str(seg.get("origin") or ""), f"segments[{index}].origin")
        destination = normalize_iata(str(seg.get("destination") or ""), f"segments[{index}].destination")
        normalized = {
            "index": index,
            "journey_index": journey_index,
            "direction": direction,
            "origin": origin,
            "destination": destination,
            "departure_at": str(seg.get("departure_at") or ""),
            "arrival_at": str(seg.get("arrival_at") or ""),
            "flight_number": seg.get("flight_number"),
            "carrier": seg.get("carrier"),
            "airline": seg.get("airline"),
            "operating_carrier": seg.get("operating_carrier"),
            "main_airline": seg.get("main_airline"),
        }
        transfer_after = normalize_transfer(seg.get("transfer_after"))
        if transfer_after is not None:
            normalized["transfer_after"] = transfer_after
        transfers = normalize_transfers(seg.get("transfers"))
        if transfers:
            normalized["transfers"] = transfers
        normalized_segments.append(normalized)
        return normalized

    raw_journeys = data.get("journeys")
    if isinstance(raw_journeys, list) and raw_journeys:
        for journey_index, journey in enumerate(raw_journeys):
            if not isinstance(journey, dict):
                raise CliError(f"journeys[{journey_index}] must be an object", error_type="validation_error")
            raw_segments = journey.get("segments")
            if not isinstance(raw_segments, list) or not raw_segments:
                raise CliError(f"journeys[{journey_index}].segments must be a non-empty list", error_type="validation_error")
            direction = str(journey.get("direction") or journey.get("name") or f"journey-{journey_index + 1}")
            indexes = []
            for seg in raw_segments:
                if not isinstance(seg, dict):
                    raise CliError(f"journeys[{journey_index}].segments must contain objects", error_type="validation_error")
                indexes.append(normalize_segment(seg, journey_index, direction)["index"])
            journeys_out.append({"index": journey_index, "direction": direction, "segment_indexes": indexes})
    else:
        raw_segments = data.get("segments")
        if not isinstance(raw_segments, list) or len(raw_segments) < 2:
            raise CliError("input JSON must contain at least two segments", error_type="validation_error")
        indexes = []
        for seg in raw_segments:
            if not isinstance(seg, dict):
                raise CliError("segments must contain objects", error_type="validation_error")
            indexes.append(normalize_segment(seg, 0, "itinerary")["index"])
        journeys_out.append({"index": 0, "direction": "itinerary", "segment_indexes": indexes})

    return normalized_segments, journeys_out


def rank_key(profile: str, score: int, price: int | None, elapsed: int | None) -> list[int]:
    values = {
        "reject": 1 if is_reject_score(score) else 0,
        "risk": score,
        "price": price if price is not None else 10**12,
        "elapsed": elapsed if elapsed is not None else 10**9,
    }
    return [values[name] for name in RISK_PROFILES[profile]["rank_order"]]


def validate_itinerary(data: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    ticketing = str(data.get("ticketing") or args.ticketing or "separate")
    profile = normalize_profile(str(data.get("profile") or getattr(args, "profile", "balanced")))
    normalized_segments, journeys = normalize_input_segments(data)

    connections: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    segments_by_index = {segment["index"]: segment for segment in normalized_segments}
    for journey in journeys:
        journey_segments = [segments_by_index[index] for index in journey["segment_indexes"] if index in segments_by_index]
        for prev, nxt in zip(journey_segments, journey_segments[1:]):
            actual = minutes_between(prev["arrival_at"], nxt["departure_at"])
            rule = connection_rule(
                prev["destination"],
                nxt["origin"],
                ticketing,
                args.min_same_airport_min,
                args.min_cross_airport_min,
                actual,
            )
            rule["journey_index"] = journey["index"]
            rule["journey_direction"] = journey["direction"]
            rule["between_segments"] = [prev["index"], nxt["index"]]
            connections.append(rule)
            if rule["severity"] == "error":
                violations.append(rule)

    stop_metrics = stop_metrics_from_normalized(journeys, normalized_segments)
    result = {
        "ok": not violations,
        "ticketing": ticketing,
        "profile": profile,
        "journeys": journeys,
        "segments": normalized_segments,
        "connections": connections,
        "violations": violations,
        "summary": {
            "segment_count": len(normalized_segments),
            "connection_count": len(connections),
            "violation_count": len(violations),
            **stop_metrics,
        },
    }
    result["risk"] = score_itinerary(result, data, profile)
    result["connections"] = result["risk"]["connection_scores"]
    return result
