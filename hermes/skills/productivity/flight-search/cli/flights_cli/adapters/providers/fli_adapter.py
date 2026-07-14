from __future__ import annotations

from typing import Any, cast

from ...domain.normalize import normalize_airport_scope, parse_iso_date
from ...domain.offer_order import provider_offer_business_key
from ...errors import CliError
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


def _fli_scope_pairs(
    origin: str,
    destination: str,
    origin_airports: list[str],
    destination_airports: list[str],
) -> list[tuple[str, str]]:
    origins = origin_airports or [origin]
    destinations = destination_airports or [destination]
    return [
        (scope_origin, scope_destination)
        for scope_origin in origins
        for scope_destination in destinations
    ]


def _fli_offer_key(offer: dict[str, Any]) -> tuple[Any, ...]:
    segments = [
        segment for segment in offer.get("segments") or [] if isinstance(segment, dict)
    ]
    if segments:
        return tuple(
            (
                segment.get("origin"),
                segment.get("destination"),
                segment.get("departure_at"),
                segment.get("arrival_at"),
                segment.get("flight_number"),
            )
            for segment in segments
        )
    return (offer.get("id"), offer.get("origin"), offer.get("destination"))


def _merge_fli_scope_results(
    results: list[dict[str, Any]],
    *,
    origin: str,
    destination: str,
    origin_airports: list[str],
    destination_airports: list[str],
    limit: int,
    scope_query_count: int,
    scope_query_errors: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(results) == 1:
        result = dict(results[0])
        result["filters"] = {
            **(result.get("filters") or {}),
            "origin_airports": origin_airports,
            "destination_airports": destination_airports,
        }
        result["scope_query_count"] = scope_query_count
        result["scope_query_errors"] = scope_query_errors
        if scope_query_errors:
            skipped = dict(result.get("skipped") or {})
            skipped["scope_query_error"] = len(scope_query_errors)
            result["skipped"] = skipped
        return result

    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    skipped: dict[str, int] = {}
    for result in results:
        for reason, count in (result.get("skipped") or {}).items():
            skipped[str(reason)] = skipped.get(str(reason), 0) + int(count or 0)
        for offer in result.get("offers") or []:
            if not isinstance(offer, dict):
                continue
            key = _fli_offer_key(offer)
            current = deduped.get(key)
            if current is None or provider_offer_business_key(
                offer
            ) < provider_offer_business_key(current):
                deduped[key] = offer
    if scope_query_errors:
        skipped["scope_query_error"] = len(scope_query_errors)

    offers = sorted(deduped.values(), key=provider_offer_business_key)
    base = dict(results[0])
    base.update(
        {
            "origin": origin,
            "destination": destination,
            "filters": {
                **(base.get("filters") or {}),
                "origin_airports": origin_airports,
                "destination_airports": destination_airports,
            },
            "raw_count": sum(int(result.get("raw_count") or 0) for result in results),
            "unique_flight_count": len(offers),
            "offer_count": min(len(offers), max(0, limit)),
            "skipped": skipped,
            "offers": offers[: max(0, limit)],
            "scope_query_count": scope_query_count,
            "scope_query_errors": scope_query_errors,
            "cache": {
                "hit": all(
                    bool((result.get("cache") or {}).get("hit")) for result in results
                ),
                "disabled": all(
                    bool((result.get("cache") or {}).get("disabled"))
                    for result in results
                ),
            },
        }
    )
    return base


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
        origin_airports = normalize_airport_scope(
            list(query.get("origin_airports") or []), "origin-airport"
        )
        destination_airports = normalize_airport_scope(
            list(query.get("destination_airports") or []), "destination-airport"
        )
        scope_pairs = _fli_scope_pairs(
            origin,
            destination,
            origin_airports,
            destination_airports,
        )
        results: list[dict[str, Any]] = []
        scope_query_errors: list[dict[str, Any]] = []
        first_error: CliError | None = None
        for scope_origin, scope_destination in scope_pairs:
            try:
                results.append(
                    cached_fli_mcp_search(
                        scope_origin,
                        scope_destination,
                        depart_date,
                        currency=str(query["currency"]).upper(),
                        only_carriers=list(query.get("only_carriers") or []),
                        origin_airports=[scope_origin] if origin_airports else [],
                        destination_airports=[scope_destination]
                        if destination_airports
                        else [],
                        direct_only=bool(query.get("direct_only", True)),
                        limit=int(query["limit"]),
                        timeout=int(query.get("timeout") or 60),
                        mcp_url=query.get("mcp_url"),
                        cache_ttl_seconds=int(query.get("cache_ttl_seconds") or 0),
                        use_cache=bool(query.get("use_cache", True)),
                        store=self.store,
                        **kwargs,
                    )
                )
            except CliError as exc:
                first_error = first_error or exc
                scope_query_errors.append(
                    {
                        "origin": scope_origin,
                        "destination": scope_destination,
                        "type": exc.error_type,
                        "message": exc.message,
                    }
                )
        if not results and first_error is not None:
            raise first_error
        result = _merge_fli_scope_results(
            results,
            origin=origin,
            destination=destination,
            origin_airports=origin_airports,
            destination_airports=destination_airports,
            limit=int(query["limit"]),
            scope_query_count=len(scope_pairs),
            scope_query_errors=scope_query_errors,
        )
        result_filters = result.get("filters") or {}
        origin_airports = list(result_filters.get("origin_airports") or origin_airports)
        destination_airports = list(
            result_filters.get("destination_airports") or destination_airports
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
        summary["scope_query_count"] = result.get("scope_query_count", 1)
        summary["scope_query_errors"] = result.get("scope_query_errors", [])
        cache_status: CacheStatus = cache_status_from_result(result)  # type: ignore[assignment]
        offer_count = len(segment_result.get("offers") or [])
        scope_query_errors = list(result.get("scope_query_errors") or [])
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
                "origin_airports": origin_airports,
                "destination_airports": destination_airports,
                "direct_only": bool(query.get("direct_only", True)),
                "mcp_url": query.get("mcp_url"),
            },
            execution_state="searched",
            cache_status=cache_status,
            evidence_type=(
                "provider_unavailable"
                if not offer_count and scope_query_errors
                else evidence_type_for_offer_count(
                    offer_count=offer_count, cache_status=cache_status
                )
            ),
            result_summary=summary,
            offers=tuple(segment_result.get("offers") or []),
            source_boundary={
                "provider": "fli",
                "source_key": segment_result.get("source_key"),
                "source": segment_result.get("source") or result.get("source"),
                "scope": "FLI MCP segment search",
                "scope_complete": not scope_query_errors,
                "scope_query_error_count": len(scope_query_errors),
                "warning": "Google Flights reverse-engineered source is advisory and must be rechecked before ticketing",
            },
            errors=tuple(scope_query_errors),
        )

    def search_aggregate(self, query: dict[str, Any]) -> ProviderProbeResult:
        origin_airports = normalize_airport_scope(
            list(query.get("origin_airports") or []), "origin-airport"
        )
        destination_airports = normalize_airport_scope(
            list(query.get("destination_airports") or []), "destination-airport"
        )
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
                "origin_airports": origin_airports,
                "destination_airports": destination_airports,
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
