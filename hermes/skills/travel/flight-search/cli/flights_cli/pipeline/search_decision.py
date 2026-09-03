from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..domain.vocabulary import normalize_direction
from ..domain.stop_policy import (
    resolve_stop_policy,
    stop_policy_payload,
    stop_policy_status,
)
from .decision_scorer import DecisionScorer, DecisionScorerOptions
from .offer_graph_builder import build_offer_graph
from .offer_graph_materializer import materialize_offer_graph_candidates
from .search_plan import SearchPlan


class SearchEvidenceView(Protocol):
    search_plan: dict[str, Any]
    provider_policy: str
    primary_offer_results: tuple[dict[str, Any], ...]
    probe_ledger: dict[str, Any]
    direct_inventory_searches: tuple[dict[str, Any], ...]

    @property
    def route_context(self) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class SearchDecision:
    """Pure decision artifacts derived from frozen search evidence."""

    offer_graph: dict[str, Any]
    offer_candidates: dict[str, Any]
    scored_decisions: dict[str, Any]
    stop_policy: dict[str, Any]
    stop_policy_status: dict[str, Any]

    @property
    def decision_frontier(self) -> dict[str, Any]:
        frontier = self.scored_decisions.get("decision_frontier")
        return frontier if isinstance(frontier, dict) else {}


class SearchDecisionBuilder:
    """Build one decision pass without provider, store, or reporting access."""

    @staticmethod
    def build(plan: SearchPlan, evidence: SearchEvidenceView) -> SearchDecision:
        route = evidence.route_context
        stop_policy = resolve_stop_policy(
            max_connections=plan.decision_policy.preferred_connections,
            tier2_max_connections=plan.decision_policy.max_connections_per_journey,
            name="search_plan",
        )
        offer_graph = build_offer_graph(
            primary_offer_results=list(evidence.primary_offer_results),
        )
        offer_candidates = materialize_offer_graph_candidates(
            offer_graph,
            round_trip=bool(plan.route.dates.get("return")),
            direct_only=bool(route.get("direct_only")),
            requested_origin=str(route.get("origin") or ""),
            requested_destination=str(route.get("destination") or ""),
            requested_origin_airports=list(route.get("origin_airports") or []),
            requested_destination_airports=list(
                route.get("destination_airports") or []
            ),
            requested_dates=_requested_dates(plan),
            max_path_offers=stop_policy.hard_max_connections + 1,
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
                round_trip=bool(plan.route.dates.get("return")),
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
            stop_policy=stop_policy_payload(stop_policy),
            stop_policy_status=stop_policy_status(
                list(scored_decisions["decision_frontier"].get("options") or []),
                ranked_candidates=list(
                    scored_decisions["mixed_candidate_ranking"].get("ranked_candidates")
                    or []
                ),
                policy=stop_policy,
            ),
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
