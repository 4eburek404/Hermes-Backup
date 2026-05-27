from __future__ import annotations

from typing import Any

from ..config import SPECIAL_CITY_AIRPORTS
from ..domain.stop_metrics import offer_stop_metrics
from ..domain.stop_policy import BUSINESS_DEFAULT_STOP_POLICY, StopPolicy, decide_stop_policy, stop_policy_payload
from .answer_line_renderer import build_answer_lines
from .coverage_projector import build_coverage_diagnostics
from .flight_display import build_flight_display
from .human_answer_renderer import build_human_answer
from .option_projector import candidate_options_from_details, priority_candidate_options, ranked_candidate_options
from .provider_aggregate_projector import aggregate_control_summary, provider_aggregate_candidate_options
from .report_budget import apply_agent_report_budget
from .source_boundary_projector import source_boundaries
from .through_fare_analyzer import through_fare_checks


def stop_policy_from_report_data(data: dict[str, Any]) -> StopPolicy:
    payload = data.get("stop_policy") if isinstance(data.get("stop_policy"), dict) else {}
    if not payload:
        return BUSINESS_DEFAULT_STOP_POLICY
    if str(payload.get("name") or "") == "debug_all":
        return BUSINESS_DEFAULT_STOP_POLICY
    return StopPolicy(
        name=str(payload.get("name") or BUSINESS_DEFAULT_STOP_POLICY.name),
        preferred_max_connections=int(payload.get("preferred_max_connections") or 1),
        fallback_max_connections=int(payload.get("fallback_max_connections") or 2),
        hard_max_connections=int(payload.get("hard_max_connections") or 2),
        allow_two_stop_fallback=bool(payload.get("two_stop_allowed_only_if_no_preferred", True)),
        suppress_three_plus=not bool(payload.get("three_plus_reportable", False)),
    )


def has_preferred_option(options: list[dict[str, Any]]) -> bool:
    return any(int(option.get("max_connections_per_journey") or 0) <= 1 for option in options if isinstance(option, dict))


def aggregate_stop_policy_counts(aggregate_controls: list[dict[str, Any]], preferred_available: bool) -> dict[str, int]:
    three_plus = 0
    two_stop = 0
    for control in aggregate_controls:
        three_plus += int(control.get("suppressed_three_plus_count") or 0)
        for offer in control.get("top_offers") or []:
            if not isinstance(offer, dict):
                continue
            max_connections = int(offer.get("connection_count") or offer.get("change_count") or 0)
            if max_connections >= 3:
                three_plus += 1
            elif max_connections == 2 and preferred_available:
                two_stop += 1
    return {
        "aggregate_three_plus_suppressed_count": three_plus,
        "aggregate_two_stop_suppressed_because_preferred_exists": two_stop,
    }


