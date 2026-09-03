from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..execution.search_evidence import SearchEvidence
from ..execution.search_executor import SearchExecutor
from ..pipeline.result_builder import build_flight_search_result
from ..pipeline.result_contract import FlightSearchResult
from ..pipeline.search_decision import SearchDecision, SearchDecisionBuilder
from ..pipeline.search_plan import SearchPlan
from ..pipeline.search_request import SearchRequest
from ..reporting.date_window_inventory import build_date_window
from ..store import Store
from .search_plan_builder import SearchPlanBuilder


@dataclass(frozen=True, slots=True)
class SearchRunArtifacts:
    # Типизированный план, а не словарь: сериализует его тот, кому нужен словарь.
    plan: SearchPlan
    evidence: SearchEvidence
    decision: SearchDecision
    date_window: dict[str, Any] | None


class SearchWorkflow:
    """The single production composition root for flight search."""

    def __init__(self, store: Store, *, adapter_resolver: Any | None = None) -> None:
        self.store = store
        self.adapter_resolver = adapter_resolver

    def plan(self, request: SearchRequest) -> SearchPlan:
        return SearchPlanBuilder(self.store).build(request)

    def run_artifacts(self, request: SearchRequest) -> SearchRunArtifacts:
        plan = self.plan(request)
        evidence = SearchExecutor(
            self.store, adapter_resolver=self.adapter_resolver
        ).execute(plan)
        decision = SearchDecisionBuilder.build(plan, evidence)
        return SearchRunArtifacts(
            plan=plan,
            evidence=evidence,
            decision=decision,
            date_window=build_date_window(
                evidence.route_context,
                list(evidence.direct_inventory_searches),
                list(evidence.direct_inventory_results),
            ),
        )

    def run(self, request: SearchRequest) -> FlightSearchResult:
        # Публичное эхо входа отдаёт сам запрос. Планирование на него не влияет:
        # начиная отсюда всё читает SearchPlan и Evidence.
        artifacts = self.run_artifacts(request)
        return build_flight_search_result(
            request,
            list(artifacts.decision.decision_frontier.get("options") or []),
            artifacts.evidence.probe_ledger,
            date_window=artifacts.date_window,
        )


__all__ = ["SearchRunArtifacts", "SearchWorkflow"]
