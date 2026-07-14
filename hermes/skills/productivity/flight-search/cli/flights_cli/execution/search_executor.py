from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from ..domain.gateway_discovery import GatewayDiscoveryService
from ..domain.immutable import thaw
from ..domain.normalize import normalize_carrier_code
from ..domain.vocabulary import Direction, Leg, RouteFamily
from ..errors import CliError
from .aggregate_control_runner import (
    AggregateControlOptions,
    evaluate_graph_coverage_controls,
    run_aggregate_controls,
)
from .gateway_leg_probe_executor import (
    GatewayLegProbeExecutor,
    GatewayLegProbeOptions,
)
from .offer_query_runner import (
    PrimaryOfferQueryOptions,
    run_primary_offer_queries,
)
from .probe_ledger import ProbeExecutionLedger
from .probe_intent import intent_from_aggregate_query
from .request_deduper import RequestDeduper
from .search_wave_planner import (
    SearchWavePlanner,
    SearchWavePlannerOptions,
)
from .search_evidence import SearchEvidence
from ..pipeline.decision_scorer import DecisionScorer, DecisionScorerOptions
from ..pipeline.offer_graph import (
    build_offer_graph as build_pipeline_offer_graph,
    materialize_offer_graph_candidates,
)
from ..pipeline.search_request import SearchRequest
from ..reporting.date_window_inventory import build_date_window_inventory
from ..store import Store
from ..orchestrators.search_plan_builder import (
    build_planning_state,
    build_search_plan,
)


# Test injection hook. Production provider calls are resolved through the
# provider-port registry in ``execution.*``.
fetch_kupibilet_search: Any | None = None


@dataclass
class SearchExecutionState:
    """Mutable state for one frontier-first live search run."""

    search_plan: dict[str, Any]
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

    @property
    def route_context(self) -> dict[str, Any]:
        context = self.search_plan.get("route_context")
        return context if isinstance(context, dict) else {}


@dataclass(frozen=True, slots=True)
class SearchDecision:
    """Pure decision artifacts derived after evidence freeze."""

    offer_graph: dict[str, Any]
    graph_controls: list[dict[str, Any]]
    offer_candidates: dict[str, Any]
    scored_decisions: dict[str, Any]

    @property
    def decision_frontier(self) -> dict[str, Any]:
        frontier = self.scored_decisions.get("decision_frontier")
        return frontier if isinstance(frontier, dict) else {}


@dataclass(frozen=True, slots=True)
class SearchRunArtifacts:
    plan: dict[str, Any]
    evidence: SearchEvidence
    decision: SearchDecision
    projection_input: dict[str, Any]


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


def gateway_discovery_market_key(state: SearchExecutionState) -> str:
    discovery = state.search_plan.get("gateway_discovery")
    if isinstance(discovery, dict) and discovery.get("prior_set"):
        return str(discovery.get("prior_set") or "")
    for query in state.search_plan.get("primary_offer_queries") or []:
        if isinstance(query, dict) and query.get("route_family"):
            return str(query.get("route_family") or "")
    for family in state.route_context.get("route_families") or []:
        if isinstance(family, dict) and family.get("id"):
            return str(family.get("id") or "")
    return ""


def search_plan_with_gateway_discovery_output(
    search_plan: dict[str, Any], gateway_discovery_diagnostics: dict[str, Any]
) -> dict[str, Any]:
    diagnostics_plan = thaw(search_plan)
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
    for key in ("offers", "top_offers"):
        offers = result.get(key)
        if isinstance(offers, list):
            return offers
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


def _direct_mode_disabled_reason(options: SearchRequest) -> str | None:
    return None


