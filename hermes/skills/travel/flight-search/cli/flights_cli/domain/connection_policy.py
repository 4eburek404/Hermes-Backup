from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .time import minutes_between, parse_iso_datetime


DEFAULT_MIN_SAME_AIRPORT_CONNECTION_MIN = 120
DEFAULT_MIN_CROSS_AIRPORT_CONNECTION_MIN = 300
DEFAULT_MAX_LAYOVER_MIN = 24 * 60
DEFAULT_PREFERRED_LAYOVER_MAX_MIN = 6 * 60


@dataclass(frozen=True, slots=True)
class ConnectionPolicy:
    min_same_airport_min: int = DEFAULT_MIN_SAME_AIRPORT_CONNECTION_MIN
    min_cross_airport_min: int = DEFAULT_MIN_CROSS_AIRPORT_CONNECTION_MIN
    max_layover_min: int = DEFAULT_MAX_LAYOVER_MIN
    preferred_layover_max_min: int = DEFAULT_PREFERRED_LAYOVER_MAX_MIN

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "min_same_airport_min", max(0, int(self.min_same_airport_min))
        )
        object.__setattr__(
            self, "min_cross_airport_min", max(0, int(self.min_cross_airport_min))
        )
        object.__setattr__(self, "max_layover_min", max(0, int(self.max_layover_min)))
        object.__setattr__(
            self,
            "preferred_layover_max_min",
            max(0, int(self.preferred_layover_max_min)),
        )


def candidate_segment_groups(
    candidate: dict[str, Any],
) -> list[tuple[int, str, list[dict[str, Any]]]]:
    groups: list[tuple[int, str, list[dict[str, Any]]]] = []
    journeys = candidate.get("journeys")
    if isinstance(journeys, list):
        for journey_index, journey in enumerate(journeys):
            if not isinstance(journey, dict):
                continue
            raw_segments = journey.get("segments")
            if not isinstance(raw_segments, list):
                continue
            segments = [
                segment for segment in raw_segments if isinstance(segment, dict)
            ]
            if segments:
                groups.append(
                    (
                        journey_index,
                        str(journey.get("direction") or f"journey_{journey_index}"),
                        segments,
                    )
                )
    raw_segments = candidate.get("segments")
    if isinstance(raw_segments, list) and not groups:
        segments = [segment for segment in raw_segments if isinstance(segment, dict)]
        if segments:
            groups.append((0, "itinerary", segments))
    return groups


def normalized_direction(value: Any) -> str:
    direction = str(value or "").strip().lower()
    return direction if direction in {"outbound", "return"} else ""


def is_cross_ticket_boundary(
    candidate: dict[str, Any],
    previous: dict[str, Any],
    current: dict[str, Any],
) -> bool:
    ticketing_model = str(candidate.get("ticketing_model") or "")
    if ticketing_model in {
        "single_pnr",
        "single_pnr_proven",
        "single_ticket_proven",
        "protected_provider_order",
        "provider_order_unverified",
        "round_trip_single_ticket",
    }:
        return False
    previous_offer_id = str(previous.get("offer_id") or "")
    current_offer_id = str(current.get("offer_id") or "")
    if previous_offer_id and current_offer_id:
        return previous_offer_id != current_offer_id
    boundaries = {
        str(previous.get("ticketing_boundary") or ""),
        str(current.get("ticketing_boundary") or ""),
    }
    if any("separate_ticket" in boundary for boundary in boundaries):
        return True
    return str(candidate.get("source_type") or "") == "gateway_separate_ticket"


