from __future__ import annotations

from typing import Any

from ..adapters.providers.registry import provider_adapter
from ..domain.vocabulary import Leg
from ..store import Store


def run_diagnostic_probe(
    provider: str, request: dict[str, Any], store: Store
) -> dict[str, Any]:
    query = (
        request.get("query")
        if isinstance(request.get("query"), dict)
        else dict(request)
    )
    query.setdefault("currency", request.get("currency") or "RUB")
    query.setdefault("probe_id", request.get("probe_id") or f"diagnose-{provider}")
    query.setdefault("direction", request.get("direction") or "outbound")
    query.setdefault("leg", request.get("leg") or Leg.DIRECT_OUTBOUND)
    adapter = provider_adapter(provider, store=store)
    probe_type = str(
        request.get("probe_type") or query.get("probe_type") or "segment_direct"
    )
    if probe_type in {
        "full_route_aggregate",
        "carrier_aggregate",
    }:
        result = adapter.search_aggregate(query)
    else:
        result = adapter.search_segment(query)
    return {
        "schema_version": "flight_search_probe_diagnostic.v1",
        "provider": provider,
        "probe_type": probe_type,
        "probe": result.as_dict(),
    }
