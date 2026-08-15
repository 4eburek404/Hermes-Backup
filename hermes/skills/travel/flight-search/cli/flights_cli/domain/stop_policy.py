from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


StopTier = Literal["T0_DIRECT", "T1_ONE_STOP", "T2_TWO_STOP", "T3_THREE_PLUS"]
_MAX_SUPPORTED_CONNECTIONS = 3


def _bounded_connections(value: int) -> int:
    return min(_MAX_SUPPORTED_CONNECTIONS, max(0, int(value)))


@dataclass(frozen=True)
class StopPolicy:
    name: str
    preferred_max_connections: int = 1
    tier2_max_connections: int = 2
    hard_max_connections: int = 2
    allow_two_stop_tier: bool = True
    suppress_three_plus: bool = True


BUSINESS_DEFAULT_STOP_POLICY = StopPolicy(name="business_default")


def resolve_stop_policy(
    *,
    max_connections: int | None,
    tier2_max_connections: int | None,
    name: str = "search_plan_resolved",
) -> StopPolicy:
    """Resolve request/plan stop limits once into the authoritative policy."""

    preferred = (
        BUSINESS_DEFAULT_STOP_POLICY.preferred_max_connections
        if max_connections is None
        else _bounded_connections(max_connections)
    )
    hard = (
        _bounded_connections(tier2_max_connections)
        if tier2_max_connections is not None
        else preferred
        if max_connections is not None
        else BUSINESS_DEFAULT_STOP_POLICY.hard_max_connections
    )
    return StopPolicy(
        name=name,
        preferred_max_connections=preferred,
        tier2_max_connections=hard,
        hard_max_connections=hard,
        allow_two_stop_tier=hard > preferred,
        suppress_three_plus=hard < 3,
    )


def connection_count_for_segments(segments: Any) -> int:
    if not isinstance(segments, list):
        return 0
    return max(0, len(segments) - 1)


def stop_metrics_from_segments(segments: Any) -> dict[str, Any]:
    if not isinstance(segments, list):
        return stop_metrics_from_connection_counts([0])
    directions = [
        str(segment.get("direction") or "").strip().lower()
        for segment in segments
        if isinstance(segment, dict)
    ]
    if (
        len(directions) == len(segments)
        and directions
        and all(direction in {"outbound", "return"} for direction in directions)
    ):
        per_journey = [
            connection_count_for_segments(
                [
                    segment
                    for segment in segments
                    if isinstance(segment, dict)
                    and str(segment.get("direction") or "").strip().lower() == direction
                ]
            )
            for direction in dict.fromkeys(directions)
        ]
        return stop_metrics_from_connection_counts(per_journey)
    return stop_metrics_from_connection_counts(
        [connection_count_for_segments(segments)]
    )


def stop_tier(connection_count: int) -> StopTier:
    count = max(0, int(connection_count))
    if count == 0:
        return "T0_DIRECT"
    if count == 1:
        return "T1_ONE_STOP"
    if count == 2:
        return "T2_TWO_STOP"
    return "T3_THREE_PLUS"


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
    for key in (
        "max_connections_per_journey",
        "connection_count",
        "change_count",
        "number_of_changes",
    ):
        if offer.get(key) is not None:
            return stop_metrics_from_connection_counts([int(offer.get(key) or 0)])
    journeys = offer.get("journeys")
    if isinstance(journeys, list):
        counts = [
            connection_count_for_segments(journey.get("segments"))
            for journey in journeys
            if isinstance(journey, dict) and isinstance(journey.get("segments"), list)
        ]
        if counts:
            return stop_metrics_from_connection_counts(counts)
    segments = offer.get("segments")
    if isinstance(segments, list):
        return stop_metrics_from_segments(segments)
    return stop_metrics_from_connection_counts([0])