def missing_segment_time_violations(
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for journey_index, direction, segments in candidate_segment_groups(candidate):
        for segment_index, segment in enumerate(segments):
            departure_at = str(segment.get("departure_at") or "").strip()
            arrival_at = str(segment.get("arrival_at") or "").strip()
            departure_valid = parse_iso_datetime(departure_at) is not None
            arrival_valid = parse_iso_datetime(arrival_at) is not None
            if departure_valid and arrival_valid:
                continue
            reason = (
                "missing_segment_time"
                if not departure_at or not arrival_at
                else "invalid_segment_time"
            )
            violations.append(
                {
                    "reason": reason,
                    "message": (
                        "segment departure and arrival times are required"
                        if reason == "missing_segment_time"
                        else "segment departure and arrival times must be valid ISO datetimes"
                    ),
                    "journey_index": journey_index,
                    "journey_direction": direction,
                    "segment_index": segment_index,
                    "departure_at": segment.get("departure_at"),
                    "arrival_at": segment.get("arrival_at"),
                    "origin": segment.get("origin"),
                    "destination": segment.get("destination"),
                }
            )
    return violations


def chronology_violations(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for journey_index, direction, segments in candidate_segment_groups(candidate):
        for segment_index, segment in enumerate(segments):
            actual = minutes_between(
                str(segment.get("departure_at") or ""),
                str(segment.get("arrival_at") or ""),
            )
            if actual is None or actual >= 0:
                continue
            violations.append(
                {
                    "reason": "segment_arrival_before_departure",
                    "message": "segment arrival is earlier than its departure",
                    "journey_index": journey_index,
                    "journey_direction": direction,
                    "segment_index": segment_index,
                    "actual_min": actual,
                    "departure_at": segment.get("departure_at"),
                    "arrival_at": segment.get("arrival_at"),
                    "origin": segment.get("origin"),
                    "destination": segment.get("destination"),
                }
            )
        for segment_index, (previous, current) in enumerate(
            zip(segments, segments[1:])
        ):
            actual = minutes_between(
                str(previous.get("arrival_at") or ""),
                str(current.get("departure_at") or ""),
            )
            if actual is None or actual >= 0:
                continue
            violations.append(
                {
                    "reason": "invalid_time_order",
                    "message": "next departure is earlier than previous arrival",
                    "journey_index": journey_index,
                    "journey_direction": direction,
                    "between_segments": [segment_index, segment_index + 1],
                    "actual_min": actual,
                    "previous_arrival_at": previous.get("arrival_at"),
                    "next_departure_at": current.get("departure_at"),
                    "previous_destination": previous.get("destination"),
                    "next_origin": current.get("origin"),
                }
            )
    violations.extend(_cross_direction_chronology_violations(candidate))
    return violations


def _cross_direction_chronology_violations(
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    outbound_groups: list[tuple[int, list[dict[str, Any]]]] = []
    return_groups: list[tuple[int, list[dict[str, Any]]]] = []
    for journey_index, direction, segments in candidate_segment_groups(candidate):
        direction = normalized_direction(direction)
        if direction == "outbound":
            outbound_groups.append((journey_index, segments))
        elif direction == "return":
            return_groups.append((journey_index, segments))

    violations: list[dict[str, Any]] = []
    for outbound_index, outbound_segments in outbound_groups:
        if not outbound_segments:
            continue
        outbound_final = outbound_segments[-1]
        for return_index, return_segments in return_groups:
            if not return_segments:
                continue
            return_first = return_segments[0]
            actual = minutes_between(
                str(outbound_final.get("arrival_at") or ""),
                str(return_first.get("departure_at") or ""),
            )
            if actual is None or actual >= 0:
                continue
            violations.append(
                {
                    "reason": "return_departure_before_outbound_arrival",
                    "message": (
                        "return departure is earlier than final outbound arrival"
                    ),
                    "outbound_journey_index": outbound_index,
                    "return_journey_index": return_index,
                    "actual_min": actual,
                    "outbound_arrival_at": outbound_final.get("arrival_at"),
                    "return_departure_at": return_first.get("departure_at"),
                    "outbound_destination": outbound_final.get("destination"),
                    "return_origin": return_first.get("origin"),
                }
            )
    return violations


def airport_mismatch_violations(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for journey_index, direction, segments in candidate_segment_groups(candidate):
        for segment_index, (previous, current) in enumerate(
            zip(segments, segments[1:])
        ):
            previous_destination = str(previous.get("destination") or "").upper()
            next_origin = str(current.get("origin") or "").upper()
            if not previous_destination or not next_origin:
                continue
            if previous_destination == next_origin:
                continue
            violations.append(
                {
                    "reason": "airport_change_forbidden",
                    "message": "connections requiring an airport change are forbidden",
                    "journey_index": journey_index,
                    "journey_direction": direction,
                    "between_segments": [segment_index, segment_index + 1],
                    "previous_destination": previous_destination,
                    "next_origin": next_origin,
                }
            )
    return violations


def cross_ticket_mct_violations(
    candidate: dict[str, Any], policy: ConnectionPolicy
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for journey_index, direction, segments in candidate_segment_groups(candidate):
        for segment_index, (previous, current) in enumerate(
            zip(segments, segments[1:])
        ):
            if not is_cross_ticket_boundary(candidate, previous, current):
                continue
            actual = minutes_between(
                str(previous.get("arrival_at") or ""),
                str(current.get("departure_at") or ""),
            )
            if actual is None or actual < 0:
                continue
            previous_destination = str(previous.get("destination") or "").upper()
            next_origin = str(current.get("origin") or "").upper()
            same_airport = bool(
                previous_destination and previous_destination == next_origin
            )
            if not same_airport:
                # Cross-airport continuity is forbidden outright. The compatible
                # min_cross_airport_min field is reserved and must not create a
                # second acceptance mechanism.
                continue
            required = policy.min_same_airport_min
            if actual >= required:
                continue
            violations.append(
                {
                    "reason": "cross_ticket_mct_violation",
                    "message": "cross-ticket connection is shorter than required MCT",
                    "journey_index": journey_index,
                    "journey_direction": direction,
                    "between_segments": [segment_index, segment_index + 1],
                    "actual_min": actual,
                    "required_min": required,
                    "same_airport": same_airport,
                    "previous_arrival_at": previous.get("arrival_at"),
                    "next_departure_at": current.get("departure_at"),
                    "previous_destination": previous.get("destination"),
                    "next_origin": current.get("origin"),
                    "previous_offer_id": previous.get("offer_id"),
                    "next_offer_id": current.get("offer_id"),
                }
            )
    return violations


def connection_assessment(
    candidate: dict[str, Any],
    policy: ConnectionPolicy,
    *,
    airport_violations: list[dict[str, Any]],
    chronology_errors: list[dict[str, Any]],
    mct_errors: list[dict[str, Any]],
) -> dict[str, Any]:
    connections: list[dict[str, Any]] = []
    comfort_scores = {
        "comfortable": 0,
        "acceptable": 1,
        "long": 2,
        "tight": 3,
        "unknown": 4,
        "invalid": 5,
    }
    for journey_index, direction, segments in candidate_segment_groups(candidate):
        for segment_index, (previous, current) in enumerate(
            zip(segments, segments[1:])
        ):
            arrival_airport = str(previous.get("destination") or "").upper()
            departure_airport = str(current.get("origin") or "").upper()
            actual = minutes_between(
                str(previous.get("arrival_at") or ""),
                str(current.get("departure_at") or ""),
            )
            cross_ticket = is_cross_ticket_boundary(candidate, previous, current)
            same_airport = bool(
                arrival_airport and arrival_airport == departure_airport
            )
            required = policy.min_same_airport_min if same_airport else None
            status = "valid"
            if not arrival_airport or not departure_airport or actual is None:
                status = "unknown"
                comfort = "unknown"
            elif not same_airport or actual < 0:
                status = "invalid"
                comfort = "invalid"
            elif actual > policy.max_layover_min:
                status = "invalid"
                comfort = "invalid"
            elif cross_ticket and required is not None and actual < required:
                status = "invalid"
                comfort = "invalid"
            elif actual < required + 60:
                comfort = "tight"
            elif actual < required + 120:
                comfort = "acceptable"
            elif actual <= policy.preferred_layover_max_min:
                comfort = "comfortable"
            else:
                comfort = "long"
            connections.append(
                {
                    "journey_index": journey_index,
                    "journey_direction": direction,
                    "between_segments": [segment_index, segment_index + 1],
                    "airport": arrival_airport or None,
                    "same_airport": same_airport,
                    "actual_min": actual,
                    "required_min": required,
                    "margin_min": (
                        actual - required
                        if actual is not None and required is not None
                        else None
                    ),
                    "cross_ticket": cross_ticket,
                    "status": status,
                    "comfort": comfort,
                }
            )
    comfort = max(
        (entry["comfort"] for entry in connections),
        key=lambda value: comfort_scores[value],
        default="comfortable",
    )
    status = (
        "invalid"
        if comfort == "invalid" or airport_violations or chronology_errors or mct_errors
        else "unknown"
        if comfort == "unknown"
        else "valid"
    )
    return {"status": status, "comfort": comfort, "connections": connections}


__all__ = [
    "ConnectionPolicy",
    "DEFAULT_MAX_LAYOVER_MIN",
    "DEFAULT_MIN_CROSS_AIRPORT_CONNECTION_MIN",
    "DEFAULT_MIN_SAME_AIRPORT_CONNECTION_MIN",
    "DEFAULT_PREFERRED_LAYOVER_MAX_MIN",
    "airport_mismatch_violations",
    "candidate_segment_groups",
    "chronology_violations",
    "connection_assessment",
    "cross_ticket_mct_violations",
    "is_cross_ticket_boundary",
    "missing_segment_time_violations",
    "normalized_direction",
]
