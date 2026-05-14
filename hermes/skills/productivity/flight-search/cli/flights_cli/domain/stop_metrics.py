from __future__ import annotations

from typing import Any

from .stop_policy import StopTier


def stop_tier(connection_count: int) -> StopTier:
    count = max(0, int(connection_count))
    if count == 0:
        return "T0_DIRECT"
    if count == 1:
        return "T1_ONE_STOP"
    if count == 2:
        return "T2_TWO_STOP"
    return "T3_THREE_PLUS"


def journey_connection_count(journey: dict[str, Any]) -> int:
    segments = journey.get("segments")
    if isinstance(segments, list):
        return max(0, len(segments) - 1)
    indexes = journey.get("segment_indexes")
    if isinstance(indexes, list):
        return max(0, len(indexes) - 1)
    return 0


def candidate_stop_metrics(candidate: dict[str, Any]) -> dict[str, Any]:
    journeys = candidate.get("journeys")
    if isinstance(journeys, list) and journeys:
        per_journey = [journey_connection_count(journey) for journey in journeys if isinstance(journey, dict)]
    else:
        segments = candidate.get("segments") if isinstance(candidate.get("segments"), list) else []
        per_journey = [max(0, len(segments) - 1)] if segments else [0]
    return stop_metrics_from_connection_counts(per_journey)


def stop_metrics_from_normalized(journeys: list[dict[str, Any]], segments: list[dict[str, Any]]) -> dict[str, Any]:
    if journeys:
        per_journey = [journey_connection_count(journey) for journey in journeys]
    else:
        per_journey = [max(0, len(segments) - 1)] if segments else [0]
    return stop_metrics_from_connection_counts(per_journey)


def stop_metrics_from_connection_counts(per_journey: list[int]) -> dict[str, Any]:
    counts = [max(0, int(count)) for count in per_journey] or [0]
    max_connections = max(counts)
    return {
        "max_connections_per_journey": max_connections,
        "connection_counts_by_journey": counts,
        "stop_tier": stop_tier(max_connections),
        "three_plus_connection_journey_count": sum(1 for count in counts if count >= 3),
    }


def offer_stop_metrics(offer: dict[str, Any]) -> dict[str, Any]:
    if offer.get("change_count") is not None:
        return stop_metrics_from_connection_counts([int(offer.get("change_count") or 0)])
    if offer.get("number_of_changes") is not None:
        return stop_metrics_from_connection_counts([int(offer.get("number_of_changes") or 0)])
    segments = offer.get("segments")
    if isinstance(segments, list):
        return stop_metrics_from_connection_counts([max(0, len(segments) - 1)])
    flights = offer.get("flights")
    if isinstance(flights, list):
        return stop_metrics_from_connection_counts([max(0, len(flights) - 1)])
    return stop_metrics_from_connection_counts([0])
