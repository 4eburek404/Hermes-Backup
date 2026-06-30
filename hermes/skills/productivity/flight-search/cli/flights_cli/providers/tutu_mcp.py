from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

from .. import __version__
from ..config import (
    DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    SUPPORTED_CURRENCIES,
    TUTU_MCP_DEFAULT_URL,
)
from ..domain.normalize import (
    normalize_carrier_code,
    normalize_iata,
    parse_iso_date,
    price_value,
)
from ..domain.offer_order import provider_offer_business_key
from ..domain.provider_offer_filter import filter_provider_offers
from ..errors import CliError
from ..store import Store
from .live_cache import live_cache_key, read_live_cache, write_live_cache
from .segment_normalization import (
    provider_offer_to_segment_offer,
    provider_result_to_segment_result,
)

MCP_PROTOCOL_VERSION = "2025-03-26"
TUTU_NORMALIZER_VERSION = "tutu-avia-v1"

# Matches a 3-letter IATA code in parentheses at end of string: "Тулуза — Тулуза-Бланьяк (TLS)" -> TLS
_IATA_RE = re.compile(r"\(([A-Z]{3})\)\s*(?:,\s*терм\.\s*\S+)?\s*$")


def default_tutu_mcp_url() -> str:
    return os.getenv("FLIGHTS_TUTU_MCP_URL", TUTU_MCP_DEFAULT_URL)


