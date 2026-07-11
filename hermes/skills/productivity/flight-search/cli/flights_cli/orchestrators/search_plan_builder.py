from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from datetime import timedelta
from typing import Any, Callable

from ..adapters.providers.registry import (
    providers_for_offer_query,
    providers_for_segment,
    route_touches_ru,
)
from ..config import MAX_DATE_WINDOW_DAYS
from ..domain.airports import airport_scope_summary, explicit_or_resolved_airports
from ..domain.gateway_discovery import GatewayDiscoveryService
from ..domain.normalize import parse_iso_date
from ..domain.route_access_profiles import MODE_REQUIRED, PROFILE_RESTRICTED_ACCESS
from ..domain.vocabulary import Direction, RequiredControl, RouteFamily
from ..errors import CliError
from ..pipeline.search_request import SearchRequest
from ..pipeline.evidence_plan import EvidencePlan, plan_evidence
from ..pipeline.flow_decision import FlowDecision, decide_flow
from ..pipeline.search_plan import GatewayDiscovery, SearchPlan
from ..store import Store


@dataclass(frozen=True, slots=True)
class _PlanningState:
    request: SearchRequest
    flow_decision: FlowDecision
    evidence_plan: EvidencePlan


def build_planning_state(
    request: SearchRequest,
    store: Store | None = None,
    *,
    today_provider: Callable[[], date] | None = None,
) -> _PlanningState:
    flow_decision = decide_flow(request, store)
    return _PlanningState(
        request=request,
        flow_decision=flow_decision,
        evidence_plan=plan_evidence(
            request, flow_decision, today_provider=today_provider
        ),
    )


def direct_inventory_dates(options: SearchRequest, flow: _PlanningState) -> list[str]:
    depart = parse_iso_date(flow.request.depart_date, "depart-date")
    window_end_raw = options.route.date_window_end
    if not window_end_raw:
        return [depart.isoformat()]
    if not flow.evidence_plan.direct_only:
        raise CliError(
            "date_window_end requires direct-only route options: set route_options.max_connections=0 and route_options.tier2_max_connections=0",
            error_type="validation_error",
        )
    if flow.request.return_date:
        raise CliError(
            "date_window_end is a one-way direct inventory option; remove return_date or drop the window",
            error_type="validation_error",
        )
    window_end = parse_iso_date(str(window_end_raw), "date-window-end")
    if window_end < depart:
        raise CliError(
            "date-window-end must be on or after depart-date",
            error_type="validation_error",
        )
    window_days = (window_end - depart).days + 1
    if window_days > MAX_DATE_WINDOW_DAYS:
        raise CliError(
            f"date window spans {window_days} days; bound it to at most {MAX_DATE_WINDOW_DAYS} days",
            error_type="validation_error",
            details={"window_days": window_days, "max_days": MAX_DATE_WINDOW_DAYS},
        )
    return [
        (depart + timedelta(days=offset)).isoformat() for offset in range(window_days)
    ]


def _city_pair_direct_controls(
    options: SearchRequest, flow: _PlanningState
) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    if not flow.evidence_plan.direct_only and not flow.request.date_window_end:
        return controls
    for date_text in direct_inventory_dates(options, flow):
        controls.append(
            {
                "type": "city_pair_direct",
                "probe_type": RequiredControl.EXACT_AIRPORT_DIRECT,
                "direction": Direction.OUTBOUND,
                "origin": flow.request.origin,
                "destination": flow.request.destination,
                "date": date_text,
                "negative_evidence": "provider_empty_only_not_route_absence",
                "source": "direct_inventory_policy",
            }
        )
    if flow.request.return_date:
        controls.append(
            {
                "type": "city_pair_direct",
                "probe_type": RequiredControl.EXACT_AIRPORT_DIRECT,
                "direction": Direction.RETURN,
                "origin": flow.request.destination,
                "destination": flow.request.origin,
                "date": flow.request.return_date,
                "negative_evidence": "provider_empty_only_not_route_absence",
                "source": "direct_inventory_policy",
            }
        )
    return controls


