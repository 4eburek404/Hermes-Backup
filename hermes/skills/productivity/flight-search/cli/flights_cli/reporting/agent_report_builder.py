from __future__ import annotations

from typing import Any

from ..config import SPECIAL_CITY_AIRPORTS, catalog_output_limits_from_mapping
from ..domain.vocabulary import Direction, Leg, RouteFamily, RoutingStrategy
from ..domain.stop_metrics import offer_stop_metrics
from ..domain.stop_policy import (
    BUSINESS_DEFAULT_STOP_POLICY,
    StopPolicy,
    decide_stop_policy,
    stop_policy_payload,
)
from .projections.summary_lines import build_summary_lines
from .coverage_projector import build_coverage_diagnostics
from .projections.itinerary_display import build_itinerary_display
from .agent_report_projector import AGENT_REPORT_SCHEMA_VERSION, project_agent_report
from .user_answer import build_user_answer
from .projections.human_answer_mirror import build_human_answer_mirror
from .option_projector import (
    decision_frontier_options,
    option_from_decision_frontier_item,
)
from .catalog_order import (
    catalog_order_key,
    option_elapsed_minutes,
    option_is_user_visible,
    option_price_amount,
)
from .offer_graph_projector import build_offer_graph
from .provider_aggregate_projector import (
    aggregate_control_summary,
    provider_aggregate_candidate_options,
)
from .report_budget import apply_agent_report_budget
from .source_boundary_projector import source_boundaries
from .through_fare_analyzer import through_fare_checks

def stop_policy_from_report_data(data: dict[str, Any]) -> StopPolicy:
    payload = (
        data.get("stop_policy") if isinstance(data.get("stop_policy"), dict) else {}
    )
    if not payload:
        return BUSINESS_DEFAULT_STOP_POLICY
    if str(payload.get("name") or "") == "debug_all":
        return BUSINESS_DEFAULT_STOP_POLICY
    return StopPolicy(
        name=str(payload.get("name") or BUSINESS_DEFAULT_STOP_POLICY.name),
        preferred_max_connections=int(payload.get("preferred_max_connections") or 1),
        tier2_max_connections=int(payload.get("tier2_max_connections") or 2),
        hard_max_connections=int(payload.get("hard_max_connections") or 2),
        allow_two_stop_tier=bool(
            payload.get("two_stop_allowed_only_if_no_preferred", True)
        ),
        suppress_three_plus=not bool(payload.get("three_plus_reportable", False)),
    )


def has_preferred_option(options: list[dict[str, Any]]) -> bool:
    return any(
        int(option.get("max_connections_per_journey") or 0) <= 1
        for option in options
        if isinstance(option, dict)
    )


def aggregate_stop_policy_counts(
    aggregate_controls: list[dict[str, Any]], preferred_available: bool
) -> dict[str, int]:
    three_plus = 0
    two_stop = 0
    for control in aggregate_controls:
        three_plus += int(control.get("suppressed_three_plus_count") or 0)
        for offer in control.get("top_offers") or []:
            if not isinstance(offer, dict):
                continue
            max_connections = int(
                offer.get("connection_count") or offer.get("change_count") or 0
            )
            if max_connections >= 3:
                three_plus += 1
            elif max_connections == 2 and preferred_available:
                two_stop += 1
    return {
        "aggregate_three_plus_suppressed_count": three_plus,
        "aggregate_two_stop_suppressed_because_preferred_exists": two_stop,
    }


def aggregate_has_preferred_offer(
    aggregate_controls: list[dict[str, Any]], stop_policy: StopPolicy
) -> bool:
    return any(
        offer_stop_metrics(offer)["max_connections_per_journey"]
        <= stop_policy.preferred_max_connections
        for control in aggregate_controls
        for offer in (control.get("top_offers") or [])
        if isinstance(control, dict)
        and control.get("status") == "ok"
        and isinstance(offer, dict)
    )


def plan_requests_round_trip(plan: dict[str, Any]) -> bool:
    dates = plan.get("dates") if isinstance(plan.get("dates"), dict) else {}
    return bool(dates.get("return") or dates.get("return_date"))


def filter_aggregate_controls_for_stop_policy(
    aggregate_controls: list[dict[str, Any]],
    stop_policy: StopPolicy,
    preferred_available: bool,
) -> list[dict[str, Any]]:
    filtered_controls: list[dict[str, Any]] = []
    for control in aggregate_controls:
        filtered = dict(control)
        filtered_offers = []
        for offer in control.get("top_offers") or []:
            if not isinstance(offer, dict):
                continue
            metrics = offer_stop_metrics(offer)
            decision = decide_stop_policy(
                metrics, stop_policy, preferred_available=preferred_available
            )
            if not decision.reportable_by_stop_policy:
                continue
            filtered_offer = dict(offer)
            filtered_offer["reportable_by_stop_policy"] = True
            filtered_offer["stop_policy_decision"] = decision.to_dict()
            filtered_offers.append(filtered_offer)
        filtered["top_offers"] = filtered_offers
        filtered_controls.append(filtered)
    return filtered_controls


