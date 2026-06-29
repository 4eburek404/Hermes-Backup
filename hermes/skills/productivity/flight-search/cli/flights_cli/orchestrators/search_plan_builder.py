from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..adapters.providers.registry import providers_for_route_query
from ..domain.route_access_profiles import MODE_REQUIRED, PROFILE_RESTRICTED_ACCESS
from ..domain.vocabulary import RequiredControl
from ..pipeline.options import LiveAssemblyOptions
from ..pipeline.search_pipeline import LiveRouteSearchFlow, build_live_route_search_flow
from ..pipeline.search_plan import FallbackSegmentPlan, GatewayDiscovery, SearchPlan
from ..store import Store
from .route_plan_builder import RoutePlanBuilder

PRIMARY_OFFER_QUERY_LIMIT = 10


class SearchPlanBuilder:
    """Builds the diagnostic SearchPlan beside the executable fallback plan."""

    def __init__(
        self,
        options: LiveAssemblyOptions,
        store: Store,
        *,
        flow: LiveRouteSearchFlow | None = None,
        fallback_route_plan: dict[str, Any] | None = None,
    ) -> None:
        self._options = options
        self._store = store
        self._flow = flow
        self._fallback_route_plan = fallback_route_plan

    def build(self) -> SearchPlan:
        flow = self._flow or build_live_route_search_flow(self._options, self._store)
        fallback_route_plan = self._fallback_route_plan
        if fallback_route_plan is None:
            fallback_route_plan = RoutePlanBuilder(
                self._options, self._store, flow=flow
            ).build()
        primary_offer_queries = self._primary_offer_queries(flow, fallback_route_plan)
        return SearchPlan(
            primary_offer_queries=primary_offer_queries,
            mandatory_controls=[],
            gateway_discovery=self._gateway_discovery(flow),
            fallback_segment_plan=FallbackSegmentPlan(
                segments=deepcopy(fallback_route_plan.get("segments") or [])
            ),
            coverage_expectations=self._coverage_expectations(
                fallback_route_plan, primary_offer_queries
            ),
        )

    def _gateway_discovery(self, flow: LiveRouteSearchFlow) -> GatewayDiscovery:
        decision = flow.flow_decision
        mode = str(decision.gateway_discovery_mode or "disabled")
        enabled = mode != "disabled"
        reasons = list(decision.route_access_reasons or [])
        reason = (
            "route_access_profile_requires_gateway_discovery"
            if mode == MODE_REQUIRED
            else "route_access_profile_allows_gateway_discovery_after_provider_failure"
            if enabled
            else None
        )
        return GatewayDiscovery(
            enabled=enabled,
            reason=reason,
            mode=mode,
            route_access_profile=decision.route_access_profile,
            route_access_reasons=reasons,
            prior_set=decision.route_access_prior_set,
            matched_rule_id=decision.route_access_rule_id,
        )

    def _provider_names_for_primary_offers(
        self, flow: LiveRouteSearchFlow, query: dict[str, Any]
    ) -> list[str]:
        return [
            str(provider)
            for provider in providers_for_route_query(
                query, self._store, flow.evidence_plan.provider_policy
            )
        ]

    def _primary_offer_queries(
        self, flow: LiveRouteSearchFlow, fallback_route_plan: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if flow.evidence_plan.direct_only or flow.request.date_window_end:
            return []

        origin = str(fallback_route_plan.get("origin") or flow.request.origin).upper()
        destination = str(
            fallback_route_plan.get("destination") or flow.request.destination
        ).upper()
        date_text = str(
            (fallback_route_plan.get("dates") or {}).get("depart")
            or flow.request.depart_date
        )
        currency = str(fallback_route_plan.get("currency") or flow.request.currency).upper()
        access_profile = str(flow.flow_decision.route_access_profile or "")
        discovery_mode = str(flow.flow_decision.gateway_discovery_mode or "disabled")

        route_query: dict[str, Any] = {
            "probe_type": RequiredControl.FULL_ROUTE_AGGREGATE,
            "origin": origin,
            "destination": destination,
            "direct_only": False,
        }
        queries: list[dict[str, Any]] = []
        seen: set[str] = set()
        for provider_name in self._provider_names_for_primary_offers(
            flow, route_query
        ):
            if not provider_name or provider_name in seen:
                continue
            seen.add(provider_name)
            query: dict[str, Any] = {
                "role": "primary_offer_collection",
                "source_type": "provider_full_route",
                "probe_type": RequiredControl.FULL_ROUTE_AGGREGATE,
                "provider": provider_name,
                "direction": "outbound",
                "origin": origin,
                "destination": destination,
                "date": date_text,
                "currency": currency,
                "direct_only": False,
                "limit": PRIMARY_OFFER_QUERY_LIMIT,
                "execution_state": "not_executed",
            }
            if access_profile == PROFILE_RESTRICTED_ACCESS:
                query["route_family"] = PROFILE_RESTRICTED_ACCESS
                query["route_access_profile"] = access_profile
                query["gateway_discovery_mode"] = discovery_mode
                query["exhaustive"] = False
                query["non_exhaustive_reason"] = (
                    "restricted_access_market_requires_gateway_discovery"
                )
            queries.append(query)
        return queries

    def _coverage_expectations(
        self,
        fallback_route_plan: dict[str, Any],
        primary_offer_queries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not primary_offer_queries:
            return []
        access_profile = str(
            primary_offer_queries[0].get("route_access_profile") or ""
        )
        if access_profile != PROFILE_RESTRICTED_ACCESS:
            return []
        return [
            {
                "type": "gateway_discovery_required",
                "route_access_profile": PROFILE_RESTRICTED_ACCESS,
                "gateway_discovery_mode": MODE_REQUIRED,
                "source_type": "provider_full_route",
                "reason": "restricted access markets keep segment fallback coverage and gateway discovery diagnostics",
            }
        ]


def build_search_plan(
    options: LiveAssemblyOptions,
    store: Store,
    *,
    flow: LiveRouteSearchFlow | None = None,
    fallback_route_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return SearchPlanBuilder(
        options,
        store,
        flow=flow,
        fallback_route_plan=fallback_route_plan,
    ).build().to_dict()
