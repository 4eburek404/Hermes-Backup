from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


SEARCH_PLAN_SCHEMA_VERSION = "flight_search_plan.v1"


@dataclass(frozen=True, slots=True)
class GatewayDiscovery:
    enabled: bool = False
    reason: str | None = None
    mode: str = "disabled"
    route_access_profile: str | None = None
    route_access_reasons: list[str] = field(default_factory=list)
    prior_set: str | None = None
    matched_rule_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "enabled": bool(self.enabled),
            "reason": self.reason,
            "mode": self.mode,
            "route_access_profile": self.route_access_profile,
            "route_access_reasons": list(self.route_access_reasons),
        }
        if self.prior_set:
            payload["prior_set"] = self.prior_set
        if self.matched_rule_id:
            payload["matched_rule_id"] = self.matched_rule_id
        return payload


@dataclass(frozen=True, slots=True)
class FallbackSegmentPlan:
    segments: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"segments": deepcopy(self.segments)}


@dataclass(frozen=True, slots=True)
class SearchPlan:
    primary_offer_queries: list[dict[str, Any]] = field(default_factory=list)
    mandatory_controls: list[dict[str, Any]] = field(default_factory=list)
    gateway_discovery: GatewayDiscovery = field(default_factory=GatewayDiscovery)
    fallback_segment_plan: FallbackSegmentPlan = field(
        default_factory=FallbackSegmentPlan
    )
    coverage_expectations: list[dict[str, Any]] = field(default_factory=list)
    schema_version: str = SEARCH_PLAN_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "primary_offer_queries": deepcopy(self.primary_offer_queries),
            "mandatory_controls": deepcopy(self.mandatory_controls),
            "gateway_discovery": self.gateway_discovery.to_dict(),
            "fallback_segment_plan": self.fallback_segment_plan.to_dict(),
            "coverage_expectations": deepcopy(self.coverage_expectations),
        }
