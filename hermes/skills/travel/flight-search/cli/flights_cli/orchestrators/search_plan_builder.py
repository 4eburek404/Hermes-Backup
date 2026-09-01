from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from datetime import timedelta
from typing import Any, Callable

from ..adapters.providers.registry import (
    providers_for_offer_query,
)
from ..config import MAX_DATE_WINDOW_DAYS
from ..domain.airports import airport_scope_summary, explicit_or_resolved_airports
from ..domain.gateway_discovery import GatewayDiscoveryService
from ..domain.connection_policy import (
    DEFAULT_MAX_LAYOVER_MIN,
    DEFAULT_PREFERRED_LAYOVER_MAX_MIN,
)
from ..domain.normalize import parse_iso_date
from ..domain.route_access_profiles import MODE_REQUIRED, PROFILE_RESTRICTED_ACCESS
from ..domain.stop_policy import resolve_stop_policy
from ..domain.vocabulary import Direction, RouteFamily
from ..errors import CliError
from ..pipeline.frontier_selection import (
    DEFAULT_FIRST_CARRIER_MAX_OPTIONS,
    DEFAULT_GATEWAY_MAX_ALTERNATIVES,
    DEFAULT_MAX_ROUND_TRIP_PAIRS,
    DEFAULT_PRIMARY_GATEWAY_MAX_OPTIONS,
)
from ..pipeline.flow_decision import FlowDecision, decide_flow
from ..pipeline.search_request import SearchRequest
from ..pipeline.direct_gate import is_direct_only
from ..pipeline.search_plan import (
    GATEWAY_TRIGGER_DISABLED,
    GATEWAY_TRIGGER_ON_PRIMARY_FAILURE,
    GATEWAY_TRIGGER_REQUIRED_IF_NO_DIRECT,
    DecisionPolicy,
    ExecutionPolicy,
    GatewayDiscovery,
    GatewayPolicy,
    OutputPolicy,
    ProviderAttemptPlan,
    RouteLegTemplate,
    RoutePlan,
    SearchPhases,
    SearchPlan,
)
from ..store import Store


@dataclass(frozen=True, slots=True)
class _PlanningState:
    request: SearchRequest
    flow_decision: FlowDecision
    today: date


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
        today=today_provider() if today_provider is not None else date.today(),
    )


def _live_cache_settings(flow: _PlanningState) -> tuple[bool, int]:
    request = flow.request
    try:
        days_until_departure = (
            date.fromisoformat(request.depart_date) - flow.today
        ).days
    except ValueError:
        days_until_departure = None
    requires_fresh_live = bool(
        request.no_live_cache
        or is_direct_only(request)
        or request.only_carriers
        or request.origin_airports
        or request.destination_airports
        or (days_until_departure is not None and days_until_departure <= 2)
    )
    if requires_fresh_live:
        return False, 0
    return True, request.live_cache_ttl_seconds


def direct_inventory_dates(options: SearchRequest, flow: _PlanningState) -> list[str]:
    window_end_raw = options.route.date_window_end
    if not window_end_raw:
        return [flow.request.depart_date]
    depart = parse_iso_date(flow.request.depart_date, "depart-date")
    if not is_direct_only(flow.request):
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


def build_route_plan(
    request: SearchRequest,
    store: Store | None = None,
    *,
    flow: _PlanningState | None = None,
) -> RoutePlan:
    """Собрать маршрутную часть плана сразу типизированной.

    Раньше здесь строился словарь из пятнадцати ключей, который следующей же
    строкой разбирался обратно в этот же датакласс с теми же именами полей.
    Теперь источник истины — объект, а словарь получается из него.
    """

    flow = flow or build_planning_state(request, store)
    window_end = request.route.date_window_end
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
        request, flow, store
    )
    return RoutePlan(
        origin=flow.request.origin,
        destination=flow.request.destination,
        dates=dates,
        currency=flow.request.currency,
        profile=flow.request.profile,
        provider_policy=flow.request.provider_policy,
        routing_strategy=flow.flow_decision.routing_strategy,
        route_mode=flow.flow_decision.route_mode,
        market_class=flow.flow_decision.market_class,
        route_families=({"id": route_family},),
        hubs=tuple(flow.request.hubs),
        origin_airports=tuple(origin_airports),
        destination_airports=tuple(destination_airports),
        airport_scope=airport_scope,
        direct_only=is_direct_only(flow.request),
    )


