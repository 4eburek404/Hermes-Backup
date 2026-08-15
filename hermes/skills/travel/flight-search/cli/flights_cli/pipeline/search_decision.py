from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..domain.stop_policy import (
    resolve_stop_policy,
    stop_policy_payload,
    stop_policy_status,
)
from .direct_gate import candidate_is_direct
from .decision_scorer import DecisionScorer, DecisionScorerOptions
from .offer_graph_builder import build_offer_graph
from .offer_graph_materializer import materialize_offer_graph_candidates
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
    research_status: dict[str, Any]

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
            max_path_offers=stop_policy.hard_max_connections + 1,
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
            research_status=_research_status(
                scored_decisions,
                evidence.gateway_leg_results,
                evidence.probe_ledger,
            ),
        )


def _research_status(
    scored_decisions: dict[str, Any],
    gateway_leg_results: dict[str, Any],
    probe_ledger: dict[str, Any],
) -> dict[str, Any]:
    ranking = scored_decisions.get("mixed_candidate_ranking")
    ranked = (
        ranking.get("ranked_candidates") if isinstance(ranking, dict) else []
    )
    candidates = [item for item in ranked or [] if isinstance(item, dict)]
    eligible_direct = any(
        candidate_is_direct(candidate)
        and (candidate.get("validation") or {}).get("status") == "valid"
        for candidate in candidates
    )
    convenient_signatures = {
        _airport_signature(candidate)
        for candidate in candidates
        if (candidate.get("validation") or {}).get("status") == "valid"
        and str((candidate.get("connection_assessment") or {}).get("comfort"))
        in {"comfortable", "acceptable"}
        and _airport_signature(candidate)
    }
    audit = _route_hypothesis_audit(gateway_leg_results)
    target_reached = eligible_direct or len(convenient_signatures) >= 3
    incomplete_evidence = bool(
        (probe_ledger.get("failed_probes") or [])
        or (probe_ledger.get("not_executed_probes") or [])
        or any(item["status"] == "not_executed" for item in audit)
    )
    evidence_incomplete = not target_reached and incomplete_evidence
    return {
        "needed": not target_reached and not evidence_incomplete,
        "evidence_incomplete": evidence_incomplete,
        "eligible_direct": eligible_direct,
        "convenient_signature_count": len(convenient_signatures),
        "target_signature_count": 3,
        "audit": audit,
    }


def _airport_signature(candidate: dict[str, Any]) -> tuple[Any, ...] | None:
    journeys = candidate.get("journeys")
    if not isinstance(journeys, list):
        return None
    signature: list[tuple[str, tuple[str, ...]]] = []
    for journey in journeys:
        if not isinstance(journey, dict):
            continue
        airports: list[str] = []
        for segment in journey.get("segments") or []:
            if not isinstance(segment, dict):
                continue
            origin = str(segment.get("origin") or "").upper()
            destination = str(segment.get("destination") or "").upper()
            if origin and not airports:
                airports.append(origin)
            if destination:
                airports.append(destination)
        if airports:
            signature.append((str(journey.get("direction") or "outbound"), tuple(airports)))
    return tuple(signature) if signature else None


def _route_hypothesis_audit(results: dict[str, Any]) -> list[dict[str, Any]]:
    hypotheses = results.get("route_hypotheses") if isinstance(results, dict) else []
    audit: list[dict[str, Any]] = []
    for hypothesis in hypotheses or []:
        if not isinstance(hypothesis, dict):
            continue
        status = str(hypothesis.get("status") or "excluded")
        if status not in {"viable", "excluded", "not_executed"}:
            status = "excluded"
        audit.append(
            {
                "hypothesis_id": str(hypothesis.get("hypothesis_id") or ""),
                "direction": str(hypothesis.get("direction") or "outbound"),
                "required_airports": list(hypothesis.get("required_airports") or []),
                "status": status,
                "reason": str(
                    hypothesis.get("reason")
                    or (
                        "route_hypothesis_viable"
                        if status == "viable"
                        else "route_hypothesis_not_executed"
                        if status == "not_executed"
                        else "route_hypothesis_excluded"
                    )
                ),
            }
        )
    return audit


__all__ = ["SearchDecision", "SearchDecisionBuilder", "SearchEvidenceView"]
