from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..domain.connection_policy import (
    DEFAULT_MAX_LAYOVER_MIN,
    DEFAULT_MIN_CROSS_AIRPORT_CONNECTION_MIN,
    DEFAULT_MIN_SAME_AIRPORT_CONNECTION_MIN,
    DEFAULT_PREFERRED_LAYOVER_MAX_MIN,
    candidate_segment_groups as _candidate_segment_groups,
)
from ..domain.normalize import numeric_or_none
from ..domain.stop_policy import BUSINESS_DEFAULT_STOP_POLICY
from ..domain.time import minutes_between
from ..domain.vocabulary import RouteFamily
from .candidate_outcome import validate_candidate_envelope


MIXED_CANDIDATE_RANKING_SCHEMA_VERSION = "flight_mixed_candidate_ranking.v1"
UNKNOWN_RANK_NUMERIC = 999_999_999
MATERIAL_ELAPSED_DELTA_MIN = 60


def rank_mixed_candidates(
    candidate_envelope: dict[str, Any],
    *,
    max_connections_per_journey: int = (
        BUSINESS_DEFAULT_STOP_POLICY.hard_max_connections
    ),
    max_connections_per_direction: dict[str, int] | None = None,
    preferred_connections_per_journey: int = (
        BUSINESS_DEFAULT_STOP_POLICY.preferred_max_connections
    ),
    min_same_airport_connection_min: int = DEFAULT_MIN_SAME_AIRPORT_CONNECTION_MIN,
    min_cross_airport_connection_min: int = DEFAULT_MIN_CROSS_AIRPORT_CONNECTION_MIN,
    max_layover_min: int = DEFAULT_MAX_LAYOVER_MIN,
    preferred_layover_max_min: int = DEFAULT_PREFERRED_LAYOVER_MAX_MIN,
) -> dict[str, Any]:
    """Compatibility entry point that composes validation then scoring."""

    validated = validate_candidate_envelope(
        candidate_envelope,
        max_connections_per_journey=max_connections_per_journey,
        max_connections_per_direction=max_connections_per_direction,
        min_same_airport_connection_min=min_same_airport_connection_min,
        min_cross_airport_connection_min=min_cross_airport_connection_min,
        max_layover_min=max_layover_min,
        preferred_layover_max_min=preferred_layover_max_min,
    )
    return score_validated_candidates(
        validated,
        preferred_connections_per_journey=preferred_connections_per_journey,
    )


def score_validated_candidates(
    validation_envelope: dict[str, Any],
    *,
    preferred_connections_per_journey: int = (
        BUSINESS_DEFAULT_STOP_POLICY.preferred_max_connections
    ),
) -> dict[str, Any]:
    """Order candidates using only facts produced by candidate validation."""

    candidates = [
        deepcopy(candidate)
        for candidate in validation_envelope.get("candidates") or []
        if isinstance(candidate, dict)
    ]
    evaluated = [
        _candidate_with_rank_diagnostics(
            candidate,
            preferred_connections_per_journey=preferred_connections_per_journey,
        )
        for candidate in candidates
    ]
    ranked = _quality_ranked_candidates(evaluated)
    for index, candidate in enumerate(ranked, start=1):
        candidate["rank"] = index
    return {
        "schema_version": MIXED_CANDIDATE_RANKING_SCHEMA_VERSION,
        "ranked_candidates": ranked,
        "rejected": deepcopy(validation_envelope.get("rejected") or []),
        "coverage": {
            "candidate_count": len(ranked),
            "rejected_count": len(validation_envelope.get("rejected") or []),
            "max_connections_per_journey": int(
                (validation_envelope.get("coverage") or {}).get(
                    "max_connections_per_journey", 0
                )
            ),
            "max_connections_per_direction": dict(
                (validation_envelope.get("coverage") or {}).get(
                    "max_connections_per_direction", {}
                )
            ),
            "preferred_connections_per_journey": max(
                0, int(preferred_connections_per_journey)
            ),
            "mct_settings": dict(
                (validation_envelope.get("coverage") or {}).get("mct_settings", {})
            ),
            "source_types": sorted(
                {
                    str(candidate.get("source_type"))
                    for candidate in ranked
                    if candidate.get("source_type")
                }
            ),
        },
    }


