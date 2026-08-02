from __future__ import annotations

from datetime import date
from typing import Any

from ..config import (
    DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    KUPIBILET_FRONTEND_SEARCH_URL,
)
from ..domain.normalize import normalize_airport_scope
from .kupibilet_parser import (
    kupibilet_flight_carriers as kupibilet_flight_carriers,
    kupibilet_flight_number as kupibilet_flight_number,
    kupibilet_offer_key as kupibilet_offer_key,
    kupibilet_price_amount as kupibilet_price_amount,
    kupibilet_total_duration as kupibilet_total_duration,
    kupibilet_variant_currency as kupibilet_variant_currency,
    kupibilet_variant_flight_ids as kupibilet_variant_flight_ids,
    normalize_kupibilet_flight as normalize_kupibilet_flight,
    parse_kupibilet_frontend_search as parse_kupibilet_frontend_search,
)
from .live_cache import live_cache_key, read_live_cache, write_live_cache
from .segment_normalization import provider_result_to_segment_result
from .kupibilet_transport import (
    build_kupibilet_payload as build_kupibilet_payload,
    decode_http_body as decode_http_body,
    post_kupibilet_search,
)


def fetch_kupibilet_search(
    origin: str,
    destination: str,
    depart_date: date,
    *,
    currency: str,
    only_carriers: list[str] | None = None,
    origin_airports: list[str] | None = None,
    destination_airports: list[str] | None = None,
    direct_only: bool = False,
    limit: int = 20,
    timeout: int = 60,
) -> dict[str, Any]:
    """Run one Kupibilet frontend_search request and normalize/dedupe offers."""
    payload = build_kupibilet_payload(
        origin, destination, depart_date.isoformat(), currency
    )
    data, status = post_kupibilet_search(payload, timeout=timeout)

    result = parse_kupibilet_frontend_search(
        data,
        origin=origin,
        destination=destination,
        depart_date=depart_date.isoformat(),
        currency=currency,
        only_carriers=only_carriers,
        origin_airports=origin_airports,
        destination_airports=destination_airports,
        direct_only=direct_only,
        limit=limit,
    )
    result["http_status"] = status
    result["request"] = {
        "method": "POST",
        "endpoint": KUPIBILET_FRONTEND_SEARCH_URL,
        "body": payload,
        "headers": {
            "Content-Type": "application/json",
            "Origin": "https://www.kupibilet.ru",
            "Referer": "https://www.kupibilet.ru/",
        },
    }
    return result


def kupibilet_result_to_segment_result(
    result: dict[str, Any], *, direction: str, leg: str
) -> dict[str, Any]:
    return provider_result_to_segment_result(
        result,
        direction=direction,
        leg=leg,
        source_key="kupibilet_frontend_search",
        source_label="Kupibilet frontend_search direct-only",
        provider_prefix="kb",
        raw_count_key="raw_variant_count",
    )


def kupibilet_segment_search_summary(
    spec: dict[str, Any], result: dict[str, Any], segment_result: dict[str, Any]
) -> dict[str, Any]:
    return {
        **spec,
        "status": "ok",
        "http_status": result.get("http_status"),
        "raw_variant_count": result.get("raw_variant_count"),
        "unique_flight_count": result.get("unique_flight_count"),
        "offer_count": len(segment_result.get("offers") or []),
        "skipped": result.get("skipped", {}),
        "filters": result.get("filters", {}),
        "cache": result.get("cache", {"hit": False}),
    }


def cached_kupibilet_search(
    origin: str,
    destination: str,
    depart_date: date,
    *,
    currency: str,
    only_carriers: list[str],
    direct_only: bool,
    limit: int,
    timeout: int,
    origin_airports: list[str] | None = None,
    destination_airports: list[str] | None = None,
    cache_ttl_seconds: int = DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    use_cache: bool = True,
    fetcher: Any = fetch_kupibilet_search,
) -> dict[str, Any]:
    normalized_origin_airports = normalize_airport_scope(
        origin_airports, "origin-airport"
    )
    normalized_destination_airports = normalize_airport_scope(
        destination_airports, "destination-airport"
    )
    params = {
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date.isoformat(),
        "currency": currency,
        "only_carriers": sorted(only_carriers),
        "origin_airports": normalized_origin_airports,
        "destination_airports": normalized_destination_airports,
        "direct_only": bool(direct_only),
        "limit": int(limit),
    }
    key = live_cache_key("kupibilet_frontend_search", params)
    if use_cache:
        cached = read_live_cache(key, ttl_seconds=int(cache_ttl_seconds))
        if cached is not None:
            return cached
    if fetcher is None:
        fetcher = fetch_kupibilet_search
    result = fetcher(
        origin,
        destination,
        depart_date,
        currency=currency,
        only_carriers=only_carriers,
        origin_airports=normalized_origin_airports,
        destination_airports=normalized_destination_airports,
        direct_only=direct_only,
        limit=limit,
        timeout=timeout,
    )
    if use_cache and int(cache_ttl_seconds) > 0:
        return write_live_cache(key, result)
    result["cache"] = {"hit": False, "key": key, "disabled": True}
    return result


__all__ = [
    "build_kupibilet_payload",
    "cached_kupibilet_search",
    "decode_http_body",
    "fetch_kupibilet_search",
    "kupibilet_flight_carriers",
    "kupibilet_flight_number",
    "kupibilet_offer_key",
    "kupibilet_price_amount",
    "kupibilet_result_to_segment_result",
    "kupibilet_segment_search_summary",
    "kupibilet_total_duration",
    "kupibilet_variant_currency",
    "kupibilet_variant_flight_ids",
    "normalize_kupibilet_flight",
    "parse_kupibilet_frontend_search",
]
