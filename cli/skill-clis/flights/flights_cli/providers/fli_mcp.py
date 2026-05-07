from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from .. import __version__
from ..config import DEFAULT_CURRENCY, DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS, FLI_MCP_DEFAULT_URL, SUPPORTED_CURRENCIES
from ..domain.carriers import carrier_from_flight_number
from ..domain.normalize import normalize_carrier_code, normalize_iata, parse_iso_date, price_value
from ..errors import CliError
from ..store import Store
from .live_cache import live_cache_key, read_live_cache, write_live_cache

MCP_PROTOCOL_VERSION = "2025-03-26"
FLI_NORMALIZER_VERSION = "airport-name-v2"


def default_fli_mcp_url() -> str:
    return os.getenv("FLIGHTS_FLI_MCP_URL", FLI_MCP_DEFAULT_URL)


def normalize_mcp_url(value: str | None) -> str:
    url = (value or default_fli_mcp_url()).strip()
    if not url:
        raise CliError("FLI MCP URL is required", error_type="validation_error")
    if url.endswith("/mcp/"):
        url = url[:-1]
    return url


def decode_mcp_response(raw: bytes, content_type: str | None) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return {}
    if "text/event-stream" in (content_type or "").lower():
        events: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                item = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
        if not events:
            raise CliError("FLI MCP returned an empty event stream", error_type="upstream_error")
        for item in reversed(events):
            if "result" in item or "error" in item:
                return item
        return events[-1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError(f"FLI MCP returned invalid JSON: {exc}", error_type="upstream_error") from exc
    if not isinstance(data, dict):
        raise CliError("FLI MCP response must be a JSON object", error_type="upstream_error")
    return data


def mcp_http_post(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: int,
    session_id: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "User-Agent": f"flights-cli/{__version__}",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type")
            next_session_id = response.headers.get("Mcp-Session-Id") or response.headers.get("mcp-session-id") or session_id
            return decode_mcp_response(raw, content_type), next_session_id
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:1000]
        raise CliError(f"FLI MCP HTTP {exc.code}: {body_text}", error_type="upstream_error") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise CliError(f"FLI MCP request failed: {type(exc).__name__}: {exc}", error_type="upstream_error") from exc


def ensure_jsonrpc_ok(response: dict[str, Any], context: str) -> dict[str, Any]:
    error = response.get("error")
    if isinstance(error, dict):
        message = error.get("message") or json.dumps(error, ensure_ascii=False, sort_keys=True)
        raise CliError(f"FLI MCP {context} failed: {message}", error_type="upstream_error")
    result = response.get("result")
    if isinstance(result, dict):
        return result
    if result is None:
        return {}
    raise CliError(f"FLI MCP {context} returned an unsupported result", error_type="upstream_error")


def extract_tool_payload(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("isError"):
        messages = []
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("text"):
                messages.append(str(item["text"]))
        raise CliError("FLI MCP tool error: " + ("; ".join(messages) or "unknown error"), error_type="upstream_error")
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        if isinstance(structured.get("result"), dict):
            return structured["result"]
        return structured
    for item in result.get("content") or []:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str):
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise CliError("FLI MCP tool response did not include a JSON payload", error_type="upstream_error")


def call_fli_mcp_tool(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    mcp_url: str | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    url = normalize_mcp_url(mcp_url)
    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "hermes-flights-cli", "version": __version__},
        },
    }
    init_response, session_id = mcp_http_post(url, init_payload, timeout=timeout)
    ensure_jsonrpc_ok(init_response, "initialize")

    initialized_payload = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    mcp_http_post(url, initialized_payload, timeout=timeout, session_id=session_id)

    call_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    call_response, _ = mcp_http_post(url, call_payload, timeout=timeout, session_id=session_id)
    return extract_tool_payload(ensure_jsonrpc_ok(call_response, f"tools/call {tool_name}"))


