from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from ..config import SPECIAL_CITY_AIRPORTS
from ..domain.gateway_discovery import GatewayDiscoveryService
from ..domain.normalize import normalize_carrier_code
from ..domain.vocabulary import Direction, Leg, RouteFamily
from ..errors import CliError
from ..execution.aggregate_control_runner import (
    AggregateControlOptions,
    evaluate_graph_coverage_controls,
    run_aggregate_controls,
)
from ..execution.gateway_leg_probe_executor import (
    GatewayLegProbeExecutor,
    GatewayLegProbeOptions,
)
from ..execution.offer_query_runner import (
    PrimaryOfferQueryOptions,
    run_primary_offer_queries,
)
from ..execution.probe_ledger import ProbeExecutionLedger
from ..execution.request_deduper import RequestDeduper
from ..execution.search_wave_planner import (
    SearchWavePlanner,
    SearchWavePlannerOptions,
)
from ..pipeline.decision_scorer import DecisionScorer, DecisionScorerOptions
from ..pipeline.offer_graph import (
    build_offer_graph as build_pipeline_offer_graph,
    materialize_offer_graph_candidates,
)
from ..pipeline.options import LiveAssemblyOptions
from ..pipeline.search_pipeline import LiveRouteSearchFlow, build_live_route_search_flow
from ..reporting.date_window_inventory import build_date_window_inventory
from ..store import Store
from .search_plan_builder import build_runtime_route_plan, build_search_plan


# Compatibility injection hook for tests and callers that patch
# ``flights_cli.orchestrators.live_assembly_runner.fetch_kupibilet_search``.
# Production keeps this as None so provider calls are resolved through the
# provider-port registry in ``execution.*``.
fetch_kupibilet_search: Any | None = None


@dataclass
class LiveAssemblyState:
    """Mutable state for one frontier-first live search run."""

    flow: LiveRouteSearchFlow
    plan: dict[str, Any]
    search_plan: dict[str, Any] = field(default_factory=dict)
    primary_offer_results: list[dict[str, Any]] = field(default_factory=list)
    gateway_leg_results: dict[str, Any] = field(default_factory=dict)
    direct_inventory_searches: list[dict[str, Any]] = field(default_factory=list)
    direct_inventory_results: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    probe_ledger: ProbeExecutionLedger = field(default_factory=ProbeExecutionLedger)
    planned_gateway_leg_queries: list[dict[str, Any]] = field(default_factory=list)
    direct_mode: dict[str, bool] = field(default_factory=dict)
    direct_presence_gate: dict[str, Any] = field(default_factory=dict)
    direct_mode_max_connections_by_direction: dict[str, int] = field(
        default_factory=dict
    )


@dataclass(frozen=True, slots=True)
class LiveSearchEvaluation:
    """Derived search data shared by fallback selection and final rendering."""

    offer_graph: dict[str, Any]
    aggregate_controls: list[dict[str, Any]]
    graph_controls: list[dict[str, Any]]
    gateway_discovery_diagnostics: dict[str, Any]
    offer_candidates: dict[str, Any]
    scored_decisions: dict[str, Any]
    date_window_inventory: dict[str, Any] | None

    @property
    def decision_frontier(self) -> dict[str, Any]:
        frontier = self.scored_decisions.get("decision_frontier")
        return frontier if isinstance(frontier, dict) else {}


