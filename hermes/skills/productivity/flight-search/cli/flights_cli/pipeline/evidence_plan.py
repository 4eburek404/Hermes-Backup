from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from ..domain.vocabulary import (
    AbsenceReason,
    EvidenceClass,
    IntentClass,
    RequiredControl,
    RoutingStrategy,
)
from .flow_decision import FlowDecision
from .search_request import SearchRequest


ABSENCE_TAXONOMY = tuple(AbsenceReason)


class Clock:
    def today(self) -> date:
        return date.today()


SYSTEM_CLOCK = Clock()


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


def _is_direct_only(request: SearchRequest) -> bool:
    return request.max_connections == 0 and request.tier2_max_connections == 0


def _days_until_departure(depart_date: str, *, today: date) -> int | None:
    try:
        depart = date.fromisoformat(str(depart_date))
    except ValueError:
        return None
    return (depart - today).days


def _required_controls(
    request: SearchRequest, decision: FlowDecision, direct_only: bool
) -> tuple[str, ...]:
    controls: list[str] = []
    if direct_only or decision.intent_class == IntentClass.DIRECT_INVENTORY:
        controls.append(RequiredControl.EXACT_AIRPORT_DIRECT)
    if request.date_window_end:
        controls.append(RequiredControl.DATE_WINDOW_DIRECT)
    if decision.routing_strategy == RoutingStrategy.RU_PRIORITY:
        controls.append(RequiredControl.MOSCOW_GATEWAY_DIRECT)
    if (
        decision.intent_class == IntentClass.CARRIER_OR_AIRPORT_SCOPE
        or request.only_carriers
        or request.exclude_carriers
        or request.constraint_only_carriers
        or request.constraint_preferred_carriers
        or request.aggregate_control_carriers
    ):
        controls.append(RequiredControl.CARRIER_AGGREGATE)
    if decision.evidence_class == EvidenceClass.TICKETING_REQUIRED:
        controls.append(RequiredControl.FULL_ROUTE_AGGREGATE)
    if (
        decision.evidence_class
        in {EvidenceClass.ABSENCE_CLAIM, EvidenceClass.TICKETING_REQUIRED}
        and not controls
    ):
        controls.append(RequiredControl.EXACT_AIRPORT_DIRECT)
    return tuple(dict.fromkeys(controls))


def _freshness_policy(
    request: SearchRequest,
    decision: FlowDecision,
    *,
    today_provider: Callable[[], date] | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    today = today_provider() if today_provider is not None else SYSTEM_CLOCK.today()
    days_until = _days_until_departure(request.depart_date, today=today)
    if decision.evidence_class == EvidenceClass.ABSENCE_CLAIM:
        reasons.append("absence_claim_requires_live_freshness")
    if decision.evidence_class == EvidenceClass.TICKETING_REQUIRED:
        reasons.append("ticketing_required_requires_live_freshness")
    if request.no_live_cache:
        reasons.append("request_disabled_live_cache")
    if days_until is not None and days_until <= 2:
        reasons.append("near_departure_requires_live_freshness")
    requires_fresh_live = bool(reasons)
    return {
        "requires_fresh_live": requires_fresh_live,
        "reasons": reasons,
        "today": today.isoformat(),
        "depart_date": request.depart_date,
        "days_until_departure": days_until,
        "cache_ttl_seconds": 0
        if requires_fresh_live
        else request.live_cache_ttl_seconds,
    }


def _missing_evidence(decision: FlowDecision) -> tuple[str, ...]:
    if decision.evidence_class == EvidenceClass.TICKETING_REQUIRED:
        return ("ticketing_contract_proof", "checked_baggage_transfer_proof")
    if decision.evidence_class == EvidenceClass.ABSENCE_CLAIM:
        return ("targeted_live_controls_until_executed",)
    return ()


def plan_evidence(
    request: SearchRequest,
    decision: FlowDecision,
    *,
    today_provider: Callable[[], date] | None = None,
) -> EvidencePlan:
    direct_route_ttl = request.direct_route_index_ttl_seconds
    direct_only = _is_direct_only(request)
    freshness_policy = _freshness_policy(
        request, decision, today_provider=today_provider
    )
    cache_enabled = not request.no_live_cache
    cache_ttl = request.live_cache_ttl_seconds
    if freshness_policy["requires_fresh_live"]:
        cache_enabled = False
        cache_ttl = 0
    required_controls = _required_controls(request, decision, direct_only)
    return EvidencePlan(
        provider_policy=request.provider_policy,
        max_segment_searches=request.max_segment_searches,
        live_cache_enabled=cache_enabled,
        live_cache_ttl_seconds=cache_ttl,
        direct_route_intel_enabled=not request.no_direct_route_intel
        and direct_route_ttl > 0,
        direct_route_index_ttl_seconds=direct_route_ttl,
        aggregate_control_limit=request.aggregate_control_limit,
        aggregate_control_carriers=request.aggregate_control_carriers,
        coverage_mode=request.coverage_mode,
        coverage_controls=request.coverage_controls,
        coverage_control_limit=request.coverage_control_limit,
        include_segment_results=request.include_segment_results,
        evidence_class=decision.evidence_class,
        direct_only=direct_only,
        required_controls=required_controls,
        freshness_policy=freshness_policy,
        absence_taxonomy=ABSENCE_TAXONOMY,
        missing_evidence=_missing_evidence(decision),
        source_boundaries=decision.source_boundaries,
    )
