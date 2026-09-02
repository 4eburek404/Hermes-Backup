from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping


SEARCH_PLAN_SCHEMA_VERSION = "flight_search_plan.v6"

GATEWAY_TRIGGER_DISABLED = "disabled"
GATEWAY_TRIGGER_REQUIRED_IF_NO_DIRECT = "required_if_no_direct"
GATEWAY_TRIGGER_ON_PRIMARY_FAILURE = "on_primary_failure"


@dataclass(frozen=True, slots=True)
class RoutePlan:
    origin: str
    destination: str
    dates: Mapping[str, Any]
    currency: str
    profile: str
    provider_policy: str
    routing_strategy: str
    origin_airports: tuple[str, ...] = ()
    destination_airports: tuple[str, ...] = ()
    airport_scope: Mapping[str, Any] | None = None
    direct_only: bool = False

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RoutePlan:
        return cls(
            origin=str(payload.get("origin") or ""),
            destination=str(payload.get("destination") or ""),
            dates=dict(payload.get("dates") or {}),
            currency=str(payload.get("currency") or ""),
            profile=str(payload.get("profile") or ""),
            provider_policy=str(payload.get("provider_policy") or "auto"),
            routing_strategy=str(payload.get("routing_strategy") or ""),
            origin_airports=tuple(
                str(item) for item in payload.get("origin_airports") or []
            ),
            destination_airports=tuple(
                str(item) for item in payload.get("destination_airports") or []
            ),
            airport_scope=(
                dict(payload["airport_scope"])
                if isinstance(payload.get("airport_scope"), Mapping)
                else None
            ),
            direct_only=bool(payload.get("direct_only")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "dates": deepcopy(dict(self.dates)),
            "currency": self.currency,
            "profile": self.profile,
            "provider_policy": self.provider_policy,
            "routing_strategy": self.routing_strategy,
            "origin_airports": list(self.origin_airports),
            "destination_airports": list(self.destination_airports),
            "airport_scope": (
                deepcopy(dict(self.airport_scope))
                if self.airport_scope is not None
                else None
            ),
            "direct_only": self.direct_only,
        }


@dataclass(frozen=True, slots=True)
class ProviderAttemptPlan:
    """One immutable provider attempt owned by a SearchPlan phase."""

    probe_id: str
    phase: str
    trigger: str
    provider: str
    probe_type: str
    direction: str
    query: Mapping[str, Any]

    def __post_init__(self) -> None:
        required = {
            "probe_id": self.probe_id,
            "phase": self.phase,
            "trigger": self.trigger,
            "provider": self.provider,
            "probe_type": self.probe_type,
            "direction": self.direction,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(
                "provider attempt missing required fields: " + ", ".join(missing)
            )
        duplicated_identity = {
            "probe_id",
            "phase",
            "trigger",
            "provider",
            "probe_type",
            "direction",
            "execution_state",
        }.intersection(self.query)
        if duplicated_identity:
            raise ValueError(
                "provider attempt query duplicates canonical identity: "
                + ", ".join(sorted(duplicated_identity))
            )
        required_query_fields = {
            "role",
            "source_type",
            "origin",
            "destination",
            "date",
            "currency",
            "direct_only",
        }
        missing_query_fields = required_query_fields.difference(self.query)
        if missing_query_fields:
            raise ValueError(
                "provider attempt query missing required fields: "
                + ", ".join(sorted(missing_query_fields))
            )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ProviderAttemptPlan:
        return cls(
            probe_id=str(payload.get("probe_id") or ""),
            phase=str(payload.get("phase") or ""),
            trigger=str(payload.get("trigger") or "always"),
            provider=str(payload.get("provider") or ""),
            probe_type=str(payload.get("probe_type") or ""),
            direction=str(payload.get("direction") or ""),
            query=(
                deepcopy(dict(payload["query"]))
                if isinstance(payload.get("query"), Mapping)
                else {}
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "phase": self.phase,
            "trigger": self.trigger,
            "provider": self.provider,
            "probe_type": self.probe_type,
            "direction": self.direction,
            "query": deepcopy(dict(self.query)),
        }

    def to_execution_dict(self) -> dict[str, Any]:
        """Return the flat provider-call spec consumed by execution and ledger."""

        return {
            **deepcopy(dict(self.query)),
            "probe_id": self.probe_id,
            "phase": self.phase,
            "trigger": self.trigger,
            "provider": self.provider,
            "probe_type": self.probe_type,
            "direction": self.direction,
        }


@dataclass(frozen=True, slots=True)
class RouteLegTemplate:
    """An immutable route shape; execution derives dated provider probes from it."""

    hypothesis_id: str
    direction: str
    required_airports: tuple[str, ...]
    source: str
    leg_policies: tuple[str, ...]
    trigger: str

    def __post_init__(self) -> None:
        if len(self.required_airports) < 3:
            raise ValueError("route leg template needs at least two legs")
        if len(self.leg_policies) != len(self.required_airports) - 1:
            raise ValueError("route leg template policies must match legs")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RouteLegTemplate:
        return cls(
            hypothesis_id=str(payload.get("hypothesis_id") or ""),
            direction=str(payload.get("direction") or ""),
            required_airports=tuple(
                str(item) for item in payload.get("required_airports") or []
            ),
            source=str(payload.get("source") or ""),
            leg_policies=tuple(
                str(item) for item in payload.get("leg_policies") or []
            ),
            trigger=str(payload.get("trigger") or "always"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "direction": self.direction,
            "required_airports": list(self.required_airports),
            "source": self.source,
            "leg_policies": list(self.leg_policies),
            "trigger": self.trigger,
        }


@dataclass(frozen=True, slots=True)
class SearchPhases:
    primary: tuple[ProviderAttemptPlan, ...] = ()
    route_legs: tuple[RouteLegTemplate, ...] = ()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SearchPhases:
        return cls(
            primary=tuple(
                ProviderAttemptPlan.from_dict(item)
                for item in payload.get("primary") or []
                if isinstance(item, Mapping)
            ),
            route_legs=tuple(
                RouteLegTemplate.from_dict(item)
                for item in payload.get("route_legs") or []
                if isinstance(item, Mapping)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": [item.to_dict() for item in self.primary],
            "route_legs": [item.to_dict() for item in self.route_legs],
        }


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

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> GatewayDiscovery:
        return cls(
            enabled=bool(payload.get("enabled")),
            reason=str(payload["reason"]) if payload.get("reason") else None,
            mode=str(payload.get("mode") or "disabled"),
            route_access_profile=(
                str(payload["route_access_profile"])
                if payload.get("route_access_profile")
                else None
            ),
            route_access_reasons=tuple(
                str(item) for item in payload.get("route_access_reasons") or []
            ),
            candidate_count=int(payload.get("candidate_count") or 0),
            candidates=tuple(
                dict(item)
                for item in payload.get("candidates") or []
                if isinstance(item, Mapping)
            ),
            skipped_reasons=tuple(
                str(item) for item in payload.get("skipped_reasons") or []
            ),
            empty_reason=(
                str(payload["empty_reason"]) if payload.get("empty_reason") else None
            ),
            prior_set=str(payload["prior_set"]) if payload.get("prior_set") else None,
            matched_rule_id=(
                str(payload["matched_rule_id"])
                if payload.get("matched_rule_id")
                else None
            ),
            market=str(payload["market"]) if payload.get("market") else None,
            rejected_gateway_signals=tuple(
                dict(item)
                for item in payload.get("rejected_gateway_signals") or []
                if isinstance(item, Mapping)
            ),
        )

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
class GatewayPolicy:
    trigger: str = GATEWAY_TRIGGER_DISABLED
    discovery: GatewayDiscovery = field(default_factory=GatewayDiscovery)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> GatewayPolicy:
        discovery = payload.get("discovery")
        return cls(
            trigger=str(payload.get("trigger") or GATEWAY_TRIGGER_DISABLED),
            discovery=GatewayDiscovery.from_dict(
                discovery if isinstance(discovery, Mapping) else {}
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"trigger": self.trigger, "discovery": self.discovery.to_dict()}


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    max_provider_attempts: int
    segment_limit: int
    live_cache_ttl_seconds: int
    live_cache_enabled: bool
    timeout: int
    fail_fast: bool
    gateway_discovery_limit: int
    gateway_probe_batch_size: int
    gateway_probe_max_batches: int
    only_carriers: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ExecutionPolicy:
        return cls(
            max_provider_attempts=int(payload.get("max_provider_attempts") or 1),
            segment_limit=int(payload.get("segment_limit") or 1),
            live_cache_ttl_seconds=int(payload.get("live_cache_ttl_seconds") or 0),
            live_cache_enabled=bool(payload.get("live_cache_enabled")),
            timeout=int(payload.get("timeout") or 1),
            fail_fast=bool(payload.get("fail_fast")),
            gateway_discovery_limit=int(payload.get("gateway_discovery_limit") or 0),
            gateway_probe_batch_size=int(payload.get("gateway_probe_batch_size") or 0),
            gateway_probe_max_batches=int(
                payload.get("gateway_probe_max_batches") or 0
            ),
            only_carriers=tuple(
                str(item) for item in payload.get("only_carriers") or []
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_provider_attempts": self.max_provider_attempts,
            "segment_limit": self.segment_limit,
            "live_cache_ttl_seconds": self.live_cache_ttl_seconds,
            "live_cache_enabled": self.live_cache_enabled,
            "timeout": self.timeout,
            "fail_fast": self.fail_fast,
            "gateway_discovery_limit": self.gateway_discovery_limit,
            "gateway_probe_batch_size": self.gateway_probe_batch_size,
            "gateway_probe_max_batches": self.gateway_probe_max_batches,
            "only_carriers": list(self.only_carriers),
        }


@dataclass(frozen=True, slots=True)
class DecisionPolicy:
    max_connections_per_journey: int
    preferred_connections: int
    min_same_airport_connection_min: int
    min_cross_airport_connection_min: int
    max_layover_min: int
    preferred_layover_max_min: int

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DecisionPolicy:
        return cls(
            max_connections_per_journey=int(
                payload.get("max_connections_per_journey") or 0
            ),
            preferred_connections=int(payload.get("preferred_connections") or 0),
            min_same_airport_connection_min=int(
                payload.get("min_same_airport_connection_min") or 0
            ),
            min_cross_airport_connection_min=int(
                payload.get("min_cross_airport_connection_min") or 0
            ),
            max_layover_min=int(payload.get("max_layover_min") or 0),
            preferred_layover_max_min=int(
                payload.get("preferred_layover_max_min") or 0
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_connections_per_journey": self.max_connections_per_journey,
            "preferred_connections": self.preferred_connections,
            "min_same_airport_connection_min": self.min_same_airport_connection_min,
            "min_cross_airport_connection_min": self.min_cross_airport_connection_min,
            "max_layover_min": self.max_layover_min,
            "preferred_layover_max_min": self.preferred_layover_max_min,
        }


@dataclass(frozen=True, slots=True)
class OutputPolicy:
    catalog_limit: int
    direct_catalog_limit: int
    max_gateway_alternatives: int
    max_primary_gateway_options: int
    max_options_per_first_carrier: int
    max_round_trip_pairs: int

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> OutputPolicy:
        return cls(
            catalog_limit=int(payload.get("catalog_limit") or 1),
            direct_catalog_limit=int(payload.get("direct_catalog_limit") or 1),
            max_gateway_alternatives=int(payload.get("max_gateway_alternatives") or 0),
            max_primary_gateway_options=int(
                payload.get("max_primary_gateway_options") or 0
            ),
            max_options_per_first_carrier=int(
                payload.get("max_options_per_first_carrier") or 1
            ),
            max_round_trip_pairs=int(payload.get("max_round_trip_pairs") or 0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "catalog_limit": self.catalog_limit,
            "direct_catalog_limit": self.direct_catalog_limit,
            "max_gateway_alternatives": self.max_gateway_alternatives,
            "max_primary_gateway_options": self.max_primary_gateway_options,
            "max_options_per_first_carrier": self.max_options_per_first_carrier,
            "max_round_trip_pairs": self.max_round_trip_pairs,
        }


@dataclass(frozen=True, slots=True)
class SearchPlan:
    """The complete immutable source of truth consumed by search execution."""

    route: RoutePlan
    phases: SearchPhases
    gateway_policy: GatewayPolicy
    execution_policy: ExecutionPolicy
    decision_policy: DecisionPolicy
    output_policy: OutputPolicy
    schema_version: str = SEARCH_PLAN_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SearchPlan:
        version = str(payload.get("schema_version") or "")
        if version != SEARCH_PLAN_SCHEMA_VERSION:
            raise ValueError(
                f"expected {SEARCH_PLAN_SCHEMA_VERSION}, received {version or 'missing schema_version'}"
            )
        return cls(
            route=RoutePlan.from_dict(dict(payload.get("route") or {})),
            phases=SearchPhases.from_dict(dict(payload.get("phases") or {})),
            gateway_policy=GatewayPolicy.from_dict(
                dict(payload.get("gateway_policy") or {})
            ),
            execution_policy=ExecutionPolicy.from_dict(
                dict(payload.get("execution_policy") or {})
            ),
            decision_policy=DecisionPolicy.from_dict(
                dict(payload.get("decision_policy") or {})
            ),
            output_policy=OutputPolicy.from_dict(
                dict(payload.get("output_policy") or {})
            ),
            schema_version=version,
        )

    @property
    def all_attempts(self) -> tuple[ProviderAttemptPlan, ...]:
        return self.phases.primary

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "route": self.route.to_dict(),
            "phases": self.phases.to_dict(),
            "gateway_policy": self.gateway_policy.to_dict(),
            "execution_policy": self.execution_policy.to_dict(),
            "decision_policy": self.decision_policy.to_dict(),
            "output_policy": self.output_policy.to_dict(),
        }
