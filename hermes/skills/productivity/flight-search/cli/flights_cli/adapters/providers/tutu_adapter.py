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
from ...providers.tutu_mcp import (
    cached_tutu_avia_search,
    tutu_result_to_segment_result,
    tutu_segment_search_summary,
)
from ...store import Store
from ...execution.cache_status import cache_status_from_result
from .common import evidence_type_for_offer_count, segment_probe_type_from_query


TUTU_CAPABILITIES = ProviderCapabilities(
    supports_ru_touching=True,
    supports_global=True,
    supports_city_code=False,
    supports_direct_only=True,
    supports_carrier_filter=True,
    supports_full_route_aggregate=True,
    supports_round_trip=True,
    supports_cache=True,
    probe_types=frozenset(
        {
            "segment_direct",
            "segment_hub_leg",
            "full_route_aggregate",
            "carrier_aggregate",
            "city_pair_direct",
        }
    ),
)


class TutuProviderAdapter:
    name: ProviderName = "tutu"
    capabilities = TUTU_CAPABILITIES

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
        direct_only = bool(query.get("direct_only", True))
        result = cached_tutu_avia_search(
            origin,
            destination,
            depart_date,
            currency=str(query["currency"]).upper(),
            only_carriers=list(query.get("only_carriers") or []),
            direct_only=direct_only,
            limit=int(query["limit"]),
            timeout=int(query.get("timeout") or 60),
            mcp_url=query.get("tutu_mcp_url"),  # Tutu-specific URL, not fli_mcp_url
            cache_ttl_seconds=int(query.get("cache_ttl_seconds") or 0),
            use_cache=bool(query.get("use_cache", True)),
            store=self.store,
            **kwargs,
        )
        segment_result = tutu_result_to_segment_result(
            result, direction=direction, leg=leg
        )
        spec = {
            "direction": direction,
            "leg": leg,
            "origin": origin,
            "destination": destination,
            "date": depart_date_text,
        }
        summary = tutu_segment_search_summary(spec, result, segment_result)
        cache_status: CacheStatus = cache_status_from_result(result)  # type: ignore[assignment]
        offer_count = len(segment_result.get("offers") or [])
        return ProviderProbeResult(
            probe_id=str(query.get("probe_id") or ""),
            probe_type=segment_probe_type_from_query(query, self.capabilities),
            provider="tutu",
            query={
                "origin": origin,
                "destination": destination,
                "date": depart_date_text,
                "currency": str(query["currency"]).upper(),
                "only_carriers": list(query.get("only_carriers") or []),
                "direct_only": direct_only,
                "mcp_url": query.get("tutu_mcp_url"),
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
                "provider": "tutu",
                "source_key": segment_result.get("source_key"),
                "source": segment_result.get("source") or result.get("source"),
                "scope": "Tutu MCP segment search",
                "warning": "tutu.ru aggregate source; verify fare, baggage, and seat availability before ticketing",
            },
        )

    def search_aggregate(self, query: dict[str, Any]) -> ProviderProbeResult:
        origin = str(query["origin"]).upper()
        destination = str(query["destination"]).upper()
        depart_date_text = str(query["date"])
        depart_date = parse_iso_date(depart_date_text, "aggregate-control-date")
        return_date_text = query.get("return_date")
        return_date = (
            parse_iso_date(return_date_text, "return-date")
            if return_date_text
            else None
        )
        direct_only = bool(query.get("direct_only", False))
        kwargs: dict[str, Any] = {}
        if self.fetcher is not None:
            kwargs["fetcher"] = self.fetcher
        result = cached_tutu_avia_search(
            origin,
            destination,
            depart_date,
            currency=str(query["currency"]).upper(),
            only_carriers=list(query.get("only_carriers") or []),
            direct_only=direct_only,
            limit=int(query["limit"]),
            timeout=int(query.get("timeout") or 60),
            mcp_url=query.get("tutu_mcp_url"),
            cache_ttl_seconds=int(query.get("cache_ttl_seconds") or 0),
            use_cache=bool(query.get("use_cache", True)),
            store=self.store,
            return_date=return_date,
            **kwargs,
        )
        from ...adapters.providers.kupibilet_adapter import aggregate_offer_summary

        offers = [
            offer for offer in (result.get("offers") or []) if isinstance(offer, dict)
        ]
        top_offers = []
        for offer in offers:
            summary_offer = aggregate_offer_summary(offer)
            if offer.get("journeys"):
                summary_offer["journeys"] = offer.get("journeys")
                summary_offer["journey_scope"] = offer.get("journey_scope")
            if offer.get("ticketing_model"):
                summary_offer["ticketing_model"] = offer.get("ticketing_model")
            top_offers.append(summary_offer)
        summary = {
            "direction": str(query.get("direction") or ""),
            "origin": origin,
            "destination": destination,
            "date": depart_date_text,
            "status": "ok",
            "provider": "tutu",
            "source": result.get("source"),
            "filters": result.get(
                "filters",
                {
                    "direct_only": direct_only,
                    "only_carriers": list(query.get("only_carriers") or []),
                },
            ),
            "offer_count": len(top_offers),
            "raw_offer_count": result.get("raw_count"),
            "omitted_offer_count": result.get("omitted_offer_count"),
            "pagination": result.get("pagination", {}),
            "cache": result.get("cache", {"hit": False}),
            "cache_status": cache_status_from_result(result),
            "top_offers": top_offers,
        }
        cache_status: CacheStatus = cache_status_from_result(result)  # type: ignore[assignment]
        offer_count = len(top_offers)
        probe_type: ProbeType = cast(
            ProbeType,
            "carrier_aggregate"
            if query.get("only_carriers")
            else "full_route_aggregate",
        )
        return ProviderProbeResult(
            probe_id=str(query.get("probe_id") or ""),
            probe_type=probe_type,
            provider="tutu",
            query={
                "origin": origin,
                "destination": destination,
                "date": depart_date_text,
                "return_date": return_date.isoformat() if return_date else None,
                "currency": str(query["currency"]).upper(),
                "only_carriers": list(query.get("only_carriers") or []),
                "direct_only": direct_only,
            },
            execution_state="searched",
            cache_status=cache_status,
            evidence_type=evidence_type_for_offer_count(
                offer_count=offer_count, cache_status=cache_status
            ),
            result_summary=summary,
            normalized_offers=top_offers,
            normalized_result={"top_offers": top_offers},
            source_boundary={
                "provider": "tutu",
                "source": result.get("source"),
                "scope": "Tutu MCP aggregate full-route search",
                "warning": "aggregate route offers are provider-returned candidates, not verified protected fares",
            },
        )