def merge_stop_policy_diagnostics(
    data: dict[str, Any],
    aggregate_controls: list[dict[str, Any]],
    preferred_available: bool,
    selected_stop_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diagnostics = dict(
        data.get("stop_policy_diagnostics")
        if isinstance(data.get("stop_policy_diagnostics"), dict)
        else {}
    )
    aggregate_counts = aggregate_stop_policy_counts(
        aggregate_controls, preferred_available
    )
    diagnostics.setdefault(
        "policy",
        str(
            (data.get("stop_policy") or {}).get("name")
            or BUSINESS_DEFAULT_STOP_POLICY.name
        )
        if isinstance(data.get("stop_policy"), dict)
        else BUSINESS_DEFAULT_STOP_POLICY.name,
    )
    diagnostics.setdefault("preferred_candidate_count", 0)
    diagnostics.setdefault("two_stop_candidate_count", 0)
    diagnostics.setdefault("three_plus_suppressed_count", 0)
    diagnostics.setdefault("two_stop_suppressed_because_preferred_exists", 0)
    diagnostics.setdefault("used_two_stop_tier", False)
    diagnostics["three_plus_suppressed_count"] = (
        int(diagnostics.get("three_plus_suppressed_count") or 0)
        + aggregate_counts["aggregate_three_plus_suppressed_count"]
    )
    diagnostics["two_stop_suppressed_because_preferred_exists"] = (
        int(diagnostics.get("two_stop_suppressed_because_preferred_exists") or 0)
        + aggregate_counts["aggregate_two_stop_suppressed_because_preferred_exists"]
    )
    selected_stop_policy = (
        selected_stop_policy if isinstance(selected_stop_policy, dict) else {}
    )
    selected_two_stop_count = int(
        selected_stop_policy.get("selected_two_stop_option_count") or 0
    )
    if selected_two_stop_count:
        diagnostics["used_two_stop_tier"] = True
        diagnostics["used_tier2_two_stop"] = True
        diagnostics["selected_stop_policy_source"] = str(
            selected_stop_policy.get("source") or "candidate_details"
        )
        diagnostics["selected_two_stop_option_count"] = selected_two_stop_count
        diagnostics["two_stop_candidate_count"] = max(
            int(diagnostics.get("two_stop_candidate_count") or 0),
            selected_two_stop_count,
        )
        diagnostics["eligible_tier2_count"] = max(
            int(diagnostics.get("eligible_tier2_count") or 0),
            selected_two_stop_count,
        )
    diagnostics["garbage_options_hidden_from_answer"] = (
        int(diagnostics.get("three_plus_suppressed_count") or 0) > 0
    )
    return diagnostics


def rejected_pair_warnings(
    data: dict[str, Any], limit: int = 5
) -> list[dict[str, Any]]:
    warnings = []
    for item in (data.get("rejected_pairs") or [])[: max(0, limit)]:
        if not isinstance(item, dict):
            continue
        warnings.append(
            {
                "direction": item.get("direction"),
                "reason": item.get("reason"),
                "airport_pair_status": item.get("airport_pair_status"),
                "arrival_airport": item.get("arrival_airport"),
                "departure_airport": item.get("departure_airport"),
                "actual_min": item.get("actual_min"),
                "required_min": item.get("required_min"),
                "price": {
                    "amount": item.get("price"),
                    "currency": item.get("currency"),
                },
                "notes": item.get("notes") or [],
            }
        )
    return warnings


def provider_failure_summary(failure: dict[str, Any]) -> dict[str, Any]:
    error = failure.get("error") if isinstance(failure.get("error"), dict) else {}
    error_summary = {
        "type": error.get("type"),
        "message": error.get("message"),
    }
    for key in (
        "classification",
        "retryable",
        "retry_after_seconds",
        "retry_after_parse_error",
        "http_status",
    ):
        if key in error:
            error_summary[key] = error.get(key)
    return {
        "direction": failure.get("direction"),
        "leg": failure.get("leg"),
        "origin": failure.get("origin"),
        "destination": failure.get("destination"),
        "date": failure.get("date"),
        "provider": failure.get("provider"),
        "cache_status": failure.get("cache_status"),
        "probe_id": failure.get("probe_id"),
        "error": error_summary,
    }


def provider_failures(live: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    return [
        provider_failure_summary(item)
        for item in (live.get("failures") or [])[: max(0, limit)]
        if isinstance(item, dict)
    ]


def primary_offer_results(
    live: dict[str, Any], limit: int = 20
) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in (live.get("primary_offer_results") or [])[: max(0, limit)]
        if isinstance(item, dict)
    ]


def carrier_scope_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def segment_search_summaries(live: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "direction": item.get("direction"),
            "leg": item.get("leg"),
            "origin": item.get("origin"),
            "destination": item.get("destination"),
            "date": item.get("date"),
            "route_family": item.get("route_family"),
            "priority": item.get("priority"),
            "only_carriers": carrier_scope_list(item.get("only_carriers")),
            "preferred_carriers": carrier_scope_list(item.get("preferred_carriers")),
            "provider_request_strategy": item.get("provider_request_strategy"),
            "provider_city_code": item.get("provider_city_code"),
            "provider": item.get("provider"),
            "status": item.get("status"),
            "reason": item.get("reason"),
            "offer_count": item.get("offer_count"),
            "cache_status": item.get("cache_status"),
            "probe_id": item.get("probe_id"),
            "original_probe_id": item.get("original_probe_id"),
        }
        for item in (live.get("segment_searches") or [])[:20]
        if isinstance(item, dict)
    ]


def hub_viability_summaries(live: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "hub": item.get("hub"),
            "viable": item.get("viable"),
            "total_offer_count": item.get("total_offer_count"),
            "missing_legs": item.get("missing_legs") or [],
        }
        for item in live.get("hub_viability") or []
        if isinstance(item, dict)
    ]


def normalize_airport_values(
    values: Any, default_value: list[str] | None = None
) -> list[str]:
    source = values if isinstance(values, list) else (default_value or [])
    normalized: list[str] = []
    for value in source:
        code = str(value or "").strip().upper()
        if code and code not in normalized:
            normalized.append(code)
    return normalized


def route_scope_airports(plan: dict[str, Any], key: str, route_code: Any) -> list[str]:
    planned = normalize_airport_values(plan.get(key))
    if planned:
        return planned
    code = str(route_code or "").strip().upper()
    if not code:
        return []
    return normalize_airport_values(SPECIAL_CITY_AIRPORTS.get(code), [code])


