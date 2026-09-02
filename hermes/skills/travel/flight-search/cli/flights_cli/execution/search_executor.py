from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain.gateway_discovery import GatewayDiscoveryService
from ..domain.normalize import normalize_carrier_code
from ..domain.vocabulary import (
    Direction,
    Leg,
    RouteFamily,
    normalize_direction,
)
from .route_leg_probe_executor import (
    RouteLegProbeExecutor,
    RouteLegProbeOptions,
)
from .offer_query_runner import (
    PrimaryOfferQueryOptions,
    run_primary_offer_queries,
)
from .probe_ledger import ProbeRunLedger
from .search_evidence import SearchEvidence
from ..pipeline.direct_gate import (
    evaluate_direct_gate,
    provider_result_has_eligible_path,
)
from ..pipeline.search_plan import (
    GATEWAY_TRIGGER_ON_PRIMARY_FAILURE,
    SearchPlan,
)
from ..store import Store


@dataclass
class SearchExecutionState:
    """Mutable state for one frontier-first live search run."""

    search_plan: SearchPlan
    primary_offer_results: list[dict[str, Any]] = field(default_factory=list)
    gateway_leg_results: dict[str, Any] = field(default_factory=dict)
    direct_inventory_searches: list[dict[str, Any]] = field(default_factory=list)
    direct_inventory_results: list[dict[str, Any]] = field(default_factory=list)
    probe_ledger: ProbeRunLedger = field(default_factory=ProbeRunLedger)
    direct_mode: dict[str, bool] = field(default_factory=dict)
    direct_presence_gate: dict[str, Any] = field(default_factory=dict)

    @property
    def route_context(self) -> dict[str, Any]:
        return self.search_plan.route.to_dict()


