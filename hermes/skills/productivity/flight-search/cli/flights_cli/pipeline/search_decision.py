from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..domain.stop_policy import (
    resolve_stop_policy,
    stop_policy_payload,
    stop_policy_status,
)
from .decision_scorer import DecisionScorer, DecisionScorerOptions
from .offer_graph import build_offer_graph, materialize_offer_graph_candidates
from .search_plan import SearchPlan


class SearchEvidenceView(Protocol):
    search_plan: dict[str, Any]
    provider_policy: str
    primary_offer_results: tuple[dict[str, Any], ...]
    gateway_leg_results: dict[str, Any]
    observed_gateway_diagnostics: dict[str, Any]
    probe_ledger: dict[str, Any]
    direct_mode: dict[str, bool]
    max_connections_by_direction: dict[str, int]
    direct_presence_gate: dict[str, Any]
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
        offer_graph = build_offer_graph(
            primary_offer_results=list(evidence.primary_offer_results),
            gateway_leg_results=evidence.gateway_leg_results,
        )
        offer_candidates = materialize_offer_graph_candidates(
            offer_graph,
            round_trip=bool(plan.route.dates.get("return")),
            direct_only=bool(route.get("direct_only")),
            direct_mode=evidence.direct_mode,
            requested_origin=str(route.get("origin") or ""),
            requested_destination=str(route.get("destination") or ""),
            requested_origin_airports=list(route.get("origin_airports") or []),
            requested_destination_airports=list(
                route.get("destination_airports") or []
            ),
        )
        scored_decisions = DecisionScorer(
            DecisionScorerOptions(
                round_trip=bool(plan.route.dates.get("return")),
                max_connections_per_journey=(
                    plan.decision_policy.max_connections_per_journey
                ),
                max_connections_per_direction=evidence.max_connections_by_direction,
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
                max_round_trip_pairs=plan.output_policy.max_round_trip_pairs,
                max_options=(
                    plan.output_policy.direct_catalog_limit
                    if any(bool(value) for value in evidence.direct_mode.values())
                    else plan.output_policy.catalog_limit
                ),
            )
        ).score(offer_candidates)
        stop_policy = resolve_stop_policy(
            max_connections=plan.decision_policy.preferred_connections,
            tier2_max_connections=plan.decision_policy.max_connections_per_journey,
            name="search_plan",
        )
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


__all__ = ["SearchDecision", "SearchDecisionBuilder", "SearchEvidenceView"]