def _candidate_with_rank_diagnostics(
    candidate: dict[str, Any],
    *,
    preferred_connections_per_journey: int,
) -> dict[str, Any]:
    item = deepcopy(candidate)
    validation = candidate.get("validation")
    if not isinstance(validation, dict):
        raise ValueError("candidate scoring requires validated candidates")
    blocking_reasons = {
        str(reason) for reason in validation.get("blocking_reasons") or []
    }
    max_connections = int(candidate.get("max_connections_per_journey") or 0)
    connection_assessment = candidate.get("connection_assessment")
    if not isinstance(connection_assessment, dict):
        connection_assessment = {}
    ticket_protection = candidate.get("ticket_protection")
    if not isinstance(ticket_protection, dict):
        ticket_protection = {
            "status": "unknown",
            "source": "provider_evidence_incomplete",
            "reasons": ["ticket_protection_unproven"],
        }
    rank_components = {
        "not_covers_requested_trip": int(
            "does_not_cover_requested_trip" in blocking_reasons
        ),
        "rejected_or_impossible_connection": int(
            bool(
                blocking_reasons
                & {
                    "rejected_or_impossible_connection",
                    "invalid_time_order",
                    "return_departure_before_outbound_arrival",
                    "airport_change_forbidden",
                    "cross_ticket_mct_violation",
                }
            )
        ),
        "max_connections_per_journey": int(
            validation.get("connections_over_limit") or 0
        ),
        "preferred_connections_per_journey": max(
            0,
            max_connections - max(0, int(preferred_connections_per_journey)),
        ),
        "ticketing_risk_tier": {
            "protected": 0,
            "unknown": 1,
            "unprotected": 2,
        }[str(ticket_protection["status"])],
        "connection_risk_score": _connection_risk_score(
            candidate, connection_assessment
        ),
        "source_confidence_penalty": _source_confidence_penalty(candidate),
        "price": _price_for_rank(candidate),
        "elapsed_time": _elapsed_time_for_rank(candidate),
    }
    item["rank_components"] = rank_components
    item["rank_key"] = [
        rank_components["not_covers_requested_trip"],
        rank_components["rejected_or_impossible_connection"],
        rank_components["max_connections_per_journey"],
        rank_components["connection_risk_score"],
        rank_components["preferred_connections_per_journey"],
        rank_components["elapsed_time"],
        rank_components["price"],
        rank_components["ticketing_risk_tier"],
        rank_components["source_confidence_penalty"],
    ]
    item["ranking_reasons"] = _ranking_reasons(
        item,
        rank_components,
        validation_reasons=list(validation.get("blocking_reasons") or []),
    )
    return item


def _connection_risk_score(
    candidate: dict[str, Any], assessment: dict[str, Any] | None = None
) -> int | float:
    payload = assessment if isinstance(assessment, dict) else {}
    return {
        "comfortable": 0,
        "acceptable": 10,
        "long": 15,
        "tight": 20,
        "unknown": 30,
        "invalid": 100,
    }.get(str(payload.get("comfort") or "unknown"), 30)


def _source_confidence_penalty(candidate: dict[str, Any]) -> int:
    source_type = str(candidate.get("source_type") or "")
    if source_type in {"provider_full_route", RouteFamily.DIRECT_INVENTORY}:
        return 0
    return 50


def _price_for_rank(candidate: dict[str, Any]) -> int | float:
    amount = numeric_or_none(candidate.get("price"))
    return amount if amount is not None else UNKNOWN_RANK_NUMERIC


