from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..adapters.providers.registry import providers_for_route_query
from ..domain.vocabulary import RequiredControl
from ..pipeline.options import LiveAssemblyOptions
from ..pipeline.search_pipeline import LiveRouteSearchFlow, build_live_route_search_flow
from ..pipeline.search_plan import FallbackSegmentPlan, GatewayDiscovery, SearchPlan
from ..store import Store
from .route_plan_builder import RoutePlanBuilder

PRIMARY_OFFER_QUERY_LIMIT = 10
WESTERN_EUROPE_COUNTRY_CODES = frozenset(
    {
        "AD",
        "AT",
        "BE",
        "CH",
        "DE",
        "DK",
        "ES",
        "FI",
        "FR",
        "GB",
        "IE",
        "IS",
        "IT",
        "LI",
        "LU",
        "MC",
        "NL",
        "NO",
        "PT",
        "SE",
        "SM",
        "VA",
    }
)


def _country_code(store: Store, code: str) -> str | None:
    normalized = str(code or "").upper()
    try:
        location = store.resolve_location(normalized)
    except Exception:
        location = None
    if location is not None and getattr(location, "country_code", None):
        return str(location.country_code or "").upper()
    airport = store.airport_by_code.get(normalized)
    if airport and airport.get("country_code"):
        return str(airport.get("country_code") or "").upper()
    city = store.city_by_code.get(normalized)
    if city and city.get("country_code"):
        return str(city.get("country_code") or "").upper()
    return None


def _is_ru_to_western_europe_bridge(
    store: Store, origin: str, destination: str
) -> bool:
    countries = {
        _country_code(store, origin),
        _country_code(store, destination),
    }
    countries.discard(None)
    return "RU" in countries and bool(countries & WESTERN_EUROPE_COUNTRY_CODES)


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
            gateway_discovery=GatewayDiscovery(enabled=False, reason=None),
            fallback_segment_plan=FallbackSegmentPlan(
                segments=deepcopy(fallback_route_plan.get("segments") or [])
            ),
            coverage_expectations=self._coverage_expectations(
                fallback_route_plan, primary_offer_queries
            ),
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
        bridge_route = _is_ru_to_western_europe_bridge(
            self._store, origin, destination
        )

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
            if bridge_route:
                query["route_family"] = "ru_to_western_europe_bridge"
                query["exhaustive"] = False
                query["non_exhaustive_reason"] = (
                    "provider_full_route_aggregate_is_primary_collection_not_coverage_proof"
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
        origin = str(fallback_route_plan.get("origin") or "").upper()
        destination = str(fallback_route_plan.get("destination") or "").upper()
        if not _is_ru_to_western_europe_bridge(self._store, origin, destination):
            return []
        return [
            {
                "type": "primary_offer_collection_not_exhaustive",
                "route_family": "ru_to_western_europe_bridge",
                "source_type": "provider_full_route",
                "reason": "keep segment fallback coverage for RU to Western Europe bridge routes",
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
