from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..config import KUPIBILET_CITY_CODE_FIRST_AIRPORTS
from ..domain.gateway_discovery import GatewayDiscoveryService
from ..domain.normalize import normalize_carrier_code
from ..domain.vocabulary import (
    Direction,
    EvidenceClass,
    IntentClass,
    Leg,
    RoutingStrategy,
    StopBucket,
)
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
from ..execution.probe_dispatcher import (
    SegmentProbeOptions,
    dispatch_segment_probe,
    search_key,
)
from ..execution.probe_intent import intent_from_control, intent_from_segment
from ..execution.probe_ledger import ProbeExecutionLedger
from ..execution.request_deduper import RequestDeduper
from ..execution.search_wave_planner import (
    SearchWavePlanner,
    SearchWavePlannerOptions,
)
from ..execution.synthetic_control_runner import (
    synthesize_moscow_gateway_control_results,
)
from ..pipeline.options import LiveAssemblyOptions
from ..pipeline.offer_graph import (
    build_offer_graph as build_pipeline_offer_graph,
    materialize_offer_graph_candidates,
)
from ..pipeline.decision_scorer import (
    DecisionScorer,
    DecisionScorerOptions,
)
from ..pipeline.search_pipeline import LiveRouteSearchFlow, build_live_route_search_flow
from .search_plan_builder import build_search_plan
from ..providers.route_intel import (
    load_or_refresh_svx_route_index,
    svx_direct_route_index_summary,
)
from ..reporting.date_window_projector import build_date_window_inventory
from ..services.agent_report import AgentReportOptions, attach_agent_report
from ..services.assembly import (
    assemble_direction,
    assemble_segment_results,
    assembly_options_from_live_options,
    direct_journeys,
    empty_assembled_result,
)
from ..store import Store


# Compatibility injection hook for tests and callers that patch
# ``flights_cli.orchestrators.live_assembly_runner.fetch_kupibilet_search``.
# Production keeps this as None so provider calls are resolved through the
# provider-port registry in ``execution.*``.
fetch_kupibilet_search: Any | None = None


class RoutePlanBuilderFn(Protocol):
    def __call__(
        self,
        options: LiveAssemblyOptions,
        store: Store,
        *,
        flow: LiveRouteSearchFlow | None = None,
    ) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Helper functions kept here to avoid a circular import.
# ---------------------------------------------------------------------------


def provider_city_code_side(spec: dict[str, Any], side: str) -> bool:
    city_code = str(spec.get("provider_city_code") or "").upper()
    if not city_code:
        return False
    code = str(spec.get(side) or "").upper()
    deferred_airports = {
        str(item).upper()
        for item in KUPIBILET_CITY_CODE_FIRST_AIRPORTS.get(city_code, [])
    }
    return code == city_code or code in deferred_airports


def endpoint_group_code(spec: dict[str, Any], side: str) -> str:
    if provider_city_code_side(spec, side):
        return str(spec.get("provider_city_code") or "").upper()
    return str(spec.get(side) or "").upper()


def city_code_primary_keys_for_deferred_airport(
    spec: dict[str, Any],
) -> list[tuple[str, str, str, str]]:
    if not spec.get("deferred_for_city_code_request"):
        return []
    city_code = str(spec.get("provider_city_code") or "").upper()
    deferred_airports = {
        str(item).upper()
        for item in KUPIBILET_CITY_CODE_FIRST_AIRPORTS.get(city_code, [])
    }
    if not city_code or not deferred_airports:
        return []
    direction = str(spec.get("direction") or "")
    leg = str(spec.get("leg") or "")
    origin = str(spec.get("origin") or "").upper()
    destination = str(spec.get("destination") or "").upper()
    keys: list[tuple[str, str, str, str]] = []
    if origin in deferred_airports:
        keys.append((direction, leg, city_code, destination))
    if destination in deferred_airports:
        keys.append((direction, leg, origin, city_code))
    return keys


