from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from datetime import timedelta
from typing import Any, Callable

from ..adapters.providers.registry import (
    provider_supports_offer_query,
    providers_for_offer_query,
)
from ..config import (
    DEFAULT_FIRST_CARRIER_MAX_OPTIONS,
    DEFAULT_GATEWAY_MAX_ALTERNATIVES,
    DEFAULT_MAX_AIRPORTS_PER_CITY,
    DEFAULT_PRIMARY_GATEWAY_MAX_OPTIONS,
    DEFAULT_PROFILE,
    DEFAULT_ROUTING_STRATEGY,
    MAX_DATE_WINDOW_DAYS,
)
from ..domain.airports import airport_scope_summary, explicit_or_resolved_airports
from ..domain.connection_policy import (
    DEFAULT_MAX_LAYOVER_MIN,
    DEFAULT_MIN_CROSS_AIRPORT_CONNECTION_MIN,
    DEFAULT_MIN_SAME_AIRPORT_CONNECTION_MIN,
    DEFAULT_PREFERRED_LAYOVER_MAX_MIN,
)
from ..domain.normalize import parse_iso_date
from ..domain.stop_policy import resolve_stop_policy
from ..domain.vocabulary import Direction, RouteFamily
from ..errors import CliError
from ..pipeline.search_request import SearchRequest
from ..pipeline.search_request import is_direct_only
from ..pipeline.search_plan import (
    DecisionPolicy,
    ExecutionPolicy,
    OutputPolicy,
    ProviderAttemptPlan,
    RoutePlan,
    SearchPhases,
    SearchPlan,
)
from ..store import Store


@dataclass(frozen=True, slots=True)
class _PlanningState:
    request: SearchRequest
    today: date


