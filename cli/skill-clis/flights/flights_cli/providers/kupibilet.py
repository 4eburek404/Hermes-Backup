from __future__ import annotations

import argparse
import gzip
import json
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date
from typing import Any

from ..config import (
    CARRIER_RE,
    DEFAULT_CURRENCY,
    DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    KUPIBILET_FRONTEND_SEARCH_URL,
    KUPIBILET_HEADERS,
    SUPPORTED_CURRENCIES,
)
from ..domain.carriers import carrier_from_flight_number
from ..domain.normalize import normalize_carrier_code, normalize_iata, parse_iso_date, price_value
from ..errors import CliError
from .live_cache import live_cache_key, read_live_cache, write_live_cache

def build_kupibilet_payload(origin: str, destination: str, depart_date: str, currency: str) -> dict[str, Any]:
    return {
        "trips": [{"departure": origin, "arrival": destination, "date": depart_date}],
        "travelers": {"adult": 1, "child": 0, "infant": 0},
        "cabin": "economy",
        "agent": "kupibilet",
        "lang": "ru",
        "currency": currency,
        "client_platform": "web",
        "filters": {},
        "sort_by": "price",
        "short_response": False,
    }


def decode_http_body(raw: bytes, content_encoding: str | None) -> bytes:
    encoding = (content_encoding or "").split(";", 1)[0].strip().lower()
    if encoding == "gzip":
        return gzip.decompress(raw)
    return raw


def kupibilet_price_amount(variant: dict[str, Any]) -> int | None:
    price = variant.get("price")
    if isinstance(price, dict):
        return price_value({"price": price.get("amount")})
    return price_value({"price": price})


def kupibilet_variant_currency(variant: dict[str, Any], fallback: str) -> str:
    price = variant.get("price")
    if isinstance(price, dict) and isinstance(price.get("currency"), str):
        return price["currency"].upper()
    return fallback


def kupibilet_flight_number(flight: dict[str, Any]) -> str:
    carrier = str(flight.get("marketing_carrier") or flight.get("operating_carrier") or "").upper()
    number = str(flight.get("transport_number") or flight.get("number") or "").strip()
    return f"{carrier}{number}" if carrier or number else ""


def kupibilet_flight_carriers(flight: dict[str, Any]) -> set[str]:
    carriers: set[str] = set()
    for key in ("marketing_carrier", "operating_carrier"):
        value = flight.get(key)
        if isinstance(value, str) and value.strip():
            code = value.strip().upper()
            if CARRIER_RE.match(code):
                carriers.add(code)
    flight_number = kupibilet_flight_number(flight)
    carrier = carrier_from_flight_number(flight_number)
    if carrier:
        carriers.add(carrier)
    return carriers


