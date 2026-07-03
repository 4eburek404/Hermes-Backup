from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..adapters.providers.registry import (
    providers_for_offer_query,
    providers_for_segment,
    route_touches_ru,
)
from ..domain.gateway_discovery import GatewayDiscoveryService
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
        gateway_discovery = self._gateway_discovery(flow, fallback_route_plan)
        return SearchPlan(
            primary_offer_queries=primary_offer_queries,
            mandatory_controls=[],
            gateway_discovery=gateway_discovery,
            gateway_leg_queries=self._gateway_leg_queries(
                flow, fallback_route_plan, gateway_discovery
            ),
            fallback_segment_plan=FallbackSegmentPlan(
                segments=deepcopy(fallback_route_plan.get("segments") or [])
            ),
            coverage_expectations=self._coverage_expectations(
                fallback_route_plan, primary_offer_queries
            ),
        )

    def _gateway_discovery(
        self, flow: LiveRouteSearchFlow, fallback_route_plan: dict[str, Any]
    ) -> GatewayDiscovery:
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
        diagnostics = self._gateway_discovery_diagnostics(
            str(decision.route_access_prior_set or ""),
            fallback_route_plan,
            enabled=enabled,
        )
        return GatewayDiscovery(
            enabled=enabled,
            reason=reason,
            mode=mode,
            route_access_profile=decision.route_access_profile,
            route_access_reasons=reasons,
            candidate_count=int(diagnostics.get("candidate_count") or 0),
            candidates=[
                dict(candidate)
                for candidate in diagnostics.get("candidates") or []
                if isinstance(candidate, dict)
            ],
            skipped_reasons=[
                str(item) for item in diagnostics.get("skipped_reasons") or [] if item
            ],
            empty_reason=diagnostics.get("empty_reason"),
            prior_set=decision.route_access_prior_set,
            matched_rule_id=decision.route_access_rule_id,
            market=diagnostics.get("market"),
            rejected_gateway_signals=[
                dict(item)
                for item in diagnostics.get("rejected_gateway_signals") or []
                if isinstance(item, dict)
            ],
        )

    def _gateway_discovery_diagnostics(
        self,
        prior_set: str,
        fallback_route_plan: dict[str, Any],
        *,
        enabled: bool,
    ) -> dict[str, Any]:
        market_key = prior_set or self._fallback_market_key(fallback_route_plan)
        if not enabled:
            return {
                "market": market_key,
                "candidate_count": 0,
                "candidates": [],
                "skipped_reasons": ["gateway_discovery_disabled"],
                "empty_reason": "gateway_discovery_disabled",
                "rejected_gateway_signals": [],
            }
        if not market_key:
            return {
                "market": "",
                "candidate_count": 0,
                "candidates": [],
                "skipped_reasons": ["no_gateway_discovery_market"],
                "empty_reason": "no_gateway_discovery_market",
                "rejected_gateway_signals": [],
            }
        diagnostics: dict[str, Any] = {}
        GatewayDiscoveryService(self._store).discover(
            market_key,
            diagnostics=diagnostics,
        )
        return diagnostics

    def _fallback_market_key(self, fallback_route_plan: dict[str, Any]) -> str:
        for family in fallback_route_plan.get("route_families") or []:
            if isinstance(family, dict) and family.get("id"):
                return str(family.get("id") or "")
        return ""

    def _provider_names_for_primary_offers(
        self, flow: LiveRouteSearchFlow, query: dict[str, Any]
    ) -> list[str]:
        return [
            str(provider)
            for provider in providers_for_offer_query(
                query, self._store, flow.evidence_plan.provider_policy
            )
        ]

    def _gateway_leg_queries(
        self,
        flow: LiveRouteSearchFlow,
        fallback_route_plan: dict[str, Any],
        gateway_discovery: GatewayDiscovery,
    ) -> list[dict[str, Any]]:
        discovery_payload = gateway_discovery.to_dict()
        if (
            discovery_payload.get("route_access_profile") != PROFILE_RESTRICTED_ACCESS
            or discovery_payload.get("mode") != MODE_REQUIRED
        ):
            return []

        candidates = [
            candidate
            for candidate in discovery_payload.get("candidates") or []
            if isinstance(candidate, dict) and candidate.get("code")
        ]
        candidate_cap = self._gateway_candidate_cap()
        if candidate_cap <= 0:
            return []

        origin = str(fallback_route_plan.get("origin") or flow.request.origin).upper()
        destination = str(
            fallback_route_plan.get("destination") or flow.request.destination
        ).upper()
        date_text = str(
            (fallback_route_plan.get("dates") or {}).get("depart")
            or flow.request.depart_date
        )
        currency = str(
            fallback_route_plan.get("currency") or flow.request.currency
        ).upper()

        queries: list[dict[str, Any]] = []
        for rank, candidate in enumerate(candidates[:candidate_cap], start=1):
            gateway = str(candidate.get("code") or "").upper()
            if not gateway:
                continue
            queries.extend(
                self._queries_for_gateway_candidate(
                    flow,
                    origin=origin,
                    destination=destination,
                    gateway=gateway,
                    date_text=date_text,
                    currency=currency,
                    rank=rank,
                    score=candidate.get("score"),
                    route_access_profile=str(
                        discovery_payload.get("route_access_profile") or ""
                    ),
                    gateway_discovery_mode=str(discovery_payload.get("mode") or ""),
                )
            )
        return queries

    def _gateway_candidate_cap(self) -> int:
        configured_limit = max(0, int(self._options.route.gateway_discovery_limit))
        batch_size = max(0, int(self._options.route.gateway_probe_batch_size))
        max_batches = max(0, int(self._options.route.gateway_probe_max_batches))
        batch_cap = batch_size * max_batches
        if batch_cap <= 0:
            return 0
        return min(configured_limit, batch_cap)

    def _queries_for_gateway_candidate(
        self,
        flow: LiveRouteSearchFlow,
        *,
        origin: str,
        destination: str,
        gateway: str,
        date_text: str,
        currency: str,
        rank: int,
        score: Any,
        route_access_profile: str,
        gateway_discovery_mode: str,
    ) -> list[dict[str, Any]]:
        legs = (
            ("origin_to_gateway", origin, gateway),
            ("gateway_to_destination", gateway, destination),
        )
        queries: list[dict[str, Any]] = []
        for leg, leg_origin, leg_destination in legs:
            touches_ru = route_touches_ru(leg_origin, leg_destination, self._store)
            direct_only = bool(touches_ru)
            connection_layer = (
                "restricted_ru_bridge_control"
                if direct_only
                else "restricted_non_ru_access"
            )
            query = {
                "role": "gateway_leg_probe",
                "source_type": "gateway_discovery_candidate",
                "probe_type": "segment_direct" if direct_only else "segment_hub_leg",
                "direction": "outbound",
                "leg": leg,
                "origin": leg_origin,
                "destination": leg_destination,
                "date": date_text,
                "currency": currency,
                "direct_only": direct_only,
                "gateway": gateway,
                "gateway_role": "bridge_gateway",
                "connection_layer": connection_layer,
                "allows_intermediate_hubs": not direct_only,
                "date_strategy": "requested_departure_date_only",
                "gateway_rank": rank,
                "candidate_score": score,
                "route_access_profile": route_access_profile,
                "gateway_discovery_mode": gateway_discovery_mode,
                "execution_state": "not_executed",
            }
            providers = providers_for_segment(
                query, self._store, flow.evidence_plan.provider_policy
            )
            if providers:
                query["provider"] = str(providers[0])
            else:
                query["provider"] = None
                query["execution_state"] = "skipped"
                query["reason"] = "provider_not_applicable"
            queries.append(query)
        return queries

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
        currency = str(
            fallback_route_plan.get("currency") or flow.request.currency
        ).upper()
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
        for provider_name in self._provider_names_for_primary_offers(flow, route_query):
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
        access_profile = str(primary_offer_queries[0].get("route_access_profile") or "")
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
    return (
        SearchPlanBuilder(
            options,
            store,
            flow=flow,
            fallback_route_plan=fallback_route_plan,
        )
        .build()
        .to_dict()
    )
