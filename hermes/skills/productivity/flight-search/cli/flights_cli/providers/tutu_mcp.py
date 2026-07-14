from __future__ import annotations

import http.client
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

from .. import __version__
from ..config import (
    DEFAULT_LIVE_SEARCH_CACHE_TTL_SECONDS,
    TUTU_MCP_DEFAULT_URL,
)
from ..domain.normalize import normalize_airport_scope, price_value
from ..domain.offer_order import provider_offer_business_key
from ..domain.provider_offer_filter import filter_provider_offers
from ..errors import CliError
from ..store import Store
from .live_cache import live_cache_key, read_live_cache, write_live_cache
from .segment_normalization import provider_result_to_segment_result

MCP_PROTOCOL_VERSION = "2025-06-18"
TUTU_NORMALIZER_VERSION = "tutu-avia-v5"
TUTU_PAGE_SIZE = 30
TUTU_MAX_PAGES = 3
TUTU_MAX_SCOPE_PAGES = 10
TUTU_MCP_INCOMPLETE_READ_RETRIES = 2
TutuToolPayload = dict[str, Any] | list[Any] | str

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
        raise CliError(
            "Tutu MCP URL is invalid", error_type="validation_error"
        ) from exc
    if parsed.scheme not in {"http", "https"}:
        raise CliError(
            "Tutu MCP URL must use http or https",
            error_type="validation_error",
        )
    if not parsed.netloc or not parsed.hostname:
        raise CliError(
            "Tutu MCP URL must include a host", error_type="validation_error"
        )
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


def _mcp_payload_context(payload: dict[str, Any]) -> dict[str, Any]:
    method = str(payload.get("method") or "")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    tool = params.get("name") if isinstance(params, dict) else None
    return {
        "provider": "tutu",
        "method": method or None,
        "tool": str(tool) if tool else method or None,
    }


def _incomplete_read_details(
    exc: http.client.IncompleteRead,
    *,
    payload: dict[str, Any],
    attempts: int,
) -> dict[str, Any]:
    partial = exc.partial
    bytes_read = len(partial) if isinstance(partial, bytes) else None
    bytes_missing = exc.expected if isinstance(exc.expected, int) else None
    bytes_expected = (
        bytes_read + bytes_missing
        if bytes_read is not None and bytes_missing is not None
        else None
    )
    details = {
        **_mcp_payload_context(payload),
        "failure_reason": "incomplete_read",
        "bytes_read": bytes_read,
        "bytes_missing": bytes_missing,
        "bytes_expected": bytes_expected,
        "attempts": attempts,
    }
    return {key: value for key, value in details.items() if value is not None}


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
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        "User-Agent": f"flights-cli/{__version__}",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    data = json.dumps(payload).encode("utf-8")
    attempts = TUTU_MCP_INCOMPLETE_READ_RETRIES + 1
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            url,
            data=data,
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
        except http.client.IncompleteRead as exc:
            details = _incomplete_read_details(
                exc,
                payload=payload,
                attempts=attempt,
            )
            if attempt < attempts:
                time.sleep(0.2 * attempt)
                continue
            read = details.get("bytes_read", "unknown")
            expected = details.get("bytes_expected", "unknown")
            tool = details.get("tool") or details.get("method") or "request"
            raise CliError(
                f"Tutu MCP incomplete HTTP response while calling {tool}: read {read} of {expected} bytes",
                error_type="upstream_incomplete_read",
                details=details,
            ) from exc
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
    raise CliError("Tutu MCP request failed", error_type="upstream_error")


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
        f"Tutu MCP {context} returned an unsupported result",
        error_type="upstream_error",
    )


def extract_tool_payload(result: dict[str, Any]) -> TutuToolPayload:
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
        if isinstance(structured.get("result"), (dict, list, str)):
            return structured["result"]
        return structured
    if isinstance(structured, list):
        return structured

    first_text: str | None = None
    for item in result.get("content") or []:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str):
            continue
        if first_text is None:
            first_text = text
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, (dict, list, str)):
            # Tutu MCP wraps the payload in a {"result": "..."} string
            if isinstance(parsed, dict) and isinstance(parsed.get("result"), str):
                try:
                    inner = json.loads(parsed["result"])
                    if isinstance(inner, (dict, list, str)):
                        return inner
                except json.JSONDecodeError:
                    return parsed["result"]
            return parsed
    if first_text is not None:
        return first_text
    raise CliError(
        "Tutu MCP tool response did not include a content payload",
        error_type="upstream_error",
    )


