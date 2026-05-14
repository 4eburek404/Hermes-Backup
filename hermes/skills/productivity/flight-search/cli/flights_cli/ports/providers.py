from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


ProviderName = Literal["kupibilet", "fli"]
ProbeType = Literal[
    "segment_direct",
    "segment_hub_leg",
    "full_route_aggregate",
    "carrier_aggregate",
    "city_pair_direct",
]
ExecutionState = Literal["searched", "skipped", "failed", "not_executed", "deduped", "cache_hit", "stale_cache_used", "not_supported"]
CacheStatus = Literal["live", "cache_hit", "stale_cache_used", "disabled", "unknown"]
EvidenceType = Literal[
    "positive_live_evidence",
    "positive_cached_hint",
    "negative_provider_empty",
    "negative_cache_absence",
    "provider_unavailable",
    "not_executed",
    "not_supported",
    "synthetic_control",
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
    normalized_offers: list[dict[str, Any]] = field(default_factory=list)
    source_boundary: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "probe_type": self.probe_type,
            "provider": self.provider,
            "query": self.query,
            "execution_state": self.execution_state,
            "cache_status": self.cache_status,
            "evidence_type": self.evidence_type,
            "result_summary": self.result_summary,
            "normalized_offers": self.normalized_offers,
            "source_boundary": self.source_boundary,
            "errors": self.errors,
        }


class FlightProviderPort(Protocol):
    name: ProviderName
    capabilities: ProviderCapabilities

    def search_segment(self, query: dict[str, Any]) -> ProviderProbeResult:
        ...

    def search_aggregate(self, query: dict[str, Any]) -> ProviderProbeResult:
        ...
