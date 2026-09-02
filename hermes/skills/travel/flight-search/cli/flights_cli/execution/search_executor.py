from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain.vocabulary import (
    Direction,
    Leg,
    RouteFamily,
)
from .offer_query_runner import (
    PrimaryOfferQueryOptions,
    run_primary_offer_queries,
)
from .probe_ledger import ProbeRunLedger
from .search_evidence import SearchEvidence
from ..pipeline.search_plan import SearchPlan
from ..store import Store


@dataclass
class SearchExecutionState:
    """Mutable state for one live search run."""

    search_plan: SearchPlan
    primary_offer_results: list[dict[str, Any]] = field(default_factory=list)
    direct_inventory_searches: list[dict[str, Any]] = field(default_factory=list)
    direct_inventory_results: list[dict[str, Any]] = field(default_factory=list)
    probe_ledger: ProbeRunLedger = field(default_factory=ProbeRunLedger)

    @property
    def route_context(self) -> dict[str, Any]:
        return self.search_plan.route.to_dict()


def _direct_leg_for_direction(direction: Any) -> str:
    return (
        Leg.DIRECT_RETURN if str(direction) == Direction.RETURN else Leg.DIRECT_OUTBOUND
    )


def _primary_direct_inventory_searches(
    primary_offer_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    searches: list[dict[str, Any]] = []
    for result in primary_offer_results:
        if not isinstance(result, dict):
            continue
        filters = (
            result.get("filters") if isinstance(result.get("filters"), dict) else {}
        )
        if not bool(filters.get("direct_only")) and not bool(result.get("direct_only")):
            continue
        searches.append(
            {
                "role": RouteFamily.DIRECT_INVENTORY,
                "leg": _direct_leg_for_direction(result.get("direction")),
                "direction": result.get("direction") or Direction.OUTBOUND,
                "origin": result.get("origin"),
                "destination": result.get("destination"),
                "date": result.get("date"),
                "provider": result.get("provider"),
                "status": result.get("status") or result.get("execution_state"),
                "offer_count": int(result.get("offer_count") or 0),
                "raw_offer_count": result.get("raw_offer_count"),
                "cache_status": result.get("cache_status"),
                "probe_id": result.get("probe_id"),
            }
        )
    return searches


def _primary_direct_inventory_results(
    primary_offer_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    segment_results: list[dict[str, Any]] = []
    for result in primary_offer_results:
        if not isinstance(result, dict):
            continue
        filters = (
            result.get("filters") if isinstance(result.get("filters"), dict) else {}
        )
        if not bool(filters.get("direct_only")) and not bool(result.get("direct_only")):
            continue
        offers = [
            offer for offer in result.get("top_offers") or [] if isinstance(offer, dict)
        ]
        segment_results.append(
            {
                "role": RouteFamily.DIRECT_INVENTORY,
                "leg": _direct_leg_for_direction(result.get("direction")),
                "direction": result.get("direction") or Direction.OUTBOUND,
                "origin": result.get("origin"),
                "destination": result.get("destination"),
                "date": result.get("date"),
                "provider": result.get("provider"),
                "offers": offers,
            }
        )
    return segment_results


class SearchExecutor:
    """Execute an authoritative SearchPlan without consulting SearchRequest."""

    def __init__(self, store: Store, *, adapter_resolver: Any | None = None) -> None:
        self.store = store
        self.adapter_resolver = adapter_resolver

    def execute(self, plan: SearchPlan) -> SearchEvidence:
        state = self.initialize_state(plan)
        try:
            return self._execute_plan(plan, state)
        finally:
            state.probe_ledger.finalize_unexecuted()

    def _execute_plan(
        self, plan: SearchPlan, state: SearchExecutionState
    ) -> SearchEvidence:
        policy = plan.execution_policy
        planned_primary = [item.to_execution_dict() for item in plan.phases.primary]
        query_options = PrimaryOfferQueryOptions(
            live_cache_ttl_seconds=policy.live_cache_ttl_seconds,
            no_live_cache=not policy.live_cache_enabled,
            timeout=policy.timeout,
            fail_fast=policy.fail_fast,
        )
        # Исполнитель делает ровно то, что запланировано: спрашивает провайдера
        # по маршруту запроса. Своих маршрутов он больше не изобретает —
        # ни шлюзовых плеч, ни обнаружения хабов, ни решения «а не сходить ли
        # через пересадку». Присутствие прямых считается ниже по кандидатам,
        # см. offer_graph_materializer.
        state.primary_offer_results = run_primary_offer_queries(
            planned_primary,
            query_options,
            store=self.store,
            adapter_resolver=self.adapter_resolver,
            probe_ledger=state.probe_ledger,
        )
        state.direct_inventory_searches = _primary_direct_inventory_searches(
            state.primary_offer_results
        )
        state.direct_inventory_results = _primary_direct_inventory_results(
            state.primary_offer_results
        )
        state.probe_ledger.finalize_unexecuted()
        evidence = SearchEvidence.freeze(
            search_plan=plan.to_dict(),
            provider_policy=plan.route.provider_policy,
            primary_offer_results=state.primary_offer_results,
            probe_ledger=state.probe_ledger.to_diagnostics(),
            direct_inventory_searches=state.direct_inventory_searches,
            direct_inventory_results=state.direct_inventory_results,
        )
        return evidence

    def initialize_state(self, plan: SearchPlan) -> SearchExecutionState:
        state = SearchExecutionState(
            search_plan=plan,
            probe_ledger=ProbeRunLedger(
                max_physical_attempts=plan.execution_policy.max_provider_attempts
            ),
        )
        state.probe_ledger.plan_probes(
            [attempt.to_execution_dict() for attempt in plan.all_attempts]
        )
        return state