def enum_code(value: Any, *, size: int | None = None) -> str:
    if isinstance(value, dict):
        for key in ("code", "name", "value"):
            if value.get(key):
                return enum_code(value[key], size=size)
    text = str(value or "").strip().upper()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    text = text.replace("_", "").replace(" ", "")
    if size is not None:
        match = re.search(rf"[A-Z0-9]{{{size}}}", text)
        return match.group(0) if match else text[:size]
    return text


def airport_name_key(value: Any) -> tuple[str, ...]:
    text = str(value or "").casefold()
    words = re.findall(r"[a-z0-9]+", text)
    noise = {"airport", "international", "intl"}
    return tuple(word for word in words if word not in noise)


def fli_airport_code_token(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("code", "value"):
            token = fli_airport_code_token(value.get(key))
            if token:
                return token
        return fli_airport_code_token(value.get("name"))
    text = str(value or "").strip().upper()
    if "." in text:
        text = text.rsplit(".", 1)[-1].strip()
    text = text.replace("_", "").replace(" ", "")
    return text if re.fullmatch(r"[A-Z0-9]{3}", text) else None


@lru_cache(maxsize=8)
def airport_name_index(cache_dir: str) -> dict[tuple[str, ...], str]:
    store = Store(Path(cache_dir))
    candidates: dict[tuple[str, ...], set[str]] = {}
    for airport in store.airports:
        if airport.get("flightable") is False:
            continue
        code = str(airport.get("code") or "").upper()
        if not code:
            continue
        names = [airport.get("name")]
        translations = airport.get("name_translations")
        if isinstance(translations, dict):
            names.extend(translations.values())
        for name in names:
            key = airport_name_key(name)
            if key:
                candidates.setdefault(key, set()).add(code)
    exact = {key: next(iter(codes)) for key, codes in candidates.items() if len(codes) == 1}
    return exact


def resolve_fli_airport(value: Any, *, store: Store, field: str, preferred_code: str | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        raise CliError(f"FLI {field} is empty", error_type="upstream_error")
    code_like = fli_airport_code_token(value)
    airport_by_code = store.airport_by_code
    preferred = str(preferred_code or "").strip().upper()
    if preferred not in airport_by_code:
        preferred = ""
    if code_like and code_like in airport_by_code:
        return code_like

    key = airport_name_key(text)
    exact = airport_name_index(str(store.cache_dir))
    if key in exact:
        return exact[key]

    matches = [
        code
        for candidate_key, code in exact.items()
        if key and (set(key) <= set(candidate_key) or set(candidate_key) <= set(key))
    ]
    unique_matches = sorted(set(matches))
    if preferred and preferred in unique_matches:
        return preferred
    if len(unique_matches) == 1:
        return unique_matches[0]
    if unique_matches:
        raise CliError(
            f"FLI {field} airport name {text!r} is ambiguous: {', '.join(unique_matches)}",
            error_type="upstream_error",
        )
    raise CliError(f"FLI {field} airport name {text!r} was not found in the airport catalog", error_type="upstream_error")


def parse_duration_minutes(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    hours = 0
    minutes = 0
    hour_match = re.search(r"(\d+)\s*(?:h|hr|hour)", text)
    minute_match = re.search(r"(\d+)\s*(?:m|min|minute)", text)
    if hour_match:
        hours = int(hour_match.group(1))
    if minute_match:
        minutes = int(minute_match.group(1))
    return hours * 60 + minutes if hours or minutes else None


def normalize_fli_leg(leg: dict[str, Any], *, store: Store) -> dict[str, Any] | None:
    origin = resolve_fli_airport(leg.get("departure_airport"), store=store, field="departure_airport")
    destination = resolve_fli_airport(leg.get("arrival_airport"), store=store, field="arrival_airport")
    airline_code = enum_code(leg.get("airline_code") or leg.get("airline"), size=2)
    flight_number = str(leg.get("flight_number") or "").strip().replace(" ", "")
    if airline_code and flight_number and not flight_number.upper().startswith(airline_code):
        flight_number = f"{airline_code}{flight_number}"
    carrier = airline_code or carrier_from_flight_number(flight_number)
    return {
        "flight_number": flight_number or None,
        "marketing_carrier": carrier,
        "operating_carrier": carrier,
        "origin": origin,
        "destination": destination,
        "departure_at": str(leg.get("departure_time") or ""),
        "arrival_at": str(leg.get("arrival_time") or ""),
        "duration": parse_duration_minutes(leg.get("duration")),
    }


def fli_offer_key(flights: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        f"{flight.get('flight_number')}:{flight.get('departure_at')}:{flight.get('arrival_at')}"
        for flight in flights
    )


def parse_fli_flight_search(
    raw: dict[str, Any],
    *,
    origin: str,
    destination: str,
    depart_date: str,
    currency: str,
    limit: int = 20,
    mcp_url: str | None = None,
    filters: dict[str, Any] | None = None,
    store: Store | None = None,
) -> dict[str, Any]:
    if raw.get("success") is False:
        raise CliError(f"FLI MCP search failed: {raw.get('error') or 'unknown error'}", error_type="upstream_error")
    raw_flights = raw.get("flights")
    if not isinstance(raw_flights, list):
        raise CliError("FLI MCP response does not contain a flights list", error_type="upstream_error")
    deduped: dict[tuple[str, ...], dict[str, Any]] = {}
    skipped: dict[str, int] = {}
    airport_store = store or Store()
    for index, flight in enumerate(raw_flights):
        if not isinstance(flight, dict):
            skipped["bad_flight"] = skipped.get("bad_flight", 0) + 1
            continue
        legs = flight.get("legs")
        if not isinstance(legs, list) or not legs:
            skipped["no_legs"] = skipped.get("no_legs", 0) + 1
            continue
        normalized_flights = []
        for leg in legs:
            if isinstance(leg, dict):
                normalized = normalize_fli_leg(leg, store=airport_store)
                if normalized is not None:
                    normalized_flights.append(normalized)
        if not normalized_flights:
            skipped["bad_legs"] = skipped.get("bad_legs", 0) + 1
            continue
        if normalized_flights[0]["origin"] != origin or normalized_flights[-1]["destination"] != destination:
            raise CliError(
                "FLI normalized route does not match query: "
                f"{normalized_flights[0]['origin']}-{normalized_flights[-1]['destination']} returned for {origin}-{destination}",
                error_type="upstream_error",
            )
        key = fli_offer_key(normalized_flights)
        amount = price_value({"price": flight.get("price")})
        offer = {
            "id": str(flight.get("id") or f"fli:{index}"),
            "price": amount,
            "currency": str(flight.get("currency") or currency).upper(),
            "number_of_changes": max(0, len(normalized_flights) - 1),
            "duration": sum(item["duration"] or 0 for item in normalized_flights) or None,
            "departure_at": normalized_flights[0]["departure_at"],
            "arrival_at": normalized_flights[-1]["arrival_at"],
            "origin": normalized_flights[0]["origin"],
            "destination": normalized_flights[-1]["destination"],
            "flight_numbers": [item["flight_number"] for item in normalized_flights if item.get("flight_number")],
            "marketing_carriers": sorted({item["marketing_carrier"] for item in normalized_flights if item.get("marketing_carrier")}),
            "operating_carriers": sorted({item["operating_carrier"] for item in normalized_flights if item.get("operating_carrier")}),
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
        "source": "FLI MCP search_flights (Google Flights reverse-engineered)",
        "source_url": normalize_mcp_url(mcp_url),
        "note": "Self-hosted FLI MCP source; Google Flights data is advisory and must be rechecked before ticketing.",
        "filters": filters or {},
        "raw_count": raw.get("count", len(raw_flights)),
        "trip_type": raw.get("trip_type"),
        "skipped": skipped,
        "offer_count": len(offers),
        "unique_flight_count": len(deduped),
        "offers": offers,
    }


def fetch_fli_mcp_search(
    origin: str,
    destination: str,
    depart_date: date,
    *,
    currency: str,
    only_carriers: list[str] | None = None,
    direct_only: bool = False,
    limit: int = 20,
    timeout: int = 60,
    mcp_url: str | None = None,
    cabin_class: str = "ECONOMY",
    max_stops: str = "ANY",
    sort_by: str = "CHEAPEST",
    passengers: int = 1,
    store: Store | None = None,
) -> dict[str, Any]:
    effective_max_stops = "NON_STOP" if direct_only else max_stops
    airlines = sorted({normalize_carrier_code(code, "only-carrier") for code in (only_carriers or [])})
    arguments: dict[str, Any] = {
        "origin": origin,
        "destination": destination,
        "departure_date": depart_date.isoformat(),
        "airlines": airlines or None,
        "cabin_class": cabin_class,
        "max_stops": effective_max_stops,
        "sort_by": sort_by,
        "passengers": passengers,
        "show_all_results": True,
    }
    raw = call_fli_mcp_tool("search_flights", arguments, mcp_url=mcp_url, timeout=timeout)
    return parse_fli_flight_search(
        raw,
        origin=origin,
        destination=destination,
        depart_date=depart_date.isoformat(),
        currency=currency,
        limit=limit,
        mcp_url=mcp_url,
        filters={
            "only_carriers": airlines,
            "direct_only": direct_only,
            "max_stops": effective_max_stops,
            "cabin_class": cabin_class,
            "sort_by": sort_by,
            "passengers": passengers,
        },
        store=store,
    )


def cached_fli_mcp_search(
    origin: str,
    destination: str,
    depart_date: date,
    *,
    currency: str,
    only_carriers: list[str],
    direct_only: bool,
    limit: int,
    timeout: int,
    mcp_url: str | None,
    cabin_class: str = "ECONOMY",
    max_stops: str = "ANY",
    sort_by: str = "CHEAPEST",
    passengers: int = 1,
    cache_ttl_seconds: int = DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    use_cache: bool = True,
    fetcher: Any = fetch_fli_mcp_search,
    store: Store | None = None,
) -> dict[str, Any]:
    url = normalize_mcp_url(mcp_url)
    params = {
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date.isoformat(),
        "currency": currency,
        "only_carriers": sorted(only_carriers),
        "direct_only": bool(direct_only),
        "limit": int(limit),
        "mcp_url": url,
        "cabin_class": cabin_class,
        "max_stops": max_stops,
        "sort_by": sort_by,
        "passengers": int(passengers),
        "normalizer": FLI_NORMALIZER_VERSION,
    }
    key = live_cache_key("fli_mcp_search_flights", params)
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
        mcp_url=url,
        cabin_class=cabin_class,
        max_stops=max_stops,
        sort_by=sort_by,
        passengers=passengers,
        store=store,
    )
    if use_cache and int(cache_ttl_seconds) > 0:
        return write_live_cache(key, result)
    result["cache"] = {"hit": False, "key": key, "disabled": True}
    return result


def fli_offer_to_segment_offer(
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
    offer_id = f"fli:{direction}:{leg}:{query_origin}-{query_destination}:{query_date}:{offer.get('id') or index}"
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
        "price": price_value({"price": offer.get("price")}),
        "currency": offer.get("currency") if isinstance(offer.get("currency"), str) else currency,
        "carrier": segments[0].get("carrier"),
        "main_airline": segments[0].get("carrier"),
        "changes": offer.get("number_of_changes"),
        "duration_min": offer.get("duration"),
        "source": "FLI MCP search_flights",
        "segments": segments,
        "transfers": [],
        "internal_connection_count": max(0, len(segments) - 1),
    }


def fli_result_to_segment_result(result: dict[str, Any], *, direction: str, leg: str) -> dict[str, Any]:
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
        normalized = fli_offer_to_segment_offer(
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
        "source_key": "fli_mcp_search_flights",
        "source": result.get("source"),
        "source_url": result.get("source_url"),
        "raw_count": result.get("raw_count"),
        "unique_flight_count": result.get("unique_flight_count"),
        "parse_errors": parse_errors,
        "offers": offers,
    }


def fli_segment_search_summary(spec: dict[str, Any], result: dict[str, Any], segment_result: dict[str, Any]) -> dict[str, Any]:
    return {
        **spec,
        "provider": "fli",
        "status": "ok",
        "raw_count": result.get("raw_count"),
        "unique_flight_count": result.get("unique_flight_count"),
        "offer_count": len(segment_result.get("offers") or []),
        "skipped": result.get("skipped", {}),
        "cache": result.get("cache", {"hit": False}),
    }


def airport_country_code(store: Store, code: str) -> str | None:
    airport = store.airport_by_code.get(code.upper())
    if not airport:
        return None
    country = airport.get("country_code")
    return str(country).upper() if country else None


def providers_for_segment(spec: dict[str, Any], store: Store, policy: str) -> list[str]:
    if policy in {"kupibilet", "fli"}:
        return [policy]
    if policy == "both":
        return ["kupibilet", "fli"]
    if policy != "auto":
        raise CliError("provider policy must be one of auto, kupibilet, fli, both", error_type="validation_error")
    origin_country = airport_country_code(store, str(spec.get("origin") or ""))
    destination_country = airport_country_code(store, str(spec.get("destination") or ""))
    if "RU" in {origin_country, destination_country}:
        return ["kupibilet"]
    return ["fli"]


def run_fli_search(args: argparse.Namespace, store: Store | None = None) -> dict[str, Any]:
    origin = normalize_iata(args.origin, "origin")
    destination = normalize_iata(args.destination, "destination")
    depart = parse_iso_date(args.depart_date, "depart-date")
    currency = args.currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise CliError(f"currency must be one of {', '.join(sorted(SUPPORTED_CURRENCIES))}", error_type="validation_error")
    only_carriers = [normalize_carrier_code(code, "only-carrier") for code in (args.only_carrier or [])]
    return cached_fli_mcp_search(
        origin,
        destination,
        depart,
        currency=currency,
        only_carriers=only_carriers,
        direct_only=args.direct_only,
        limit=args.limit,
        timeout=args.timeout,
        mcp_url=args.mcp_url,
        cabin_class=args.cabin_class,
        max_stops=args.max_stops,
        sort_by=args.sort_by,
        passengers=args.passengers,
        cache_ttl_seconds=args.cache_ttl_seconds,
        use_cache=not args.no_cache,
        store=store,
    )


def run_fli_dates(args: argparse.Namespace) -> dict[str, Any]:
    origin = normalize_iata(args.origin, "origin")
    destination = normalize_iata(args.destination, "destination")
    start = parse_iso_date(args.from_date, "from-date")
    end = parse_iso_date(args.to_date, "to-date")
    if end < start:
        raise CliError("to-date must be on or after from-date", error_type="validation_error")
    only_carriers = [normalize_carrier_code(code, "only-carrier") for code in (args.only_carrier or [])]
    raw = call_fli_mcp_tool(
        "search_dates",
        {
            "origin": origin,
            "destination": destination,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "trip_duration": args.trip_duration,
            "is_round_trip": args.round_trip,
            "airlines": only_carriers or None,
            "cabin_class": args.cabin_class,
            "max_stops": "NON_STOP" if args.direct_only else args.max_stops,
            "sort_by_price": args.sort_by_price,
            "passengers": args.passengers,
        },
        mcp_url=args.mcp_url,
        timeout=args.timeout,
    )
    if raw.get("success") is False:
        raise CliError(f"FLI MCP date search failed: {raw.get('error') or 'unknown error'}", error_type="upstream_error")
    dates = raw.get("dates") if isinstance(raw.get("dates"), list) else []
    return {
        "origin": origin,
        "destination": destination,
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "source": "FLI MCP search_dates (Google Flights reverse-engineered)",
        "source_url": normalize_mcp_url(args.mcp_url),
        "note": "Self-hosted FLI MCP source; Google Flights date prices are advisory and must be rechecked before ticketing.",
        "trip_type": raw.get("trip_type"),
        "date_range": raw.get("date_range"),
        "duration": raw.get("duration"),
        "count": raw.get("count", len(dates)),
        "dates": dates[: max(0, args.limit)],
    }