def _elapsed_time_for_rank(candidate: dict[str, Any]) -> int | float:
    for key in ("elapsed_min", "elapsed_time", "duration_min", "total_duration_min"):
        amount = numeric_or_none(candidate.get(key))
        if amount is not None:
            return amount
    elapsed = 0
    found = False
    for _, _direction, segments in _candidate_segment_groups(candidate):
        if not segments:
            continue
        minutes = minutes_between(
            str(segments[0].get("departure_at") or ""),
            str(segments[-1].get("arrival_at") or ""),
        )
        if minutes is None or minutes < 0:
            continue
        elapsed += minutes
        found = True
    if found:
        return elapsed
    return UNKNOWN_RANK_NUMERIC


def _ranking_reasons(
    candidate: dict[str, Any],
    rank_components: dict[str, Any],
    *,
    validation_reasons: list[str],
) -> list[str]:
    reasons = list(dict.fromkeys(str(reason) for reason in validation_reasons))
    if rank_components["rejected_or_impossible_connection"]:
        reasons.insert(0, "rejected_or_impossible_connection")
    if rank_components.get("preferred_connections_per_journey"):
        reasons.append("exceeds_preferred_connections_per_journey")
    if "provider_ticketing_protection_unverified" in set(
        candidate.get("warnings") or []
    ):
        reasons.append("provider_ticketing_protection_unverified")
    return reasons


def _quality_ranked_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    fastest_by_quality: dict[tuple[int, ...], int | float] = {}
    for candidate in candidates:
        prefix = _quality_rank_prefix(candidate)
        elapsed = rank_component(candidate, "elapsed_time")
        fastest_by_quality[prefix] = min(
            fastest_by_quality.get(prefix, UNKNOWN_RANK_NUMERIC),
            elapsed,
        )

    for candidate in candidates:
        components = candidate.get("rank_components")
        if not isinstance(components, dict):
            components = {}
            candidate["rank_components"] = components
        prefix = _quality_rank_prefix(candidate)
        elapsed = rank_component(candidate, "elapsed_time")
        fastest = fastest_by_quality.get(prefix, elapsed)
        elapsed_band = (
            0
            if elapsed >= UNKNOWN_RANK_NUMERIC or fastest >= UNKNOWN_RANK_NUMERIC
            else max(0, int(elapsed - fastest) // MATERIAL_ELAPSED_DELTA_MIN)
        )
        components["elapsed_time_band"] = elapsed_band
        candidate["rank_key"] = [
            *prefix,
            elapsed_band,
            rank_component(candidate, "ticketing_risk_tier"),
            rank_component(candidate, "source_confidence_penalty"),
            rank_component(candidate, "price"),
            elapsed,
        ]

    return sorted(
        candidates,
        key=lambda candidate: (
            tuple(candidate.get("rank_key") or []),
            str(candidate.get("id") or ""),
        ),
    )


def _quality_rank_prefix(candidate: dict[str, Any]) -> tuple[int, ...]:
    components = candidate.get("rank_components")
    payload = components if isinstance(components, dict) else {}
    return (
        int(payload.get("not_covers_requested_trip") or 0),
        int(payload.get("rejected_or_impossible_connection") or 0),
        int(payload.get("max_connections_per_journey") or 0),
        int(payload.get("preferred_connections_per_journey") or 0),
        int(payload.get("connection_risk_score") or 0),
    )


def rank_component(candidate: dict[str, Any], key: str) -> int | float:
    components = candidate.get("rank_components")
    if not isinstance(components, dict):
        return UNKNOWN_RANK_NUMERIC
    value = numeric_or_none(components.get(key))
    return value if value is not None else UNKNOWN_RANK_NUMERIC


__all__ = [
    "MIXED_CANDIDATE_RANKING_SCHEMA_VERSION",
    "UNKNOWN_RANK_NUMERIC",
    "rank_component",
    "rank_mixed_candidates",
    "score_validated_candidates",
]