def build_route_context(
    request: SearchRequest,
    store: Store | None = None,
    *,
    flow: _PlanningState | None = None,
) -> dict[str, Any]:
    planning = flow or build_planning_state(request, store)
    options = request
    flow = planning
    window_end = options.route.date_window_end
    dates: dict[str, Any] = {
        "depart": flow.request.depart_date,
        "return": flow.request.return_date,
    }
    if window_end:
        dates["window_end"] = str(window_end)
    route_family = str(
        flow.flow_decision.route_mode or flow.flow_decision.routing_strategy
    )
    origin_airports, destination_airports, airport_scope = _resolved_airport_scope(
        options, flow, store
    )
    return {
        "origin": flow.request.origin,
        "destination": flow.request.destination,
        "dates": dates,
        "currency": flow.request.currency,
        "profile": flow.request.profile,
        "ticketing": flow.request.ticketing,
        "provider_policy": flow.evidence_plan.provider_policy,
        "routing_strategy": flow.flow_decision.routing_strategy,
        "route_mode": flow.flow_decision.route_mode,
        "market_class": flow.flow_decision.market_class,
        "route_families": [{"id": route_family}],
        "hubs": list(flow.request.hubs),
        "origin_airports": origin_airports,
        "destination_airports": destination_airports,
        "airport_scope": airport_scope,
        "direct_only": bool(flow.evidence_plan.direct_only),
        "coverage_controls": _city_pair_direct_controls(options, flow),
    }


def _resolved_airport_scope(
    options: SearchRequest,
    flow: _PlanningState,
    store: Store | None,
) -> tuple[list[str], list[str], dict[str, Any] | None]:
    if store is None:
        return (
            list(flow.request.origin_airports),
            list(flow.request.destination_airports),
            deepcopy(flow.flow_decision.airport_scope)
            if flow.flow_decision.airport_scope is not None
            else None,
        )

    origin_location = store.resolve_location(flow.request.origin)
    destination_location = store.resolve_location(flow.request.destination)
    origin_airports = explicit_or_resolved_airports(
        store,
        origin_location,
        list(options.route.origin_airports),
        role="origin",
        max_airports=options.route.max_airports_per_city,
    )
    destination_airports = explicit_or_resolved_airports(
        store,
        destination_location,
        list(options.route.destination_airports),
        role="destination",
        max_airports=options.route.max_airports_per_city,
    )
    return (
        origin_airports,
        destination_airports,
        {
            "origin": airport_scope_summary(
                origin_location,
                origin_airports,
                list(options.route.origin_airports),
                role="origin",
            ),
            "destination": airport_scope_summary(
                destination_location,
                destination_airports,
                list(options.route.destination_airports),
                role="destination",
            ),
        },
    )