def filter_provider_offers(
    offers: list[dict[str, Any]],
    *,
    policy: StopPolicy = BUSINESS_DEFAULT_STOP_POLICY,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Apply the authoritative hard stop cap before provider output limiting."""

    kept: list[dict[str, Any]] = []
    stats = {
        "raw_offer_count": len(offers),
        "suppressed_three_plus_count": 0,
    }
    for offer in offers:
        stop_metrics = offer_stop_metrics(offer)
        if (
            int(stop_metrics["max_connections_per_journey"])
            > policy.hard_max_connections
        ):
            stats["suppressed_three_plus_count"] += 1
            continue
        kept.append(offer)
    return kept, stats


def candidate_connection_counts(candidate: dict[str, Any]) -> list[int]:
    journeys = candidate.get("journeys")
    if isinstance(journeys, list):
        counts = [
            connection_count_for_segments(journey["segments"])
            for journey in journeys
            if isinstance(journey, dict) and isinstance(journey.get("segments"), list)
        ]
        if counts:
            return counts
    for key in ("max_connections_per_journey", "connection_count"):
        try:
            if candidate.get(key) is not None:
                return [max(0, int(candidate.get(key) or 0))]
        except (TypeError, ValueError):
            return [0]
    return [0]


def candidate_max_connections(candidate: dict[str, Any]) -> int:
    return max(candidate_connection_counts(candidate), default=0)


def candidate_connections_over_limit(
    candidate: dict[str, Any],
    *,
    default_limit: int,
    direction_limits: dict[str, int],
) -> int:
    default_cap = max(0, int(default_limit))
    journeys = candidate.get("journeys")
    if not isinstance(journeys, list) or not journeys:
        return candidate_max_connections(candidate) - default_cap

    over_limit = 0
    usable_journey = False
    for journey in journeys:
        if not isinstance(journey, dict) or not isinstance(
            journey.get("segments"), list
        ):
            continue
        usable_journey = True
        direction = str(journey.get("direction") or "").strip().lower()
        cap = direction_limits.get(direction, default_cap)
        over_limit = max(
            over_limit,
            connection_count_for_segments(journey["segments"]) - cap,
        )
    if usable_journey:
        return over_limit
    return candidate_max_connections(candidate) - default_cap


def select_best_stop_tier(
    candidates: list[dict[str, Any]],
    *,
    preferred_max_connections: int,
) -> list[dict[str, Any]]:
    """Apply the stop-tier suppression policy without ordering candidates."""

    if not candidates:
        return []
    preferred_cap = max(0, int(preferred_max_connections))
    preferred = [
        candidate
        for candidate in candidates
        if candidate_max_connections(candidate) <= preferred_cap
    ]
    if preferred:
        return preferred
    minimum_connections = min(candidate_max_connections(item) for item in candidates)
    return [
        candidate
        for candidate in candidates
        if candidate_max_connections(candidate) == minimum_connections
    ]


def stop_policy_status(
    options: list[dict[str, Any]],
    *,
    ranked_candidates: list[dict[str, Any]] | None = None,
    policy: StopPolicy = BUSINESS_DEFAULT_STOP_POLICY,
) -> dict[str, Any]:
    connection_counts = [candidate_max_connections(option) for option in options]
    used_two_stop_tier = (
        policy.tier2_max_connections > policy.preferred_max_connections
        and any(
            policy.preferred_max_connections < count <= policy.tier2_max_connections
            for count in connection_counts
        )
    )
    suppressed_count = sum(
        1
        for candidate in ranked_candidates or []
        if candidate_max_connections(candidate) > policy.hard_max_connections
    )
    return {
        "policy": policy.name,
        "max_reported_connections": (
            policy.tier2_max_connections
            if used_two_stop_tier
            else policy.preferred_max_connections
        ),
        "used_two_stop_tier": used_two_stop_tier,
        "three_plus_suppressed_count": suppressed_count,
        "garbage_options_hidden_from_answer": suppressed_count > 0,
    }


def stop_policy_payload(policy: StopPolicy) -> dict[str, Any]:
    return {
        "name": policy.name,
        "preferred_max_connections": policy.preferred_max_connections,
        "tier2_max_connections": policy.tier2_max_connections,
        "hard_max_connections": policy.hard_max_connections,
        "two_stop_allowed_only_if_no_preferred": policy.allow_two_stop_tier,
        "three_plus_reportable": not policy.suppress_three_plus,
    }


__all__ = [
    "BUSINESS_DEFAULT_STOP_POLICY",
    "StopPolicy",
    "StopTier",
    "candidate_connection_counts",
    "candidate_connections_over_limit",
    "candidate_max_connections",
    "connection_count_for_segments",
    "filter_provider_offers",
    "offer_stop_metrics",
    "resolve_stop_policy",
    "select_best_stop_tier",
    "stop_metrics_from_connection_counts",
    "stop_metrics_from_segments",
    "stop_policy_payload",
    "stop_policy_status",
    "stop_tier",
]
