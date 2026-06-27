from __future__ import annotations

from typing import Any, cast

from ...domain.normalize import parse_iso_date
from ...ports.providers import (
    CacheStatus,
    ProviderCapabilities,
    ProviderName,
    ProviderProbeResult,
    ProbeType,
)
from ...providers.fli_mcp import (
    cached_fli_mcp_search,
    fli_result_to_segment_result,
    fli_segment_search_summary,
)
from ...store import Store
from ...execution.cache_status import cache_status_from_result
from .common import evidence_type_for_offer_count, segment_probe_type_from_query


FLI_CAPABILITIES = ProviderCapabilities(
    supports_ru_touching=False,
    supports_global=True,
    supports_city_code=False,
    supports_direct_only=True,
    supports_carrier_filter=True,
    supports_full_route_aggregate=False,
    supports_round_trip=False,
    supports_cache=True,
    probe_types=frozenset({"segment_direct", "segment_hub_leg", "city_pair_direct"}),
)


class FliProviderAdapter:
    name: ProviderName = "fli"
    capabilities = FLI_CAPABILITIES

    def __init__(self, *, store: Store | None = None, fetcher: Any = None) -> None:
        self.store = store
        self.fetcher = fetcher

    def search_segment(self, query: dict[str, Any]) -> ProviderProbeResult:
        origin = str(query["origin"]).upper()
        destination = str(query["destination"]).upper()
        depart_date_text = str(query["date"])
        depart_date = parse_iso_date(depart_date_text, "segment-date")
        direction = str(query["direction"])
        leg = str(query["leg"])
        kwargs: dict[str, Any] = {}
        if self.fetcher is not None:
            kwargs["fetcher"] = self.fetcher
        result = cached_fli_mcp_search(
            origin,
            destination,
            depart_date,
            currency=str(query["currency"]).upper(),
            only_carriers=list(query.get("only_carriers") or []),
            direct_only=bool(query.get("direct_only", True)),
            limit=int(query.get("limit") or 30),
            timeout=int(query.get("timeout") or 60),
            mcp_url=query.get("mcp_url"),
            cache_ttl_seconds=int(query.get("cache_ttl_seconds") or 0),
            use_cache=bool(query.get("use_cache", True)),
            store=self.store,
            **kwargs,
        )
        segment_result = fli_result_to_segment_result(
            result, direction=direction, leg=leg
        )
        spec = {
            "direction": direction,
            "leg": leg,
            "origin": origin,
            "destination": destination,
            "date": depart_date_text,
        }
        summary = fli_segment_search_summary(spec, result, segment_result)
        cache_status: CacheStatus = cache_status_from_result(result)  # type: ignore[assignment]
        offer_count = len(segment_result.get("offers") or [])
        return ProviderProbeResult(
            probe_id=str(query.get("probe_id") or ""),
            probe_type=segment_probe_type_from_query(query, self.capabilities),
            provider="fli",
            query={
                "origin": origin,
                "destination": destination,
                "date": depart_date_text,
                "currency": str(query["currency"]).upper(),
                "only_carriers": list(query.get("only_carriers") or []),
                "direct_only": bool(query.get("direct_only", True)),
                "mcp_url": query.get("mcp_url"),
            },
            execution_state="searched",
            cache_status=cache_status,
            evidence_type=evidence_type_for_offer_count(
                offer_count=offer_count, cache_status=cache_status
            ),
            result_summary=summary,
            normalized_offers=list(segment_result.get("offers") or []),
            normalized_result=segment_result,
            source_boundary={
                "provider": "fli",
                "source_key": segment_result.get("source_key"),
                "source": segment_result.get("source") or result.get("source"),
                "scope": "FLI MCP segment search",
                "warning": "Google Flights reverse-engineered source is advisory and must be rechecked before ticketing",
            },
        )

    def search_aggregate(self, query: dict[str, Any]) -> ProviderProbeResult:
        probe_type: ProbeType = cast(
            ProbeType,
            query.get("probe_type")
            if query.get("probe_type") in {"full_route_aggregate", "carrier_aggregate"}
            else "full_route_aggregate",
        )
        reason = "fli does not support full-route aggregate probes"
        return ProviderProbeResult(
            probe_id=str(query.get("probe_id") or "probe-unsupported"),
            probe_type=probe_type,
            provider="fli",
            query={
                "origin": str(query.get("origin") or "").upper(),
                "destination": str(query.get("destination") or "").upper(),
                "date": query.get("date"),
            },
            execution_state="not_supported",
            cache_status="unknown",
            evidence_type="not_supported",
            result_summary={"reason": reason},
            source_boundary={
                "warning": "provider capability does not support this probe type"
            },
            errors=[{"type": "not_supported", "message": reason}],
        )
