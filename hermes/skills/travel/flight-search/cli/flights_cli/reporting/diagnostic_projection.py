from __future__ import annotations

from typing import Any

from ..domain.immutable import thaw
from ..pipeline.search_decision import SearchDecision, SearchEvidenceView
from ..pipeline.search_plan import SearchPlan


# Пояснение к трассе, а не текст для путешественника: рендер сюда не нужен.
PROVIDER_SHOPPING_EVIDENCE_NOTE = (
    "Выдача поставщика — свидетельство о наличии, а не о цене: финальный тариф, "
    "багаж и защиту билета проверять на странице оплаты."
)


def _decision_options(decision_frontier: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in decision_frontier.get("options") or []
        if isinstance(item, dict)
    ]


def _candidate_ids(candidate_envelope: dict[str, Any]) -> list[str]:
    return [
        str(candidate.get("id"))
        for candidate in candidate_envelope.get("candidates") or []
        if isinstance(candidate, dict) and candidate.get("id")
    ]


def build_projection_input(
    plan: SearchPlan,
    evidence: SearchEvidenceView,
    decision: SearchDecision,
    date_window_inventory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project frozen artifacts into the internal trace/diagnostic view."""

    decision_frontier = decision.decision_frontier
    mixed_candidate_ranking = decision.scored_decisions["mixed_candidate_ranking"]
    coverage = (
        decision_frontier.get("coverage_summary")
        if isinstance(decision_frontier.get("coverage_summary"), dict)
        else {}
    )
    decision_options = _decision_options(decision_frontier)
    route_trace: dict[str, Any] = {
        "schema_version": "flight_decision_projection_input.v1",
        "origin": evidence.route_context.get("origin"),
        "destination": evidence.route_context.get("destination"),
        "dates": thaw(evidence.route_context.get("dates") or {}),
        "currency": evidence.route_context.get("currency"),
        "count": len(decision_options),
        "decision_frontier": thaw(decision_frontier),
        "assembly": {
            "source": "decision_frontier",
            "candidate_count": int(coverage.get("candidate_count") or 0),
            "ranked_total_count": int(coverage.get("candidate_count") or 0),
            "ranked_output_count": len(decision_options),
        },
        "live_search": {
            "source": "frontier-first provider search",
            "provider_policy": evidence.provider_policy,
            "note": PROVIDER_SHOPPING_EVIDENCE_NOTE,
            "plan": thaw(evidence.route_context),
            "output": {
                "catalog_limit": plan.output_policy.catalog_limit,
                "direct_catalog_limit": plan.output_policy.direct_catalog_limit,
            },
            "segment_searches": thaw(evidence.direct_inventory_searches),
            "primary_offer_results": thaw(evidence.primary_offer_results),
            "offer_graph": thaw(decision.offer_graph),
            "candidate_input_ids": _candidate_ids(decision.offer_candidates),
            "decision_scorer": thaw(decision.scored_decisions["scorer"]),
            "mixed_candidate_ranking": thaw(mixed_candidate_ranking),
            "stop_policy": thaw(decision.stop_policy),
            "stop_policy_status": thaw(decision.stop_policy_status),
            "research_status": thaw(decision.research_status),
            "probe_ledger": thaw(evidence.probe_ledger),
            "diagnostics": {
                "search_plan": thaw(evidence.search_plan),
            },
        },
    }
    if date_window_inventory is not None:
        route_trace["live_search"]["date_window_inventory"] = thaw(
            date_window_inventory
        )
    return route_trace


__all__ = ["build_projection_input"]
