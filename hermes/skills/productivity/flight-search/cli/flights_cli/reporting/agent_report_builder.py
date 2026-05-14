from __future__ import annotations

from typing import Any

from ..domain.stop_metrics import offer_stop_metrics
from ..domain.stop_policy import BUSINESS_DEFAULT_STOP_POLICY, StopPolicy, decide_stop_policy, stop_policy_payload
from .answer_line_renderer import build_answer_lines
from .coverage_projector import build_coverage_diagnostics
from .flight_display import build_flight_display
from .option_projector import priority_candidate_options, ranked_candidate_options
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
    )
    if aggregate_priority_options:
        priority_options.extend(aggregate_priority_options)
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
    report["display"] = build_flight_display(report, store)
    report["answer_lines"] = build_answer_lines(report)
    return apply_agent_report_budget(report)