def build_planning_state(
    request: SearchRequest,
    store: Store | None = None,
    *,
    today_provider: Callable[[], date] | None = None,
) -> _PlanningState:
    return _PlanningState(
        request=request,
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
            "date_window_end scans direct inventory only: set max_connections to 0 or drop the window",
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
    origin_airports, destination_airports, airport_scope = _resolved_airport_scope(
        request, flow, store
    )
    return RoutePlan(
        origin=flow.request.origin,
        destination=flow.request.destination,
        dates=dates,
        currency=flow.request.currency,
        profile=DEFAULT_PROFILE,
        provider_policy=flow.request.provider_policy,
        routing_strategy=DEFAULT_ROUTING_STRATEGY,
        origin_airports=tuple(origin_airports),
        destination_airports=tuple(destination_airports),
        airport_scope=airport_scope,
        direct_only=is_direct_only(flow.request),
    )


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
        max_airports=DEFAULT_MAX_AIRPORTS_PER_CITY,
    )
    destination_airports = explicit_or_resolved_airports(
        destination_location,
        list(options.route.destination_airports),
        role="destination",
        max_airports=DEFAULT_MAX_AIRPORTS_PER_CITY,
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
        live_cache_enabled, live_cache_ttl_seconds = _live_cache_settings(flow)
        stop_policy = resolve_stop_policy(
            max_connections=self._options.route.preferred_connections,
            tier2_max_connections=self._options.route.max_connections,
        )
        return SearchPlan(
            route=route,
            phases=SearchPhases(
                primary=self._attempts(primary_offer_queries, phase="primary"),
            ),
            execution_policy=ExecutionPolicy(
                max_provider_attempts=flow.request.max_segment_searches,
                segment_limit=self._options.execution.segment_limit,
                live_cache_ttl_seconds=live_cache_ttl_seconds,
                live_cache_enabled=live_cache_enabled,
                timeout=self._options.execution.timeout,
                fail_fast=self._options.execution.fail_fast,
                only_carriers=self._options.effective_only_carriers(),
            ),
            decision_policy=DecisionPolicy(
                max_connections_per_journey=stop_policy.hard_max_connections,
                preferred_connections=stop_policy.preferred_max_connections,
                min_same_airport_connection_min=(
                    DEFAULT_MIN_SAME_AIRPORT_CONNECTION_MIN
                ),
                min_cross_airport_connection_min=(
                    DEFAULT_MIN_CROSS_AIRPORT_CONNECTION_MIN
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
            ),
        )

    def _attempts(
        self, queries: list[dict[str, Any]], *, phase: str
    ) -> tuple[ProviderAttemptPlan, ...]:
        attempts: list[ProviderAttemptPlan] = []
        for index, query in enumerate(queries, start=1):
            trigger = "always"
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

    def _provider_names_for_primary_offers(
        self, flow: _PlanningState, query: dict[str, Any]
    ) -> list[str]:
        return [
            str(provider)
            for provider in providers_for_offer_query(
                query, self._store, flow.request.provider_policy
            )
        ]

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
        # Прицельная проба direct_only остаётся ровно для двух случаев, где она
        # и есть искомое: запрос «только прямые» и перебор окна дат. Разведкой
        # перед широкой пробой она больше не работает — широкая выдача содержит
        # те же прямые рейсы, см. эталон direct-first-measurement.
        if is_direct_only(flow.request) or flow.request.date_window_end:
            direct_queries = self._direct_inventory_queries(
                flow,
                origin=origin,
                destination=destination,
                origin_airports=origin_airports,
                destination_airports=destination_airports,
                currency=currency,
            )
            return direct_queries

        # Круговой маршрут — одна проба с обеими датами, а не два
        # односторонних поиска со склейкой пар. Провайдера, который кругового
        # не умеет, отбраковывает гейт возможностей, а не эта функция.
        return self._provider_offer_queries_for_route(
            flow,
            direction=Direction.OUTBOUND,
            origin=origin,
            destination=destination,
            origin_airports=origin_airports,
            destination_airports=destination_airports,
            date_text=date_text,
            currency=currency,
            direct_only=False,
            return_date=flow.request.return_date or None,
        )

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
        # Окно дат и return_date несовместимы (проверено выше), поэтому при
        # круговом запросе здесь ровно одна дата и ровно одна проба.
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
                    return_date=flow.request.return_date or None,
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
        return_date: str | None = None,
    ) -> list[dict[str, Any]]:
        route_query: dict[str, Any] = {
            "probe_type": "full_route_aggregate",
            "origin": origin,
            "destination": destination,
            "direct_only": direct_only,
        }
        if return_date:
            route_query["return_date"] = return_date
        self._apply_filters(route_query)
        provider_names = self._provider_names_for_primary_offers(flow, route_query)
        if return_date:
            # Явно названный провайдер обходит отбор по возможностям — это
            # старое поведение и оно остаётся. Но круговой поиск обойти нельзя:
            # провайдер, который его не умеет, вернёт односторонние офферы и
            # выдача молча опустеет. Лучше сказать это вслух.
            provider_names = [
                name
                for name in provider_names
                if provider_supports_offer_query(name, route_query, self._store)
            ]
        queries: list[dict[str, Any]] = []
        seen: set[str] = set()
        for provider_name in provider_names:
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
            if return_date:
                query["return_date"] = return_date
            if route_family:
                query["route_family"] = route_family
            self._apply_filters(query)
            queries.append(query)
        if return_date and not queries:
            # Круговой поиск — возможность провайдера. Если её нет ни у кого из
            # выбранных, честнее сказать это, чем отдать пустую выдачу.
            raise CliError(
                "round-trip search is not supported by the selected providers; "
                "drop return_date or choose a provider that supports it",
                error_type="validation_error",
                details={"origin": origin, "destination": destination},
            )
        return queries

    def _apply_filters(self, query: dict[str, Any]) -> None:
        only_carriers = list(self._options.effective_only_carriers())
        if only_carriers:
            query["only_carriers"] = only_carriers
