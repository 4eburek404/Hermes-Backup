from __future__ import annotations

from .stop_policy import StopTier


def journey_connection_count(journey: dict) -> int:
    segments = journey.get("segments")
    if isinstance(segments, list):
        return max(0, len(segments) - 1)
    return 0


def stop_tier(connection_count: int) -> StopTier:
    if connection_count <= 0:
        return "T0_DIRECT"
    if connection_count == 1:
        return "T1_ONE_STOP"
    if connection_count == 2:
        return "T2_TWO_STOP"
    return "T3_THREE_PLUS"


def candidate_stop_metrics(candidate: dict) -> dict:
    journeys = candidate.get("journeys") if isinstance(candidate.get("journeys"), list) else []
    connection_counts_by_journey: list[int] = []
    for journey in journeys:
        if isinstance(journey, dict):
            connection_counts_by_journey.append(journey_connection_count(journey))
    if not connection_counts_by_journey:
        connection_counts_by_journey = [0]
    max_connections_per_journey = max(connection_counts_by_journey)
    return {
        "connection_counts_by_journey": connection_counts_by_journey,
        "max_connections_per_journey": max_connections_per_journey,
        "stop_tier": stop_tier(max_connections_per_journey),
        "three_plus_connection_journey_count": sum(1 for value in connection_counts_by_journey if value >= 3),
        "segment_count": sum(
            len(journey.get("segments") or [])
            for journey in journeys
            if isinstance(journey, dict)
        ),
    }