def _direct_mode_from_primary_results(
    options: SearchRequest,
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


def _partition_gateway_queries(
    queries: list[dict[str, Any]],
    fallback_directions: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fallback = set(fallback_directions)
    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for query in queries:
        if not isinstance(query, dict):
            continue
        target = (
            kept
            if _normalize_direction(query.get("direction")) in fallback
            else skipped
        )
        target.append(query)
    return kept, skipped


def assess_fallback(
    primary_offer_results: list[dict[str, Any]],
    direct_mode: dict[str, bool],
) -> list[str]:
    """Assess fallback from primary evidence without graph/scoring side effects."""

    evidence_directions: set[str] = set()
    for result in primary_offer_results:
        if not isinstance(result, dict):
            continue
        fallback_direction = _normalize_direction(result.get("direction"))
        for offer in _provider_result_offers(result):
            if not isinstance(offer, dict):
                continue
            for path in _offer_paths(offer, fallback_direction=fallback_direction):
                segments = path.get("segments") or []
                if segments and all(
                    all(
                        segment.get(field)
                        for field in (
                            "origin",
                            "destination",
                            "departure_at",
                            "arrival_at",
                        )
                    )
                    for segment in segments
                    if isinstance(segment, dict)
                ):
                    evidence_directions.add(_normalize_direction(path.get("direction")))
    return [
        direction for direction in direct_mode if direction not in evidence_directions
    ]


def _effective_hard_max_connections(options: SearchRequest) -> int:
    if options.route.tier2_max_connections is not None:
        return max(0, int(options.route.tier2_max_connections))
    if options.route.max_connections is not None:
        return max(0, int(options.route.max_connections))
    return 2


def _preferred_max_connections(options: SearchRequest) -> int:
    if options.route.max_connections is not None:
        return max(0, int(options.route.max_connections))
    return 1


def _wave_diagnostics(gateway_leg_results: dict[str, Any]) -> dict[str, Any]:
    diagnostics = gateway_leg_results.get("wave_diagnostics")
    return deepcopy(diagnostics) if isinstance(diagnostics, dict) else {}


def _aggregate_candidates(
    controls: tuple[dict[str, Any], ...], *, round_trip: bool
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for control_index, control in enumerate(controls):
        direction = _normalize_direction(control.get("direction")) or "outbound"
        provider = str(control.get("provider") or "provider")
        for offer_index, offer in enumerate(control.get("top_offers") or []):
            if not isinstance(offer, dict):
                continue
            segments = [
                {**segment, "direction": segment.get("direction") or direction}
                for segment in offer.get("segments") or []
                if isinstance(segment, dict)
            ]
            journeys = [
                journey
                for journey in offer.get("journeys") or []
                if isinstance(journey, dict)
            ]
            if not journeys and segments:
                journeys = [{"direction": direction, "segments": segments}]
            directions = {
                _normalize_direction(journey.get("direction")) for journey in journeys
            }
            covers_requested_trip = not round_trip or {
                "outbound",
                "return",
            }.issubset(directions)
            candidate = {
                **deepcopy(offer),
                "id": str(offer.get("id") or "")
                or f"aggregate:{provider}:{control_index}:{offer_index}",
                "source_type": "provider_full_route",
                "provider": provider,
                "source_providers": [provider],
                "journeys": journeys,
                "segments": segments,
                "covers_requested_trip": covers_requested_trip,
                "journey_scope": "round_trip"
                if covers_requested_trip and round_trip
                else "one_way",
                "price": offer.get("price"),
                "currency": offer.get("currency"),
                "price_basis": "provider_offer_price"
                if offer.get("price") is not None
                else "unknown",
                "elapsed_min": offer.get("duration_min"),
                "ticketing_model": offer.get("ticketing_model") or "unknown",
                "evidence_sources": [
                    {
                        "provider": provider,
                        "probe_id": control.get("probe_id"),
                        "source_type": "provider_full_route",
                    }
                ],
            }
            candidates.append(candidate)
    return candidates


class SearchDecisionBuilder:
    def __init__(self, *, options: SearchRequest) -> None:
        self.options = options

    def evaluate(self, evidence: SearchEvidence) -> SearchDecision:
        offer_graph = build_pipeline_offer_graph(
            primary_offer_results=list(evidence.primary_offer_results),
            gateway_leg_results=evidence.gateway_leg_results,
            direct_mode=evidence.direct_mode,
            requested_origin=str(evidence.route_context.get("origin") or ""),
            requested_destination=str(evidence.route_context.get("destination") or ""),
            requested_origin_airports=list(
                evidence.route_context.get("origin_airports") or []
            ),
            requested_destination_airports=list(
                evidence.route_context.get("destination_airports") or []
            ),
        )
        graph_controls = evaluate_graph_coverage_controls(
            evidence.route_context,
            offer_graph,
        )
        offer_candidates = materialize_offer_graph_candidates(
            offer_graph,
            direct_only=bool(evidence.route_context.get("direct_only")),
            direct_mode=evidence.direct_mode,
            requested_origin=str(evidence.route_context.get("origin") or ""),
            requested_destination=str(evidence.route_context.get("destination") or ""),
            requested_origin_airports=list(
                evidence.route_context.get("origin_airports") or []
            ),
            requested_destination_airports=list(
                evidence.route_context.get("destination_airports") or []
            ),
        )
        offer_candidates["candidates"] = [
            *(
                candidate
                for candidate in offer_candidates.get("candidates") or []
                if isinstance(candidate, dict)
            ),
            *_aggregate_candidates(
                evidence.aggregate_controls,
                round_trip=bool(
                    (evidence.route_context.get("dates") or {}).get("return")
                ),
            ),
        ]
        scored_decisions = DecisionScorer(
            DecisionScorerOptions(
                round_trip=bool(
                    (evidence.route_context.get("dates") or {}).get("return")
                ),
                max_connections_per_journey=_effective_hard_max_connections(
                    self.options
                ),
                max_connections_per_direction=evidence.max_connections_by_direction,
                preferred_connections=_preferred_max_connections(self.options),
                min_same_airport_connection_min=self.options.route.min_same_airport_min,
                min_cross_airport_connection_min=self.options.route.min_cross_airport_min,
                max_options=(
                    self.options.output.direct_catalog_limit
                    if any(bool(value) for value in evidence.direct_mode.values())
                    else self.options.output.catalog_limit
                ),
            )
        ).score(
            offer_candidates,
            controls=[*graph_controls, *evidence.aggregate_controls],
        )
        return SearchDecision(
            offer_graph=offer_graph,
            graph_controls=graph_controls,
            offer_candidates=offer_candidates,
            scored_decisions=scored_decisions,
        )

    def build_projection_input(
        self,
        evidence: SearchEvidence,
        decision: SearchDecision,
    ) -> dict[str, Any]:
        decision_frontier = decision.decision_frontier
        mixed_candidate_ranking = decision.scored_decisions["mixed_candidate_ranking"]
        coverage = (
            decision_frontier.get("coverage_summary")
            if isinstance(decision_frontier.get("coverage_summary"), dict)
            else {}
        )
        route_trace: dict[str, Any] = {
            "schema_version": "flight_decision_projection_input.v1",
            "origin": evidence.route_context.get("origin"),
            "destination": evidence.route_context.get("destination"),
            "dates": thaw(evidence.route_context.get("dates") or {}),
            "currency": evidence.route_context.get("currency"),
            "count": len(_decision_options(decision_frontier)),
            "decision_frontier": thaw(decision_frontier),
            "assembly": {
                "source": "decision_frontier",
                "direct_mode": dict(evidence.direct_mode),
                "candidate_count": int(coverage.get("candidate_count") or 0),
                "ranked_total_count": int(coverage.get("candidate_count") or 0),
                "ranked_output_count": len(_decision_options(decision_frontier)),
                "candidate_pool_truncated": False,
            },
            "live_search": {
                "source": "frontier-first provider search",
                "provider_policy": evidence.provider_policy,
                "note": "Provider offers are shopping evidence; verify final fare, baggage, and ticket protection on the booking screen.",
                "plan": thaw(evidence.route_context),
                "output": {
                    "catalog_limit": self.options.output.catalog_limit,
                    "direct_catalog_limit": self.options.output.direct_catalog_limit,
                },
                "segment_searches": thaw(evidence.direct_inventory_searches),
                "hub_viability": hub_viability_summary(
                    evidence.route_context,
                    list(evidence.direct_inventory_searches),
                    evidence.gateway_leg_results,
                ),
                "primary_offer_results": thaw(evidence.primary_offer_results),
                "gateway_leg_results": thaw(evidence.gateway_leg_results),
                "offer_graph": thaw(decision.offer_graph),
                "candidate_input_ids": _candidate_ids(decision.offer_candidates),
                "decision_scorer": thaw(decision.scored_decisions["scorer"]),
                "mixed_candidate_ranking": thaw(mixed_candidate_ranking),
                "policy_controls": thaw(decision.graph_controls),
                "aggregate_controls": thaw(evidence.aggregate_controls),
                "probe_ledger": thaw(evidence.probe_ledger),
                "direct_presence_gate": thaw(evidence.direct_presence_gate),
                "diagnostics": {
                    "search_plan": search_plan_with_gateway_discovery_output(
                        evidence.search_plan,
                        evidence.observed_gateway_diagnostics,
                    ),
                    "wave_diagnostics": _wave_diagnostics(evidence.gateway_leg_results),
                },
                "failure_count": len(evidence.failures),
                "failures": thaw(evidence.failures),
            },
        }
        if evidence.date_window_inventory is not None:
            route_trace["live_search"]["date_window_inventory"] = thaw(
                evidence.date_window_inventory
            )
        return route_trace


class SearchExecutor:
    """Frontier-first live search orchestrator."""

    def __init__(self, options: SearchRequest, store: Store) -> None:
        self.options = options
        self.store = store
        self.state: SearchExecutionState | None = None
        self.max_searches: int = 0
        self.only_carriers: list[str] = []
        self.cache_ttl_seconds: int = 0
        self.use_live_cache: bool = False
        self.provider_policy: str = ""
        self.request_deduper = RequestDeduper()
        self.gateway_leg_probe_executor: GatewayLegProbeExecutor | None = None
        self.search_wave_planner: SearchWavePlanner | None = None
        self.decision_builder = SearchDecisionBuilder(options=options)

    def execute(self, plan: dict[str, Any]) -> SearchRunArtifacts:
        """Execute one prebuilt SearchPlan without replanning."""

        state = self.initialize_state(plan)
        planned_primary = list(state.search_plan.get("primary_offer_queries") or [])
        query_options = PrimaryOfferQueryOptions(
            live_cache_ttl_seconds=self.cache_ttl_seconds,
            no_live_cache=not self.use_live_cache,
            timeout=self.options.evidence.timeout,
        )
        direct_query_specs = [
            {**query, "wave_index": 0}
            for query in planned_primary
            if bool(query.get("direct_only"))
        ]
        direct_results = (
            run_primary_offer_queries(
                direct_query_specs,
                query_options,
                store=self.store,
                kupibilet_fetcher=fetch_kupibilet_search,
                probe_ledger=state.probe_ledger,
            )
            if direct_query_specs
            else []
        )
        state.direct_mode, state.direct_presence_gate = (
            _direct_mode_from_primary_results(
                self.options,
                state.route_context,
                direct_results,
            )
        )
        fallback_directions = [
            direction
            for direction, direct_present in state.direct_mode.items()
            if not direct_present
        ]
        fallback_queries = [
            {**query, "wave_index": 1}
            for query in planned_primary
            if not bool(query.get("direct_only"))
            and _normalize_direction(query.get("direction")) in fallback_directions
        ]
        for query in planned_primary:
            if bool(query.get("direct_only")):
                continue
            if _normalize_direction(query.get("direction")) in fallback_directions:
                continue
            state.probe_ledger.record_skipped(
                intent_from_aggregate_query(
                    query, provider=str(query.get("provider") or "") or None
                ),
                reason="direct_available",
            )
        fallback_results = run_primary_offer_queries(
            fallback_queries,
            query_options,
            store=self.store,
            kupibilet_fetcher=fetch_kupibilet_search,
            probe_ledger=state.probe_ledger,
        )
        state.primary_offer_results = [*direct_results, *fallback_results]
        if not direct_query_specs:
            state.direct_mode, state.direct_presence_gate = (
                _direct_mode_from_primary_results(
                    self.options,
                    state.route_context,
                    fallback_results,
                )
            )
            fallback_directions = [
                direction
                for direction, direct_present in state.direct_mode.items()
                if not direct_present
            ]
        successful_direct_directions = {
            _normalize_direction(result.get("direction"))
            for result in direct_results
            if str(result.get("execution_state") or "") == "searched"
        }
        state.direct_presence_gate["direct_search_confirmed"] = {
            direction: direction in successful_direct_directions
            for direction in state.direct_mode
        }
        gateway_queries, skipped_gateway_queries = _partition_gateway_queries(
            list(state.planned_gateway_leg_queries), fallback_directions
        )
        state.direct_presence_gate["skipped_gateway_probe_count"] = len(
            skipped_gateway_queries
        )
        if fallback_directions:
            if gateway_queries and self.search_wave_planner is not None:
                state.gateway_leg_results = self.search_wave_planner.run(
                    gateway_queries, state.route_context
                )
                state.direct_presence_gate["fallback"] = {
                    "status": "executed",
                    "reason": "direct_mode_no_acceptable_candidates",
                    "directions": fallback_directions,
                    "max_connections_per_journey": (
                        1
                        if state.direct_mode_max_connections_by_direction
                        else _effective_hard_max_connections(self.options)
                    ),
                    "max_connections_per_direction": dict(
                        state.direct_mode_max_connections_by_direction
                    ),
                    "wave_count": 1,
                }
            elif not gateway_queries:
                state.direct_presence_gate["fallback"] = {
                    "status": "no_gateway_leg_queries",
                    "reason": "direct_mode_no_acceptable_candidates",
                    "directions": fallback_directions,
                    "max_connections_per_journey": (
                        1
                        if state.direct_mode_max_connections_by_direction
                        else _effective_hard_max_connections(self.options)
                    ),
                    "max_connections_per_direction": dict(
                        state.direct_mode_max_connections_by_direction
                    ),
                }
        for query in skipped_gateway_queries:
            state.probe_ledger.record_skipped(query, reason="direct_available")

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
            state.route_context,
            planned_queries=list(state.search_plan.get("aggregate_queries") or []),
            kupibilet_fetcher=fetch_kupibilet_search,
            probe_ledger=state.probe_ledger,
            store=self.store,
            offer_graph=None,
        )
        observed_gateway_diagnostics: dict[str, Any] = {}
        GatewayDiscoveryService(self.store).discover(
            gateway_discovery_market_key(state),
            provider_results=[*state.primary_offer_results, *aggregate_controls],
            diagnostics=observed_gateway_diagnostics,
        )
        state.direct_inventory_searches = _primary_direct_inventory_searches(
            state.primary_offer_results
        )
        state.direct_inventory_results = _primary_direct_inventory_results(
            state.primary_offer_results
        )
        date_window_inventory = build_date_window_inventory(
            state.route_context,
            state.direct_inventory_searches,
            state.direct_inventory_results,
        )
        state.probe_ledger.finalize_unexecuted()
        evidence = SearchEvidence.freeze(
            search_plan=state.search_plan,
            provider_policy=self.provider_policy,
            primary_offer_results=state.primary_offer_results,
            gateway_leg_results=state.gateway_leg_results,
            aggregate_controls=aggregate_controls,
            observed_gateway_diagnostics=observed_gateway_diagnostics,
            probe_ledger=state.probe_ledger.to_coverage_diagnostics(
                state.route_context
            ),
            failures=state.failures,
            direct_mode=state.direct_mode,
            max_connections_by_direction=(
                state.direct_mode_max_connections_by_direction
            ),
            direct_presence_gate=state.direct_presence_gate,
            direct_inventory_searches=state.direct_inventory_searches,
            direct_inventory_results=state.direct_inventory_results,
            date_window_inventory=date_window_inventory,
        )
        decision = self.decision_builder.evaluate(evidence)
        return SearchRunArtifacts(
            plan=evidence.search_plan,
            evidence=evidence,
            decision=decision,
            projection_input=self.decision_builder.build_projection_input(
                evidence, decision
            ),
        )

    def initialize_state(self, search_plan: dict[str, Any]) -> SearchExecutionState:
        limits = (
            search_plan.get("execution_limits")
            if isinstance(search_plan.get("execution_limits"), dict)
            else {}
        )
        route_context = (
            search_plan.get("route_context")
            if isinstance(search_plan.get("route_context"), dict)
            else {}
        )
        planned_probe_count = len(search_plan.get("primary_offer_queries") or []) + len(
            search_plan.get("conditional_gateway_queries") or []
        )
        self.max_searches = max(1, int(limits.get("max_segment_searches") or 1))
        if planned_probe_count > self.max_searches:
            raise CliError(
                f"planned {planned_probe_count} provider probes exceeds --max-segment-searches {self.max_searches}",
                error_type="validation_error",
                details={
                    "planned": planned_probe_count,
                    "max_segment_searches": self.max_searches,
                },
            )
        self.state = SearchExecutionState(
            search_plan=search_plan,
            planned_gateway_leg_queries=list(
                search_plan.get("conditional_gateway_queries") or []
            ),
        )
        self.only_carriers = [
            normalize_carrier_code(code, "only-carrier")
            for code in self.options.effective_only_carriers()
        ]
        self.cache_ttl_seconds = int(limits.get("live_cache_ttl_seconds") or 0)
        self.use_live_cache = bool(limits.get("live_cache_enabled"))
        self.provider_policy = str(route_context.get("provider_policy") or "auto")
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
                max_waves=1,
                probes_per_wave=int(limits.get("search_wave_probe_limit") or 1),
                max_segment_searches=self.max_searches,
                top_k_partial_paths=int(limits.get("search_wave_top_k") or 1),
                timeout_seconds=int(limits.get("timeout") or 60),
            ),
            executor=self.gateway_leg_probe_executor,
        )
        return self.state


def execute_search(request: SearchRequest, store: Store) -> SearchRunArtifacts:
    flow = build_planning_state(request, store)
    plan = build_search_plan(request, store, flow=flow)
    return SearchExecutor(request, store).execute(plan)
