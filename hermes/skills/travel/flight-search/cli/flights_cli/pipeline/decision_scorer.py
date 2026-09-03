from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from ..domain.connection_policy import (
    DEFAULT_MAX_LAYOVER_MIN,
    DEFAULT_MIN_CROSS_AIRPORT_CONNECTION_MIN,
    DEFAULT_MIN_SAME_AIRPORT_CONNECTION_MIN,
    DEFAULT_PREFERRED_LAYOVER_MAX_MIN,
)
from ..domain.stop_policy import BUSINESS_DEFAULT_STOP_POLICY
from .candidate_scoring import score_validated_candidates
from .candidate_validation import validate_candidate_envelope
from ..config import (
    DEFAULT_FIRST_CARRIER_MAX_OPTIONS,
    DEFAULT_GATEWAY_MAX_ALTERNATIVES,
    DEFAULT_MAX_ROUND_TRIP_PAIRS,
    DEFAULT_PRIMARY_GATEWAY_MAX_OPTIONS,
)
from .frontier_selection import (
    DEFAULT_FRONTIER_MAX_OPTIONS,
    build_decision_frontier,
)


DECISION_SCORER_SCHEMA_VERSION = "flight_decision_scorer.v1"


@dataclass(frozen=True, slots=True)
class DecisionScorerOptions:
    round_trip: bool = False
    max_connections_per_journey: int = BUSINESS_DEFAULT_STOP_POLICY.hard_max_connections
    max_connections_per_direction: dict[str, int] = field(default_factory=dict)
    preferred_connections: int = BUSINESS_DEFAULT_STOP_POLICY.preferred_max_connections
    min_same_airport_connection_min: int = DEFAULT_MIN_SAME_AIRPORT_CONNECTION_MIN
    min_cross_airport_connection_min: int = DEFAULT_MIN_CROSS_AIRPORT_CONNECTION_MIN
    max_layover_min: int = DEFAULT_MAX_LAYOVER_MIN
    preferred_layover_max_min: int = DEFAULT_PREFERRED_LAYOVER_MAX_MIN
    max_gateway_alternatives: int = DEFAULT_GATEWAY_MAX_ALTERNATIVES
    max_primary_gateway_options: int = DEFAULT_PRIMARY_GATEWAY_MAX_OPTIONS
    max_options_per_first_carrier: int = DEFAULT_FIRST_CARRIER_MAX_OPTIONS
    max_round_trip_pairs: int = DEFAULT_MAX_ROUND_TRIP_PAIRS
    max_options: int | None = DEFAULT_FRONTIER_MAX_OPTIONS


class DecisionScorer:
    """Compose candidate validation, scoring, and frontier selection once."""

    def __init__(self, options: DecisionScorerOptions) -> None:
        self.options = options

    def score(self, candidate_envelope: dict[str, Any]) -> dict[str, Any]:
        prepared_envelope = self._prepare_candidate_envelope(candidate_envelope)
        validation = validate_candidate_envelope(
            prepared_envelope,
            max_connections_per_journey=self.options.max_connections_per_journey,
            max_connections_per_direction=self.options.max_connections_per_direction,
            min_same_airport_connection_min=(
                self.options.min_same_airport_connection_min
            ),
            min_cross_airport_connection_min=(
                self.options.min_cross_airport_connection_min
            ),
            max_layover_min=self.options.max_layover_min,
            preferred_layover_max_min=self.options.preferred_layover_max_min,
        )
        ranking = score_validated_candidates(
            validation,
            preferred_connections_per_journey=self.options.preferred_connections,
        )
        frontier = build_decision_frontier(
            ranking,
            max_gateway_alternatives=self.options.max_gateway_alternatives,
            max_options=self.options.max_options,
            max_primary_gateway_options=self.options.max_primary_gateway_options,
            max_options_per_first_carrier=(self.options.max_options_per_first_carrier),
            max_round_trip_pairs=self.options.max_round_trip_pairs,
            preferred_connections_per_journey=self.options.preferred_connections,
            preferred_layover_max_min=self.options.preferred_layover_max_min,
        )
        return {
            "schema_version": DECISION_SCORER_SCHEMA_VERSION,
            "scorer": {
                "name": "DecisionScorer",
                "schema_version": DECISION_SCORER_SCHEMA_VERSION,
                "round_trip": bool(self.options.round_trip),
                "max_connections_per_journey": max(
                    0, int(self.options.max_connections_per_journey)
                ),
                "max_connections_per_direction": dict(
                    self.options.max_connections_per_direction
                ),
                "preferred_connections": max(
                    0, int(self.options.preferred_connections)
                ),
                "min_same_airport_connection_min": max(
                    0, int(self.options.min_same_airport_connection_min)
                ),
                "min_cross_airport_connection_min": max(
                    0, int(self.options.min_cross_airport_connection_min)
                ),
                "max_layover_min": max(0, int(self.options.max_layover_min)),
                "adapters": {
                    "candidate_ranking": "flight_mixed_candidate_ranking.v1",
                    "frontier": "flight_decision_frontier.v1",
                },
                "max_options": self.options.max_options,
                "max_gateway_alternatives": max(
                    0, int(self.options.max_gateway_alternatives)
                ),
                "max_primary_gateway_options": max(
                    0, int(self.options.max_primary_gateway_options)
                ),
                "max_options_per_first_carrier": max(
                    1, int(self.options.max_options_per_first_carrier)
                ),
                "preferred_layover_max_min": max(
                    0, int(self.options.preferred_layover_max_min)
                ),
                "max_round_trip_pairs": max(0, int(self.options.max_round_trip_pairs)),
            },
            "mixed_candidate_ranking": ranking,
            "decision_frontier": frontier,
        }

    def _prepare_candidate_envelope(
        self, candidate_envelope: dict[str, Any]
    ) -> dict[str, Any]:
        envelope = deepcopy(candidate_envelope)
        candidates = [
            candidate
            for candidate in envelope.get("candidates") or []
            if isinstance(candidate, dict)
        ]
        if not self.options.round_trip:
            envelope["candidates"] = candidates
            return envelope

        # Круговой вариант приезжает от провайдера целиком. Односторонний
        # кандидат кругового запроса не покрывает, поэтому в выдачу не идёт.
        envelope["candidates"] = [
            candidate for candidate in candidates if _has_outbound_and_return(candidate)
        ]
        return envelope


def _has_outbound_and_return(candidate: dict[str, Any]) -> bool:
    directions = {
        _candidate_direction_from_journey(journey) for journey in _journeys(candidate)
    }
    return "outbound" in directions and "return" in directions


def _candidate_direction_from_journey(journey: dict[str, Any]) -> str:
    return str(journey.get("direction") or "").strip().lower()


def _journeys(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    journeys = candidate.get("journeys")
    if not isinstance(journeys, list):
        return []
    return [journey for journey in journeys if isinstance(journey, dict)]


__all__ = [
    "DECISION_SCORER_SCHEMA_VERSION",
    "DecisionScorer",
    "DecisionScorerOptions",
]
