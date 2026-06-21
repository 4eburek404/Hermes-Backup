from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from ..domain.vocabulary import AbsenceReason, EvidenceClass, IntentClass, RequiredControl, RoutingStrategy
from .flow_decision import FlowDecision
from .search_request import SearchRequest


ABSENCE_TAXONOMY = tuple(AbsenceReason)


@dataclass(frozen=True, slots=True)
class EvidencePlan:
    """Typed evidence policy derived from the flow decision and search options."""

    provider_policy: str
    max_segment_searches: int
    live_cache_enabled: bool
    live_cache_ttl_seconds: int
    direct_route_intel_enabled: bool
    direct_route_index_ttl_seconds: int
    aggregate_control_limit: int
    aggregate_control_carriers: tuple[Any, ...]
    coverage_mode: str
    coverage_controls: tuple[Any, ...]
    coverage_control_limit: int
    include_segment_results: int
    evidence_class: str
    direct_only: bool
    required_controls: tuple[str, ...]
    freshness_policy: dict[str, Any]
    absence_taxonomy: tuple[str, ...]
    planned_controls: tuple[Any, ...] = ()
    skipped_controls: tuple[Any, ...] = ()
    failed_controls: tuple[Any, ...] = ()
    not_supported_controls: tuple[Any, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    source_boundaries: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_policy": self.provider_policy,
            "max_segment_searches": self.max_segment_searches,
            "live_cache_enabled": self.live_cache_enabled,
            "live_cache_ttl_seconds": self.live_cache_ttl_seconds,
            "direct_route_intel_enabled": self.direct_route_intel_enabled,
            "direct_route_index_ttl_seconds": self.direct_route_index_ttl_seconds,
            "aggregate_control_limit": self.aggregate_control_limit,
            "aggregate_control_carriers": list(self.aggregate_control_carriers),
            "coverage_mode": self.coverage_mode,
            "coverage_controls": list(self.coverage_controls),
            "coverage_control_limit": self.coverage_control_limit,
            "include_segment_results": self.include_segment_results,
            "evidence_class": self.evidence_class,
            "direct_only": self.direct_only,
            "required_controls": list(self.required_controls),
            "freshness_policy": self.freshness_policy,
            "absence_taxonomy": list(self.absence_taxonomy),
            "planned_controls": list(self.planned_controls),
            "skipped_controls": list(self.skipped_controls),
            "failed_controls": list(self.failed_controls),
            "not_supported_controls": list(self.not_supported_controls),
            "missing_evidence": list(self.missing_evidence),
            "source_boundaries": list(self.source_boundaries),
        }


def _int_option(options: dict[str, Any], name: str, default: int) -> int:
    try:
        return int(options.get(name, default))
    except (TypeError, ValueError):
        return default


def _tuple_option(options: dict[str, Any], name: str) -> tuple[Any, ...]:
    value = options.get(name)
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def _is_direct_only(options: dict[str, Any]) -> bool:
    return options.get("max_connections") == 0 and options.get("tier2_max_connections") == 0


def _days_until_departure(depart_date: str) -> int | None:
    try:
        depart = date.fromisoformat(str(depart_date))
    except ValueError:
        return None
    return (depart - date.today()).days


def _required_controls(options: dict[str, Any], decision: FlowDecision, direct_only: bool) -> tuple[str, ...]:
    controls: list[str] = []
    if direct_only or decision.intent_class == IntentClass.DIRECT_INVENTORY:
        controls.append(RequiredControl.EXACT_AIRPORT_DIRECT)
    if options.get("date_window_end"):
        controls.append(RequiredControl.DATE_WINDOW_DIRECT)
    if decision.routing_strategy == RoutingStrategy.RU_PRIORITY:
        controls.append(RequiredControl.MOSCOW_GATEWAY_DIRECT)
    if decision.intent_class == IntentClass.CARRIER_OR_AIRPORT_SCOPE or _tuple_option(options, "only_carrier") or _tuple_option(options, "aggregate_control_carrier"):
        controls.append(RequiredControl.CARRIER_AGGREGATE)
    if decision.evidence_class == EvidenceClass.TICKETING_REQUIRED:
        controls.append(RequiredControl.FULL_ROUTE_AGGREGATE)
    if decision.evidence_class in {EvidenceClass.ABSENCE_CLAIM, EvidenceClass.TICKETING_REQUIRED} and not controls:
        controls.append(RequiredControl.EXACT_AIRPORT_DIRECT)
    return tuple(dict.fromkeys(controls))


def _freshness_policy(request: SearchRequest, decision: FlowDecision, options: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    days_until = _days_until_departure(request.depart_date)
    if decision.evidence_class == EvidenceClass.ABSENCE_CLAIM:
        reasons.append("absence_claim_requires_live_freshness")
    if decision.evidence_class == EvidenceClass.TICKETING_REQUIRED:
        reasons.append("ticketing_required_requires_live_freshness")
    if bool(options.get("no_live_cache", False)):
        reasons.append("request_disabled_live_cache")
    if days_until is not None and days_until <= 2:
        reasons.append("near_departure_requires_live_freshness")
    requires_fresh_live = bool(reasons)
    return {
        "requires_fresh_live": requires_fresh_live,
        "reasons": reasons,
        "days_until_departure": days_until,
        "cache_ttl_seconds": 0 if requires_fresh_live else _int_option(options, "live_cache_ttl_seconds", 0),
    }


def _missing_evidence(decision: FlowDecision) -> tuple[str, ...]:
    if decision.evidence_class == EvidenceClass.TICKETING_REQUIRED:
        return ("single_pnr_or_protection_proof", "baggage_through_proof")
    if decision.evidence_class == EvidenceClass.ABSENCE_CLAIM:
        return ("targeted_live_controls_until_executed",)
    return ()


def plan_evidence(request: SearchRequest, decision: FlowDecision) -> EvidencePlan:
    options = dict(request.compatibility_options)
    direct_route_ttl = _int_option(options, "direct_route_index_ttl_seconds", 0)
    direct_only = _is_direct_only(options)
    freshness_policy = _freshness_policy(request, decision, options)
    cache_enabled = not bool(options.get("no_live_cache", False))
    cache_ttl = _int_option(options, "live_cache_ttl_seconds", 0)
    if freshness_policy["requires_fresh_live"]:
        cache_enabled = False
        cache_ttl = 0
    required_controls = _required_controls(options, decision, direct_only)
    return EvidencePlan(
        provider_policy=request.provider_policy,
        max_segment_searches=_int_option(options, "max_segment_searches", 300),
        live_cache_enabled=cache_enabled,
        live_cache_ttl_seconds=cache_ttl,
        direct_route_intel_enabled=not bool(options.get("no_direct_route_intel", False)) and direct_route_ttl > 0,
        direct_route_index_ttl_seconds=direct_route_ttl,
        aggregate_control_limit=_int_option(options, "aggregate_control_limit", 0),
        aggregate_control_carriers=_tuple_option(options, "aggregate_control_carrier"),
        coverage_mode=str(options.get("coverage_mode") or "targeted"),
        coverage_controls=_tuple_option(options, "coverage_control"),
        coverage_control_limit=_int_option(options, "coverage_control_limit", 0),
        include_segment_results=_int_option(options, "include_segment_results", 0),
        evidence_class=decision.evidence_class,
        direct_only=direct_only,
        required_controls=required_controls,
        freshness_policy=freshness_policy,
        absence_taxonomy=ABSENCE_TAXONOMY,
        missing_evidence=_missing_evidence(decision),
        source_boundaries=decision.source_boundaries,
    )