def gateway_discovery_market_key(state: SearchExecutionState) -> str:
    discovery = state.search_plan.gateway_policy.discovery
    if discovery.prior_set:
        return discovery.prior_set
    for attempt in state.search_plan.phases.primary:
        if attempt.query.get("route_family"):
            return str(attempt.query.get("route_family") or "")
    for family in state.route_context.get("route_families") or []:
        if isinstance(family, dict) and family.get("id"):
            return str(family.get("id") or "")
    return ""


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
        self.route_leg_probe_executor: RouteLegProbeExecutor | None = None

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
        # Один проход. Раньше здесь было две фазы: прицельная проба
        # direct_only, потом широкая — и только по тем направлениям, где прямых
        # не нашлось. Разведка убрана: широкая выдача содержит те же прямые
        # рейсы, поэтому вызовов столько же там, где прямые есть, и вдвое
        # меньше там, где их нет. Присутствие прямых считается по результату,
        # а не управляет тем, что спрашивать.
        state.primary_offer_results = run_primary_offer_queries(
            planned_primary,
            query_options,
            store=self.store,
            adapter_resolver=self.adapter_resolver,
            probe_ledger=state.probe_ledger,
        )
        gate = evaluate_direct_gate(
            state.route_context,
            state.primary_offer_results,
            only_carriers=plan.execution_policy.only_carriers,
        )
        state.direct_mode = dict(gate.direct_mode)
        state.direct_presence_gate = gate.to_dict()
        successful_directions = {
            normalize_direction(result.get("direction"))
            for result in state.primary_offer_results
            if str(result.get("execution_state") or "") == "searched"
        }
        state.direct_presence_gate["direct_search_confirmed"] = {
            direction: direction in successful_directions
            for direction in state.direct_mode
        }
        # Направления без прямых по-прежнему открывают шлюзовое плечо — это
        # отдельное решение от того, что спрашивать у провайдера.
        fallback_directions = [
            direction
            for direction, direct_present in state.direct_mode.items()
            if not direct_present
        ]
        primary_path_present = {
            direction: any(
                normalize_direction(result.get("direction")) == direction
                and provider_result_has_eligible_path(
                    result,
                    {
                        **result,
                        **(
                            result.get("filters")
                            if isinstance(result.get("filters"), dict)
                            else {}
                        ),
                    },
                    only_carriers=plan.execution_policy.only_carriers,
                    max_connections_per_journey=(
                        plan.decision_policy.max_connections_per_journey
                    ),
                )
                for result in state.primary_offer_results
                if isinstance(result, dict)
            )
            for direction in state.direct_mode
        }

        eligible_templates = []
        skipped_templates = []
        for template in plan.phases.route_legs:
            direction = normalize_direction(template.direction)
            if (
                len(template.required_airports) - 2
                > plan.decision_policy.max_connections_per_journey
            ):
                skipped_templates.append((template, "hypothesis_exceeds_stop_policy"))
            elif template.trigger == "always":
                eligible_templates.append(template)
            elif direction not in fallback_directions:
                skipped_templates.append((template, "direct_available"))
            elif (
                template.trigger == GATEWAY_TRIGGER_ON_PRIMARY_FAILURE
                and not gate.primary_failure.get(direction, False)
                and primary_path_present.get(direction, False)
            ):
                skipped_templates.append((template, "gateway_trigger_not_satisfied"))
            else:
                eligible_templates.append(template)
        state.direct_presence_gate["gateway_trigger"] = plan.gateway_policy.trigger
        state.direct_presence_gate["skipped_gateway_probe_count"] = len(
            skipped_templates
        )
        if eligible_templates and self.route_leg_probe_executor is not None:
            state.gateway_leg_results = self.route_leg_probe_executor.run(
                eligible_templates, plan.to_dict()
            )
            fallback_status = "executed"
        else:
            state.gateway_leg_results = {"route_hypotheses": []}
            fallback_status = "no_route_leg_templates"
        route_audit = state.gateway_leg_results.setdefault("route_hypotheses", [])
        route_audit.extend(
            {
                **template.to_dict(),
                "status": "not_executed",
                "reason": reason,
                "legs": [],
            }
            for template, reason in skipped_templates
        )
        if fallback_directions:
            state.direct_presence_gate["fallback"] = {
                "status": fallback_status,
                "reason": "no_eligible_direct_evidence",
                "directions": fallback_directions,
                "gateway_directions": [
                    normalize_direction(template.direction)
                    for template in eligible_templates
                ],
                "max_connections_per_journey": (
                    plan.decision_policy.max_connections_per_journey
                ),
            }
        observed_gateway_diagnostics: dict[str, Any] = {}
        GatewayDiscoveryService(self.store).discover(
            gateway_discovery_market_key(state),
            provider_results=state.primary_offer_results,
            diagnostics=observed_gateway_diagnostics,
        )
        state.direct_inventory_searches = _primary_direct_inventory_searches(
            state.primary_offer_results
        )
        state.direct_inventory_results = _primary_direct_inventory_results(
            state.primary_offer_results
        )
        state.probe_ledger.finalize_unexecuted()
        max_connections_by_direction = gate.connection_caps(
            plan.decision_policy.max_connections_per_journey
        )
        evidence = SearchEvidence.freeze(
            search_plan=plan.to_dict(),
            provider_policy=plan.route.provider_policy,
            primary_offer_results=state.primary_offer_results,
            gateway_leg_results=state.gateway_leg_results,
            observed_gateway_diagnostics=observed_gateway_diagnostics,
            probe_ledger=state.probe_ledger.to_diagnostics(),
            direct_mode=state.direct_mode,
            max_connections_by_direction=max_connections_by_direction,
            direct_presence_gate=state.direct_presence_gate,
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
        policy = plan.execution_policy
        only_carriers = [
            normalize_carrier_code(code, "only-carrier")
            for code in policy.only_carriers
        ]
        self.route_leg_probe_executor = RouteLegProbeExecutor(
            options=RouteLegProbeOptions(
                segment_limit=policy.segment_limit,
                timeout=policy.timeout,
                fail_fast=policy.fail_fast,
            ),
            store=self.store,
            only_carriers=only_carriers,
            cache_ttl_seconds=policy.live_cache_ttl_seconds,
            use_live_cache=policy.live_cache_enabled,
            adapter_resolver=self.adapter_resolver,
            probe_ledger=state.probe_ledger,
        )
        return state