class SearchPlanBuilder:
    """Pure builder for the single plan consumed by search execution."""

    def __init__(
        self,
        options: SearchRequest,
        store: Store,
        *,
        flow: _PlanningState | None = None,
    ) -> None:
        self._options = options
        self._store = store
        self._flow = flow

    def build(self) -> SearchPlan:
        flow = self._flow or build_planning_state(self._options, self._store)
        route_context = build_route_context(self._options, self._store, flow=flow)
        primary_offer_queries = self._primary_offer_queries(flow, route_context)
        gateway_discovery = self._gateway_discovery(flow, route_context)
        return SearchPlan(
            route_context=route_context,
            primary_offer_queries=tuple(primary_offer_queries),
            gateway_discovery=gateway_discovery,
            conditional_gateway_queries=tuple(
                self._gateway_leg_queries(flow, route_context, gateway_discovery)
            ),
            aggregate_queries=tuple(self._aggregate_queries(route_context)),
            coverage_expectations=tuple(
                self._coverage_expectations(route_context, primary_offer_queries)
            ),
            execution_limits={
                "max_segment_searches": flow.evidence_plan.max_segment_searches,
                "search_wave_max_waves": self._options.evidence.search_wave_max_waves,
                "search_wave_probe_limit": self._options.evidence.search_wave_probe_limit,
                "search_wave_top_k": self._options.evidence.search_wave_top_k,
                "aggregate_control_limit": flow.evidence_plan.aggregate_control_limit,
                "segment_limit": self._options.evidence.segment_limit,
                "live_cache_ttl_seconds": flow.evidence_plan.live_cache_ttl_seconds,
                "live_cache_enabled": flow.evidence_plan.live_cache_enabled,
                "timeout": self._options.evidence.timeout,
                "fail_fast": self._options.evidence.fail_fast,
            },
            output_limits={
                "catalog_limit": self._options.output.catalog_limit,
                "direct_catalog_limit": self._options.output.direct_catalog_limit,
            },
            planning_reasons=tuple(
                dict.fromkeys(
                    [
                        *flow.flow_decision.route_access_reasons,
                        *flow.flow_decision.limitations,
                    ]
                )
            ),
        )

    def _aggregate_queries(self, route_context: dict[str, Any]) -> list[dict[str, Any]]:
        limit = max(0, int(self._options.evidence.aggregate_control_limit))
        if limit == 0:
            return []
        base_carriers = list(self._options.effective_only_carriers())
        carrier_sets = [base_carriers] if base_carriers else []
        for carrier in self._options.evidence.aggregate_control_carriers:
            normalized = [str(carrier).upper()]
            if normalized not in carrier_sets:
                carrier_sets.append(normalized)
        if not carrier_sets:
            carrier_sets.append([])
        directions = [
            (
                "outbound",
                str(route_context["origin"]),
                str(route_context["destination"]),
                str(route_context["dates"]["depart"]),
            )
        ]
        if route_context["dates"].get("return"):
            directions.append(
                (
                    "return",
                    str(route_context["destination"]),
                    str(route_context["origin"]),
                    str(route_context["dates"]["return"]),
                )
            )
        return [
            {
                "role": "aggregate_evidence",
                "source_type": "provider_full_route",
                "probe_type": RequiredControl.CARRIER_AGGREGATE
                if carriers
                else RequiredControl.FULL_ROUTE_AGGREGATE,
                "provider": None,
                "direction": direction,
                "origin": origin,
                "destination": destination,
                "date": date_text,
                "currency": str(route_context["currency"]),
                "direct_only": False,
                "only_carriers": carriers,
                "limit": limit,
                "execution_state": "not_executed",
            }
            for direction, origin, destination, date_text in directions
            for carriers in carrier_sets
        ]

    def _gateway_discovery(
        self, flow: _PlanningState, route_context: dict[str, Any]
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
            route_context,
            enabled=enabled,
        )
        return GatewayDiscovery(
            enabled=enabled,
            reason=reason,
            mode=mode,
            route_access_profile=decision.route_access_profile,
            route_access_reasons=tuple(reasons),
            candidate_count=int(diagnostics.get("candidate_count") or 0),
            candidates=tuple(
                dict(candidate)
                for candidate in diagnostics.get("candidates") or []
                if isinstance(candidate, dict)
            ),
            skipped_reasons=tuple(
                str(item) for item in diagnostics.get("skipped_reasons") or [] if item
            ),
            empty_reason=diagnostics.get("empty_reason"),
            prior_set=decision.route_access_prior_set,
            matched_rule_id=decision.route_access_rule_id,
            market=diagnostics.get("market"),
            rejected_gateway_signals=tuple(
                dict(item)
                for item in diagnostics.get("rejected_gateway_signals") or []
                if isinstance(item, dict)
            ),
        )

    def _gateway_discovery_diagnostics(
        self,
        prior_set: str,
        route_context: dict[str, Any],
        *,
        enabled: bool,
    ) -> dict[str, Any]:
        market_key = prior_set or self._fallback_market_key(route_context)
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

    def _fallback_market_key(self, route_context: dict[str, Any]) -> str:
        for family in route_context.get("route_families") or []:
            if isinstance(family, dict) and family.get("id"):
                return str(family.get("id") or "")
        return ""

    def _provider_names_for_primary_offers(
        self, flow: _PlanningState, query: dict[str, Any]
    ) -> list[str]:
        return [
            str(provider)
            for provider in providers_for_offer_query(
                query, self._store, flow.evidence_plan.provider_policy
            )
        ]

    def _gateway_leg_queries(
        self,
        flow: _PlanningState,
        route_context: dict[str, Any],
        gateway_discovery: GatewayDiscovery,
    ) -> list[dict[str, Any]]:
        discovery_payload = gateway_discovery.to_dict()
        if not bool(discovery_payload.get("enabled")):
            return []

        candidates: list[dict[str, Any]] = []
        candidate_cap = self._gateway_candidate_cap()
        if candidate_cap > 0:
            candidates.extend(
                candidate
                for candidate in (discovery_payload.get("candidates") or [])[
                    :candidate_cap
                ]
                if isinstance(candidate, dict) and candidate.get("code")
            )
        if not candidates:
            return []
        candidates = self._dedupe_gateway_candidates(candidates)

        origin = str(route_context.get("origin") or flow.request.origin).upper()
        destination = str(
            route_context.get("destination") or flow.request.destination
        ).upper()
        date_text = str(
            (route_context.get("dates") or {}).get("depart") or flow.request.depart_date
        )
        currency = str(route_context.get("currency") or flow.request.currency).upper()

        queries: list[dict[str, Any]] = []
        for rank, candidate in enumerate(candidates, start=1):
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
                    gateway_source=str(candidate.get("source") or ""),
                )
            )
        return queries

    def _dedupe_gateway_candidates(
        self, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate in candidates:
            code = str(candidate.get("code") or "").upper()
            if not code or code in seen:
                continue
            seen.add(code)
            deduped.append(candidate)
        return deduped

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
        flow: _PlanningState,
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
        gateway_source: str,
    ) -> list[dict[str, Any]]:
        legs = (
            ("origin_to_gateway", origin, gateway),
            ("gateway_to_destination", gateway, destination),
        )
        queries: list[dict[str, Any]] = []
        for leg, leg_origin, leg_destination in legs:
            touches_ru = route_touches_ru(leg_origin, leg_destination, self._store)
            connection_layer = (
                "restricted_ru_bridge_control"
                if touches_ru
                else "restricted_non_ru_access"
            )
            leg_dates = [date_text]
            if leg == "gateway_to_destination":
                next_date = (date.fromisoformat(date_text) + timedelta(days=1)).isoformat()
                if next_date not in leg_dates:
                    leg_dates.append(next_date)
            for leg_date in leg_dates:
                query = {
                "role": "gateway_leg_probe",
                "source_type": "gateway_discovery_candidate",
                "probe_type": "segment_hub_leg",
                "direction": "outbound",
                "leg": leg,
                "origin": leg_origin,
                "destination": leg_destination,
                "origin_airports": [leg_origin],
                "destination_airports": [leg_destination],
                "date": leg_date,
                "currency": currency,
                "direct_only": False,
                "gateway": gateway,
                "gateway_role": "bridge_gateway",
                "connection_layer": connection_layer,
                "allows_intermediate_hubs": True,
                "date_strategy": (
                    "requested_day_and_next_day"
                    if leg == "gateway_to_destination"
                    else "requested_departure_date_only"
                ),
                "gateway_rank": rank,
                "gateway_source": gateway_source,
                "candidate_score": score,
                "route_access_profile": route_access_profile,
                "gateway_discovery_mode": gateway_discovery_mode,
                "execution_state": "not_executed",
                }
                self._apply_filters(query)
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
        self, flow: _PlanningState, route_context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        origin = str(route_context.get("origin") or flow.request.origin).upper()
        destination = str(
            route_context.get("destination") or flow.request.destination
        ).upper()
        date_text = str(
            (route_context.get("dates") or {}).get("depart") or flow.request.depart_date
        )
        currency = str(route_context.get("currency") or flow.request.currency).upper()
        origin_airports = [
            str(code).upper()
            for code in route_context.get("origin_airports") or [origin]
            if str(code).strip()
        ]
        destination_airports = [
            str(code).upper()
            for code in route_context.get("destination_airports") or [destination]
            if str(code).strip()
        ]
        access_profile = str(flow.flow_decision.route_access_profile or "")
        discovery_mode = str(flow.flow_decision.gateway_discovery_mode or "disabled")

        if flow.evidence_plan.direct_only or flow.request.date_window_end:
            return self._direct_inventory_queries(
                flow,
                origin=origin,
                destination=destination,
                origin_airports=origin_airports,
                destination_airports=destination_airports,
                currency=currency,
            )

        route_query: dict[str, Any] = {
            "probe_type": RequiredControl.FULL_ROUTE_AGGREGATE,
            "origin": origin,
            "destination": destination,
            "direct_only": False,
        }
        self._apply_filters(route_query)
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
                "origin_airports": origin_airports,
                "destination_airports": destination_airports,
                "date": date_text,
                "currency": currency,
                "direct_only": False,
                "limit": flow.evidence_plan.primary_offer_limit,
                "execution_state": "not_executed",
            }
            if flow.request.return_date:
                query["return_date"] = flow.request.return_date
            self._apply_filters(query)
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

    def _direct_inventory_queries(
        self,
        flow: _PlanningState,
        *,
        origin: str,
        destination: str,
        origin_airports: list[str],
        destination_airports: list[str],
        currency: str,
    ) -> list[dict[str, Any]]:
        queries: list[dict[str, Any]] = []
        outbound_dates = direct_inventory_dates(self._options, flow)
        for date_text in outbound_dates:
            queries.extend(
                self._provider_offer_queries_for_route(
                    flow,
                    direction=Direction.OUTBOUND,
                    origin=origin,
                    destination=destination,
                    origin_airports=origin_airports,
                    destination_airports=destination_airports,
                    date_text=date_text,
                    currency=currency,
                    direct_only=True,
                    route_family=RouteFamily.DIRECT_INVENTORY,
                )
            )
        if flow.request.return_date:
            queries.extend(
                self._provider_offer_queries_for_route(
                    flow,
                    direction=Direction.RETURN,
                    origin=destination,
                    destination=origin,
                    origin_airports=destination_airports,
                    destination_airports=origin_airports,
                    date_text=flow.request.return_date,
                    currency=currency,
                    direct_only=True,
                    route_family=RouteFamily.DIRECT_INVENTORY,
                )
            )
        return queries

    def _provider_offer_queries_for_route(
        self,
        flow: _PlanningState,
        *,
        direction: str,
        origin: str,
        destination: str,
        origin_airports: list[str],
        destination_airports: list[str],
        date_text: str,
        currency: str,
        direct_only: bool,
        route_family: str | None = None,
    ) -> list[dict[str, Any]]:
        route_query: dict[str, Any] = {
            "probe_type": RequiredControl.FULL_ROUTE_AGGREGATE,
            "origin": origin,
            "destination": destination,
            "direct_only": direct_only,
        }
        self._apply_filters(route_query)
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
                "direction": str(direction),
                "origin": origin,
                "destination": destination,
                "origin_airports": list(origin_airports),
                "destination_airports": list(destination_airports),
                "date": date_text,
                "currency": currency,
                "direct_only": direct_only,
                "limit": flow.evidence_plan.primary_offer_limit,
                "execution_state": "not_executed",
                "exhaustive": direct_only,
            }
            if route_family:
                query["route_family"] = route_family
            self._apply_filters(query)
            queries.append(query)
        return queries

    def _apply_filters(self, query: dict[str, Any]) -> None:
        only_carriers = list(self._options.effective_only_carriers())
        preferred_carriers = list(self._options.effective_prefer_carriers())
        if only_carriers:
            query["only_carriers"] = only_carriers
        if preferred_carriers:
            query["preferred_carriers"] = preferred_carriers

    def _coverage_expectations(
        self,
        route_context: dict[str, Any],
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
    options: SearchRequest,
    store: Store,
    *,
    flow: _PlanningState | None = None,
) -> dict[str, Any]:
    return (
        SearchPlanBuilder(
            options,
            store,
            flow=flow,
        )
        .build()
        .to_dict()
    )
