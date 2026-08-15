from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..execution.search_evidence import SearchEvidence
from ..execution.search_executor import SearchExecutor
from ..pipeline.result_builder import (
    build_flight_search_result,
    build_result_projection,
)
from ..pipeline.result_contract import FlightSearchResult
from ..pipeline.search_decision import SearchDecision, SearchDecisionBuilder
from ..pipeline.search_plan import SearchPlan
from ..pipeline.search_request import SearchRequest
from ..reporting.date_window_inventory import build_date_window_inventory
from ..reporting.diagnostic_projection import build_projection_input
from ..store import Store
from .search_plan_builder import SearchPlanBuilder


@dataclass(frozen=True, slots=True)
class SearchRunArtifacts:
    plan: dict[str, Any]
    evidence: SearchEvidence
    decision: SearchDecision
    projection_input: dict[str, Any]
    projection: dict[str, Any]


class SearchWorkflow:
    """The single production composition root for flight search."""

    def __init__(
        self,
        store: Store,
        *,
        catalog_refresh: dict[str, Any] | None = None,
        adapter_resolver: Any | None = None,
    ) -> None:
        self.store = store
        self.catalog_refresh = catalog_refresh
        self.adapter_resolver = adapter_resolver

    def plan(self, request: SearchRequest) -> SearchPlan:
        return SearchPlanBuilder(self.store).build(request)

    def run_artifacts(self, request: SearchRequest) -> SearchRunArtifacts:
        plan = self.plan(request)
        evidence = SearchExecutor(
            self.store, adapter_resolver=self.adapter_resolver
        ).execute(plan)
        decision = SearchDecisionBuilder.build(plan, evidence)
        date_window_inventory = build_date_window_inventory(
            evidence.route_context,
            list(evidence.direct_inventory_searches),
            list(evidence.direct_inventory_results),
        )
        projection_input = build_projection_input(
            plan,
            evidence,
            decision,
            date_window_inventory=date_window_inventory,
        )
        return SearchRunArtifacts(
            plan=plan.to_dict(),
            evidence=evidence,
            decision=decision,
            projection_input=projection_input,
            projection=build_result_projection(projection_input),
        )

    def run(self, request: SearchRequest) -> FlightSearchResult:
        # Capture the public request echo at the input boundary. Once planning
        # starts, every runtime decision reads SearchPlan/Evidence only.
        request_payload = request.to_payload()
        artifacts = self.run_artifacts(request)
        return build_flight_search_result(
            request_payload,
            artifacts.projection,
            self.catalog_refresh,
        )


__all__ = ["SearchRunArtifacts", "SearchWorkflow"]
