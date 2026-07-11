from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from ..domain.immutable import freeze, thaw


ProviderName = Literal["kupibilet", "fli", "tutu"]
ProbeType = Literal[
    "segment_direct",
    "segment_hub_leg",
    "full_route_aggregate",
    "carrier_aggregate",
    "city_pair_direct",
]
ExecutionState = Literal[
    "searched",
    "skipped",
    "failed",
    "not_executed",
    "deduped",
    "not_supported",
]
CacheStatus = Literal["live", "cache_hit", "stale_cache_used", "disabled", "unknown"]
EvidenceType = Literal[
    "positive_live_evidence",
    "positive_cached_hint",
    "negative_provider_empty",
    "negative_cache_absence",
    "provider_unavailable",
    "not_executed",
    "not_supported",
]


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_ru_touching: bool = False
    supports_global: bool = False
    supports_city_code: bool = False
    supports_direct_only: bool = False
    supports_carrier_filter: bool = False
    supports_full_route_aggregate: bool = False
    supports_round_trip: bool = False
    supports_cache: bool = False
    probe_types: frozenset[ProbeType] = frozenset()


@dataclass(frozen=True)
class ProviderProbeResult:
    probe_id: str
    probe_type: ProbeType
    provider: ProviderName
    query: dict[str, Any]
    execution_state: ExecutionState
    cache_status: CacheStatus = "unknown"
    evidence_type: EvidenceType = "not_executed"
    result_summary: dict[str, Any] = field(default_factory=dict)
    offers: tuple[dict[str, Any], ...] = ()
    source_boundary: dict[str, Any] = field(default_factory=dict)
    errors: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "query", freeze(self.query))
        object.__setattr__(self, "result_summary", freeze(self.result_summary))
        object.__setattr__(self, "offers", tuple(freeze(self.offers)))
        object.__setattr__(self, "source_boundary", freeze(self.source_boundary))
        object.__setattr__(self, "errors", tuple(freeze(self.errors)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "probe_type": self.probe_type,
            "provider": self.provider,
            "query": thaw(self.query),
            "execution_state": self.execution_state,
            "cache_status": self.cache_status,
            "evidence_type": self.evidence_type,
            "result_summary": thaw(self.result_summary),
            "offers": thaw(self.offers),
            "source_boundary": thaw(self.source_boundary),
            "errors": thaw(self.errors),
        }

    def as_dict(self) -> dict[str, Any]:
        return self.to_dict()


@runtime_checkable
class FlightProviderPort(Protocol):
    name: ProviderName
    capabilities: ProviderCapabilities

    def search_segment(self, query: dict[str, Any]) -> ProviderProbeResult: ...

    def search_aggregate(self, query: dict[str, Any]) -> ProviderProbeResult: ...