def hub_viability_summary(
    plan: dict[str, Any],
    searches: list[dict[str, Any]] | None = None,
    gateway_leg_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gateways = (
        gateway_leg_results.get("gateways")
        if isinstance(gateway_leg_results, dict)
        else []
    )
    gateway_rows = [item for item in gateways or [] if isinstance(item, dict)]
    return {
        "hubs": list(plan.get("hubs") or []),
        "searched_gateways": int(gateway_leg_results.get("searched_gateways") or 0)
        if isinstance(gateway_leg_results, dict)
        else 0,
        "viable_gateways": int(gateway_leg_results.get("viable_gateways") or 0)
        if isinstance(gateway_leg_results, dict)
        else 0,
        "gateway_count": len(gateway_rows),
        "direct_inventory_probe_count": len(searches or []),
    }


def gateway_discovery_market_key(state: LiveAssemblyState) -> str:
    discovery = state.search_plan.get("gateway_discovery")
    if isinstance(discovery, dict) and discovery.get("prior_set"):
        return str(discovery.get("prior_set") or "")
    for query in state.search_plan.get("primary_offer_queries") or []:
        if isinstance(query, dict) and query.get("route_family"):
            return str(query.get("route_family") or "")
    for family in state.plan.get("route_families") or []:
        if isinstance(family, dict) and family.get("id"):
            return str(family.get("id") or "")
    return ""


def search_plan_with_gateway_discovery_output(
    search_plan: dict[str, Any], gateway_discovery_diagnostics: dict[str, Any]
) -> dict[str, Any]:
    diagnostics_plan = deepcopy(search_plan)
    discovery = (
        dict(diagnostics_plan.get("gateway_discovery"))
        if isinstance(diagnostics_plan.get("gateway_discovery"), dict)
        else {}
    )
    candidate_count = int(gateway_discovery_diagnostics.get("candidate_count") or 0)
    if candidate_count:
        discovery["candidate_count"] = candidate_count
        discovery["candidates"] = [
            dict(candidate)
            for candidate in gateway_discovery_diagnostics.get("candidates") or []
            if isinstance(candidate, dict)
        ]
    empty_reason = gateway_discovery_diagnostics.get("empty_reason")
    if empty_reason:
        discovery["empty_reason"] = str(empty_reason)
    skipped = [
        str(item)
        for item in gateway_discovery_diagnostics.get("skipped_reasons") or []
        if item
    ]
    if skipped:
        discovery["skipped_reasons"] = skipped
    if gateway_discovery_diagnostics.get("market") is not None:
        discovery["market"] = str(gateway_discovery_diagnostics.get("market") or "")
    if gateway_discovery_diagnostics.get("rejected_gateway_signals"):
        discovery["rejected_gateway_signals"] = [
            dict(item)
            for item in gateway_discovery_diagnostics.get("rejected_gateway_signals")
            or []
            if isinstance(item, dict)
        ]
    diagnostics_plan["gateway_discovery"] = discovery
    return diagnostics_plan


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


def _decision_options(decision_frontier: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in decision_frontier.get("options") or []
        if isinstance(item, dict)
    ]


def _candidate_ids(candidate_envelope: dict[str, Any]) -> list[str]:
    return [
        str(candidate.get("id"))
        for candidate in candidate_envelope.get("candidates") or []
        if isinstance(candidate, dict) and candidate.get("id")
    ]


def _normalize_direction(value: Any) -> str:
    direction = str(value or Direction.OUTBOUND).strip().lower()
    return Direction.RETURN if direction == Direction.RETURN else Direction.OUTBOUND


def _airport_set(*values: Any) -> set[str]:
    airports: set[str] = set()
    for value in values:
        code = str(value or "").strip().upper()
        if not code:
            continue
        airports.add(code)
        airports.update(
            str(item).upper() for item in SPECIAL_CITY_AIRPORTS.get(code, [])
        )
    return airports


def _requested_airport_pair(
    plan: dict[str, Any], direction: str
) -> tuple[set[str], set[str]]:
    origin = plan.get("origin")
    destination = plan.get("destination")
    origin_airports = (
        plan.get("origin_airports")
        if isinstance(plan.get("origin_airports"), list)
        else []
    )
    destination_airports = (
        plan.get("destination_airports")
        if isinstance(plan.get("destination_airports"), list)
        else []
    )
    if _normalize_direction(direction) == Direction.RETURN:
        return (
            _airport_set(destination, *destination_airports),
            _airport_set(origin, *origin_airports),
        )
    return (
        _airport_set(origin, *origin_airports),
        _airport_set(destination, *destination_airports),
    )


def _provider_result_offers(result: dict[str, Any]) -> list[Any]:
    for key in ("top_offers", "normalized_offers", "offers"):
        offers = result.get(key)
        if isinstance(offers, list):
            return offers
    normalized_result = result.get("normalized_result")
    if isinstance(normalized_result, dict):
        return _provider_result_offers(normalized_result)
    return []


def _offer_paths(
    offer: dict[str, Any], *, fallback_direction: str
) -> list[dict[str, Any]]:
    journeys = offer.get("journeys")
    paths: list[dict[str, Any]] = []
    if isinstance(journeys, list):
        for journey in journeys:
            if not isinstance(journey, dict):
                continue
            journey_segments = _segment_dicts(journey.get("segments"))
            if not journey_segments:
                continue
            paths.append(
                {
                    "direction": _normalize_direction(
                        journey.get("direction") or fallback_direction
                    ),
                    "segments": journey_segments,
                }
            )
    if paths:
        return paths
    segments = _segment_dicts(offer.get("segments"))
    if segments:
        return [
            {
                "direction": _normalize_direction(
                    offer.get("direction") or fallback_direction
                ),
                "segments": segments,
            }
        ]
    return []


def _segment_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [segment for segment in value if isinstance(segment, dict)]


def _segment_origin(segment: dict[str, Any]) -> str:
    return str(
        segment.get("origin")
        or segment.get("departure")
        or segment.get("from")
        or segment.get("departure_airport")
        or ""
    ).upper()


def _segment_destination(segment: dict[str, Any]) -> str:
    return str(
        segment.get("destination")
        or segment.get("arrival")
        or segment.get("to")
        or segment.get("arrival_airport")
        or ""
    ).upper()


def _path_has_requested_direct_segment(
    path: dict[str, Any],
    *,
    requested_origins: set[str],
    requested_destinations: set[str],
) -> bool:
    segments = path["segments"]
    if len(segments) != 1:
        return False
    segment = segments[0]
    return (
        _segment_origin(segment) in requested_origins
        and _segment_destination(segment) in requested_destinations
    )


def _direct_evidence_by_direction(
    plan: dict[str, Any], primary_offer_results: list[dict[str, Any]]
) -> dict[str, bool]:
    evidence = {Direction.OUTBOUND: False}
    if (plan.get("dates") or {}).get("return"):
        evidence[Direction.RETURN] = False
    for result in primary_offer_results:
        if not isinstance(result, dict):
            continue
        direction = _normalize_direction(result.get("direction"))
        for offer in _provider_result_offers(result):
            if not isinstance(offer, dict):
                continue
            for path in _offer_paths(offer, fallback_direction=direction):
                path_direction = _normalize_direction(path.get("direction"))
                if path_direction not in evidence:
                    continue
                requested_origins, requested_destinations = _requested_airport_pair(
                    plan, path_direction
                )
                if path_direction == direction:
                    requested_origins.update(_airport_set(result.get("origin")))
                    requested_destinations.update(
                        _airport_set(result.get("destination"))
                    )
                if _path_has_requested_direct_segment(
                    path,
                    requested_origins=requested_origins,
                    requested_destinations=requested_destinations,
                ):
                    evidence[path_direction] = True
    return evidence


def _direct_mode_disabled_reason(options: LiveAssemblyOptions) -> str | None:
    if (
        options.route.max_connections is not None
        and int(options.route.max_connections) >= 1
    ):
        return "max_connections_override"
    return None


def _direct_mode_from_primary_results(
    options: LiveAssemblyOptions,
    plan: dict[str, Any],
    primary_offer_results: list[dict[str, Any]],
) -> tuple[dict[str, bool], dict[str, Any]]:
    evidence = _direct_evidence_by_direction(plan, primary_offer_results)
    disabled_reason = _direct_mode_disabled_reason(options)
    if disabled_reason:
        direct_mode = {direction: False for direction in evidence}
    else:
        direct_mode = {
            direction: bool(present) for direction, present in evidence.items()
        }
    return direct_mode, {
        "schema_version": "flight_direct_presence_gate.v1",
        "direct_evidence_present": dict(evidence),
        "direct_mode": dict(direct_mode),
        "disabled_reason": disabled_reason,
        "source": "wave0_primary_offer_results",
    }


def _query_in_direct_mode(query: dict[str, Any], direct_mode: dict[str, bool]) -> bool:
    direction = _normalize_direction(query.get("direction"))
    return bool(direct_mode.get(direction))


def _filter_gateway_queries_for_direct_mode(
    queries: list[dict[str, Any]],
    direct_mode: dict[str, bool],
    probe_ledger: ProbeExecutionLedger,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for query in queries:
        if not isinstance(query, dict):
            continue
        if _query_in_direct_mode(query, direct_mode):
            skipped.append(query)
            probe_ledger.record_skipped(query, reason="direct_mode")
            continue
        kept.append(query)
    return kept, skipped


def _fallback_directions_from_frontier(
    decision_frontier: dict[str, Any], direct_mode: dict[str, bool]
) -> list[str]:
    coverage = (
        decision_frontier.get("coverage_summary")
        if isinstance(decision_frontier.get("coverage_summary"), dict)
        else {}
    )
    if int(coverage.get("acceptable_count") or 0) > 0:
        return []
    if int(coverage.get("direct_option_count") or 0) <= 0:
        return []
    by_direction = (
        coverage.get("direct_option_count_by_direction")
        if isinstance(coverage.get("direct_option_count_by_direction"), dict)
        else {}
    )
    return [
        direction
        for direction, enabled in direct_mode.items()
        if enabled and int(by_direction.get(direction) or 0) > 0
    ]


def _merge_gateway_leg_results(
    base: dict[str, Any], fallback: dict[str, Any]
) -> dict[str, Any]:
    if not base:
        return fallback
    if not fallback:
        return base
    merged = deepcopy(base)
    merged["gateways"] = [
        *(base.get("gateways") or []),
        *(fallback.get("gateways") or []),
    ]
    for key in (
        "searched_gateways",
        "viable_gateways",
        "failed_gateways",
        "not_searched_budget",
    ):
        merged[key] = int(base.get(key) or 0) + int(fallback.get(key) or 0)
    diagnostics = deepcopy(base.get("wave_diagnostics") or {})
    fallback_diagnostics = fallback.get("wave_diagnostics")
    if isinstance(fallback_diagnostics, dict):
        diagnostics["direct_mode_fallback"] = fallback_diagnostics
    if diagnostics:
        merged["wave_diagnostics"] = diagnostics
    return merged


def _effective_hard_max_connections(options: LiveAssemblyOptions) -> int:
    if options.route.tier2_max_connections is not None:
        return max(0, int(options.route.tier2_max_connections))
    if options.route.max_connections is not None:
        return max(0, int(options.route.max_connections))
    return 2


def _preferred_max_connections(options: LiveAssemblyOptions) -> int:
    if options.route.max_connections is not None:
        return max(0, int(options.route.max_connections))
    return 1


def _wave_diagnostics(gateway_leg_results: dict[str, Any]) -> dict[str, Any]:
    diagnostics = gateway_leg_results.get("wave_diagnostics")
    return deepcopy(diagnostics) if isinstance(diagnostics, dict) else {}


class LiveSearchResultBuilder:
    def __init__(
        self, *, options: LiveAssemblyOptions, store: Store, provider_policy: str
    ) -> None:
        self.options = options
        self.store = store
        self.provider_policy = provider_policy

    def evaluate(self, state: LiveAssemblyState) -> LiveSearchEvaluation:
        offer_graph = build_pipeline_offer_graph(
            primary_offer_results=state.primary_offer_results,
            gateway_leg_results=state.gateway_leg_results,
            direct_mode=state.direct_mode,
            requested_origin=str(state.plan.get("origin") or ""),
            requested_destination=str(state.plan.get("destination") or ""),
        )
        aggregate_controls = run_aggregate_controls(
            AggregateControlOptions(
                provider_policy=self.provider_policy,
                aggregate_control_limit=self.options.evidence.aggregate_control_limit,
                only_carriers=self.options.effective_only_carriers(),
                aggregate_control_carriers=self.options.evidence.aggregate_control_carriers,
                live_cache_ttl_seconds=self.options.evidence.live_cache_ttl_seconds,
                no_live_cache=self.options.evidence.no_live_cache,
                timeout=self.options.evidence.timeout,
            ),
            state.plan,
            kupibilet_fetcher=fetch_kupibilet_search,
            probe_ledger=state.probe_ledger,
            store=self.store,
            offer_graph=offer_graph,
        )
        graph_controls = evaluate_graph_coverage_controls(
            state.plan,
            offer_graph,
            probe_ledger=state.probe_ledger,
        )
        gateway_discovery_diagnostics: dict[str, Any] = {}
        GatewayDiscoveryService(self.store).discover(
            gateway_discovery_market_key(state),
            provider_results=[*state.primary_offer_results, *aggregate_controls],
            diagnostics=gateway_discovery_diagnostics,
        )
        state.probe_ledger.finalize_unexecuted()
        offer_candidates = materialize_offer_graph_candidates(
            offer_graph,
            direct_only=bool(state.flow.evidence_plan.direct_only),
            direct_mode=state.direct_mode,
            requested_origin=str(state.plan.get("origin") or ""),
            requested_destination=str(state.plan.get("destination") or ""),
        )
        scored_decisions = DecisionScorer(
            DecisionScorerOptions(
                round_trip=bool((state.plan.get("dates") or {}).get("return")),
                max_connections_per_journey=_effective_hard_max_connections(
                    self.options
                ),
                max_connections_per_direction=(
                    state.direct_mode_max_connections_by_direction
                ),
                preferred_connections=_preferred_max_connections(self.options),
                min_same_airport_connection_min=self.options.route.min_same_airport_min,
                min_cross_airport_connection_min=self.options.route.min_cross_airport_min,
            )
        ).score(
            offer_candidates,
            controls=[*graph_controls, *aggregate_controls],
        )
        state.direct_inventory_searches = _primary_direct_inventory_searches(
            state.primary_offer_results
        )
        state.direct_inventory_results = _primary_direct_inventory_results(
            state.primary_offer_results
        )
        date_window_inventory = build_date_window_inventory(
            state.plan,
            state.direct_inventory_searches,
            state.direct_inventory_results,
        )
        return LiveSearchEvaluation(
            offer_graph=offer_graph,
            aggregate_controls=aggregate_controls,
            graph_controls=graph_controls,
            gateway_discovery_diagnostics=gateway_discovery_diagnostics,
            offer_candidates=offer_candidates,
            scored_decisions=scored_decisions,
            date_window_inventory=date_window_inventory,
        )

    def build_route_trace(
        self,
        state: LiveAssemblyState,
        evaluation: LiveSearchEvaluation | None = None,
    ) -> dict[str, Any]:
        evaluated = evaluation or self.evaluate(state)
        decision_frontier = evaluated.decision_frontier
        mixed_candidate_ranking = evaluated.scored_decisions["mixed_candidate_ranking"]
        coverage = (
            decision_frontier.get("coverage_summary")
            if isinstance(decision_frontier.get("coverage_summary"), dict)
            else {}
        )
        route_trace: dict[str, Any] = {
            "schema_version": "flight_route_trace_diagnostic.v1",
            "origin": state.plan.get("origin"),
            "destination": state.plan.get("destination"),
            "dates": deepcopy(state.plan.get("dates") or {}),
            "currency": state.plan.get("currency"),
            "count": len(_decision_options(decision_frontier)),
            "decision_frontier": decision_frontier,
            "assembly": {
                "source": "decision_frontier",
                "direct_mode": dict(state.direct_mode),
                "candidate_count": int(coverage.get("candidate_count") or 0),
                "ranked_total_count": int(coverage.get("candidate_count") or 0),
                "ranked_output_count": len(_decision_options(decision_frontier)),
                "candidate_pool_truncated": False,
            },
            "live_search": {
                "source": "frontier-first provider search",
                "provider_policy": self.provider_policy,
                "note": "Provider offers are shopping evidence; verify final fare, baggage, and ticket protection on the booking screen.",
                "plan": deepcopy(state.plan),
                "output": {
                    "catalog_limit": self.options.output.catalog_limit,
                    "direct_catalog_limit": self.options.output.direct_catalog_limit,
                },
                "segment_searches": state.direct_inventory_searches,
                "hub_viability": hub_viability_summary(
                    state.plan,
                    state.direct_inventory_searches,
                    state.gateway_leg_results,
                ),
                "primary_offer_results": state.primary_offer_results,
                "gateway_leg_results": state.gateway_leg_results,
                "offer_graph": evaluated.offer_graph,
                "candidate_input_ids": _candidate_ids(evaluated.offer_candidates),
                "decision_scorer": evaluated.scored_decisions["scorer"],
                "mixed_candidate_ranking": mixed_candidate_ranking,
                "policy_controls": evaluated.graph_controls,
                "aggregate_controls": evaluated.aggregate_controls,
                "probe_ledger": state.probe_ledger.to_coverage_diagnostics(state.plan),
                "direct_presence_gate": deepcopy(state.direct_presence_gate),
                "diagnostics": {
                    "search_plan": search_plan_with_gateway_discovery_output(
                        state.search_plan,
                        evaluated.gateway_discovery_diagnostics,
                    ),
                    "wave_diagnostics": _wave_diagnostics(state.gateway_leg_results),
                },
                "failure_count": len(state.failures),
                "failures": state.failures,
            },
        }
        if evaluated.date_window_inventory is not None:
            route_trace["live_search"]["date_window_inventory"] = (
                evaluated.date_window_inventory
            )
        return route_trace

    def build(
        self,
        state: LiveAssemblyState,
        evaluation: LiveSearchEvaluation | None = None,
    ) -> dict[str, Any]:
        return self.build_route_trace(state, evaluation)


class LiveAssemblyRunner:
    """Frontier-first live search orchestrator."""

    def __init__(self, options: LiveAssemblyOptions, store: Store) -> None:
        self.options = options
        self.store = store
        self.state: LiveAssemblyState | None = None
        self.max_searches: int = 0
        self.only_carriers: list[str] = []
        self.cache_ttl_seconds: int = 0
        self.use_live_cache: bool = False
        self.provider_policy: str = ""
        self.request_deduper = RequestDeduper()
        self.gateway_leg_probe_executor: GatewayLegProbeExecutor | None = None
        self.search_wave_planner: SearchWavePlanner | None = None
        self.result_builder: LiveSearchResultBuilder | None = None

    def run(self) -> dict[str, Any]:
        state = self.initialize_state()
        assert self.result_builder is not None
        state.primary_offer_results = run_primary_offer_queries(
            [
                {**query, "wave_index": 0}
                for query in list(state.search_plan.get("primary_offer_queries") or [])
            ],
            PrimaryOfferQueryOptions(
                live_cache_ttl_seconds=self.cache_ttl_seconds,
                no_live_cache=not self.use_live_cache,
                timeout=self.options.evidence.timeout,
            ),
            store=self.store,
            kupibilet_fetcher=fetch_kupibilet_search,
            probe_ledger=state.probe_ledger,
        )
        state.direct_mode, state.direct_presence_gate = (
            _direct_mode_from_primary_results(
                self.options,
                state.plan,
                state.primary_offer_results,
            )
        )
        gateway_queries, skipped_gateway_queries = (
            _filter_gateway_queries_for_direct_mode(
                list(state.planned_gateway_leg_queries),
                state.direct_mode,
                state.probe_ledger,
            )
        )
        state.search_plan["gateway_leg_queries"] = gateway_queries
        state.direct_presence_gate["skipped_gateway_probe_count"] = len(
            skipped_gateway_queries
        )
        if self.search_wave_planner is not None:
            state.gateway_leg_results = self.search_wave_planner.run(
                gateway_queries,
                state.plan,
            )
        evaluation = self.result_builder.evaluate(state)
        fallback_directions = _fallback_directions_from_frontier(
            evaluation.decision_frontier,
            state.direct_mode,
        )
        if fallback_directions and self.gateway_leg_probe_executor is not None:
            fallback_queries = [
                query
                for query in state.planned_gateway_leg_queries
                if _normalize_direction(query.get("direction"))
                in set(fallback_directions)
            ]
            if fallback_queries:
                for direction in fallback_directions:
                    state.direct_mode[direction] = False
                    state.direct_mode_max_connections_by_direction[direction] = 1
                for query in fallback_queries:
                    state.probe_ledger.reopen_for_execution(query)
                remaining_budget = max(
                    0,
                    self.max_searches
                    - len(state.search_plan.get("primary_offer_queries") or []),
                )
                fallback_planner = SearchWavePlanner(
                    options=SearchWavePlannerOptions(
                        max_waves=1,
                        probes_per_wave=min(
                            max(1, self.options.evidence.search_wave_probe_limit),
                            max(1, remaining_budget),
                        ),
                        max_segment_searches=remaining_budget,
                        top_k_partial_paths=self.options.evidence.search_wave_top_k,
                        timeout_seconds=self.options.evidence.timeout,
                    ),
                    executor=self.gateway_leg_probe_executor,
                )
                fallback_results = fallback_planner.run(fallback_queries, state.plan)
                state.gateway_leg_results = _merge_gateway_leg_results(
                    state.gateway_leg_results, fallback_results
                )
                evaluation = self.result_builder.evaluate(state)
                state.direct_presence_gate["fallback"] = {
                    "status": "executed",
                    "reason": "direct_mode_no_acceptable_candidates",
                    "directions": fallback_directions,
                    "max_connections_per_journey": 1,
                    "max_connections_per_direction": {
                        direction: 1 for direction in fallback_directions
                    },
                    "wave_count": 1,
                }
            else:
                state.direct_presence_gate["fallback"] = {
                    "status": "no_gateway_leg_queries",
                    "reason": "direct_mode_no_acceptable_candidates",
                    "directions": fallback_directions,
                    "max_connections_per_journey": 1,
                    "max_connections_per_direction": {
                        direction: 1 for direction in fallback_directions
                    },
                }
        elif fallback_directions:
            state.direct_presence_gate["fallback"] = {
                "status": "not_executed",
                "reason": "direct_mode_no_acceptable_candidates",
                "directions": fallback_directions,
                "max_connections_per_journey": 1,
                "max_connections_per_direction": {
                    direction: 1 for direction in fallback_directions
                },
            }
        return self.result_builder.build(state, evaluation)

    def initialize_state(self) -> LiveAssemblyState:
        flow = build_live_route_search_flow(self.options, self.store)
        plan = build_runtime_route_plan(self.options, flow, self.store)
        search_plan = build_search_plan(
            self.options,
            self.store,
            flow=flow,
            fallback_route_plan=plan,
        )
        planned_probe_count = len(search_plan.get("primary_offer_queries") or []) + len(
            search_plan.get("gateway_leg_queries") or []
        )
        self.max_searches = max(1, int(flow.evidence_plan.max_segment_searches))
        if planned_probe_count > self.max_searches:
            raise CliError(
                f"planned {planned_probe_count} provider probes exceeds --max-segment-searches {self.max_searches}",
                error_type="validation_error",
                details={
                    "planned": planned_probe_count,
                    "max_segment_searches": self.max_searches,
                },
            )
        plan["metrics"]["primary_offer_query_count"] = len(
            search_plan.get("primary_offer_queries") or []
        )
        plan["metrics"]["gateway_leg_query_count"] = len(
            search_plan.get("gateway_leg_queries") or []
        )
        self.state = LiveAssemblyState(
            flow=flow,
            plan=plan,
            search_plan=search_plan,
            planned_gateway_leg_queries=list(
                search_plan.get("gateway_leg_queries") or []
            ),
        )
        self.only_carriers = [
            normalize_carrier_code(code, "only-carrier")
            for code in self.options.effective_only_carriers()
        ]
        self.cache_ttl_seconds = int(flow.evidence_plan.live_cache_ttl_seconds)
        self.use_live_cache = bool(flow.evidence_plan.live_cache_enabled)
        self.provider_policy = flow.evidence_plan.provider_policy
        self.request_deduper = RequestDeduper()
        self.gateway_leg_probe_executor = GatewayLegProbeExecutor(
            options=GatewayLegProbeOptions(
                gateway_discovery_limit=self.options.route.gateway_discovery_limit,
                gateway_probe_batch_size=self.options.route.gateway_probe_batch_size,
                gateway_probe_max_batches=self.options.route.gateway_probe_max_batches,
                segment_limit=self.options.evidence.segment_limit,
                timeout=self.options.evidence.timeout,
                fli_mcp_url=self.options.evidence.fli_mcp_url,
                fail_fast=self.options.evidence.fail_fast,
            ),
            store=self.store,
            only_carriers=self.only_carriers,
            cache_ttl_seconds=self.cache_ttl_seconds,
            use_live_cache=self.use_live_cache,
            kupibilet_fetcher=fetch_kupibilet_search,
            request_deduper=self.request_deduper,
            probe_ledger=self.state.probe_ledger,
        )
        self.search_wave_planner = SearchWavePlanner(
            options=SearchWavePlannerOptions(
                max_waves=self.options.evidence.search_wave_max_waves,
                probes_per_wave=self.options.evidence.search_wave_probe_limit,
                max_segment_searches=self.max_searches,
                top_k_partial_paths=self.options.evidence.search_wave_top_k,
                timeout_seconds=self.options.evidence.timeout,
            ),
            executor=self.gateway_leg_probe_executor,
        )
        self.result_builder = LiveSearchResultBuilder(
            options=self.options,
            store=self.store,
            provider_policy=self.provider_policy,
        )
        return self.state
