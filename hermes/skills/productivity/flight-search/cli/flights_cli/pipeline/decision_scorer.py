from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .candidate_ranker import build_decision_frontier, rank_mixed_candidates


DECISION_SCORER_SCHEMA_VERSION = "flight_decision_scorer.v1"


@dataclass(frozen=True, slots=True)
class DecisionScorerOptions:
    round_trip: bool = False
    max_connections_per_journey: int = 2
    preferred_connections: int = 1
    min_same_airport_connection_min: int = 120
    min_cross_airport_connection_min: int = 300
    max_gateway_alternatives: int = 2
    max_round_trip_pairs: int = 12


class DecisionScorer:
    """Single owner for candidate evaluation and frontier selection.

    The current ranker/frontier functions remain as adapters while the runtime
    moves to one scoring entrypoint.
    """

    def __init__(self, options: DecisionScorerOptions | None = None) -> None:
        self.options = options or DecisionScorerOptions()

    def score(
        self,
        candidate_envelope: dict[str, Any],
        *,
        legacy_candidates: list[dict[str, Any]] | None = None,
        constraints: dict[str, Any] | None = None,
        controls: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        prepared_envelope = self._prepare_candidate_envelope(candidate_envelope)
        ranking = rank_mixed_candidates(
            prepared_envelope,
            legacy_candidates=legacy_candidates,
            max_connections_per_journey=self.options.max_connections_per_journey,
            preferred_connections_per_journey=self.options.preferred_connections,
            constraints=constraints,
            min_same_airport_connection_min=(
                self.options.min_same_airport_connection_min
            ),
            min_cross_airport_connection_min=(
                self.options.min_cross_airport_connection_min
            ),
        )
        frontier = build_decision_frontier(
            ranking,
            controls=controls,
            max_gateway_alternatives=self.options.max_gateway_alternatives,
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
                "preferred_connections": max(
                    0, int(self.options.preferred_connections)
                ),
                "adapters": {
                    "candidate_ranking": "flight_mixed_candidate_ranking.v1",
                    "frontier": "flight_decision_frontier.v1",
                },
                "round_trip_pairing": prepared_envelope.get("round_trip_pairing"),
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

        ready_round_trip = [
            candidate for candidate in candidates if _has_outbound_and_return(candidate)
        ]
        outbound = [
            candidate
            for candidate in candidates
            if not _has_outbound_and_return(candidate)
            and _candidate_direction(candidate) == "outbound"
        ]
        returns = [
            candidate
            for candidate in candidates
            if not _has_outbound_and_return(candidate)
            and _candidate_direction(candidate) == "return"
        ]
        paired = _round_trip_one_way_pairs(
            outbound,
            returns,
            max_pairs=self.options.max_round_trip_pairs,
        )
        envelope["candidates"] = [*ready_round_trip, *paired]
        envelope["round_trip_pairing"] = {
            "input_candidate_count": len(candidates),
            "provider_round_trip_candidate_count": len(ready_round_trip),
            "outbound_one_way_candidate_count": len(outbound),
            "return_one_way_candidate_count": len(returns),
            "one_way_pair_candidate_count": len(paired),
            "max_round_trip_pairs": max(0, int(self.options.max_round_trip_pairs)),
        }
        return envelope


def _round_trip_one_way_pairs(
    outbound_candidates: list[dict[str, Any]],
    return_candidates: list[dict[str, Any]],
    *,
    max_pairs: int,
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    cap = max(0, int(max_pairs))
    if cap == 0:
        return pairs
    for outbound in outbound_candidates:
        for inbound in return_candidates:
            pairs.append(_one_way_sum_candidate(outbound, inbound))
            if len(pairs) >= cap:
                return pairs
    return pairs


def _one_way_sum_candidate(
    outbound: dict[str, Any], inbound: dict[str, Any]
) -> dict[str, Any]:
    outbound_id = str(outbound.get("id") or "outbound")
    inbound_id = str(inbound.get("id") or "return")
    price, currency = _summed_price(outbound, inbound)
    warnings = _ordered_unique(
        [
            "round_trip_built_from_one_way_offers",
            *(outbound.get("warnings") or []),
            *(inbound.get("warnings") or []),
        ]
    )
    return {
        "id": f"round-trip-pair:{outbound_id}:{inbound_id}",
        "source_type": _combined_source_type(outbound, inbound),
        "provider": _common_provider(outbound, inbound),
        "source_providers": _ordered_unique(
            [
                *(outbound.get("source_providers") or []),
                outbound.get("provider"),
                *(inbound.get("source_providers") or []),
                inbound.get("provider"),
            ]
        ),
        "gateway": None,
        "gateways": _ordered_unique(
            [
                outbound.get("gateway"),
                *(outbound.get("gateways") or []),
                inbound.get("gateway"),
                *(inbound.get("gateways") or []),
            ]
        ),
        "covers_requested_trip": bool(outbound.get("covers_requested_trip"))
        and bool(inbound.get("covers_requested_trip")),
        "journey_scope": "round_trip",
        "price": price,
        "currency": currency,
        "price_basis": "summed_one_way_prices" if price is not None else "unknown",
        "ticketing_model": "one_way_sum",
        "detail_status": _combined_detail_status(outbound, inbound),
        "journeys": [
            *_journeys_for_direction(outbound, "outbound"),
            *_journeys_for_direction(inbound, "return"),
        ],
        "warnings": warnings,
        "offer_ids": _ordered_unique(
            [*(outbound.get("offer_ids") or []), *(inbound.get("offer_ids") or [])]
        ),
        "edge_ids": _ordered_unique(
            [*(outbound.get("edge_ids") or []), *(inbound.get("edge_ids") or [])]
        ),
        "round_trip_pair": {
            "ticketing_model": "one_way_sum",
            "outbound_candidate_id": outbound_id,
            "return_candidate_id": inbound_id,
        },
    }


def _has_outbound_and_return(candidate: dict[str, Any]) -> bool:
    directions = {
        _candidate_direction_from_journey(journey) for journey in _journeys(candidate)
    }
    return "outbound" in directions and "return" in directions


def _candidate_direction(candidate: dict[str, Any]) -> str:
    for journey in _journeys(candidate):
        direction = _candidate_direction_from_journey(journey)
        if direction in {"outbound", "return"}:
            return direction
    direction = str(candidate.get("direction") or "").strip().lower()
    return direction if direction in {"outbound", "return"} else "outbound"


def _candidate_direction_from_journey(journey: dict[str, Any]) -> str:
    return str(journey.get("direction") or "").strip().lower()


def _journeys(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    journeys = candidate.get("journeys")
    if not isinstance(journeys, list):
        return []
    return [journey for journey in journeys if isinstance(journey, dict)]


def _journeys_for_direction(
    candidate: dict[str, Any], direction: str
) -> list[dict[str, Any]]:
    selected = []
    for journey in _journeys(candidate):
        copied = deepcopy(journey)
        copied["direction"] = direction
        selected.append(copied)
    if selected:
        return selected
    segments = candidate.get("segments")
    if isinstance(segments, list) and segments:
        return [{"direction": direction, "segments": deepcopy(segments)}]
    return []


def _summed_price(
    outbound: dict[str, Any], inbound: dict[str, Any]
) -> tuple[int | float | None, str | None]:
    outbound_price = _numeric_or_none(outbound.get("price"))
    inbound_price = _numeric_or_none(inbound.get("price"))
    outbound_currency = str(outbound.get("currency") or "").strip()
    inbound_currency = str(inbound.get("currency") or "").strip()
    if outbound_price is None or inbound_price is None:
        return None, outbound_currency or inbound_currency or None
    if outbound_currency and inbound_currency and outbound_currency != inbound_currency:
        return None, outbound_currency
    return outbound_price + inbound_price, outbound_currency or inbound_currency or None


def _combined_source_type(outbound: dict[str, Any], inbound: dict[str, Any]) -> str:
    outbound_type = str(outbound.get("source_type") or "")
    inbound_type = str(inbound.get("source_type") or "")
    if outbound_type and outbound_type == inbound_type:
        return outbound_type
    return "one_way_sum"


def _common_provider(outbound: dict[str, Any], inbound: dict[str, Any]) -> str | None:
    outbound_provider = str(outbound.get("provider") or "").strip()
    inbound_provider = str(inbound.get("provider") or "").strip()
    if outbound_provider and outbound_provider == inbound_provider:
        return outbound_provider
    return None


def _combined_detail_status(outbound: dict[str, Any], inbound: dict[str, Any]) -> str:
    statuses = {
        str(outbound.get("detail_status") or "").strip().lower(),
        str(inbound.get("detail_status") or "").strip().lower(),
    }
    if "missing" in statuses:
        return "missing"
    if "summary_only" in statuses:
        return "summary_only"
    return "full"


def _numeric_or_none(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).replace(" ", ""))
    except ValueError:
        return None


def _ordered_unique(items: list[Any]) -> list[Any]:
    values: list[Any] = []
    seen: set[str] = set()
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(item)
    return values


__all__ = [
    "DECISION_SCORER_SCHEMA_VERSION",
    "DecisionScorer",
    "DecisionScorerOptions",
]