def kupibilet_variant_flight_ids(variant: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for segment in variant.get("segments", []):
        if isinstance(segment, dict) and isinstance(segment.get("flights"), list):
            ids.extend(str(item) for item in segment["flights"] if item)
    return ids


def normalize_kupibilet_flight(raw: dict[str, Any]) -> dict[str, Any]:
    flight_number = kupibilet_flight_number(raw)
    return {
        "flight_number": flight_number,
        "marketing_carrier": str(raw.get("marketing_carrier") or "").upper(),
        "operating_carrier": str(raw.get("operating_carrier") or "").upper(),
        "origin": str(raw.get("departure") or "").upper(),
        "destination": str(raw.get("arrival") or "").upper(),
        "departure_at": str(raw.get("departure_datetime") or ""),
        "arrival_at": str(raw.get("arrival_datetime") or ""),
        "aircraft": raw.get("equipment"),
        "duration": raw.get("duration"),
        "transport_kind": raw.get("transport_kind"),
        "is_charter": raw.get("is_charter"),
    }


def kupibilet_total_duration(raw_flights: list[dict[str, Any]]) -> int | None:
    total = 0
    seen = False
    for flight in raw_flights:
        raw_duration = flight.get("duration")
        if raw_duration is None:
            continue
        try:
            duration = int(float(raw_duration))
        except (TypeError, ValueError):
            continue
        total += max(0, duration)
        seen = True
    return total if seen else None


def kupibilet_offer_key(flights: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        f"{flight.get('flight_number')}:{flight.get('departure_at')}:{flight.get('arrival_at')}"
        for flight in flights
    )


def parse_kupibilet_frontend_search(
    raw: dict[str, Any],
    *,
    origin: str,
    destination: str,
    depart_date: str,
    currency: str,
    only_carriers: list[str] | None = None,
    direct_only: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    variants = raw.get("variants") if isinstance(raw, dict) else None
    flights_by_id = raw.get("flights") if isinstance(raw, dict) else None
    if not isinstance(variants, list) or not isinstance(flights_by_id, dict):
        raise CliError("Kupibilet response does not contain variants/flights maps", error_type="upstream_error")

    carrier_filter = {code.strip().upper() for code in (only_carriers or []) if code.strip()}
    deduped: dict[tuple[str, ...], dict[str, Any]] = {}
    skipped = defaultdict(int)

    for index, variant in enumerate(variants):
        if not isinstance(variant, dict):
            skipped["bad_variant"] += 1
            continue
        flight_ids = kupibilet_variant_flight_ids(variant)
        if not flight_ids:
            skipped["no_flights"] += 1
            continue
        raw_flights = []
        for flight_id in flight_ids:
            raw_flight = flights_by_id.get(flight_id)
            if isinstance(raw_flight, dict):
                raw_flights.append(raw_flight)
        if len(raw_flights) != len(flight_ids):
            skipped["missing_flight_details"] += 1
            continue
        if any(flight.get("transport_kind") != "airplane" for flight in raw_flights):
            skipped["non_airplane"] += 1
            continue
        if direct_only and len(raw_flights) != 1:
            skipped["not_direct"] += 1
            continue
        if carrier_filter and not all(kupibilet_flight_carriers(flight) & carrier_filter for flight in raw_flights):
            skipped["carrier"] += 1
            continue

        normalized_flights = [normalize_kupibilet_flight(flight) for flight in raw_flights]
        key = kupibilet_offer_key(normalized_flights)
        if not key:
            skipped["empty_key"] += 1
            continue
        amount = kupibilet_price_amount(variant)
        offer = {
            "id": str(variant.get("id") or f"kupibilet:{index}"),
            "price": amount,
            "currency": kupibilet_variant_currency(variant, currency),
            "number_of_changes": max(0, len(normalized_flights) - 1),
            "duration": kupibilet_total_duration(raw_flights),
            "departure_at": normalized_flights[0]["departure_at"],
            "arrival_at": normalized_flights[-1]["arrival_at"],
            "origin": normalized_flights[0]["origin"],
            "destination": normalized_flights[-1]["destination"],
            "flight_numbers": [flight["flight_number"] for flight in normalized_flights],
            "marketing_carriers": sorted({flight["marketing_carrier"] for flight in normalized_flights if flight["marketing_carrier"]}),
            "operating_carriers": sorted({flight["operating_carrier"] for flight in normalized_flights if flight["operating_carrier"]}),
            "flights": normalized_flights,
        }
        previous = deduped.get(key)
        previous_price = previous.get("price") if previous else None
        if previous is None or (amount is not None and (previous_price is None or amount < previous_price)):
            deduped[key] = offer

    offers = sorted(
        deduped.values(),
        key=lambda item: (
            item.get("price") if item.get("price") is not None else 10**12,
            item.get("departure_at") or "",
            "-".join(item.get("flight_numbers") or []),
        ),
    )[: max(0, limit)]
    return {
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date,
        "currency": currency,
        "source": "Kupibilet frontend_search (live aggregate)",
        "source_url": KUPIBILET_FRONTEND_SEARCH_URL,
        "note": "Live aggregate source, not official aeroflot.ru; recheck final fare and seat availability before ticketing.",
        "filters": {"only_carriers": sorted(carrier_filter), "direct_only": direct_only, "dedupe": "flight_numbers+times"},
        "raw_variant_count": len(variants),
        "skipped": dict(skipped),
        "offer_count": len(offers),
        "unique_flight_count": len(deduped),
        "offers": offers,
    }


def fetch_kupibilet_search(
    origin: str,
    destination: str,
    depart_date: date,
    *,
    currency: str,
    only_carriers: list[str] | None = None,
    direct_only: bool = False,
    limit: int = 20,
    timeout: int = 60,
) -> dict[str, Any]:
    """Run one Kupibilet frontend_search request and normalize/dedupe offers."""
    payload = build_kupibilet_payload(origin, destination, depart_date.isoformat(), currency)
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        KUPIBILET_FRONTEND_SEARCH_URL,
        data=body,
        headers=KUPIBILET_HEADERS,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            decoded = decode_http_body(raw, response.headers.get("Content-Encoding"))
            data = json.loads(decoded.decode("utf-8"))
            status = response.status
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:1000]
        raise CliError(f"Kupibilet HTTP {exc.code}: {body_text}", error_type="upstream_error") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CliError(f"Kupibilet request failed: {type(exc).__name__}: {exc}", error_type="upstream_error") from exc

    result = parse_kupibilet_frontend_search(
        data,
        origin=origin,
        destination=destination,
        depart_date=depart_date.isoformat(),
        currency=currency,
        only_carriers=only_carriers,
        direct_only=direct_only,
        limit=limit,
    )
    result["http_status"] = status
    result["request"] = {
        "method": "POST",
        "endpoint": KUPIBILET_FRONTEND_SEARCH_URL,
        "body": payload,
        "headers": {"Content-Type": "application/json", "Origin": "https://www.kupibilet.ru", "Referer": "https://www.kupibilet.ru/"},
    }
    return result


def kupibilet_offer_to_segment_offer(
    offer: dict[str, Any],
    *,
    direction: str,
    leg: str,
    query_origin: str,
    query_destination: str,
    query_date: str,
    currency: str,
    index: int,
) -> dict[str, Any] | None:
    raw_flights = offer.get("flights")
    if not isinstance(raw_flights, list) or not raw_flights:
        return None
    segments = []
    for flight in raw_flights:
        if not isinstance(flight, dict):
            continue
        origin = str(flight.get("origin") or "").upper()
        destination = str(flight.get("destination") or "").upper()
        if not origin or not destination:
            continue
        flight_number = str(flight.get("flight_number") or "")
        operating = str(flight.get("operating_carrier") or "").upper()
        marketing = str(flight.get("marketing_carrier") or "").upper()
        carrier = operating or marketing or carrier_from_flight_number(flight_number)
        segments.append(
            {
                "origin": origin,
                "destination": destination,
                "departure_at": str(flight.get("departure_at") or ""),
                "arrival_at": str(flight.get("arrival_at") or ""),
                "carrier": carrier,
                "flight_number": flight_number or None,
                "marketing_carrier": marketing or None,
                "operating_carrier": operating or None,
                "aircraft_code": flight.get("aircraft"),
            }
        )
    if not segments:
        return None
    price = price_value({"price": offer.get("price")})
    currency_value_result = offer.get("currency") if isinstance(offer.get("currency"), str) else currency
    offer_id = f"kb:{direction}:{leg}:{query_origin}-{query_destination}:{query_date}:{offer.get('id') or index}"
    return {
        "id": offer_id,
        "direction": direction,
        "leg": leg,
        "query_origin": query_origin,
        "query_destination": query_destination,
        "query_date": query_date,
        "origin": segments[0]["origin"],
        "destination": segments[-1]["destination"],
        "departure_airport": segments[0]["origin"],
        "arrival_airport": segments[-1]["destination"],
        "departure_at": segments[0]["departure_at"],
        "arrival_at": segments[-1]["arrival_at"],
        "price": price,
        "currency": currency_value_result,
        "carrier": segments[0].get("carrier"),
        "main_airline": segments[0].get("carrier"),
        "changes": offer.get("number_of_changes"),
        "duration_min": offer.get("duration"),
        "source": "Kupibilet frontend_search direct-only",
        "segments": segments,
        "transfers": [],
        "internal_connection_count": max(0, len(segments) - 1),
    }


def kupibilet_result_to_segment_result(result: dict[str, Any], *, direction: str, leg: str) -> dict[str, Any]:
    query_origin = str(result.get("origin") or "").upper()
    query_destination = str(result.get("destination") or "").upper()
    query_date = str(result.get("depart_date") or "")
    currency = str(result.get("currency") or DEFAULT_CURRENCY).upper()
    offers = []
    parse_errors = 0
    for index, offer in enumerate(result.get("offers") or []):
        if not isinstance(offer, dict):
            parse_errors += 1
            continue
        normalized = kupibilet_offer_to_segment_offer(
            offer,
            direction=direction,
            leg=leg,
            query_origin=query_origin,
            query_destination=query_destination,
            query_date=query_date,
            currency=currency,
            index=index,
        )
        if normalized is None:
            parse_errors += 1
            continue
        offers.append(normalized)
    return {
        "direction": direction,
        "leg": leg,
        "query": {"origin": query_origin, "destination": query_destination, "date": query_date, "currency": currency},
        "source_key": "kupibilet_frontend_search",
        "source": result.get("source"),
        "source_url": result.get("source_url"),
        "raw_count": result.get("raw_variant_count"),
        "unique_flight_count": result.get("unique_flight_count"),
        "parse_errors": parse_errors,
        "offers": offers,
    }


def kupibilet_segment_search_summary(spec: dict[str, Any], result: dict[str, Any], segment_result: dict[str, Any]) -> dict[str, Any]:
    return {
        **spec,
        "status": "ok",
        "http_status": result.get("http_status"),
        "raw_variant_count": result.get("raw_variant_count"),
        "unique_flight_count": result.get("unique_flight_count"),
        "offer_count": len(segment_result.get("offers") or []),
        "skipped": result.get("skipped", {}),
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
    cache_ttl_seconds: int = DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    use_cache: bool = True,
    fetcher: Any = fetch_kupibilet_search,
) -> dict[str, Any]:
    params = {
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date.isoformat(),
        "currency": currency,
        "only_carriers": sorted(only_carriers),
        "direct_only": bool(direct_only),
        "limit": int(limit),
    }
    key = live_cache_key("kupibilet_frontend_search", params)
    if use_cache:
        cached = read_live_cache(key, ttl_seconds=int(cache_ttl_seconds))
        if cached is not None:
            return cached
    result = fetcher(
        origin,
        destination,
        depart_date,
        currency=currency,
        only_carriers=only_carriers,
        direct_only=direct_only,
        limit=limit,
        timeout=timeout,
    )
    if use_cache and int(cache_ttl_seconds) > 0:
        return write_live_cache(key, result)
    result["cache"] = {"hit": False, "key": key, "disabled": True}
    return result


def run_kb_search(args: argparse.Namespace) -> dict[str, Any]:
    """Run a Kupibilet live aggregate search and normalize/dedupe offers."""
    origin = normalize_iata(args.origin, "origin")
    destination = normalize_iata(args.destination, "destination")
    depart = parse_iso_date(args.depart_date, "depart-date")
    currency = args.currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise CliError(f"currency must be one of {', '.join(sorted(SUPPORTED_CURRENCIES))}", error_type="validation_error")
    only_carriers = [normalize_carrier_code(code, "only-carrier") for code in (args.only_carrier or [])]
    return cached_kupibilet_search(
        origin,
        destination,
        depart,
        currency=currency,
        only_carriers=only_carriers,
        direct_only=args.direct_only,
        limit=args.limit,
        timeout=args.timeout,
        cache_ttl_seconds=int(getattr(args, "cache_ttl_seconds", DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS)),
        use_cache=not bool(getattr(args, "no_cache", False)),
    )