def normalize_tutu_mcp_url(value: str | None) -> str:
    url = (value or default_tutu_mcp_url()).strip()
    if not url:
        raise CliError("Tutu MCP URL is required", error_type="validation_error")
    if url.endswith("/mcp/"):
        url = url[:-1]
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError as exc:
        raise CliError("Tutu MCP URL is invalid", error_type="validation_error") from exc
    if parsed.scheme not in {"http", "https"}:
        raise CliError(
            "Tutu MCP URL must use http or https",
            error_type="validation_error",
        )
    if not parsed.netloc or not parsed.hostname:
        raise CliError("Tutu MCP URL must include a host", error_type="validation_error")
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
            raise CliError(
                "Tutu MCP returned an empty event stream", error_type="upstream_error"
            )
        for item in reversed(events):
            if "result" in item or "error" in item:
                return item
        return events[-1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError(
            f"Tutu MCP returned invalid JSON: {exc}", error_type="upstream_error"
        ) from exc
    if not isinstance(data, dict):
        raise CliError(
            "Tutu MCP response must be a JSON object", error_type="upstream_error"
        )
    return data


def tutu_mcp_http_post(
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
            next_session_id = (
                response.headers.get("Mcp-Session-Id")
                or response.headers.get("mcp-session-id")
                or session_id
            )
            return decode_mcp_response(raw, content_type), next_session_id
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:1000]
        raise CliError(
            f"Tutu MCP HTTP {exc.code}: {body_text}",
            error_type="upstream_error",
            details={
                "http_status": exc.code,
                "retry_after": exc.headers.get("Retry-After"),
            },
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise CliError(
            f"Tutu MCP request failed: {type(exc).__name__}: {exc}",
            error_type="upstream_error",
        ) from exc


def ensure_jsonrpc_ok(response: dict[str, Any], context: str) -> dict[str, Any]:
    error = response.get("error")
    if isinstance(error, dict):
        message = error.get("message") or json.dumps(
            error, ensure_ascii=False, sort_keys=True
        )
        raise CliError(
            f"Tutu MCP {context} failed: {message}", error_type="upstream_error"
        )
    result = response.get("result")
    if isinstance(result, dict):
        return result
    if result is None:
        return {}
    raise CliError(
        f"Tutu MCP {context} returned an unsupported result", error_type="upstream_error"
    )


def extract_tool_payload(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("isError"):
        messages = []
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("text"):
                messages.append(str(item["text"]))
        raise CliError(
            "Tutu MCP tool error: " + ("; ".join(messages) or "unknown error"),
            error_type="upstream_error",
        )
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
            # Tutu MCP wraps the payload in a {"result": "..."} string
            if isinstance(parsed.get("result"), str):
                try:
                    inner = json.loads(parsed["result"])
                    if isinstance(inner, dict):
                        return inner
                except json.JSONDecodeError:
                    pass
            return parsed
    raise CliError(
        "Tutu MCP tool response did not include a JSON payload",
        error_type="upstream_error",
    )


def call_tutu_mcp_tool(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    mcp_url: str | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    url = normalize_tutu_mcp_url(mcp_url)
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
    init_response, session_id = tutu_mcp_http_post(url, init_payload, timeout=timeout)
    ensure_jsonrpc_ok(init_response, "initialize")

    initialized_payload = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    }
    tutu_mcp_http_post(url, initialized_payload, timeout=timeout, session_id=session_id)

    call_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    call_response, _ = tutu_mcp_http_post(
        url, call_payload, timeout=timeout, session_id=session_id
    )
    return extract_tool_payload(
        ensure_jsonrpc_ok(call_response, f"tools/call {tool_name}")
    )


# --- IATA extraction from Tutu airport strings ---

def extract_iata_from_airport_string(text: str) -> str | None:
    """Extract IATA code from a Tutu airport string like 'Тулуза — Тулуза-Бланьяк (TLS)'."""
    if not text:
        return None
    match = _IATA_RE.search(text.strip())
    if match:
        return match.group(1)
    # Fallback: bare IATA at end
    match2 = re.search(r"\b([A-Z]{3})\b\s*$", text.strip())
    if match2:
        return match2.group(1)
    return None


# --- Carrier name → IATA code resolution ---

def _build_carrier_name_index(store: Store | None) -> dict[str, str]:
    if store is None:
        return {}
    index: dict[str, str] = {}
    for airline in store.airlines:
        code = str(airline.get("code") or "").upper()
        if not code:
            continue
        name = str(airline.get("name") or "").strip().lower()
        if name:
            index[name] = code
        translations = airline.get("name_translations")
        if isinstance(translations, dict):
            for tr_name in translations.values():
                tr = str(tr_name or "").strip().lower()
                if tr:
                    index[tr] = code
    return index


def resolve_carrier_code(
    carrier_name: str | None,
    *,
    name_index: dict[str, str] | None = None,
) -> str | None:
    if not carrier_name:
        return None
    text = carrier_name.strip()
    # Already a 2-letter IATA code
    if re.fullmatch(r"[A-Z0-9]{2,3}", text.upper()):
        return text.upper()
    if name_index:
        key = text.lower()
        if key in name_index:
            return name_index[key]
    return None


# --- IATA → city name resolution for Tutu API calls ---

def iata_to_city_name(iata_code: str, store: Store | None) -> str | None:
    """Resolve IATA code to Russian city name for Tutu search_avia."""
    if store is None:
        return None
    code = iata_code.upper()
    # Check city catalog first
    city = store.city_by_code.get(code)
    if city and city.get("name"):
        return str(city["name"])
    # Check airport catalog → city_code → city
    airport = store.airport_by_code.get(code)
    if airport:
        city_code = str(airport.get("city_code") or "").upper()
        if city_code:
            city = store.city_by_code.get(city_code)
            if city and city.get("name"):
                return str(city["name"])
    return None


# --- Normalization ---

def normalize_tutu_segment(
    segment: dict[str, Any],
    *,
    carrier_name_index: dict[str, str],
    expected_origin: str | None = None,
    expected_destination: str | None = None,
) -> dict[str, Any] | None:
    from_text = str(segment.get("from") or "")
    to_text = str(segment.get("to") or "")
    origin = extract_iata_from_airport_string(from_text) or expected_origin or ""
    destination = extract_iata_from_airport_string(to_text) or expected_destination or ""
    if not origin or not destination:
        return None

    carrier_name = str(segment.get("carrier") or "")
    carrier_code = resolve_carrier_code(
        carrier_name, name_index=carrier_name_index
    )
    voyage_no = str(segment.get("voyage_no") or "").strip()
    flight_number = voyage_no or None
    if carrier_code and flight_number and not flight_number.upper().startswith(
        carrier_code
    ):
        flight_number = f"{carrier_code}{flight_number}"

    # Extract terminal info if present
    departure_terminal = None
    arrival_terminal = None
    term_match = re.search(r"терм\.\s*(\S+)", from_text)
    if term_match:
        departure_terminal = term_match.group(1).rstrip(",")
    term_match2 = re.search(r"терм\.\s*(\S+)", to_text)
    if term_match2:
        arrival_terminal = term_match2.group(1).rstrip(",")

    return {
        "flight_number": flight_number or None,
        "marketing_carrier": carrier_code or "",
        "operating_carrier": carrier_code or "",
        "origin": origin.upper(),
        "destination": destination.upper(),
        "departure_terminal": departure_terminal,
        "arrival_terminal": arrival_terminal,
        "departure_at": str(segment.get("departure_at") or ""),
        "arrival_at": str(segment.get("arrival_at") or ""),
        "duration": segment.get("duration_min"),
    }


def tutu_offer_key(flights: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        f"{flight.get('flight_number')}:{flight.get('departure_at')}:{flight.get('arrival_at')}"
        for flight in flights
    )


def parse_tutu_avia_search(
    raw: dict[str, Any],
    *,
    origin: str,
    destination: str,
    depart_date: str,
    currency: str,
    limit: int = 20,
    store: Store | None = None,
) -> dict[str, Any]:
    offers_raw = raw.get("offers")
    if not isinstance(offers_raw, list):
        raise CliError(
            "Tutu MCP response does not contain an offers list",
            error_type="upstream_error",
        )

    carrier_name_index = _build_carrier_name_index(store)
    deduped: dict[tuple[str, ...], dict[str, Any]] = {}
    skipped: dict[str, int] = {}

    for index, offer in enumerate(offers_raw):
        if not isinstance(offer, dict):
            skipped["bad_offer"] = skipped.get("bad_offer", 0) + 1
            continue

        legs = offer.get("legs")
        if not isinstance(legs, list) or not legs:
            skipped["no_legs"] = skipped.get("no_legs", 0) + 1
            continue

        # Flatten all segments from all legs (Tutu legs[0] = outbound)
        raw_segments: list[dict[str, Any]] = []
        for leg in legs:
            if not isinstance(leg, dict):
                continue
            segments = leg.get("segments")
            if isinstance(segments, list):
                raw_segments.extend(s for s in segments if isinstance(s, dict))

        if not raw_segments:
            skipped["no_segments"] = skipped.get("no_segments", 0) + 1
            continue

        normalized_flights: list[dict[str, Any]] = []
        for seg_index, seg in enumerate(raw_segments):
            normalized = normalize_tutu_segment(
                seg,
                carrier_name_index=carrier_name_index,
                expected_origin=origin if seg_index == 0 else None,
                expected_destination=(
                    destination if seg_index == len(raw_segments) - 1 else None
                ),
            )
            if normalized is not None:
                normalized_flights.append(normalized)

        if not normalized_flights:
            skipped["bad_segments"] = skipped.get("bad_segments", 0) + 1
            continue

        price_data = offer.get("price")
        if isinstance(price_data, dict):
            amount = price_value({"price": price_data.get("amount")})
            offer_currency = str(
                price_data.get("currency") or currency
            ).upper()
        else:
            amount = price_value({"price": price_data})
            offer_currency = currency

        key = tutu_offer_key(normalized_flights)
        offer_obj = {
            "id": str(offer.get("offer_id") or f"tutu:{index}"),
            "price": amount,
            "currency": offer_currency,
            "number_of_changes": max(0, len(normalized_flights) - 1),
            "duration": offer.get("duration_min"),
            "departure_at": normalized_flights[0]["departure_at"],
            "arrival_at": normalized_flights[-1]["arrival_at"],
            "origin": normalized_flights[0]["origin"],
            "destination": normalized_flights[-1]["destination"],
            "flight_numbers": [
                f["flight_number"] for f in normalized_flights if f.get("flight_number")
            ],
            "marketing_carriers": sorted(
                {f["marketing_carrier"] for f in normalized_flights if f.get("marketing_carrier")}
            ),
            "operating_carriers": sorted(
                {f["operating_carrier"] for f in normalized_flights if f.get("operating_carrier")}
            ),
            "segments": normalized_flights,
        }
        previous = deduped.get(key)
        previous_price = previous.get("price") if previous else None
        if previous is None or (
            amount is not None and (previous_price is None or amount < previous_price)
        ):
            deduped[key] = offer_obj

    filtered_offers, filter_stats = filter_provider_offers(list(deduped.values()))
    offers = sorted(filtered_offers, key=provider_offer_business_key)[: max(0, limit)]
    return {
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date,
        "currency": currency,
        "source": "Tutu MCP search_avia (tutu.ru)",
        "source_url": default_tutu_mcp_url(),
        "note": "Tutu.ru aggregate source; recheck final fare and seat availability before ticketing.",
        "filters": {},
        "raw_count": len(offers_raw),
        "skipped": skipped,
        "offer_count": len(offers),
        "unique_flight_count": len(filtered_offers),
        **filter_stats,
        "offers": offers,
    }


def fetch_tutu_avia_search(
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
    store: Store | None = None,
    return_date: date | None = None,
) -> dict[str, Any]:
    """Call Tutu MCP search_avia and normalize results."""
    # Resolve IATA codes to city names for Tutu API
    origin_city = iata_to_city_name(origin, store) or origin
    destination_city = iata_to_city_name(destination, store) or destination

    arguments: dict[str, Any] = {
        "origin": origin_city,
        "destination": destination_city,
        "departure_date": depart_date.isoformat(),
        "adults": 1,
        "view": "compact",
        "sort": "departure_asc",
        "page_size": min(max(limit, 10), 30),
    }
    if return_date is not None:
        arguments["return_date"] = return_date.isoformat()

    # Fetch first page
    raw = call_tutu_mcp_tool(
        "search_avia", arguments, mcp_url=mcp_url, timeout=timeout
    )

    # Paginate if more pages exist (up to 3 pages = 90 offers max)
    all_offers = list(raw.get("offers") or [])
    meta = raw.get("meta") or {}
    page = 1
    while meta.get("has_more") and page < 3 and len(all_offers) < limit:
        page += 1
        page_args = dict(arguments)
        page_args["page"] = page
        page_raw = call_tutu_mcp_tool(
            "search_avia", page_args, mcp_url=mcp_url, timeout=timeout
        )
        page_offers = list(page_raw.get("offers") or [])
        if not page_offers:
            break
        all_offers.extend(page_offers)
        meta = page_raw.get("meta") or {}

    raw["offers"] = all_offers
    if "meta" in raw and isinstance(raw["meta"], dict):
        raw["meta"]["total_returned"] = len(all_offers)
        raw["meta"]["has_more"] = False

    return parse_tutu_avia_search(
        raw,
        origin=origin.upper(),
        destination=destination.upper(),
        depart_date=depart_date.isoformat(),
        currency=currency,
        limit=limit,
        store=store,
    )


def cached_tutu_avia_search(
    origin: str,
    destination: str,
    depart_date: date,
    *,
    currency: str,
    only_carriers: list[str],
    direct_only: bool,
    limit: int,
    timeout: int,
    mcp_url: str | None = None,
    cache_ttl_seconds: int = DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    use_cache: bool = True,
    fetcher: Any = fetch_tutu_avia_search,
    store: Store | None = None,
    return_date: date | None = None,
) -> dict[str, Any]:
    url = normalize_tutu_mcp_url(mcp_url)
    params = {
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date.isoformat(),
        "return_date": return_date.isoformat() if return_date else None,
        "currency": currency,
        "only_carriers": sorted(only_carriers),
        "direct_only": bool(direct_only),
        "limit": int(limit),
        "mcp_url": url,
        "normalizer": TUTU_NORMALIZER_VERSION,
    }
    key = live_cache_key("tutu_mcp_search_avia", params)
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
        store=store,
        return_date=return_date,
    )
    if use_cache and int(cache_ttl_seconds) > 0:
        return write_live_cache(key, result)
    result["cache"] = {"hit": False, "key": key, "disabled": True}
    return result


def tutu_offer_to_segment_offer(
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
    return provider_offer_to_segment_offer(
        offer,
        provider_prefix="tutu",
        source_label="Tutu MCP search_avia",
        direction=direction,
        leg=leg,
        query_origin=query_origin,
        query_destination=query_destination,
        query_date=query_date,
        currency=currency,
        index=index,
    )


def tutu_result_to_segment_result(
    result: dict[str, Any], *, direction: str, leg: str
) -> dict[str, Any]:
    return provider_result_to_segment_result(
        result,
        direction=direction,
        leg=leg,
        source_key="tutu_mcp_search_avia",
        source_label="Tutu MCP search_avia",
        provider_prefix="tutu",
        raw_count_key="raw_count",
    )


def tutu_segment_search_summary(
    spec: dict[str, Any], result: dict[str, Any], segment_result: dict[str, Any]
) -> dict[str, Any]:
    return {
        **spec,
        "provider": "tutu",
        "status": "ok",
        "raw_count": result.get("raw_count"),
        "unique_flight_count": result.get("unique_flight_count"),
        "offer_count": len(segment_result.get("offers") or []),
        "skipped": result.get("skipped", {}),
        "cache": result.get("cache", {"hit": False}),
    }


def run_tutu_search(
    args: argparse.Namespace, store: Store | None = None
) -> dict[str, Any]:
    origin = normalize_iata(args.origin, "origin")
    destination = normalize_iata(args.destination, "destination")
    depart = parse_iso_date(args.depart_date, "depart-date")
    currency = args.currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise CliError(
            f"currency must be one of {', '.join(sorted(SUPPORTED_CURRENCIES))}",
            error_type="validation_error",
        )
    only_carriers = [
        normalize_carrier_code(code, "only-carrier")
        for code in (getattr(args, "only_carrier", None) or [])
    ]
    return cached_tutu_avia_search(
        origin,
        destination,
        depart,
        currency=currency,
        only_carriers=only_carriers,
        direct_only=getattr(args, "direct_only", False),
        limit=getattr(args, "limit", 20),
        timeout=getattr(args, "timeout", 60),
        mcp_url=getattr(args, "tutu_mcp_url", None),
        cache_ttl_seconds=int(
            getattr(args, "cache_ttl_seconds", DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS)
        ),
        use_cache=not bool(getattr(args, "no_cache", False)),
        store=store,
    )