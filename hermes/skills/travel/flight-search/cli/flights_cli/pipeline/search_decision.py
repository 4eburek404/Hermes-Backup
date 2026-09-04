from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..domain.vocabulary import normalize_direction
from .decision_scorer import DecisionScorer, DecisionScorerOptions
from .offer_graph_builder import build_offer_graph
from .offer_graph_materializer import materialize_offer_graph_candidates
from .search_plan import SearchPlan


class SearchEvidenceView(Protocol):
    """То, что решение действительно читает у свидетельства, и только это."""

    primary_offer_results: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class SearchDecision:
    """Pure decision artifacts derived from frozen search evidence."""

    offer_graph: dict[str, Any]
    offer_candidates: dict[str, Any]
    scored_decisions: dict[str, Any]

    @property
    def decision_frontier(self) -> dict[str, Any]:
        frontier = self.scored_decisions.get("decision_frontier")
        return frontier if isinstance(frontier, dict) else {}


class SearchDecisionBuilder:
    """Build one decision pass without provider, store, or reporting access."""

    @staticmethod
    def build(plan: SearchPlan, evidence: SearchEvidenceView) -> SearchDecision:
        route = plan.route
        offer_graph = build_offer_graph(
            primary_offer_results=list(evidence.primary_offer_results),
        )
        offer_candidates = materialize_offer_graph_candidates(
            offer_graph,
            round_trip=bool(route.dates.get("return")),
            direct_only=route.direct_only,
            requested_origin=route.origin,
            requested_destination=route.destination,
            requested_origin_airports=list(route.origin_airports),
            requested_destination_airports=list(route.destination_airports),
            requested_dates=_requested_dates(plan),
        )
        # Присутствие прямых считается по кандидатам и живёт в их конверте.
        # И лимит выдачи, и потолок пересадок по направлению читают оттуда, а
        # не из отдельной копии, посчитанной исполнителем по сырым ответам.
        direct_directions = {
            str(direction)
            for direction, enabled in (
                (offer_candidates.get("coverage") or {}).get("direct_mode") or {}
            ).items()
            if enabled
        }
        max_connections_by_direction = {direction: 0 for direction in direct_directions}
        scored_decisions = DecisionScorer(
            DecisionScorerOptions(
                round_trip=bool(route.dates.get("return")),
                max_connections_per_journey=(
                    plan.decision_policy.max_connections_per_journey
                ),
                max_connections_per_direction=max_connections_by_direction,
                preferred_connections=plan.decision_policy.preferred_connections,
                min_same_airport_connection_min=(
                    plan.decision_policy.min_same_airport_connection_min
                ),
                min_cross_airport_connection_min=(
                    plan.decision_policy.min_cross_airport_connection_min
                ),
                max_layover_min=plan.decision_policy.max_layover_min,
                preferred_layover_max_min=(
                    plan.decision_policy.preferred_layover_max_min
                ),
                max_gateway_alternatives=(plan.output_policy.max_gateway_alternatives),
                max_primary_gateway_options=(
                    plan.output_policy.max_primary_gateway_options
                ),
                max_options_per_first_carrier=(
                    plan.output_policy.max_options_per_first_carrier
                ),
                max_options=(
                    plan.output_policy.direct_catalog_limit
                    if direct_directions
                    else plan.output_policy.catalog_limit
                ),
            )
        ).score(offer_candidates)
        return SearchDecision(
            offer_graph=offer_graph,
            offer_candidates=offer_candidates,
            scored_decisions=scored_decisions,
        )


def _requested_dates(plan: SearchPlan) -> dict[str, set[str]]:
    """Даты, которые действительно спрашивали у провайдера, по направлениям.

    Источник — сам план, а не запрос: при переборе окна дат на одно
    направление приходится несколько дат, и все они законны.
    """
    dates: dict[str, set[str]] = {}
    for attempt in plan.phases.primary:
        date = str(attempt.query.get("date") or "")
        if date:
            dates.setdefault(normalize_direction(attempt.direction), set()).add(date)
    return dates


__all__ = ["SearchDecision", "SearchDecisionBuilder", "SearchEvidenceView"]
