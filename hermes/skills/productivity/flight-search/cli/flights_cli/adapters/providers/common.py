from __future__ import annotations

from typing import Any, Mapping, cast

from ...ports.providers import EvidenceType, ProviderCapabilities, ProbeType

_CACHE_EVIDENCE_STATUSES = {"cache_hit", "stale_cache_used"}


def segment_probe_type_from_query(
    query: Mapping[str, Any], capabilities: ProviderCapabilities
) -> ProbeType:
    probe_type = query.get("probe_type")
    if probe_type in capabilities.probe_types:
        return cast(ProbeType, probe_type)
    leg = str(query.get("leg") or "")
    return "segment_direct" if "direct" in leg else "segment_hub_leg"


def evidence_type_for_offer_count(
    *, offer_count: int, cache_status: str
) -> EvidenceType:
    if offer_count > 0:
        return (
            "positive_cached_hint"
            if cache_status in _CACHE_EVIDENCE_STATUSES
            else "positive_live_evidence"
        )
    return (
        "negative_cache_absence"
        if cache_status in _CACHE_EVIDENCE_STATUSES
        else "negative_provider_empty"
    )