def aggregate_has_preferred_offer(aggregate_controls: list[dict[str, Any]], stop_policy: StopPolicy) -> bool:
    return any(
        offer_stop_metrics(offer)["max_connections_per_journey"] <= stop_policy.preferred_max_connections
        for control in aggregate_controls
        for offer in (control.get("top_offers") or [])
        if isinstance(control, dict) and control.get("status") == "ok" and isinstance(offer, dict)
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
            decision = decide_stop_policy(metrics, stop_policy, preferred_available=preferred_available)
            if not decision.reportable_by_stop_policy:
                continue
            filtered_offer = dict(offer)
            filtered_offer["reportable_by_stop_policy"] = True
            filtered_offer["stop_policy_decision"] = decision.to_dict()
            filtered_offers.append(filtered_offer)
        filtered["top_offers"] = filtered_offers
        filtered_controls.append(filtered)
    return filtered_controls


def merge_stop_policy_diagnostics(data: dict[str, Any], aggregate_controls: list[dict[str, Any]], preferred_available: bool) -> dict[str, Any]:
    diagnostics = dict(data.get("stop_policy_diagnostics") if isinstance(data.get("stop_policy_diagnostics"), dict) else {})
    aggregate_counts = aggregate_stop_policy_counts(aggregate_controls, preferred_available)
    diagnostics.setdefault("policy", str((data.get("stop_policy") or {}).get("name") or BUSINESS_DEFAULT_STOP_POLICY.name) if isinstance(data.get("stop_policy"), dict) else BUSINESS_DEFAULT_STOP_POLICY.name)
    diagnostics.setdefault("preferred_candidate_count", 0)
    diagnostics.setdefault("two_stop_candidate_count", 0)
    diagnostics.setdefault("three_plus_suppressed_count", 0)
    diagnostics.setdefault("two_stop_suppressed_because_preferred_exists", 0)
    diagnostics.setdefault("used_two_stop_fallback", False)
    diagnostics["three_plus_suppressed_count"] = int(diagnostics.get("three_plus_suppressed_count") or 0) + aggregate_counts["aggregate_three_plus_suppressed_count"]
    diagnostics["two_stop_suppressed_because_preferred_exists"] = int(diagnostics.get("two_stop_suppressed_because_preferred_exists") or 0) + aggregate_counts["aggregate_two_stop_suppressed_because_preferred_exists"]
    diagnostics["garbage_options_hidden_from_answer"] = int(diagnostics.get("three_plus_suppressed_count") or 0) > 0
    return diagnostics


def rejected_pair_warnings(data: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
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
                "price": {"amount": item.get("price"), "currency": item.get("currency")},
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
    for key in ("classification", "retryable", "retry_after_seconds", "retry_after_parse_error", "http_status"):
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


def segment_search_summaries(live: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "direction": item.get("direction"),
            "leg": item.get("leg"),
            "origin": item.get("origin"),
            "destination": item.get("destination"),
            "date": item.get("date"),
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


def normalize_airport_values(values: Any, fallback: list[str] | None = None) -> list[str]:
    source = values if isinstance(values, list) else (fallback or [])
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


def option_direction_segments(option: dict[str, Any], direction: str) -> list[dict[str, Any]]:
    return [
        segment
        for segment in option.get("segments") or []
        if isinstance(segment, dict) and str(segment.get("direction") or "").lower() == direction
    ]


def segment_origin(segment: dict[str, Any]) -> str:
    return str(segment.get("origin") or "").strip().upper()


def segment_destination(segment: dict[str, Any]) -> str:
    return str(segment.get("destination") or "").strip().upper()


def segment_carrier(segment: dict[str, Any]) -> str:
    return str(segment.get("carrier") or segment.get("operating_carrier") or segment.get("marketing_carrier") or "").strip().upper()


def segment_path_signature(segments: list[dict[str, Any]]) -> tuple[tuple[str, str, str, str, str, str], ...]:
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
    if direction == "outbound":
        return "direct_outbound"
    if direction == "return":
        return "direct_return"
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
    option_signature = segment_path_signature(option_direction_segments(option, direction))
    if not option_signature:
        return False
    for item in live.get("segment_searches") or []:
        if not isinstance(item, dict):
            continue
        if not segment_search_matches_direct_destination_branch(item, direction, origins, destinations):
            continue
        if not segment_search_is_executed(item):
            continue
        for offer in item.get("offers") or []:
            if not isinstance(offer, dict):
                continue
            offer_segments = [segment for segment in offer.get("segments") or [] if isinstance(segment, dict)]
            if segment_path_signature(offer_segments) == option_signature:
                return True
    return False


def matches_two_leg_path(segments: list[dict[str, Any]], origins: set[str], hubs: set[str], destinations: set[str]) -> bool:
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
        outbound_ok = matches_two_leg_path(outbound, origin_airports, hub_airports, destination_airports)
    elif branch == "moscow_gateway":
        outbound_ok = matches_two_leg_path(outbound, origin_airports, moscow_airports, destination_airports)
    elif branch == "moscow_via_ist_fallback":
        outbound_ok = matches_moscow_via_ist_path(outbound, origin_airports, moscow_airports, hub_airports, destination_airports)
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
        return matches_two_leg_path(return_segments, destination_airports, hub_airports, origin_airports)
    if branch == "moscow_gateway":
        return matches_two_leg_path(return_segments, destination_airports, moscow_airports, origin_airports)
    return matches_moscow_via_ist_path(return_segments, destination_airports, hub_airports, moscow_airports, origin_airports)


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
    return bool(status) or segment_search_offer_count(item) is not None or isinstance(item.get("offers"), list)


def segment_search_matches_edge(
    item: dict[str, Any],
    direction: str,
    origins: set[str],
    destinations: set[str],
) -> bool:
    item_direction = str(item.get("direction") or "").strip().lower()
    if item_direction and item_direction != direction:
        return False
    return search_value(item, "origin") in origins and search_value(item, "destination") in destinations


def segment_search_matches_required_edge(
    item: dict[str, Any],
    branch: str,
    direction: str,
    origins: set[str],
    destinations: set[str],
) -> bool:
    if branch == "direct_destination":
        return segment_search_matches_direct_destination_branch(item, direction, origins, destinations)
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
        return option_has_direct_destination_branch_evidence(option, live, direction, origins, destinations)
    return option_has_segment_edge(option, direction, origins, destinations)


def option_has_segment_edge(
    option: dict[str, Any],
    direction: str,
    origins: set[str],
    destinations: set[str],
) -> bool:
    return any(
        segment_origin(segment) in origins and segment_destination(segment) in destinations
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
        outbound = [("outbound", origin_airports, hub_airports), ("outbound", hub_airports, destination_airports)]
        inbound = [("return", destination_airports, hub_airports), ("return", hub_airports, origin_airports)]
    elif branch == "moscow_gateway":
        outbound = [("outbound", origin_airports, moscow_airports), ("outbound", moscow_airports, destination_airports)]
        inbound = [("return", destination_airports, moscow_airports), ("return", moscow_airports, origin_airports)]
    elif branch == "moscow_via_ist_fallback":
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
    segment_searches = [item for item in live.get("segment_searches") or [] if isinstance(item, dict)]
    executed_edges = [
        any(
            segment_search_matches_required_edge(item, branch, direction, origins, destinations)
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
        or any(segment_search_matches_required_edge(item, branch, direction, origins, destinations) for item in segment_searches)
        or any(option_has_required_edge_evidence(option, live, branch, direction, origins, destinations) for option in source_options)
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


def has_lower_stop_viable_option(source_options: list[dict[str, Any]], fallback_connections: int) -> bool:
    for option in source_options:
        if not isinstance(option, dict) or option.get("ok") is not True:
            continue
        connections = option_max_connections_per_journey(option)
        if connections is not None and connections < fallback_connections:
            return True
    return False


def ru_priority_source_options(
    data: dict[str, Any],
    recommended_options: list[dict[str, Any]],
    priority_options: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    details: list[Any] = []
    for key in ("ranked_candidates", "frontier_candidates"):
        values = data.get(key)
        if isinstance(values, list):
            details.extend(values)
    projected = candidate_options_from_details(details, limit=len(details)) if details else []
    source = projected + recommended_options + priority_options
    seen: set[tuple[str, tuple[tuple[str, str, str], ...]]] = set()
    unique: list[dict[str, Any]] = []
    for option in source:
        if not isinstance(option, dict) or option.get("ok") is not True:
            continue
        if option.get("category") == "provider_aggregate_candidate" or str(option.get("id") or "").startswith("provider-aggregate:"):
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
            int((option.get("price") or {}).get("amount") or 10**12) if isinstance(option.get("price"), dict) else 10**12,
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
    control_option["reason"] = "RU-priority structural visibility control; compare as decision evidence, not as a ranking rewrite."
    control_option["control_family"] = "ru_priority"
    control_option["control_branch"] = branch
    control_option["visibility_role"] = "priority_control"
    return control_option


def build_ru_priority_controls(
    data: dict[str, Any],
    plan: dict[str, Any],
    recommended_options: list[dict[str, Any]],
    priority_options: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if plan.get("routing_strategy") != "ru-priority":
        return None, []

    origin = str(plan.get("origin") or "").strip().upper()
    destination = str(plan.get("destination") or "").strip().upper()
    origin_airports = route_scope_airports(plan, "origin_airports", origin)
    destination_airports = route_scope_airports(plan, "destination_airports", destination)
    moscow_airports = normalize_airport_values(SPECIAL_CITY_AIRPORTS.get("MOW"), ["SVO", "DME", "VKO"])
    primary_hub = "IST"
    hub_airports = normalize_airport_values(SPECIAL_CITY_AIRPORTS.get(primary_hub), [primary_hub])

    controls: dict[str, Any] = {
        "requested": True,
        "checked": True,
        "route_family": "ru_priority",
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
        "moscow_via_ist_fallback_control": branch_control_template(),
        "decision": "no_viable_ru_priority_control",
    }
    source_options = ru_priority_source_options(data, recommended_options, priority_options)
    live = data.get("live_search") if isinstance(data.get("live_search"), dict) else {}
    branch_options: list[dict[str, Any]] = []
    branch_map = {
        "direct_destination_control": "direct_destination",
        "ist_primary_hub_control": "ist_primary_hub",
        "moscow_gateway_control": "moscow_gateway",
        "moscow_via_ist_fallback_control": "moscow_via_ist_fallback",
    }
    origin_set = set(origin_airports) | ({origin} if origin else set())
    destination_set = set(destination_airports) | ({destination} if destination else set())
    moscow_set = set(moscow_airports) | {"MOW"}
    hub_set = set(hub_airports) | ({primary_hub} if primary_hub else set())
    include_return = plan_requests_round_trip(plan)
    fallback_skipped_by_lower_stop = has_lower_stop_viable_option(source_options, fallback_connections=2)

    for control_key, branch in branch_map.items():
        if branch == "moscow_via_ist_fallback" and fallback_skipped_by_lower_stop:
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
        ("moscow_via_ist_fallback_viable", "moscow_via_ist_fallback_control"),
    ):
        if controls[control_key]["viable"] is True:
            controls["decision"] = decision
            break
    return controls, branch_options


def build_agent_report(data: dict[str, Any], store: Any | None = None) -> dict[str, Any]:
    live = data.get("live_search") if isinstance(data.get("live_search"), dict) else {}
    plan = live.get("plan") if isinstance(live.get("plan"), dict) else {}
    assembly = data.get("assembly") if isinstance(data.get("assembly"), dict) else {}
    raw_aggregate_controls = [aggregate_control_summary(item) for item in live.get("aggregate_controls") or [] if isinstance(item, dict)]
    stop_policy = stop_policy_from_report_data(data)
    options = ranked_candidate_options(data, limit=5)
    priority_options = priority_candidate_options(data, limit=5)
    preferred_available = has_preferred_option(options + priority_options) or aggregate_has_preferred_offer(raw_aggregate_controls, stop_policy)
    aggregate_controls = filter_aggregate_controls_for_stop_policy(raw_aggregate_controls, stop_policy, preferred_available)
    aggregate_priority_options = provider_aggregate_candidate_options(
        raw_aggregate_controls,
        limit=5,
        stop_policy=stop_policy,
        preferred_available=has_preferred_option(options + priority_options),
        requested_round_trip=plan_requests_round_trip(plan),
    )
    if aggregate_priority_options:
        priority_options.extend(aggregate_priority_options)
    ru_priority_controls, ru_priority_priority_options = build_ru_priority_controls(data, plan, options, priority_options)
    if ru_priority_priority_options:
        priority_options = ru_priority_priority_options + priority_options
    stop_policy_diagnostics = merge_stop_policy_diagnostics(data, raw_aggregate_controls, preferred_available)
    coverage_diagnostics = build_coverage_diagnostics(plan, live)
    fallback_segments = options[0].get("segments") if options else []
    fallback_origin = fallback_segments[0].get("origin") if fallback_segments else None
    fallback_destination = fallback_segments[-1].get("destination") if fallback_segments else None
    report = {
        "schema_version": "agent_report.v1",
        "route": {
            "origin": plan.get("origin") or fallback_origin,
            "destination": plan.get("destination") or fallback_destination,
            "origin_airports": plan.get("origin_airports") or [],
            "destination_airports": plan.get("destination_airports") or [],
            "dates": plan.get("dates") or {},
            "profile": data.get("profile") or plan.get("profile"),
            "routing_strategy": plan.get("routing_strategy"),
            "provider_policy": live.get("provider_policy"),
        },
        "status": {
            "ranked_output_count": assembly.get("ranked_output_count", len(data.get("ranked") or [])),
            "ranked_total_count": assembly.get("ranked_total_count"),
            "candidate_count": assembly.get("candidate_count"),
            "candidate_pool_truncated": assembly.get("candidate_pool_truncated"),
            "failure_count": live.get("failure_count", 0),
        },
        "source_boundaries": source_boundaries(),
        "hub_viability": hub_viability_summaries(live),
        "segment_searches": segment_search_summaries(live),
        "provider_failures": provider_failures(live),
        "recommended_options": options,
        "priority_options": priority_options,
        "aggregate_controls": aggregate_controls,
        "coverage_diagnostics": coverage_diagnostics,
        "stop_policy": stop_policy_payload(stop_policy),
        "stop_policy_diagnostics": stop_policy_diagnostics,
        "through_fare_checks": through_fare_checks(aggregate_controls, priority_options),
        "rejected_pair_warnings": rejected_pair_warnings(data, limit=5),
    }
    if ru_priority_controls is not None:
        report["ru_priority_controls"] = ru_priority_controls
    report["display"] = build_flight_display(report, store)
    report["answer_lines"] = build_answer_lines(report)
    report["human_answer"] = build_human_answer(report)
    return apply_agent_report_budget(report)