def deferred_airport_priority_sides(
    spec: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    sides: list[tuple[str, dict[str, Any]]] = []
    for side in ("origin", "destination"):
        metadata = spec.get(f"{side}_airport_priority")
        if not isinstance(metadata, dict):
            continue
        tier = int(metadata.get("tier") or 0)
        role = str(metadata.get("role") or "").lower()
        if tier > 1 or role == "deferred":
            sides.append((side, metadata))
    return sides


def preferred_keys_for_deferred_airport(
    spec: dict[str, Any], plan: dict[str, Any]
) -> list[tuple[str, str, str, str]]:
    keys: list[tuple[str, str, str, str]] = []
    for priority_side, deferred_metadata in deferred_airport_priority_sides(spec):
        city_code = str(deferred_metadata.get("city_code") or "").upper()
        deferred_tier = int(deferred_metadata.get("tier") or 0)
        if not city_code or deferred_tier <= 1:
            continue
        other_side = "destination" if priority_side == "origin" else "origin"
        other_group = endpoint_group_code(spec, other_side)
        for candidate in plan.get("segments") or []:
            if not isinstance(candidate, dict) or candidate is spec:
                continue
            if str(candidate.get("direction") or "") != str(
                spec.get("direction") or ""
            ):
                continue
            if str(candidate.get("leg") or "") != str(spec.get("leg") or ""):
                continue
            if str(candidate.get("date") or "") != str(spec.get("date") or ""):
                continue
            if str(candidate.get("route_family") or "") != str(
                spec.get("route_family") or ""
            ):
                continue
            candidate_metadata = candidate.get(f"{priority_side}_airport_priority")
            if not isinstance(candidate_metadata, dict):
                continue
            if str(candidate_metadata.get("city_code") or "").upper() != city_code:
                continue
            if int(candidate_metadata.get("tier") or 0) >= deferred_tier:
                continue
            if endpoint_group_code(candidate, other_side) != other_group:
                continue
            keys.append(search_key(candidate))
    return keys


def plan_has_svx_direct_control(plan: dict[str, Any]) -> bool:
    for spec in plan.get("segments") or []:
        if not isinstance(spec, dict) or spec.get("leg") not in {
            Leg.DIRECT_OUTBOUND,
            Leg.DIRECT_RETURN,
        }:
            continue
        if (
            str(spec.get("origin") or "").upper() == "SVX"
            or str(spec.get("destination") or "").upper() == "SVX"
        ):
            return True
    return False


def direct_route_intel_context(
    options: LiveAssemblyOptions, store: Store, plan: dict[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if options.evidence.no_direct_route_intel:
        return None, {
            "enabled": False,
            "available": False,
            "reason": "disabled_by_flag",
        }
    ttl_seconds = int(options.evidence.direct_route_index_ttl_seconds)
    if ttl_seconds <= 0:
        return None, {"enabled": False, "available": False, "reason": "disabled_by_ttl"}
    if not plan_has_svx_direct_control(plan):
        return None, {
            "enabled": False,
            "available": False,
            "reason": "no_supported_svx_direct_control",
        }
    try:
        known_airports = set(store.airport_by_code)
        index, cache = load_or_refresh_svx_route_index(
            ttl_seconds=ttl_seconds,
            timeout=int(options.evidence.timeout),
            known_airports=known_airports or None,
            cache_dir=store.cache_dir / "route_intel",
        )
    except CliError as exc:
        return None, {
            "enabled": True,
            "available": False,
            "reason": "route_index_unavailable",
            "error": {"type": exc.error_type, "message": exc.message},
            StopBucket.TIER2: "direct-control live searches were kept because the official route index was unavailable.",
        }
    return index, svx_direct_route_index_summary(index, cache)


def direct_route_intel_skip_allowed(
    flow: LiveRouteSearchFlow | None,
    options: LiveAssemblyOptions | None,
) -> tuple[bool, str | None]:
    """Return whether the official route index may skip live direct probes.

    The SVX route index is advisory route intelligence. It can prune obvious
    fallback direct probes, but it must not replace live evidence when the
    request asks for proof of absence, ticketing, or hard-scoped controls.
    """

    if flow is None:
        return False, "flow_unavailable"
    if options is not None and options.route.date_window_end:
        return False, "date_window_direct_inventory"
    if flow.evidence_plan.direct_only:
        return False, "direct_only"
    if options is not None and (
        options.filters.only_carriers or options.filters.exclude_carriers
    ):
        return False, "hard_carrier_scope"
    if options is not None and (
        options.route.origin_airports or options.route.destination_airports
    ):
        return False, "hard_airport_scope"
    if options is not None and str(options.ticketing or "").lower() == "single":
        return False, IntentClass.TICKETING_PROOF
    if options is not None and options.evidence.coverage_controls:
        return False, "targeted_controls_required"
    if flow.flow_decision.intent_class != IntentClass.ROUTE_RECOMMENDATION:
        return False, "non_advisory_intent"
    if flow.flow_decision.evidence_class != EvidenceClass.SHOPPING_ADVISORY:
        return False, "non_advisory_evidence"
    return True, None


def hub_viability_summary(
    plan: dict[str, Any], searches: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_hub: dict[str, dict[str, Any]] = {
        hub: {
            "hub": hub,
            "viable": False,
            "total_offer_count": 0,
            "legs": {
                Leg.ORIGIN_TO_HUB: {"offer_count": 0, "search_count": 0, "dates": []},
                Leg.HUB_TO_DESTINATION: {
                    "offer_count": 0,
                    "search_count": 0,
                    "dates": [],
                },
                Leg.DESTINATION_TO_HUB: {
                    "offer_count": 0,
                    "search_count": 0,
                    "dates": [],
                },
                Leg.HUB_TO_ORIGIN: {"offer_count": 0, "search_count": 0, "dates": []},
            },
            "missing_legs": [],
        }
        for hub in plan["hubs"]
    }
    for search in searches:
        leg = search.get("leg")
        if leg == Leg.ORIGIN_TO_HUB:
            hub = search.get("destination")
        elif leg == Leg.HUB_TO_DESTINATION:
            hub = search.get("origin")
        elif leg == Leg.DESTINATION_TO_HUB:
            hub = search.get("destination")
        elif leg == Leg.HUB_TO_ORIGIN:
            hub = search.get("origin")
        else:
            continue
        if hub not in by_hub or leg not in by_hub[hub]["legs"]:
            continue
        leg_summary = by_hub[hub]["legs"][leg]
        leg_summary["search_count"] += 1
        leg_summary["offer_count"] += int(search.get("offer_count") or 0)
        date = search.get("date")
        if date and date not in leg_summary["dates"]:
            leg_summary["dates"].append(date)
        by_hub[hub]["total_offer_count"] += int(search.get("offer_count") or 0)

    required_legs = [Leg.ORIGIN_TO_HUB, Leg.HUB_TO_DESTINATION]
    if plan["dates"].get("return"):
        required_legs += [Leg.DESTINATION_TO_HUB, Leg.HUB_TO_ORIGIN]
    for item in by_hub.values():
        item["missing_legs"] = [
            leg for leg in required_legs if int(item["legs"][leg]["offer_count"]) <= 0
        ]
        item["viable"] = not item["missing_legs"]
    return sorted(
        by_hub.values(),
        key=lambda item: (
            not item["viable"],
            -int(item["total_offer_count"]),
            item["hub"],
        ),
    )


def gateway_discovery_market_key(state: "LiveAssemblyState") -> str:
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
    discovery.setdefault("enabled", False)
    discovery.setdefault("reason", None)
    discovery.setdefault("mode", "disabled")
    discovery.setdefault("route_access_profile", None)
    discovery.setdefault("route_access_reasons", [])

    candidate_count = int(gateway_discovery_diagnostics.get("candidate_count") or 0)
    candidates = [
        dict(candidate)
        for candidate in gateway_discovery_diagnostics.get("candidates") or []
        if isinstance(candidate, dict)
    ]
    empty_reason = gateway_discovery_diagnostics.get("empty_reason")
    if candidate_count == 0 and not empty_reason:
        empty_reason = (
            "gateway_discovery_disabled"
            if not bool(discovery.get("enabled"))
            else "no_gateway_candidates_discovered"
        )
    skipped_reasons = [
        str(item)
        for item in gateway_discovery_diagnostics.get("skipped_reasons") or []
        if item
    ]
    if candidate_count == 0 and empty_reason and not skipped_reasons:
        skipped_reasons = [str(empty_reason)]

    discovery["candidate_count"] = candidate_count
    discovery["candidates"] = candidates
    discovery["skipped_reasons"] = skipped_reasons
    discovery["empty_reason"] = empty_reason
    if gateway_discovery_diagnostics.get("market") is not None:
        discovery["market"] = str(gateway_discovery_diagnostics.get("market") or "")
    rejected = [
        dict(item)
        for item in gateway_discovery_diagnostics.get("rejected_gateway_signals") or []
        if isinstance(item, dict)
    ]
    if rejected:
        discovery["rejected_gateway_signals"] = rejected
    diagnostics_plan["gateway_discovery"] = discovery
    return diagnostics_plan


# ---------------------------------------------------------------------------
# LiveAssemblyRunner
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LiveAssemblyState:
    """Mutable state for one live route-assembly run."""

    flow: LiveRouteSearchFlow
    plan: dict[str, Any]
    search_plan: dict[str, Any] = field(default_factory=dict)
    primary_offer_results: list[dict[str, Any]] = field(default_factory=list)
    gateway_leg_results: dict[str, Any] = field(default_factory=dict)
    segment_results: list[dict[str, Any]] = field(default_factory=list)
    searches: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    offer_counts: dict[tuple[str, str, str, str], int] = field(default_factory=dict)
    probe_ledger: ProbeExecutionLedger = field(default_factory=ProbeExecutionLedger)
    synthetic_controls_done: set[str] = field(default_factory=set)
    priority_route_viability: dict[str, bool] = field(default_factory=dict)


class SyntheticControlService:
    def apply_pending(
        self, state: LiveAssemblyState, direction: str | None = None
    ) -> None:
        directions = {"outbound", "return"} if direction is None else {str(direction)}
        pending = directions - state.synthetic_controls_done
        if not pending:
            return
        state.synthetic_controls_done.update(pending)
        synthetic_results, synthetic_searches = (
            synthesize_moscow_gateway_control_results(
                state.plan,
                state.segment_results,
                directions=pending,
            )
        )
        state.segment_results.extend(synthetic_results)
        state.searches.extend(synthetic_searches)
        for search in synthetic_searches:
            key = (
                str(search.get("direction") or ""),
                str(search.get("leg") or ""),
                str(search.get("origin") or "").upper(),
                str(search.get("destination") or "").upper(),
            )
            state.offer_counts[key] = state.offer_counts.get(key, 0) + int(
                search.get("offer_count") or 0
            )


class PriorityRouteEvaluator:
    def __init__(
        self, options: LiveAssemblyOptions, synthetic_controls: SyntheticControlService
    ) -> None:
        self.options = options
        self.synthetic_controls = synthetic_controls

    def is_viable(self, state: LiveAssemblyState, direction: str) -> bool:
        if state.plan.get("routing_strategy") != RoutingStrategy.RU_PRIORITY:
            return False
        if direction in state.priority_route_viability:
            return state.priority_route_viability[direction]
        self.synthetic_controls.apply_pending(state, direction)
        if direction == Direction.OUTBOUND:
            first_leg = Leg.ORIGIN_TO_HUB
            second_leg = Leg.HUB_TO_DESTINATION
            direct_leg = Leg.DIRECT_OUTBOUND
        elif direction == Direction.RETURN:
            first_leg = Leg.DESTINATION_TO_HUB
            second_leg = Leg.HUB_TO_ORIGIN
            direct_leg = Leg.DIRECT_RETURN
        else:
            return False
        direct = direct_journeys(
            state.segment_results,
            direct_leg,
            direction,
            self.options.output.limit_per_pair,
            profile=self.options.profile,
        )
        if direct:
            state.priority_route_viability[direction] = True
            return True
        pairs, _ = assemble_direction(
            state.segment_results,
            first_leg,
            second_leg,
            direction,
            self.options.output.limit_per_pair,
            ticketing=self.options.ticketing,
            min_same_airport=self.options.route.min_same_airport_min,
            min_cross_airport=self.options.route.min_cross_airport_min,
            profile=self.options.profile,
        )
        viable = False
        for pair in pairs:
            offers = [
                offer for offer in (pair.get("offers") or []) if isinstance(offer, dict)
            ]
            if len(offers) < 2:
                continue
            hub = str(
                offers[0].get("arrival_airport") or offers[0].get("destination") or ""
            ).upper()
            next_origin = str(
                offers[1].get("departure_airport") or offers[1].get("origin") or ""
            ).upper()
            if hub != next_origin:
                continue
            if (pair.get("connection_quality") or {}).get("severity") != "error":
                viable = True
                break
        state.priority_route_viability[direction] = viable
        return viable


class SkipPolicy:
    def __init__(
        self,
        *,
        options: LiveAssemblyOptions,
        direct_route_index: dict[str, Any] | None,
        priority_route_evaluator: PriorityRouteEvaluator,
    ) -> None:
        self.options = options
        self.direct_route_index = direct_route_index
        self.priority_route_evaluator = priority_route_evaluator

    def skipped_by_offer_keys(
        self,
        state: LiveAssemblyState,
        spec: dict[str, Any],
        *,
        keys: list[tuple[str, str, str, str]],
        reason: str,
        note: str,
    ) -> dict[str, Any] | None:
        matched = [
            {
                "direction": key[0],
                "leg": key[1],
                "origin": key[2],
                "destination": key[3],
                "offer_count": state.offer_counts[key],
            }
            for key in keys
            if int(state.offer_counts.get(key, 0)) > 0
        ]
        if not matched:
            return None
        return {
            **spec,
            "status": "skipped",
            "reason": reason,
            "offer_count": 0,
            "skipped_because": {
                "matched_offer_counts": matched,
                "note": note,
            },
        }

    def skipped_by_preferred_airport_tier(
        self, state: LiveAssemblyState, spec: dict[str, Any]
    ) -> dict[str, Any] | None:
        return self.skipped_by_offer_keys(
            state,
            spec,
            keys=preferred_keys_for_deferred_airport(spec, state.plan),
            reason="preferred_airport_tier_has_offers",
            note="Fallback airport tier was deferred because a preferred airport tier already produced accepted offers.",
        )

    def skipped_by_city_code_primary(
        self, state: LiveAssemblyState, spec: dict[str, Any]
    ) -> dict[str, Any] | None:
        return self.skipped_by_offer_keys(
            state,
            spec,
            keys=city_code_primary_keys_for_deferred_airport(spec),
            reason="city_code_request_has_offers",
            note="Exact airport deferred probe was skipped because the provider city-code request already produced accepted offers.",
        )

    def skipped_by_direct_route_intel(
        self, state: LiveAssemblyState, spec: dict[str, Any]
    ) -> dict[str, Any] | None:
        if self.direct_route_index is None or spec.get("leg") not in {
            Leg.DIRECT_OUTBOUND,
            Leg.DIRECT_RETURN,
        }:
            return None
        skip_allowed, _ = direct_route_intel_skip_allowed(state.flow, self.options)
        if not skip_allowed:
            return None
        direct_route_index = self.direct_route_index
        routes = (
            direct_route_index.get("routes")
            if isinstance(direct_route_index.get("routes"), dict)
            else {}
        )
        origin = str(spec.get("origin") or "").upper()
        destination = str(spec.get("destination") or "").upper()
        if origin == "SVX":
            route_set = {str(code).upper() for code in (routes.get("outbound") or [])}
            checked_airport = destination
        elif destination == "SVX":
            route_set = {str(code).upper() for code in (routes.get("return") or [])}
            checked_airport = origin
        else:
            return None
        if checked_airport in route_set:
            return None
        return {
            **spec,
            "status": "skipped",
            "reason": "direct_route_schedule_negative",
            "offer_count": 0,
            "skipped_because": {
                "checked_airport": checked_airport,
                "airport": "SVX",
                "source": direct_route_index.get("source"),
                "fetched_at": direct_route_index.get("fetched_at"),
                "note": "Official SVX seasonal schedule has no direct route for this exact airport pair; hub routing is still checked.",
            },
        }

    def skipped_by_condition(
        self, state: LiveAssemblyState, spec: dict[str, Any]
    ) -> dict[str, Any] | None:
        direct_skip = self.skipped_by_direct_route_intel(state, spec)
        if direct_skip is not None:
            return direct_skip
        preferred_skip = self.skipped_by_preferred_airport_tier(state, spec)
        if preferred_skip is not None:
            return preferred_skip
        city_code_skip = self.skipped_by_city_code_primary(state, spec)
        if city_code_skip is not None:
            return city_code_skip
        condition = spec.get("skip_if_offer_exists")
        if not isinstance(condition, dict):
            priority_direction = spec.get("skip_if_priority_route_viable")
            if not priority_direction:
                return None
            direction = str(priority_direction)
            if not self.priority_route_evaluator.is_viable(state, direction):
                return None
            return {
                **spec,
                "status": "skipped",
                "reason": "priority_route_viable",
                "offer_count": 0,
                "skipped_because": {
                    "direction": direction,
                    "note": "Secondary fallback skipped because priority routing already produced a non-error journey.",
                },
            }
        key = (
            str(condition.get("direction") or ""),
            str(condition.get("leg") or ""),
            str(condition.get("origin") or "").upper(),
            str(condition.get("destination") or "").upper(),
        )
        if int(state.offer_counts.get(key, 0)) <= 0:
            return None
        return {
            **spec,
            "status": "skipped",
            "reason": "direct_probe_has_offers",
            "offer_count": 0,
            "skipped_because": {
                "direction": key[0],
                "leg": key[1],
                "origin": key[2],
                "destination": key[3],
                "offer_count": state.offer_counts[key],
            },
        }


class ProbeResultAccumulator:
    def __init__(self, only_carriers: list[str]) -> None:
        self.only_carriers = only_carriers

    def _search_summary(
        self, spec: dict[str, Any], summary: dict[str, Any]
    ) -> dict[str, Any]:
        enriched = dict(summary)
        for summary_field in (
            "direction",
            "leg",
            "origin",
            "destination",
            "date",
            "route_family",
            "priority",
            "only_carriers",
            "preferred_carriers",
            "coverage_control",
            "provider_request_strategy",
            "provider_city_code",
            "provider_city_code_deferred_airports",
            "deferred_for_city_code_request",
            "origin_airport_priority",
            "destination_airport_priority",
        ):
            if summary_field not in enriched and summary_field in spec:
                enriched[summary_field] = spec[summary_field]
        for summary_field in ("only_carriers", "preferred_carriers"):
            value = enriched.get(summary_field)
            if value is None:
                enriched[summary_field] = []
            elif isinstance(value, tuple):
                enriched[summary_field] = list(value)
        return enriched

    def record_skipped(
        self, state: LiveAssemblyState, spec: dict[str, Any], skipped: dict[str, Any]
    ) -> None:
        summary = self._search_summary(spec, skipped)
        state.searches.append(summary)
        self.record_segment_probe_summary(state, spec, summary)

    def record_outcome(
        self, state: LiveAssemblyState, spec: dict[str, Any], outcome: Any
    ) -> None:
        summary = self._search_summary(spec, outcome.summary)
        state.searches.append(summary)
        self.record_segment_probe_summary(
            state, spec, summary, provider_result=outcome.provider_result
        )
        if outcome.failure is not None:
            state.failures.append(outcome.failure)
            return
        segment_result = outcome.segment_result
        if segment_result is None:
            return
        key = search_key(spec)
        state.offer_counts[key] = state.offer_counts.get(key, 0) + len(
            segment_result.get("offers") or []
        )
        if outcome.include_segment_result and segment_result["offers"]:
            state.segment_results.append(segment_result)

    def record_segment_probe_summary(
        self,
        state: LiveAssemblyState,
        spec: dict[str, Any],
        summary: dict[str, Any],
        *,
        provider_result: Any | None = None,
    ) -> None:
        intent_spec = {
            **spec,
            "only_carriers": spec.get("only_carriers") or self.only_carriers,
        }
        intent = intent_from_segment(
            intent_spec,
            provider=summary.get("provider"),
            probe_id=summary.get("probe_id"),
        )
        status = summary.get("status")
        if status == "deduped":
            state.probe_ledger.record_deduped(
                intent, original_probe_id=summary.get("original_probe_id")
            )
            return
        state.probe_ledger.plan_intents([intent])
        if provider_result is not None:
            state.probe_ledger.record_provider_result(intent, provider_result)
            return
        if status == "skipped":
            state.probe_ledger.record_skipped(intent, reason=summary.get("reason"))
            return
        if status == "error":
            state.probe_ledger.record_failed(
                intent, provider=summary.get("provider"), error=summary.get("error")
            )
            return
        if status == "not_supported":
            state.probe_ledger.record_not_supported(
                intent, provider=summary.get("provider"), reason=summary.get("reason")
            )
            return
        state.probe_ledger.record_searched(
            intent,
            status=status or "ok",
            provider=summary.get("provider"),
            offer_count=summary.get("offer_count", 0),
            cache_status=summary.get("cache_status"),
        )


class SegmentProbeExecutor:
    def __init__(
        self,
        *,
        options: LiveAssemblyOptions,
        store: Store,
        only_carriers: list[str],
        cache_ttl_seconds: int,
        use_live_cache: bool,
        provider_policy: str,
        request_deduper: RequestDeduper,
        skip_policy: SkipPolicy,
        accumulator: ProbeResultAccumulator,
    ) -> None:
        self.options = options
        self.store = store
        self.only_carriers = only_carriers
        self.cache_ttl_seconds = cache_ttl_seconds
        self.use_live_cache = use_live_cache
        self.provider_policy = provider_policy
        self.request_deduper = request_deduper
        self.skip_policy = skip_policy
        self.accumulator = accumulator
        self.probe_options = SegmentProbeOptions(
            segment_limit=options.evidence.segment_limit,
            timeout=options.evidence.timeout,
            fli_mcp_url=options.evidence.fli_mcp_url,
            fail_fast=options.evidence.fail_fast,
        )

    def run(self, state: LiveAssemblyState) -> None:
        for spec in state.plan["segments"]:
            skipped = self.skip_policy.skipped_by_condition(state, spec)
            if skipped is not None:
                self.accumulator.record_skipped(state, spec, skipped)
                continue
            for outcome in dispatch_segment_probe(
                spec=spec,
                plan=state.plan,
                options=self.probe_options,
                store=self.store,
                only_carriers=self.only_carriers,
                cache_ttl_seconds=self.cache_ttl_seconds,
                use_live_cache=self.use_live_cache,
                provider_policy=self.provider_policy,
                kupibilet_fetcher=fetch_kupibilet_search,
                request_deduper=self.request_deduper,
            ):
                self.accumulator.record_outcome(state, spec, outcome)


class LiveSearchResultBuilder:
    def __init__(
        self, *, options: LiveAssemblyOptions, store: Store, provider_policy: str
    ) -> None:
        self.options = options
        self.store = store
        self.provider_policy = provider_policy

    def build(
        self, state: LiveAssemblyState, direct_route_intel: dict[str, Any]
    ) -> dict[str, Any]:
        routing_strategy = state.plan.get("routing_strategy")
        assembly_options = assembly_options_from_live_options(
            self.options, routing_strategy=routing_strategy
        )
        date_window_inventory = build_date_window_inventory(
            state.plan, state.searches, state.segment_results
        )
        assembled = (
            assemble_segment_results(state.segment_results, assembly_options)
            if state.segment_results
            else empty_assembled_result(assembly_options)
        )
        offer_graph = build_pipeline_offer_graph(
            primary_offer_results=state.primary_offer_results,
            gateway_leg_results=state.gateway_leg_results,
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
        )
        graph_controls = evaluate_graph_coverage_controls(
            state.plan,
            offer_graph,
            probe_ledger=state.probe_ledger,
        )
        graph_control_keys = {
            (
                control.get("type"),
                control.get("direction"),
                control.get("origin"),
                control.get("destination"),
                control.get("date"),
            )
            for control in graph_controls
        }
        for control in state.plan.get("coverage_controls") or []:
            if isinstance(control, dict) and control.get("type") == "city_pair_direct":
                control_key = (
                    control.get("type"),
                    control.get("direction"),
                    control.get("origin"),
                    control.get("destination"),
                    control.get("date"),
                )
                if control_key in graph_control_keys:
                    continue
                state.probe_ledger.plan_intents(
                    [intent_from_control(control, provider=self.provider_policy)]
                )
        state.probe_ledger.finalize_unexecuted()
        source_label = "Kupibilet frontend_search direct-only segment assembly"
        note = "Live aggregate source; recheck price/seat availability and whether segments can be ticketed together before purchase."
        if self.provider_policy != "kupibilet":
            source_label = "Provider-policy live segment assembly"
            note = "Kupibilet is used for Russia-touching segments; FLI MCP is used for non-Russia segments under auto policy. Recheck price/seat availability before purchase."
        gateway_discovery_diagnostics: dict[str, Any] = {}
        GatewayDiscoveryService(self.store).discover(
            gateway_discovery_market_key(state),
            provider_results=[*state.primary_offer_results, *aggregate_controls],
            diagnostics=gateway_discovery_diagnostics,
        )
        search_plan_diagnostics = search_plan_with_gateway_discovery_output(
            state.search_plan,
            gateway_discovery_diagnostics,
        )
        offer_candidates = materialize_offer_graph_candidates(
            offer_graph,
            direct_only=bool(state.flow.evidence_plan.direct_only),
            requested_origin=str(state.plan.get("origin") or ""),
            requested_destination=str(state.plan.get("destination") or ""),
        )
        scored_decisions = DecisionScorer(
            DecisionScorerOptions(
                round_trip=bool((state.plan.get("dates") or {}).get("return")),
                max_connections_per_journey=2,
                min_same_airport_connection_min=(
                    self.options.route.min_same_airport_min
                ),
                min_cross_airport_connection_min=(
                    self.options.route.min_cross_airport_min
                ),
            )
        ).score(
            offer_candidates,
            constraints=self.options.constraints.to_dict(),
            controls=[*graph_controls, *aggregate_controls],
        )
        mixed_candidate_ranking = scored_decisions["mixed_candidate_ranking"]
        decision_frontier = scored_decisions["decision_frontier"]
        assembled["live_search"] = {
            "source": source_label,
            "provider_policy": self.provider_policy,
            "note": note,
            "plan": {
                key: value for key, value in state.plan.items() if key != "segments"
            },
            "segment_searches": state.searches,
            "hub_viability": hub_viability_summary(state.plan, state.searches),
            "primary_offer_results": state.primary_offer_results,
            "gateway_leg_results": state.gateway_leg_results,
            "offer_graph": offer_graph,
            "offer_candidates": offer_candidates,
            "decision_scorer": scored_decisions["scorer"],
            "mixed_candidate_ranking": mixed_candidate_ranking,
            "decision_frontier": decision_frontier,
            "policy_controls": graph_controls,
            "aggregate_controls": aggregate_controls,
            "probe_ledger": state.probe_ledger.to_coverage_diagnostics(state.plan),
            "direct_route_intelligence": direct_route_intel,
            "diagnostics": {
                "search_plan": search_plan_diagnostics,
                "primary_offer_results": state.primary_offer_results,
                "gateway_leg_results": state.gateway_leg_results,
                "offer_graph": offer_graph,
                "offer_candidates": offer_candidates,
                "decision_scorer": scored_decisions["scorer"],
                "mixed_candidate_ranking": mixed_candidate_ranking,
                "decision_frontier": decision_frontier,
                "policy_controls": graph_controls,
                "gateway_discovery": gateway_discovery_diagnostics,
            },
            "failure_count": len(state.failures),
            "failures": state.failures,
            "included_segment_result_count": min(
                len(state.segment_results), self.options.output.include_segment_results
            ),
        }
        if date_window_inventory is not None:
            assembled["live_search"]["date_window_inventory"] = date_window_inventory
        assembled["segment_results"] = state.segment_results[
            : self.options.output.include_segment_results
        ]
        return attach_agent_report(
            assembled,
            AgentReportOptions(agent_report=self.options.output.agent_report),
            self.store,
        )


class LiveAssemblyRunner:
    """Stateful orchestrator for live route assembly.

    Created once per search; ``run()`` executes the full probe-assemble
    pipeline and returns the assembled result dict.
    """

    def __init__(
        self,
        options: LiveAssemblyOptions,
        store: Store,
        *,
        plan_builder: RoutePlanBuilderFn,
    ) -> None:
        self.options = options
        self.store = store
        # Injected dependency avoids a circular import with the public wrapper.
        self._plan_builder = plan_builder
        # --- config (read-only after init) ---
        self.state: LiveAssemblyState | None = None
        self.max_searches: int = 0
        self.only_carriers: list[str] = []
        self.cache_ttl_seconds: int = 0
        self.use_live_cache: bool = False
        self.provider_policy: str = ""
        self.direct_route_index: dict[str, Any] | None = None
        self.direct_route_intel: dict[str, Any] = {}
        self.synthetic_controls = SyntheticControlService()
        self.priority_route_evaluator: PriorityRouteEvaluator | None = None
        self.skip_policy: SkipPolicy | None = None
        self.probe_accumulator: ProbeResultAccumulator | None = None
        self.gateway_leg_probe_executor: GatewayLegProbeExecutor | None = None
        self.search_wave_planner: SearchWavePlanner | None = None
        self.probe_executor: SegmentProbeExecutor | None = None
        self.result_builder: LiveSearchResultBuilder | None = None

    def run(self) -> dict[str, Any]:
        state = self.initialize_state()
        assert self.probe_executor is not None
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
        if self.search_wave_planner is not None:
            state.gateway_leg_results = self.search_wave_planner.run(
                list(state.search_plan.get("gateway_leg_queries") or []),
                state.plan,
            )
        self.probe_executor.run(state)
        self.synthetic_controls.apply_pending(state)
        return self.result_builder.build(state, self.direct_route_intel)

    def initialize_state(self) -> LiveAssemblyState:
        store = self.store
        flow = build_live_route_search_flow(self.options, store)
        # Use injected plan_builder or fall back to build_live_route_segment_plan.
        build_plan = self._plan_builder
        plan = build_plan(self.options, store, flow=flow)
        search_plan = build_search_plan(
            self.options, store, flow=flow, fallback_route_plan=plan
        )
        self.state = LiveAssemblyState(flow=flow, plan=plan, search_plan=search_plan)
        self.max_searches = max(1, int(flow.evidence_plan.max_segment_searches))
        if plan["metrics"]["segment_search_count"] > self.max_searches:
            raise CliError(
                f"planned {plan['metrics']['segment_search_count']} segment searches exceeds --max-segment-searches {self.max_searches}",
                error_type="validation_error",
                details={
                    "planned": plan["metrics"]["segment_search_count"],
                    "max_segment_searches": self.max_searches,
                },
            )
        self.only_carriers = [
            normalize_carrier_code(code, "only-carrier")
            for code in self.options.effective_only_carriers()
        ]
        self.cache_ttl_seconds = int(flow.evidence_plan.live_cache_ttl_seconds)
        self.use_live_cache = bool(flow.evidence_plan.live_cache_enabled)
        self.provider_policy = flow.evidence_plan.provider_policy
        self.direct_route_index, self.direct_route_intel = direct_route_intel_context(
            self.options, store, plan
        )
        self.request_deduper = RequestDeduper()
        self.synthetic_controls = SyntheticControlService()
        self.priority_route_evaluator = PriorityRouteEvaluator(
            self.options, self.synthetic_controls
        )
        self.skip_policy = SkipPolicy(
            options=self.options,
            direct_route_index=self.direct_route_index,
            priority_route_evaluator=self.priority_route_evaluator,
        )
        self.probe_accumulator = ProbeResultAccumulator(self.only_carriers)
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
            store=store,
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
        self.probe_executor = SegmentProbeExecutor(
            options=self.options,
            store=store,
            only_carriers=self.only_carriers,
            cache_ttl_seconds=self.cache_ttl_seconds,
            use_live_cache=self.use_live_cache,
            provider_policy=self.provider_policy,
            request_deduper=self.request_deduper,
            skip_policy=self.skip_policy,
            accumulator=self.probe_accumulator,
        )
        self.result_builder = LiveSearchResultBuilder(
            options=self.options, store=store, provider_policy=self.provider_policy
        )
        return self.state