def option_direction_segments(
    option: dict[str, Any], direction: str
) -> list[dict[str, Any]]:
    return [
        segment
        for segment in option.get("segments") or []
        if isinstance(segment, dict)
        and str(segment.get("direction") or "").lower() == direction
    ]


def segment_origin(segment: dict[str, Any]) -> str:
    return str(segment.get("origin") or "").strip().upper()


def segment_destination(segment: dict[str, Any]) -> str:
    return str(segment.get("destination") or "").strip().upper()


def segment_carrier(segment: dict[str, Any]) -> str:
    return (
        str(
            segment.get("carrier")
            or segment.get("operating_carrier")
            or segment.get("marketing_carrier")
            or ""
        )
        .strip()
        .upper()
    )


def segment_path_signature(
    segments: list[dict[str, Any]],
) -> tuple[tuple[str, str, str, str, str, str], ...]:
    return tuple(
        (
            segment_origin(segment),
            segment_destination(segment),
            str(segment.get("departure_at") or ""),
            str(segment.get("arrival_at") or ""),
            str(segment.get("flight_number") or ""),
            segment_carrier(segment),
        )
        for segment in segments
        if isinstance(segment, dict)
    )


def direct_destination_leg(direction: str) -> str | None:
    if direction == Direction.OUTBOUND:
        return Leg.DIRECT_OUTBOUND
    if direction == Direction.RETURN:
        return Leg.DIRECT_RETURN
    return None


def segment_search_matches_direct_destination_branch(
    item: dict[str, Any],
    direction: str,
    origins: set[str],
    destinations: set[str],
) -> bool:
    expected_leg = direct_destination_leg(direction)
    if expected_leg is None:
        return False
    if str(item.get("leg") or "").strip().lower() != expected_leg:
        return False
    return segment_search_matches_edge(item, direction, origins, destinations)


def option_has_direct_destination_branch_evidence(
    option: dict[str, Any],
    live: dict[str, Any],
    direction: str,
    origins: set[str],
    destinations: set[str],
) -> bool:
    option_signature = segment_path_signature(
        option_direction_segments(option, direction)
    )
    if not option_signature:
        return False
    for item in live.get("segment_searches") or []:
        if not isinstance(item, dict):
            continue
        if not segment_search_matches_direct_destination_branch(
            item, direction, origins, destinations
        ):
            continue
        if not segment_search_is_executed(item):
            continue
        for offer in item.get("offers") or []:
            if not isinstance(offer, dict):
                continue
            offer_segments = [
                segment
                for segment in offer.get("segments") or []
                if isinstance(segment, dict)
            ]
            if segment_path_signature(offer_segments) == option_signature:
                return True
    return False


def matches_two_leg_path(
    segments: list[dict[str, Any]],
    origins: set[str],
    hubs: set[str],
    destinations: set[str],
) -> bool:
    if len(segments) != 2:
        return False
    first, second = segments
    hub = segment_destination(first)
    return (
        segment_origin(first) in origins
        and hub in hubs
        and segment_origin(second) == hub
        and segment_destination(second) in destinations
    )


def matches_moscow_via_ist_path(
    segments: list[dict[str, Any]],
    origins: set[str],
    moscow_airports: set[str],
    hub_airports: set[str],
    destinations: set[str],
) -> bool:
    if len(segments) != 3:
        return False
    first, second, third = segments
    moscow = segment_destination(first)
    hub = segment_destination(second)
    return (
        segment_origin(first) in origins
        and moscow in moscow_airports
        and segment_origin(second) == moscow
        and hub in hub_airports
        and segment_origin(third) == hub
        and segment_destination(third) in destinations
    )


def option_matches_branch(
    option: dict[str, Any],
    live: dict[str, Any],
    branch: str,
    *,
    origin_airports: set[str],
    destination_airports: set[str],
    moscow_airports: set[str],
    hub_airports: set[str],
) -> bool:
    outbound = option_direction_segments(option, "outbound")
    if not outbound:
        return False
    direct_destination_source_outbound = option_has_direct_destination_branch_evidence(
        option,
        live,
        "outbound",
        origin_airports,
        destination_airports,
    )
    if branch == "direct_destination":
        outbound_ok = direct_destination_source_outbound
    elif direct_destination_source_outbound:
        return False
    elif branch == "ist_primary_hub":
        outbound_ok = matches_two_leg_path(
            outbound, origin_airports, hub_airports, destination_airports
        )
    elif branch == "moscow_gateway":
        outbound_ok = matches_two_leg_path(
            outbound, origin_airports, moscow_airports, destination_airports
        )
    elif branch == "moscow_via_ist_secondary":
        outbound_ok = matches_moscow_via_ist_path(
            outbound,
            origin_airports,
            moscow_airports,
            hub_airports,
            destination_airports,
        )
    else:
        return False
    if not outbound_ok:
        return False

    return_segments = option_direction_segments(option, "return")
    if not return_segments:
        return True
    direct_destination_source_return = option_has_direct_destination_branch_evidence(
        option,
        live,
        "return",
        destination_airports,
        origin_airports,
    )
    if branch == "direct_destination":
        return direct_destination_source_return
    if direct_destination_source_return:
        return False
    if branch == "ist_primary_hub":
        return matches_two_leg_path(
            return_segments, destination_airports, hub_airports, origin_airports
        )
    if branch == "moscow_gateway":
        return matches_two_leg_path(
            return_segments, destination_airports, moscow_airports, origin_airports
        )
    return matches_moscow_via_ist_path(
        return_segments,
        destination_airports,
        hub_airports,
        moscow_airports,
        origin_airports,
    )


RU_PRIORITY_EXECUTION_STATES = {
    "executed",
    "executed_no_viable_result",
    "not_generated",
    "partial",
    "assembled_evidence",
    "skipped_better_options_available",
}


