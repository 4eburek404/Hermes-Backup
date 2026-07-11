from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


SEARCH_PLAN_SCHEMA_VERSION = "flight_search_plan.v2"


@dataclass(frozen=True, slots=True)
class GatewayDiscovery:
    enabled: bool = False
    reason: str | None = None
    mode: str = "disabled"
    route_access_profile: str | None = None
    route_access_reasons: tuple[str, ...] = ()
    candidate_count: int = 0
    candidates: tuple[dict[str, Any], ...] = ()
    skipped_reasons: tuple[str, ...] = ()
    empty_reason: str | None = None
    prior_set: str | None = None
    matched_rule_id: str | None = None
    market: str | None = None
    rejected_gateway_signals: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        candidate_count = max(0, int(self.candidate_count))
        empty_reason = self.empty_reason
        if candidate_count == 0 and not empty_reason:
            empty_reason = (
                "gateway_discovery_disabled"
                if not self.enabled
                else "no_gateway_candidates_discovered"
            )
        skipped_reasons = list(self.skipped_reasons)
        if candidate_count == 0 and empty_reason and not skipped_reasons:
            skipped_reasons = [empty_reason]
        payload: dict[str, Any] = {
            "enabled": bool(self.enabled),
            "reason": self.reason,
            "mode": self.mode,
            "route_access_profile": self.route_access_profile,
            "route_access_reasons": list(self.route_access_reasons),
            "candidate_count": candidate_count,
            "candidates": [deepcopy(item) for item in self.candidates],
            "skipped_reasons": skipped_reasons,
            "empty_reason": empty_reason,
        }
        if self.prior_set:
            payload["prior_set"] = self.prior_set
        if self.matched_rule_id:
            payload["matched_rule_id"] = self.matched_rule_id
        if self.market:
            payload["market"] = self.market
        if self.rejected_gateway_signals:
            payload["rejected_gateway_signals"] = [
                deepcopy(item) for item in self.rejected_gateway_signals
            ]
        return payload


@dataclass(frozen=True, slots=True)
class SearchPlan:
    """Single serializable plan consumed by search execution."""

    route_context: dict[str, Any]
    primary_offer_queries: tuple[dict[str, Any], ...] = ()
    gateway_discovery: GatewayDiscovery = field(default_factory=GatewayDiscovery)
    conditional_gateway_queries: tuple[dict[str, Any], ...] = ()
    aggregate_queries: tuple[dict[str, Any], ...] = ()
    coverage_expectations: tuple[dict[str, Any], ...] = ()
    execution_limits: dict[str, Any] = field(default_factory=dict)
    output_limits: dict[str, Any] = field(default_factory=dict)
    planning_reasons: tuple[str, ...] = ()
    schema_version: str = SEARCH_PLAN_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "route_context": deepcopy(self.route_context),
            "primary_offer_queries": [
                deepcopy(item) for item in self.primary_offer_queries
            ],
            "gateway_discovery": self.gateway_discovery.to_dict(),
            "conditional_gateway_queries": [
                deepcopy(item) for item in self.conditional_gateway_queries
            ],
            "aggregate_queries": [deepcopy(item) for item in self.aggregate_queries],
            "coverage_expectations": [
                deepcopy(item) for item in self.coverage_expectations
            ],
            "execution_limits": deepcopy(self.execution_limits),
            "output_limits": deepcopy(self.output_limits),
            "planning_reasons": list(self.planning_reasons),
        }