def build_route_context(
    request: SearchRequest,
    store: Store | None = None,
    *,
    flow: _PlanningState | None = None,
) -> dict[str, Any]:
    """Словарное представление маршрутного плана для потребителей трассы."""

    return build_route_plan(request, store, flow=flow).to_dict()


def _resolved_airport_scope(
    options: SearchRequest,
    flow: _PlanningState,
    store: Store | None,
) -> tuple[list[str], list[str], dict[str, Any] | None]:
    if store is None:
        return (
            list(flow.request.origin_airports),
            list(flow.request.destination_airports),
            None,
        )

    origin_location = store.resolve_location(flow.request.origin)
    destination_location = store.resolve_location(flow.request.destination)
    origin_airports = explicit_or_resolved_airports(
        origin_location,
        list(options.route.origin_airports),
        role="origin",
        max_airports=options.route.max_airports_per_city,
    )
    destination_airports = explicit_or_resolved_airports(
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

    def __init__(self, store: Store) -> None:
        self._store = store
        self._options: SearchRequest

    def build(self, request: SearchRequest) -> SearchPlan:
        self._options = request
        flow = build_planning_state(self._options, self._store)
        route = build_route_plan(self._options, self._store, flow=flow)
        primary_offer_queries = self._primary_offer_queries(flow, route)
        gateway_discovery = self._gateway_discovery(flow, route)
        gateway_trigger = self._gateway_trigger(flow, gateway_discovery)
        route_leg_templates = self._route_leg_templates(
            flow, route, gateway_discovery, gateway_trigger
        )
        live_cache_enabled, live_cache_ttl_seconds = _live_cache_settings(flow)
        stop_policy = resolve_stop_policy(
            max_connections=self._options.route.max_connections,
            tier2_max_connections=self._options.route.tier2_max_connections,
        )
        return SearchPlan(
            route=route,
            phases=SearchPhases(
                primary=self._attempts(
                    primary_offer_queries,
                    phase="primary",
                    conditional_trigger="no_direct",
                ),
                route_legs=route_leg_templates,
            ),
            gateway_policy=GatewayPolicy(
                trigger=gateway_trigger,
                discovery=gateway_discovery,
            ),
            execution_policy=ExecutionPolicy(
                max_provider_attempts=flow.request.max_segment_searches,
                segment_limit=self._options.evidence.segment_limit,
                live_cache_ttl_seconds=live_cache_ttl_seconds,
                live_cache_enabled=live_cache_enabled,
                timeout=self._options.evidence.timeout,
                fail_fast=self._options.evidence.fail_fast,
                gateway_discovery_limit=self._options.route.gateway_discovery_limit,
                gateway_probe_batch_size=self._options.route.gateway_probe_batch_size,
                gateway_probe_max_batches=self._options.route.gateway_probe_max_batches,
                only_carriers=self._options.effective_only_carriers(),
            ),
            decision_policy=DecisionPolicy(
                max_connections_per_journey=stop_policy.hard_max_connections,
                preferred_connections=stop_policy.preferred_max_connections,
                min_same_airport_connection_min=(
                    self._options.route.min_same_airport_min
                ),
                min_cross_airport_connection_min=(
                    self._options.route.min_cross_airport_min
                ),
                max_layover_min=DEFAULT_MAX_LAYOVER_MIN,
                preferred_layover_max_min=DEFAULT_PREFERRED_LAYOVER_MAX_MIN,
            ),
            output_policy=OutputPolicy(
                catalog_limit=self._options.output.catalog_limit,
                direct_catalog_limit=self._options.output.direct_catalog_limit,
                max_gateway_alternatives=DEFAULT_GATEWAY_MAX_ALTERNATIVES,
                max_primary_gateway_options=DEFAULT_PRIMARY_GATEWAY_MAX_OPTIONS,
                max_options_per_first_carrier=DEFAULT_FIRST_CARRIER_MAX_OPTIONS,
                max_round_trip_pairs=DEFAULT_MAX_ROUND_TRIP_PAIRS,
            ),
            planning_reasons=tuple(
                dict.fromkeys(
                    [
                        *flow.flow_decision.route_access_reasons,
                        *flow.flow_decision.limitations,
                    ]
                )
            ),
        )

    def _route_leg_templates(
        self,
        flow: _PlanningState,
        route: RoutePlan,
        gateway_discovery: GatewayDiscovery,
        gateway_trigger: str,
    ) -> tuple[RouteLegTemplate, ...]:
        origin = str(route.origin or flow.request.origin).upper()
        destination = str(route.destination or flow.request.destination).upper()
        templates: list[RouteLegTemplate] = []
        signatures: set[tuple[str, tuple[str, ...]]] = set()

        def add_template(
            airports: tuple[str, ...],
            *,
            source: str,
            policies: tuple[str, ...],
            trigger: str,
        ) -> None:
            outbound_signature = (Direction.OUTBOUND, airports)
            if outbound_signature in signatures:
                return
            signatures.add(outbound_signature)
            templates.append(
                RouteLegTemplate(
                    hypothesis_id=f"{source}:outbound:{'-'.join(airports)}",
                    direction=Direction.OUTBOUND,
                    required_airports=airports,
                    source=source,
                    leg_policies=policies,
                    trigger=trigger,
                )
            )
            if flow.request.return_date:
                mirrored = tuple(reversed(airports))
                return_signature = (Direction.RETURN, mirrored)
                if return_signature in signatures:
                    return
                signatures.add(return_signature)
                templates.append(
                    RouteLegTemplate(
                        hypothesis_id=f"{source}:return:{'-'.join(mirrored)}",
                        direction=Direction.RETURN,
                        required_airports=mirrored,
                        source=source,
                        leg_policies=tuple(reversed(policies)),
                        trigger=trigger,
                    )
                )

        for hypothesis in flow.request.route_hypotheses:
            add_template(
                hypothesis.airports,
                source=hypothesis.source,
                policies=("exact_direct",) * (len(hypothesis.airports) - 1),
                trigger="always",
            )

        if gateway_trigger == GATEWAY_TRIGGER_DISABLED:
            return tuple(templates)
        discovery_payload = gateway_discovery.to_dict()
        candidates = [
            item
            for item in (discovery_payload.get("candidates") or [])[
                : self._gateway_candidate_cap()
            ]
            if isinstance(item, dict) and item.get("code")
        ]
        seen_gateway_codes: set[str] = set()
        for candidate in candidates:
            gateway = str(candidate.get("code") or "").upper()
            if not gateway or gateway in seen_gateway_codes:
                continue
            seen_gateway_codes.add(gateway)
            add_template(
                (origin, gateway, destination),
                source="configured_prior",
                policies=(
                    "direct_then_controlled_broad",
                    "direct_then_controlled_broad",
                ),
                trigger=gateway_trigger,
            )
        return tuple(templates)

    def _attempts(
        self,
        queries: list[dict[str, Any]],
        *,
        phase: str,
        conditional_trigger: str,
    ) -> tuple[ProviderAttemptPlan, ...]:
        attempts: list[ProviderAttemptPlan] = []
        for index, query in enumerate(queries, start=1):
            trigger = (
                "always"
                if phase == "primary" and bool(query.get("direct_only"))
                else conditional_trigger
            )
            execution_query = dict(query)
            provider = str(execution_query.pop("provider", "")).strip().lower()
            probe_type = str(execution_query.pop("probe_type", "")).strip()
            direction = str(execution_query.pop("direction", "")).strip()
            attempts.append(
                ProviderAttemptPlan(
                    probe_id=f"{phase}-{index:03d}",
                    phase=phase,
                    trigger=trigger,
                    provider=provider,
                    probe_type=probe_type,
                    direction=direction,
                    query=execution_query,
                )
            )
        return tuple(attempts)

    def _gateway_trigger(
        self, flow: _PlanningState, discovery: GatewayDiscovery
    ) -> str:
        if is_direct_only(flow.request) or not discovery.enabled:
            return GATEWAY_TRIGGER_DISABLED
        if discovery.mode in {MODE_REQUIRED, "diagnostic_required"}:
            return GATEWAY_TRIGGER_REQUIRED_IF_NO_DIRECT
        return GATEWAY_TRIGGER_ON_PRIMARY_FAILURE

    def _gateway_discovery(
        self, flow: _PlanningState, route: RoutePlan
    ) -> GatewayDiscovery:
        decision = flow.flow_decision
        mode = (
            "disabled"
            if is_direct_only(flow.request)
            else str(decision.gateway_discovery_mode or "disabled")
        )
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
            route,
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
        route: RoutePlan,
        *,
        enabled: bool,
    ) -> dict[str, Any]:
        market_key = prior_set or self._fallback_market_key(route)
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

    def _fallback_market_key(self, route: RoutePlan) -> str:
        for family in route.route_families:
            if family.get("id"):
                return str(family.get("id") or "")
        return ""

    def _provider_names_for_primary_offers(
        self, flow: _PlanningState, query: dict[str, Any]
    ) -> list[str]:
        return [
            str(provider)
            for provider in providers_for_offer_query(
                query, self._store, flow.request.provider_policy
            )
        ]

    def _gateway_candidate_cap(self) -> int:
        configured_limit = max(0, int(self._options.route.gateway_discovery_limit))
        batch_size = max(0, int(self._options.route.gateway_probe_batch_size))
        max_batches = max(0, int(self._options.route.gateway_probe_max_batches))
        batch_cap = batch_size * max_batches
        if batch_cap <= 0:
            return 0
        return min(configured_limit, batch_cap)

    def _primary_offer_queries(
        self, flow: _PlanningState, route: RoutePlan
    ) -> list[dict[str, Any]]:
        origin = str(route.origin or flow.request.origin).upper()
        destination = str(route.destination or flow.request.destination).upper()
        date_text = str(route.dates.get("depart") or flow.request.depart_date)
        currency = str(route.currency or flow.request.currency).upper()
        origin_airports = [
            str(code).upper()
            for code in route.origin_airports or (origin,)
            if str(code).strip()
        ]
        destination_airports = [
            str(code).upper()
            for code in route.destination_airports or (destination,)
            if str(code).strip()
        ]
        access_profile = str(flow.flow_decision.route_access_profile or "")
        discovery_mode = str(flow.flow_decision.gateway_discovery_mode or "disabled")

        direct_queries = self._direct_inventory_queries(
            flow,
            origin=origin,
            destination=destination,
            origin_airports=origin_airports,
            destination_airports=destination_airports,
            currency=currency,
        )
        if access_profile == PROFILE_RESTRICTED_ACCESS:
            for query in direct_queries:
                query["route_access_profile"] = access_profile
                query["gateway_discovery_mode"] = discovery_mode
        if is_direct_only(flow.request) or flow.request.date_window_end:
            return direct_queries

        # Оба плеча строит одна функция. До этого прямое собиралось здесь
        # вручную, а обратное — вызовом ниже, и куски расходились по мелочам.
        restricted = (
            (access_profile, discovery_mode)
            if access_profile == PROFILE_RESTRICTED_ACCESS
            else None
        )
        queries: list[dict[str, Any]] = list(direct_queries)
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
                direct_only=False,
                restricted_access=restricted,
            )
        )
        if flow.request.return_date:
            # Обратное плечо украшения ограниченного доступа не получает —
            # так было и раньше; асимметрия уходит вместе со шлюзовым слоем.
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
                    direct_only=False,
                )
            )
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
        restricted_access: tuple[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        route_query: dict[str, Any] = {
            "probe_type": "full_route_aggregate",
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
                "probe_type": "full_route_aggregate",
                "provider": provider_name,
                "direction": str(direction),
                "origin": origin,
                "destination": destination,
                "origin_airports": list(origin_airports),
                "destination_airports": list(destination_airports),
                "date": date_text,
                "currency": currency,
                "direct_only": direct_only,
                "limit": flow.request.primary_offer_limit,
                "exhaustive": direct_only,
            }
            if route_family:
                query["route_family"] = route_family
            if restricted_access is not None:
                access_profile, discovery_mode = restricted_access
                query["route_family"] = PROFILE_RESTRICTED_ACCESS
                query["route_access_profile"] = access_profile
                query["gateway_discovery_mode"] = discovery_mode
                query["exhaustive"] = False
                query["non_exhaustive_reason"] = (
                    "restricted_access_market_requires_gateway_discovery"
                )
            self._apply_filters(query)
            queries.append(query)
        return queries

    def _apply_filters(self, query: dict[str, Any]) -> None:
        only_carriers = list(self._options.effective_only_carriers())
        if only_carriers:
            query["only_carriers"] = only_carriers