def search_value(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if value is None and isinstance(item.get("query"), dict):
        value = item["query"].get(key)
    return str(value or "").strip().upper()


def segment_search_offer_count(item: dict[str, Any]) -> int | None:
    value = item.get("offer_count")
    if value is None:
        value = item.get("raw_count")
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    offers = item.get("offers")
    if isinstance(offers, list):
        return len(offers)
    return None


def segment_search_is_executed(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "").strip().lower()
    if status in {"skipped", "not_executed", "planned", "pending"}:
        return False
    if status in {"error", "failed", "failure"}:
        return False
    return (
        bool(status)
        or segment_search_offer_count(item) is not None
        or isinstance(item.get("offers"), list)
    )


def segment_search_matches_edge(
    item: dict[str, Any],
    direction: str,
    origins: set[str],
    destinations: set[str],
) -> bool:
    item_direction = str(item.get("direction") or "").strip().lower()
    if item_direction and item_direction != direction:
        return False
    return (
        search_value(item, "origin") in origins
        and search_value(item, "destination") in destinations
    )


def segment_search_matches_required_edge(
    item: dict[str, Any],
    branch: str,
    direction: str,
    origins: set[str],
    destinations: set[str],
) -> bool:
    if branch == "direct_destination":
        return segment_search_matches_direct_destination_branch(
            item, direction, origins, destinations
        )
    return segment_search_matches_edge(item, direction, origins, destinations)


def option_has_required_edge_evidence(
    option: dict[str, Any],
    live: dict[str, Any],
    branch: str,
    direction: str,
    origins: set[str],
    destinations: set[str],
) -> bool:
    if branch == "direct_destination":
        return option_has_direct_destination_branch_evidence(
            option, live, direction, origins, destinations
        )
    return option_has_segment_edge(option, direction, origins, destinations)


def option_has_segment_edge(
    option: dict[str, Any],
    direction: str,
    origins: set[str],
    destinations: set[str],
) -> bool:
    return any(
        segment_origin(segment) in origins
        and segment_destination(segment) in destinations
        for segment in option_direction_segments(option, direction)
    )


def branch_required_edges(
    branch: str,
    *,
    origin_airports: set[str],
    destination_airports: set[str],
    moscow_airports: set[str],
    hub_airports: set[str],
    include_return: bool,
) -> list[tuple[str, set[str], set[str]]]:
    if branch == "direct_destination":
        outbound = [("outbound", origin_airports, destination_airports)]
        inbound = [("return", destination_airports, origin_airports)]
    elif branch == "ist_primary_hub":
        outbound = [
            ("outbound", origin_airports, hub_airports),
            ("outbound", hub_airports, destination_airports),
        ]
        inbound = [
            ("return", destination_airports, hub_airports),
            ("return", hub_airports, origin_airports),
        ]
    elif branch == "moscow_gateway":
        outbound = [
            ("outbound", origin_airports, moscow_airports),
            ("outbound", moscow_airports, destination_airports),
        ]
        inbound = [
            ("return", destination_airports, moscow_airports),
            ("return", moscow_airports, origin_airports),
        ]
    elif branch == "moscow_via_ist_secondary":
        outbound = [
            ("outbound", origin_airports, moscow_airports),
            ("outbound", moscow_airports, hub_airports),
            ("outbound", hub_airports, destination_airports),
        ]
        inbound = [
            ("return", destination_airports, hub_airports),
            ("return", hub_airports, moscow_airports),
            ("return", moscow_airports, origin_airports),
        ]
    else:
        return []
    return outbound + (inbound if include_return else [])


def branch_execution_state(
    live: dict[str, Any],
    source_options: list[dict[str, Any]],
    branch: str,
    selected_option: dict[str, Any] | None,
    *,
    origin_airports: set[str],
    destination_airports: set[str],
    moscow_airports: set[str],
    hub_airports: set[str],
    include_return: bool,
) -> str:
    edges = branch_required_edges(
        branch,
        origin_airports=origin_airports,
        destination_airports=destination_airports,
        moscow_airports=moscow_airports,
        hub_airports=hub_airports,
        include_return=include_return,
    )
    if not edges:
        return "not_generated"
    segment_searches = [
        item for item in live.get("segment_searches") or [] if isinstance(item, dict)
    ]
    executed_edges = [
        any(
            segment_search_matches_required_edge(
                item, branch, direction, origins, destinations
            )
            and segment_search_is_executed(item)
            for item in segment_searches
        )
        for direction, origins, destinations in edges
    ]
    if selected_option is not None:
        return "executed" if all(executed_edges) else "assembled_evidence"
    if all(executed_edges):
        return "executed_no_viable_result"

    evidence_edges = [
        executed
        or any(
            segment_search_matches_required_edge(
                item, branch, direction, origins, destinations
            )
            for item in segment_searches
        )
        or any(
            option_has_required_edge_evidence(
                option, live, branch, direction, origins, destinations
            )
            for option in source_options
        )
        for executed, (direction, origins, destinations) in zip(executed_edges, edges)
    ]
    if any(evidence_edges):
        return "partial"
    return "not_generated"


def option_max_connections_per_journey(option: dict[str, Any]) -> int | None:
    counts: list[int] = []
    for direction in ("outbound", "return"):
        segments = option_direction_segments(option, direction)
        if segments:
            counts.append(max(0, len(segments) - 1))
    return max(counts) if counts else None


def order_frontier_options(
    options: list[dict[str, Any]], *, is_round_trip_request: bool
) -> list[dict[str, Any]]:
    visible = [
        option
        for option in options
        if isinstance(option, dict) and option_is_user_visible(option)
    ]
    return sorted(
        visible,
        key=lambda option: catalog_order_key(
            option, is_round_trip_request=is_round_trip_request
        ),
    )


def active_direct_mode_directions(
    live: dict[str, Any], assembly: dict[str, Any]
) -> list[str]:
    direct_mode = (
        assembly.get("direct_mode")
        if isinstance(assembly.get("direct_mode"), dict)
        else {}
    )
    if not direct_mode:
        gate = (
            live.get("direct_presence_gate")
            if isinstance(live.get("direct_presence_gate"), dict)
            else {}
        )
        direct_mode = (
            gate.get("direct_mode") if isinstance(gate.get("direct_mode"), dict) else {}
        )
    return [
        direction
        for direction in ("outbound", "return")
        if bool(direct_mode.get(direction))
    ]


def _ranked_candidates(data: dict[str, Any]) -> list[dict[str, Any]]:
    live = data.get("live_search") if isinstance(data.get("live_search"), dict) else {}
    ranking = (
        live.get("mixed_candidate_ranking")
        if isinstance(live.get("mixed_candidate_ranking"), dict)
        else {}
    )
    return [
        candidate
        for candidate in ranking.get("ranked_candidates") or []
        if isinstance(candidate, dict)
    ]


def _ranked_candidate_acceptable(candidate: dict[str, Any]) -> bool:
    components = (
        candidate.get("rank_components")
        if isinstance(candidate.get("rank_components"), dict)
        else {}
    )
    for key in (
        "hard_constraint_violation",
        "not_covers_requested_trip",
        "rejected_or_impossible_connection",
        "max_connections_per_journey",
    ):
        if int(components.get(key) or 0) > 0:
            return False
    return bool(candidate.get("covers_requested_trip", True))


def _ranked_candidate_hard_constraint_violations(
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    violations = candidate.get("hard_constraint_violations")
    return [item for item in violations or [] if isinstance(item, dict)]


def _candidate_direction_segments(
    candidate: dict[str, Any], direction: str
) -> list[dict[str, Any]]:
    journeys = candidate.get("journeys") if isinstance(candidate.get("journeys"), list) else []
    rows: list[dict[str, Any]] = []
    for journey in journeys:
        if not isinstance(journey, dict):
            continue
        if str(journey.get("direction") or "outbound") != direction:
            continue
        rows.extend(
            segment
            for segment in journey.get("segments") or []
            if isinstance(segment, dict)
        )
    return rows


def _candidate_matches_direct_mode(
    candidate: dict[str, Any], direct_mode_directions: list[str]
) -> bool:
    if str(candidate.get("source_type") or "") == "gateway_separate_ticket":
        return False
    for direction in direct_mode_directions:
        if len(_candidate_direction_segments(candidate, direction)) != 1:
            return False
    return True


def _direct_mode_departure_key(
    option: dict[str, Any], direct_mode_directions: list[str]
) -> tuple[str, int | float, int]:
    direction_order = direct_mode_directions or ["outbound", "return"]
    for direction in direction_order:
        for segment in option_direction_segments(option, direction):
            departure = str(segment.get("departure_at") or "")
            if departure:
                return (
                    departure,
                    catalog_order_key(option, is_round_trip_request=False)[-1],
                    int(option.get("rank") or 0),
                )
    return (
        "",
        catalog_order_key(option, is_round_trip_request=False)[-1],
        int(option.get("rank") or 0),
    )


def direct_mode_candidate_options(
    data: dict[str, Any], direct_mode_directions: list[str], *, limit: int
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for candidate in _ranked_candidates(data):
        if not _ranked_candidate_acceptable(candidate):
            continue
        if not _candidate_matches_direct_mode(candidate, direct_mode_directions):
            continue
        option = option_from_decision_frontier_item(
            {**candidate, "selection_reasons": ["direct_mode_schedule"]}
        )
        options.append(option)
    options.sort(key=lambda item: _direct_mode_departure_key(item, direct_mode_directions))
    return annotate_schedule_options(options[:limit])


def annotate_schedule_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not options:
        return []
    prices = [
        option_price_amount(option)
        for option in options
        if option_price_amount(option) < 10**12
    ]
    elapsed_values = [
        option_elapsed_minutes(option)
        for option in options
        if option_elapsed_minutes(option) < 10**9
    ]
    cheapest = min(prices) if prices else None
    fastest = min(elapsed_values) if elapsed_values else None
    annotated: list[dict[str, Any]] = []
    for option in options:
        item = dict(option)
        badges = [
            str(value)
            for value in item.get("option_badges") or []
            if str(value).strip()
        ]
        if cheapest is not None and option_price_amount(item) == cheapest:
            badges.append("cheapest")
        if fastest is not None and option_elapsed_minutes(item) == fastest:
            badges.append("fastest")
        if badges:
            item["option_badges"] = list(dict.fromkeys(badges))
        annotated.append(item)
    return annotated


def _direct_mode_fallback(live: dict[str, Any]) -> dict[str, Any]:
    gate = (
        live.get("direct_presence_gate")
        if isinstance(live.get("direct_presence_gate"), dict)
        else {}
    )
    fallback = gate.get("fallback") if isinstance(gate.get("fallback"), dict) else {}
    if fallback.get("reason") != "constraints_emptied_direct_set":
        return {}
    return fallback


def _conflict_directions(live: dict[str, Any]) -> list[str]:
    fallback = _direct_mode_fallback(live)
    return [
        direction
        for direction in fallback.get("directions") or []
        if direction in ("outbound", "return")
    ]


def _constraint_type_and_value(violation: dict[str, Any]) -> tuple[str, Any] | None:
    reason = str(violation.get("reason") or "")
    if reason in (
        "first_departure_before_requested_time",
        "missing_first_departure_time",
    ):
        return ("first_departure_after", violation.get("first_departure_after"))
    if reason in ("carrier_not_allowed", "missing_carrier_evidence"):
        return ("only_carriers", violation.get("only_carriers") or [])
    if reason == "missing_required_airport":
        return ("must_include_airports", violation.get("must_include_airports") or [])
    return None


def _candidate_conflict_constraints(
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for violation in _ranked_candidate_hard_constraint_violations(candidate):
        parsed = _constraint_type_and_value(violation)
        if parsed is None:
            continue
        constraint_type, value = parsed
        value_key = ",".join(str(item) for item in value) if isinstance(value, list) else str(value)
        key = (constraint_type, value_key)
        if key in seen:
            continue
        seen.add(key)
        constraints.append(
            {
                "type": constraint_type,
                "value": value,
                "reason": violation.get("reason"),
            }
        )
    return constraints


def _direct_schedule_option_from_candidate(
    candidate: dict[str, Any],
    *,
    direction: str,
    constraints: list[dict[str, Any]],
) -> dict[str, Any]:
    segments = _candidate_direction_segments(candidate, direction)
    item = {
        **candidate,
        "journeys": [{"direction": direction, "segments": segments}],
        "selection_reasons": ["constraint_conflict_direct_schedule"],
        "connection_count": 0,
        "max_connections_per_journey": 0,
        "journey_scope": "one_way",
        "covers_requested_trip": False,
    }
    option = option_from_decision_frontier_item(item)
    option["category"] = "constraint_conflict_direct_schedule"
    option["constraint_violations"] = _ranked_candidate_hard_constraint_violations(
        candidate
    )
    option["conflicting_constraints"] = constraints
    return option


def direct_conflict_schedule_options(
    data: dict[str, Any],
    direction: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for candidate in _ranked_candidates(data):
        constraints = _candidate_conflict_constraints(candidate)
        if not constraints:
            continue
        if not _candidate_matches_direct_mode(candidate, [direction]):
            continue
        options.append(
            _direct_schedule_option_from_candidate(
                candidate,
                direction=direction,
                constraints=constraints,
            )
        )
    options.sort(key=lambda item: _direct_mode_departure_key(item, [direction]))
    return annotate_schedule_options(options[:limit])


def constraint_conflict_report(
    data: dict[str, Any],
    live: dict[str, Any],
    recommended_options: list[dict[str, Any]],
    priority_options: list[dict[str, Any]],
    *,
    direct_schedule_limit: int,
) -> dict[str, Any] | None:
    fallback = _direct_mode_fallback(live)
    directions = _conflict_directions(live)
    if not fallback or not directions:
        return None
    visible_fallback_options = [
        option
        for option in [*recommended_options, *priority_options]
        if int(option.get("max_connections_per_journey") or 0) <= 1
    ]
    fallback_payload = {
        "status": fallback.get("status"),
        "reason": fallback.get("reason"),
        "max_connections_per_journey": int(
            fallback.get("max_connections_per_journey") or 1
        ),
        "acceptable_count": len(visible_fallback_options),
    }
    conflict_directions: list[dict[str, Any]] = []
    for direction in directions:
        direct_schedule = direct_conflict_schedule_options(
            data, direction, limit=direct_schedule_limit
        )
        constraints: list[dict[str, Any]] = []
        for option in direct_schedule:
            for constraint in option.get("conflicting_constraints") or []:
                if isinstance(constraint, dict) and constraint not in constraints:
                    constraints.append(constraint)
        conflict_directions.append(
            {
                "direction": direction,
                "constraints": constraints,
                "direct_schedule": direct_schedule,
                "fallback": fallback_payload,
            }
        )
    return {
        "schema_version": "flight_constraint_conflict.v1",
        "present": True,
        "directions": conflict_directions,
        "fallback": fallback_payload,
    }


def has_lower_stop_viable_option(
    source_options: list[dict[str, Any]], tier2_connections: int
) -> bool:
    for option in source_options:
        if not isinstance(option, dict) or option.get("ok") is not True:
            continue
        connections = option_max_connections_per_journey(option)
        if connections is not None and connections < tier2_connections:
            return True
    return False


def frontier_stop_policy_selection(options: list[dict[str, Any]]) -> dict[str, Any]:
    selected_two_stop_count = sum(
        1
        for option in options
        if int(option.get("max_connections_per_journey") or 0) == 2
    )
    return {
        "source": "decision_frontier",
        "selected_two_stop_option_count": selected_two_stop_count,
        "used_two_stop_tier": selected_two_stop_count > 0,
        "used_tier2_two_stop": selected_two_stop_count > 0,
    }


def ru_priority_source_options(
    data: dict[str, Any],
    recommended_options: list[dict[str, Any]],
    priority_options: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source = recommended_options + priority_options
    seen: set[tuple[str, tuple[tuple[str, str, str], ...]]] = set()
    unique: list[dict[str, Any]] = []
    for option in source:
        if not isinstance(option, dict) or option.get("ok") is not True:
            continue
        if option.get("category") == "provider_aggregate_candidate" or str(
            option.get("id") or ""
        ).startswith("provider-aggregate:"):
            continue
        signature = tuple(
            (
                str(segment.get("direction") or ""),
                segment_origin(segment),
                segment_destination(segment),
            )
            for segment in option.get("segments") or []
            if isinstance(segment, dict)
        )
        if not signature:
            continue
        key = (str(option.get("id") or ""), signature)
        if key in seen:
            continue
        seen.add(key)
        unique.append(option)
    return sorted(
        unique,
        key=lambda option: (
            int(option.get("rank") or 10**6),
            int((option.get("price") or {}).get("amount") or 10**12)
            if isinstance(option.get("price"), dict)
            else 10**12,
            int(option.get("elapsed_min") or 10**9),
        ),
    )


def branch_control_template() -> dict[str, Any]:
    return {
        "checked": True,
        "execution_state": "not_generated",
        "viable": False,
        "visible": False,
        "priority_option_id": None,
        "evidence_option_ids": [],
    }


def ru_priority_control_option(option: dict[str, Any], branch: str) -> dict[str, Any]:
    base_id = str(option.get("id") or branch).strip() or branch
    control_option = dict(option)
    control_option["id"] = f"ru-priority-{branch}:{base_id}"
    control_option["category"] = f"{branch}_control"
    control_option["reason"] = (
        "RU-priority structural visibility control; compare as decision evidence, not as a ranking rewrite."
    )
    control_option["control_family"] = RouteFamily.RU_PRIORITY
    control_option["control_branch"] = branch
    control_option["visibility_role"] = "priority_control"
    return control_option


def build_ru_priority_controls(
    data: dict[str, Any],
    plan: dict[str, Any],
    recommended_options: list[dict[str, Any]],
    priority_options: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if plan.get("routing_strategy") != RoutingStrategy.RU_PRIORITY:
        return None, []

    origin = str(plan.get("origin") or "").strip().upper()
    destination = str(plan.get("destination") or "").strip().upper()
    origin_airports = route_scope_airports(plan, "origin_airports", origin)
    destination_airports = route_scope_airports(
        plan, "destination_airports", destination
    )
    moscow_airports = normalize_airport_values(
        SPECIAL_CITY_AIRPORTS.get("MOW"), ["SVO", "DME", "VKO"]
    )
    primary_hub = "IST"
    hub_airports = normalize_airport_values(
        SPECIAL_CITY_AIRPORTS.get(primary_hub), [primary_hub]
    )

    controls: dict[str, Any] = {
        "requested": True,
        "checked": True,
        "route_family": RouteFamily.RU_PRIORITY,
        "scope": {
            "origin": origin,
            "destination": destination,
            "origin_airports": origin_airports,
            "destination_airports": destination_airports,
            "moscow_airports": moscow_airports,
            "primary_hub": primary_hub,
        },
        "direct_destination_control": branch_control_template(),
        "ist_primary_hub_control": branch_control_template(),
        "moscow_gateway_control": branch_control_template(),
        "moscow_via_ist_secondary_control": branch_control_template(),
        "decision": "no_viable_ru_priority_control",
    }
    source_options = ru_priority_source_options(
        data, recommended_options, priority_options
    )
    live = data.get("live_search") if isinstance(data.get("live_search"), dict) else {}
    branch_options: list[dict[str, Any]] = []
    branch_map = {
        "direct_destination_control": "direct_destination",
        "ist_primary_hub_control": "ist_primary_hub",
        "moscow_gateway_control": "moscow_gateway",
        "moscow_via_ist_secondary_control": "moscow_via_ist_secondary",
    }
    origin_set = set(origin_airports) | ({origin} if origin else set())
    destination_set = set(destination_airports) | (
        {destination} if destination else set()
    )
    moscow_set = set(moscow_airports) | {"MOW"}
    hub_set = set(hub_airports) | ({primary_hub} if primary_hub else set())
    include_return = plan_requests_round_trip(plan)
    tier2_skipped_by_lower_stop = has_lower_stop_viable_option(
        source_options, tier2_connections=2
    )

    for control_key, branch in branch_map.items():
        if branch == "moscow_via_ist_secondary" and tier2_skipped_by_lower_stop:
            controls[control_key] = {
                **branch_control_template(),
                "execution_state": "skipped_better_options_available",
            }
            continue
        selected = next(
            (
                option
                for option in source_options
                if option_matches_branch(
                    option,
                    live,
                    branch,
                    origin_airports=origin_set,
                    destination_airports=destination_set,
                    moscow_airports=moscow_set,
                    hub_airports=hub_set,
                )
            ),
            None,
        )
        execution_state = branch_execution_state(
            live,
            source_options,
            branch,
            selected,
            origin_airports=origin_set,
            destination_airports=destination_set,
            moscow_airports=moscow_set,
            hub_airports=hub_set,
            include_return=include_return,
        )
        if selected is None:
            controls[control_key]["execution_state"] = execution_state
            continue
        control_option = ru_priority_control_option(selected, branch)
        branch_options.append(control_option)
        evidence_option_ids = [control_option["id"]]
        source_option_id = str(selected.get("id") or "").strip()
        if source_option_id and source_option_id not in evidence_option_ids:
            evidence_option_ids.append(source_option_id)
        controls[control_key] = {
            "checked": True,
            "execution_state": execution_state,
            "viable": True,
            "visible": True,
            "priority_option_id": control_option["id"],
            "evidence_option_ids": evidence_option_ids,
        }

    for decision, control_key in (
        ("direct_destination_viable", "direct_destination_control"),
        ("ist_primary_viable", "ist_primary_hub_control"),
        ("moscow_gateway_viable", "moscow_gateway_control"),
        ("moscow_via_ist_secondary_viable", "moscow_via_ist_secondary_control"),
    ):
        if controls[control_key]["viable"] is True:
            controls["decision"] = decision
            break
    return controls, branch_options


def build_agent_report(
    data: dict[str, Any], store: Any | None = None
) -> dict[str, Any]:
    live = data.get("live_search") if isinstance(data.get("live_search"), dict) else {}
    output_limits = catalog_output_limits_from_mapping(
        live.get("output") if isinstance(live.get("output"), dict) else None
    )
    catalog_limit = output_limits.catalog_limit
    direct_catalog_limit = output_limits.direct_catalog_limit
    plan = live.get("plan") if isinstance(live.get("plan"), dict) else {}
    assembly = data.get("assembly") if isinstance(data.get("assembly"), dict) else {}
    direct_mode_directions = active_direct_mode_directions(live, assembly)
    raw_aggregate_controls = [
        aggregate_control_summary(item)
        for item in live.get("aggregate_controls") or []
        if isinstance(item, dict)
    ]
    stop_policy = stop_policy_from_report_data(data)
    live_decision_frontier = live.get("decision_frontier")
    decision_frontier = (
        live_decision_frontier if isinstance(live_decision_frontier, dict) else {}
    )
    if not decision_frontier and isinstance(data.get("decision_frontier"), dict):
        decision_frontier = data["decision_frontier"]
    decision_coverage = (
        decision_frontier.get("coverage_summary")
        if isinstance(decision_frontier.get("coverage_summary"), dict)
        else {}
    )
    frontier_source_options = decision_frontier_options(
        data, limit=catalog_limit + 5
    )
    if direct_mode_directions:
        frontier_source_options = direct_mode_candidate_options(
            data, direct_mode_directions, limit=direct_catalog_limit
        )
    ranked_total_count = int(
        decision_coverage.get("candidate_count") or len(frontier_source_options)
    )
    requested_round_trip = plan_requests_round_trip(plan)
    if direct_mode_directions:
        options = frontier_source_options
        priority_options: list[dict[str, Any]] = []
    else:
        frontier_ordered = order_frontier_options(
            frontier_source_options,
            is_round_trip_request=requested_round_trip,
        )
        options = frontier_ordered[:1]
        priority_options = frontier_ordered[1:catalog_limit]
    selected_stop_policy = frontier_stop_policy_selection(
        [*options, *priority_options]
    )
    preferred_available = has_preferred_option(
        options + priority_options
    ) or aggregate_has_preferred_offer(raw_aggregate_controls, stop_policy)
    aggregate_controls = filter_aggregate_controls_for_stop_policy(
        raw_aggregate_controls, stop_policy, preferred_available
    )
    aggregate_priority_options = (
        []
        if direct_mode_directions
        else provider_aggregate_candidate_options(
            raw_aggregate_controls,
            limit=5,
            stop_policy=stop_policy,
            preferred_available=has_preferred_option(options + priority_options),
            requested_round_trip=requested_round_trip,
        )
    )
    if aggregate_priority_options:
        priority_options.extend(aggregate_priority_options)
    ru_priority_controls, ru_priority_priority_options = build_ru_priority_controls(
        data, plan, options, priority_options
    )
    if ru_priority_priority_options:
        priority_options = ru_priority_priority_options + priority_options
    constraint_conflict = constraint_conflict_report(
        data,
        live,
        options,
        priority_options,
        direct_schedule_limit=direct_catalog_limit,
    )
    stop_policy_diagnostics = merge_stop_policy_diagnostics(
        data,
        raw_aggregate_controls,
        preferred_available,
        selected_stop_policy=selected_stop_policy,
    )
    coverage_diagnostics = build_coverage_diagnostics(plan, live)
    plan_flow_decision = plan.get("flow_decision") if isinstance(plan, dict) else {}
    plan_evidence_plan = plan.get("evidence_plan") if isinstance(plan, dict) else {}
    tier2_segments = options[0].get("segments") if options else []
    tier2_origin = tier2_segments[0].get("origin") if tier2_segments else None
    tier2_destination = (
        tier2_segments[-1].get("destination") if tier2_segments else None
    )
    report = {
        "schema_version": AGENT_REPORT_SCHEMA_VERSION,
        "route": {
            "origin": plan.get("origin") or tier2_origin,
            "destination": plan.get("destination") or tier2_destination,
            "origin_airports": plan.get("origin_airports") or [],
            "destination_airports": plan.get("destination_airports") or [],
            "dates": plan.get("dates") or {},
            "profile": data.get("profile") or plan.get("profile"),
            "routing_strategy": plan.get("routing_strategy"),
            "provider_policy": live.get("provider_policy"),
            "flow_decision": plan_flow_decision
            if isinstance(plan_flow_decision, dict)
            else {},
            "evidence_plan": plan_evidence_plan
            if isinstance(plan_evidence_plan, dict)
            else {},
        },
        "status": {
            "ranked_output_count": assembly.get(
                "ranked_output_count", len(data.get("ranked") or [])
            ),
            "ranked_total_count": ranked_total_count,
            "candidate_count": assembly.get("candidate_count"),
            "candidate_pool_truncated": assembly.get("candidate_pool_truncated"),
            "failure_count": live.get("failure_count", 0),
            "direct_priority_applied": assembly.get("direct_priority_applied", False),
            "direct_mode": {
                direction: True for direction in direct_mode_directions
            },
            "output_limits": output_limits.to_dict(),
        },
        "source_boundaries": source_boundaries(),
        "hub_viability": hub_viability_summaries(live),
        "segment_searches": segment_search_summaries(live),
        "provider_failures": provider_failures(live),
        "primary_offer_results": primary_offer_results(live),
        "gateway_leg_results": live.get("gateway_leg_results")
        if isinstance(live.get("gateway_leg_results"), dict)
        else {},
        "decision_frontier": decision_frontier,
        "recommended_options": options,
        "priority_options": priority_options,
        "aggregate_controls": aggregate_controls,
        "coverage_diagnostics": coverage_diagnostics,
        "stop_policy": stop_policy_payload(stop_policy),
        "stop_policy_diagnostics": stop_policy_diagnostics,
        "through_fare_checks": through_fare_checks(
            aggregate_controls, [*options, *priority_options]
        ),
        "rejected_pair_warnings": rejected_pair_warnings(data, limit=5),
        "direct_flights": assembly.get("direct_flights", []),
    }
    if constraint_conflict is not None:
        report["constraint_conflict"] = constraint_conflict
        report["status"]["constraint_conflict"] = constraint_conflict
    date_window_inventory = live.get("date_window_inventory")
    if isinstance(date_window_inventory, dict):
        report["date_window_inventory"] = date_window_inventory
    if ru_priority_controls is not None:
        report["ru_priority_controls"] = ru_priority_controls
    report["offer_graph"] = build_offer_graph(report, plan, live, data)
    display_limit = len(options) if direct_mode_directions else catalog_limit
    report["display"] = build_itinerary_display(
        report, store, limit=max(display_limit, catalog_limit)
    )
    report["answer_lines"] = build_summary_lines(report)
    report["user_answer"] = build_user_answer(report)
    report["human_answer"] = build_human_answer_mirror(report)
    return project_agent_report(apply_agent_report_budget(report))