def call_tutu_mcp_tool(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    mcp_url: str | None = None,
    timeout: int = 60,
) -> TutuToolPayload:
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


def require_tutu_tool_object(
    payload: TutuToolPayload, tool_name: str
) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    raise CliError(
        f"Tutu MCP tool {tool_name} returned a non-JSON payload",
        error_type="upstream_error",
        details={"tool": tool_name, "payload_type": type(payload).__name__},
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


def _carrier_name_key(value: str) -> str:
    text = str(value or "").replace("\u00a0", " ").strip().casefold()
    text = text.replace("ё", "е")
    return re.sub(r"\s+", " ", text)


def _carrier_match_key(value: str) -> str:
    return "".join(
        character for character in _carrier_name_key(value) if character.isalnum()
    )


def _valid_carrier_code(value: str) -> str | None:
    code = str(value or "").strip().upper()
    return code if re.fullmatch(r"[A-Z0-9]{2,3}", code) else None


def _carrier_catalog_rows(store: Store) -> list[dict[str, Any]]:
    rows = list(store.airlines)
    rows.extend(store.load_json("airlines_ru.json"))
    return rows


def _build_carrier_name_index(store: Store | None) -> dict[str, str]:
    if store is None:
        return {}
    index: dict[str, str] = {}
    for airline in _carrier_catalog_rows(store):
        code = _valid_carrier_code(str(airline.get("code") or ""))
        if not code:
            continue
        name = _carrier_name_key(str(airline.get("name") or ""))
        if name:
            index.setdefault(name, code)
        translations = airline.get("name_translations")
        if isinstance(translations, dict):
            for tr_name in translations.values():
                tr = _carrier_name_key(str(tr_name or ""))
                if tr:
                    index.setdefault(tr, code)
    return index


def _carrier_display_names_by_code(store: Store | None) -> dict[str, list[str]]:
    if store is None:
        return {}
    names_by_code: dict[str, list[str]] = {}
    seen_by_code: dict[str, set[str]] = {}

    def add_name(code: str, name: str) -> None:
        display_name = str(name or "").strip()
        if not display_name:
            return
        key = _carrier_name_key(display_name)
        seen = seen_by_code.setdefault(code, set())
        if key in seen:
            return
        seen.add(key)
        names_by_code.setdefault(code, []).append(display_name)

    # Tutu currently exposes Russian display names for many carriers, so prefer
    # the RU catalog row while still sending EN aliases as fallbacks.
    rows = list(store.load_json("airlines_ru.json"))
    rows.extend(store.airlines)
    for airline in rows:
        code = _valid_carrier_code(str(airline.get("code") or ""))
        if not code:
            continue
        add_name(code, str(airline.get("name") or ""))
        translations = airline.get("name_translations")
        if isinstance(translations, dict):
            for tr_name in translations.values():
                add_name(code, str(tr_name or ""))
    return names_by_code


def _carrier_facets(raw: dict[str, Any]) -> list[str]:
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    facets = meta.get("carriers_available") if isinstance(meta, dict) else None
    names: list[str] = []
    for item in facets or []:
        value = item.get("name") if isinstance(item, dict) else item
        name = str(value or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _match_carrier_facet(candidates: list[str], facets: list[str]) -> str | None:
    candidate_keys = [_carrier_match_key(item) for item in candidates]
    for facet in facets:
        facet_key = _carrier_match_key(facet)
        if facet_key and facet_key in candidate_keys:
            return facet
    for facet in facets:
        facet_key = _carrier_match_key(facet)
        for candidate_key in candidate_keys:
            if len(candidate_key) >= 4 and facet_key.startswith(candidate_key):
                return facet
    return None


def resolve_tutu_carrier_facets(
    only_carriers: list[str] | None,
    *,
    facets: list[str],
    store: Store | None,
) -> tuple[list[str], dict[str, str], list[str]]:
    name_index = _build_carrier_name_index(store)
    display_names_by_code = _carrier_display_names_by_code(store)
    resolved: list[str] = []
    overrides: dict[str, str] = {}
    unmatched: list[str] = []

    for facet in facets:
        code = resolve_carrier_code(facet, name_index=name_index)
        if code:
            overrides[_carrier_name_key(facet)] = code
            continue
        for candidate_code, candidates in display_names_by_code.items():
            if _match_carrier_facet(candidates, [facet]):
                overrides[_carrier_name_key(facet)] = candidate_code
                break

    for raw_value in only_carriers or []:
        value = str(raw_value or "").strip()
        if not value:
            continue
        code = resolve_carrier_code(value, name_index=name_index)
        candidates = display_names_by_code.get(code or "", []) or [value]
        matched = _match_carrier_facet(candidates, facets)
        if matched:
            if matched not in resolved:
                resolved.append(matched)
            if code:
                overrides[_carrier_name_key(matched)] = code
            continue
        if code:
            unmatched.append(value)
            continue
        raise CliError(
            f"Tutu carrier filter could not be resolved: {value}",
            error_type="carrier_filter_unresolved",
            details={"carrier": value, "carriers_available": facets},
        )
    return resolved, overrides, unmatched


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
        key = _carrier_name_key(text)
        if key in name_index:
            return name_index[key]
    return None


# --- Planner-owned airport scope → Tutu location resolution ---


def _iata_to_city_name(iata_code: str, store: Store | None) -> str | None:
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


def _normalized_airport_scope(
    location_code: str,
    airport_scope: list[str] | None,
    store: Store | None,
) -> list[str]:
    explicit = normalize_airport_scope(airport_scope, "airport-scope")
    if explicit:
        return explicit
    if store is not None:
        try:
            location = store.resolve_location(location_code.upper())
        except CliError:
            pass
        else:
            resolved = sorted(
                {str(code).upper() for code in (location.airports or []) if code}
            )
            if resolved:
                return resolved
    return [location_code.upper()]


def _tutu_location_input(
    location_code: str,
    airport_scope: list[str],
    store: Store | None,
) -> tuple[str, str]:
    if len(airport_scope) == 1:
        return airport_scope[0], "airport"
    city_name = _iata_to_city_name(location_code, store)
    if city_name is None and airport_scope:
        city_name = _iata_to_city_name(airport_scope[0], store)
    return city_name or location_code, "city"


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
    destination = (
        extract_iata_from_airport_string(to_text) or expected_destination or ""
    )
    if not origin or not destination:
        return None

    carrier_name = str(segment.get("carrier") or "")
    carrier_code = resolve_carrier_code(carrier_name, name_index=carrier_name_index)
    voyage_no = str(segment.get("voyage_no") or "").strip()
    flight_number = voyage_no or None
    if (
        carrier_code
        and flight_number
        and not flight_number.upper().startswith(carrier_code)
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
        "carrier_name": carrier_name or None,
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
        ":".join(
            [
                str(flight.get("flight_number") or ""),
                str(flight.get("origin") or ""),
                str(flight.get("destination") or ""),
                str(flight.get("departure_at") or ""),
                str(flight.get("arrival_at") or ""),
            ]
        )
        for flight in flights
    )


def _increment(counter: dict[str, int], key: str, amount: int = 1) -> None:
    counter[key] = counter.get(key, 0) + amount


def _journey_segments(journey: dict[str, Any]) -> list[dict[str, Any]]:
    segments = journey.get("segments")
    return [segment for segment in (segments or []) if isinstance(segment, dict)]


def _all_journey_segments(journeys: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for journey in journeys:
        result.extend(_journey_segments(journey))
    return result


def _journey_connection_count(journey: dict[str, Any]) -> int:
    return max(0, len(_journey_segments(journey)) - 1)


def _journeys_have_airport_change(journeys: list[dict[str, Any]]) -> bool:
    for journey in journeys:
        segments = _journey_segments(journey)
        for previous, current in zip(segments, segments[1:]):
            arrival = str(previous.get("destination") or "").upper()
            departure = str(current.get("origin") or "").upper()
            if arrival and departure and arrival != departure:
                return True
    return False


def _tutu_journey_key(journeys: list[dict[str, Any]]) -> tuple[str, ...]:
    parts: list[str] = []
    for index, journey in enumerate(journeys):
        direction = str(journey.get("direction") or f"journey_{index}")
        for segment_key in tutu_offer_key(_journey_segments(journey)):
            parts.append(f"{direction}:{segment_key}")
    return tuple(parts)


def _journey_endpoint_codes(
    journey: dict[str, Any],
) -> tuple[str | None, str | None]:
    segments = _journey_segments(journey)
    if not segments:
        return None, None
    origin = str(segments[0].get("origin") or "").upper() or None
    destination = str(segments[-1].get("destination") or "").upper() or None
    return origin, destination


def _matches_allowed_airport_scope(
    journeys: list[dict[str, Any]],
    *,
    origin_airports: list[str],
    destination_airports: list[str],
    skipped: dict[str, int],
) -> bool:
    origin_codes = set(origin_airports)
    destination_codes = set(destination_airports)
    expected = [(origin_codes, destination_codes, "outbound")]
    if len(journeys) > 1:
        expected.append((destination_codes, origin_codes, "return"))

    for journey, (allowed_origins, allowed_destinations, direction) in zip(
        journeys, expected
    ):
        journey_origin, journey_destination = _journey_endpoint_codes(journey)
        if (
            journey_origin not in allowed_origins
            or journey_destination not in allowed_destinations
        ):
            _increment(skipped, "outside_airport_scope")
            debug = journey.setdefault("debug", {})
            debug["airport_scope_mismatch"] = {
                "direction": direction,
                "allowed_origins": sorted(allowed_origins),
                "allowed_destinations": sorted(allowed_destinations),
                "actual_origin": journey_origin,
                "actual_destination": journey_destination,
            }
            return False
    return True


def _normalize_tutu_journeys(
    offer: dict[str, Any],
    *,
    origin: str,
    destination: str,
    carrier_name_index: dict[str, str],
    skipped: dict[str, int],
) -> list[dict[str, Any]]:
    legs = offer.get("legs")
    if not isinstance(legs, list) or not legs:
        _increment(skipped, "no_legs")
        return []

    journeys: list[dict[str, Any]] = []
    for leg_index, leg in enumerate(legs):
        if not isinstance(leg, dict):
            continue
        raw_segments = [
            segment
            for segment in (leg.get("segments") or [])
            if isinstance(segment, dict)
        ]
        if not raw_segments:
            continue

        direction = (
            "outbound"
            if leg_index == 0
            else "return"
            if leg_index == 1
            else f"journey_{leg_index + 1}"
        )
        expected_start = (
            origin if leg_index == 0 else destination if leg_index == 1 else None
        )
        expected_end = (
            destination if leg_index == 0 else origin if leg_index == 1 else None
        )
        normalized_segments: list[dict[str, Any]] = []
        for segment_index, segment in enumerate(raw_segments):
            normalized = normalize_tutu_segment(
                segment,
                carrier_name_index=carrier_name_index,
                expected_origin=expected_start if segment_index == 0 else None,
                expected_destination=(
                    expected_end if segment_index == len(raw_segments) - 1 else None
                ),
            )
            if normalized is not None:
                normalized_segments.append(normalized)
        if normalized_segments:
            journeys.append({"direction": direction, "segments": normalized_segments})

    if not journeys:
        _increment(skipped, "no_segments")
    return journeys


def parse_tutu_avia_search(
    raw: dict[str, Any],
    *,
    origin: str,
    destination: str,
    depart_date: str,
    currency: str,
    only_carriers: list[str] | None = None,
    direct_only: bool = False,
    return_date: str | None = None,
    limit: int = 20,
    store: Store | None = None,
    source_url: str | None = None,
    origin_airports: list[str] | None = None,
    destination_airports: list[str] | None = None,
    carrier_name_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    offers_raw = raw.get("offers")
    if not isinstance(offers_raw, list):
        raise CliError(
            "Tutu MCP response does not contain an offers list",
            error_type="upstream_error",
        )

    allowed_origins = _normalized_airport_scope(origin, origin_airports, store)
    allowed_destinations = _normalized_airport_scope(
        destination, destination_airports, store
    )
    carrier_name_index = _build_carrier_name_index(store)
    carrier_name_index.update(carrier_name_overrides or {})
    requested_carriers = {
        str(code).strip().upper() for code in (only_carriers or []) if str(code).strip()
    }
    deduped: dict[tuple[str, ...], dict[str, Any]] = {}
    skipped: dict[str, int] = {}

    for index, offer in enumerate(offers_raw):
        if not isinstance(offer, dict):
            _increment(skipped, "bad_offer")
            continue

        journeys = _normalize_tutu_journeys(
            offer,
            origin=origin,
            destination=destination,
            carrier_name_index=carrier_name_index,
            skipped=skipped,
        )
        if not journeys:
            continue
        if len(journeys) > 2:
            _increment(skipped, "unsupported_journey_count")
            continue
        if _journeys_have_airport_change(journeys):
            _increment(skipped, "airport_change")
            continue
        if not _matches_allowed_airport_scope(
            journeys,
            origin_airports=allowed_origins,
            destination_airports=allowed_destinations,
            skipped=skipped,
        ):
            continue
        price_data = offer.get("price")
        if isinstance(price_data, dict):
            amount = price_value({"price": price_data.get("amount")})
            offer_currency = str(price_data.get("currency") or currency).upper()
        else:
            amount = price_value({"price": price_data})
            offer_currency = currency

        outbound_segments = _journey_segments(journeys[0])
        if not outbound_segments:
            _increment(skipped, "bad_segments")
            continue
        all_segments = _all_journey_segments(journeys)
        key = _tutu_journey_key(journeys)
        has_self_transfer_field = any(
            key in offer for key in ("is_multi_pnr", "has_self_transfer")
        )
        self_transfer = (
            bool(offer.get("is_multi_pnr") or offer.get("has_self_transfer"))
            if has_self_transfer_field
            else None
        )
        offer_obj = {
            "id": str(offer.get("offer_id") or f"tutu:{index}"),
            "price": amount,
            "currency": offer_currency,
            "number_of_changes": max(_journey_connection_count(j) for j in journeys),
            "duration": offer.get("duration_min"),
            "departure_at": outbound_segments[0]["departure_at"],
            "arrival_at": outbound_segments[-1]["arrival_at"],
            "origin": outbound_segments[0]["origin"],
            "destination": outbound_segments[-1]["destination"],
            "flight_numbers": [
                f["flight_number"] for f in all_segments if f.get("flight_number")
            ],
            "marketing_carriers": sorted(
                {
                    f["marketing_carrier"]
                    for f in all_segments
                    if f.get("marketing_carrier")
                }
            ),
            "operating_carriers": sorted(
                {
                    f["operating_carrier"]
                    for f in all_segments
                    if f.get("operating_carrier")
                }
            ),
            "segments": outbound_segments,
            "journeys": journeys,
            "journey_scope": "round_trip" if len(journeys) == 2 else "one_way",
            "ticketing_model": "provider_order_unverified",
            "self_transfer": self_transfer,
            "self_transfer_note": offer.get("multi_pnr_note"),
            "self_transfer_source": "tutu" if has_self_transfer_field else None,
        }
        if len(journeys) == 2:
            return_segments = _journey_segments(journeys[1])
            if return_segments:
                offer_obj["return_departure_at"] = return_segments[0]["departure_at"]
                offer_obj["return_arrival_at"] = return_segments[-1]["arrival_at"]
        previous = deduped.get(key)
        previous_price = previous.get("price") if previous else None
        if previous is None or (
            amount is not None and (previous_price is None or amount < previous_price)
        ):
            deduped[key] = offer_obj

    filtered_offers, filter_stats = filter_provider_offers(list(deduped.values()))
    sorted_offers = sorted(filtered_offers, key=provider_offer_business_key)
    normalized_limit = max(0, int(limit))
    offers = sorted_offers[:normalized_limit] if normalized_limit else sorted_offers
    omitted_offer_count = max(0, len(sorted_offers) - len(offers))
    return {
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date,
        "currency": currency,
        "source": "Tutu MCP search_avia (tutu.ru)",
        "source_url": source_url or default_tutu_mcp_url(),
        "note": "Tutu.ru aggregate source; recheck final fare and seat availability before ticketing.",
        "filters": {
            "direct_only": bool(direct_only),
            "only_carriers": sorted(requested_carriers),
            "origin_airports": allowed_origins,
            "destination_airports": allowed_destinations,
        },
        "return_date": return_date,
        "pagination": raw.get("meta") if isinstance(raw.get("meta"), dict) else {},
        "raw_count": len(offers_raw),
        "skipped": skipped,
        "offer_count": len(offers),
        "unique_flight_count": len(filtered_offers),
        "omitted_offer_count": omitted_offer_count,
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
    origin_airports: list[str] | None = None,
    destination_airports: list[str] | None = None,
) -> dict[str, Any]:
    """Call Tutu MCP search_avia and normalize results."""
    allowed_origins = _normalized_airport_scope(origin, origin_airports, store)
    allowed_destinations = _normalized_airport_scope(
        destination, destination_airports, store
    )
    origin_input, origin_input_kind = _tutu_location_input(
        origin, allowed_origins, store
    )
    destination_input, destination_input_kind = _tutu_location_input(
        destination, allowed_destinations, store
    )

    arguments: dict[str, Any] = {
        "origin": origin_input,
        "destination": destination_input,
        "departure_date": depart_date.isoformat(),
        "adults": 1,
        "view": "compact",
        "sort": "departure_asc",
        "page_size": TUTU_PAGE_SIZE,
    }
    if return_date is not None:
        arguments["return_date"] = return_date.isoformat()
    if direct_only:
        arguments["direct_only"] = True

    carrier_name_overrides: dict[str, str] = {}
    unmatched_carriers: list[str] = []
    carrier_facets: list[str] = []
    if only_carriers:
        discovery_arguments = {**arguments, "page_size": 1}
        discovery_raw = require_tutu_tool_object(
            call_tutu_mcp_tool(
                "search_avia",
                discovery_arguments,
                mcp_url=mcp_url,
                timeout=timeout,
            ),
            "search_avia",
        )
        carrier_facets = _carrier_facets(discovery_raw)
        mcp_carriers, carrier_name_overrides, unmatched_carriers = (
            resolve_tutu_carrier_facets(
                only_carriers,
                facets=carrier_facets,
                store=store,
            )
        )
        if not mcp_carriers:
            discovery_meta = (
                discovery_raw.get("meta")
                if isinstance(discovery_raw.get("meta"), dict)
                else {}
            )
            empty_raw = {
                "offers": [],
                "meta": {
                    **discovery_meta,
                    "carrier_filter_unmatched": unmatched_carriers,
                    "carrier_facets_discovered": carrier_facets,
                    "pages_fetched": 1,
                    "total_returned": 0,
                    "origin_input": origin_input,
                    "origin_input_kind": origin_input_kind,
                    "origin_airports": allowed_origins,
                    "destination_input": destination_input,
                    "destination_input_kind": destination_input_kind,
                    "destination_airports": allowed_destinations,
                },
            }
            return parse_tutu_avia_search(
                empty_raw,
                origin=origin.upper(),
                destination=destination.upper(),
                depart_date=depart_date.isoformat(),
                currency=currency,
                only_carriers=only_carriers,
                direct_only=direct_only,
                return_date=return_date.isoformat() if return_date else None,
                limit=limit,
                store=store,
                source_url=normalize_tutu_mcp_url(mcp_url),
                origin_airports=allowed_origins,
                destination_airports=allowed_destinations,
                carrier_name_overrides=carrier_name_overrides,
            )
        arguments["carriers"] = mcp_carriers

    # Fetch first page
    raw = require_tutu_tool_object(
        call_tutu_mcp_tool("search_avia", arguments, mcp_url=mcp_url, timeout=timeout),
        "search_avia",
    )
    if not carrier_facets:
        carrier_facets = _carrier_facets(raw)
        _, carrier_name_overrides, _ = resolve_tutu_carrier_facets(
            [], facets=carrier_facets, store=store
        )

    all_offers = list(raw.get("offers") or [])
    meta = raw.get("meta") or {}
    page = 1
    pages_fetched = 1
    page_budget_exhausted = False
    empty_page_seen = False
    max_pages = (
        TUTU_MAX_SCOPE_PAGES
        if len(allowed_origins) > 1 or len(allowed_destinations) > 1
        else TUTU_MAX_PAGES
    )
    while meta.get("has_more") and page < max_pages:
        page += 1
        page_args = dict(arguments)
        page_args["page"] = page
        page_raw = require_tutu_tool_object(
            call_tutu_mcp_tool(
                "search_avia", page_args, mcp_url=mcp_url, timeout=timeout
            ),
            "search_avia",
        )
        pages_fetched += 1
        page_offers = list(page_raw.get("offers") or [])
        if not page_offers:
            empty_page_seen = True
            meta = page_raw.get("meta") or meta
            break
        all_offers.extend(page_offers)
        meta = page_raw.get("meta") or {}
    if meta.get("has_more") and page >= max_pages:
        page_budget_exhausted = True

    raw["offers"] = all_offers
    raw_meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    raw["meta"] = {
        **raw_meta,
        **(meta if isinstance(meta, dict) else {}),
        "page_size": TUTU_PAGE_SIZE,
        "pages_fetched": pages_fetched,
        "total_returned": len(all_offers),
        "max_pages": max_pages,
        "has_more_after_fetch": bool(meta.get("has_more"))
        if isinstance(meta, dict)
        else False,
        "not_fetched_due_to_page_budget": page_budget_exhausted,
        "airport_scope_incomplete": page_budget_exhausted
        and (len(allowed_origins) > 1 or len(allowed_destinations) > 1),
        "empty_page_seen": empty_page_seen,
        "origin_input": origin_input,
        "origin_input_kind": origin_input_kind,
        "origin_airports": allowed_origins,
        "destination_input": destination_input,
        "destination_input_kind": destination_input_kind,
        "destination_airports": allowed_destinations,
        "carrier_facets_discovered": carrier_facets,
        "carrier_filter_unmatched": unmatched_carriers,
    }

    return parse_tutu_avia_search(
        raw,
        origin=origin.upper(),
        destination=destination.upper(),
        depart_date=depart_date.isoformat(),
        currency=currency,
        only_carriers=only_carriers,
        direct_only=direct_only,
        return_date=return_date.isoformat() if return_date else None,
        limit=limit,
        store=store,
        source_url=normalize_tutu_mcp_url(mcp_url),
        origin_airports=allowed_origins,
        destination_airports=allowed_destinations,
        carrier_name_overrides=carrier_name_overrides,
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
    origin_airports: list[str] | None = None,
    destination_airports: list[str] | None = None,
) -> dict[str, Any]:
    url = normalize_tutu_mcp_url(mcp_url)
    allowed_origins = _normalized_airport_scope(origin, origin_airports, store)
    allowed_destinations = _normalized_airport_scope(
        destination, destination_airports, store
    )
    params = {
        "origin": origin,
        "destination": destination,
        "origin_airports": allowed_origins,
        "destination_airports": allowed_destinations,
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
        origin_airports=allowed_origins,
        destination_airports=allowed_destinations,
    )
    if use_cache and int(cache_ttl_seconds) > 0:
        return write_live_cache(key, result)
    result["cache"] = {"hit": False, "key": key, "disabled": True}
    return result


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
        "filters": result.get("filters", {}),
        "pagination": result.get("pagination", {}),
        "skipped": result.get("skipped", {}),
        "cache": result.get("cache", {"hit": False}),
    }
