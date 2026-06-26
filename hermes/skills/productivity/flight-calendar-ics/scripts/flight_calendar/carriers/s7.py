#!/usr/bin/env python3
"""Fetch S7 manage-booking data and convert it to itinerary JSON.

S7's ``myb.s7.ru`` manage-order entrypoint first returns a small auto-submit
HTML form.  The POST response embeds the booking payload in the JavaScript global
``__r_airs_data``; this adapter extracts that data and maps only the compact
calendar fields.
"""
from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from curl_cffi import requests as curl_requests

from flight_calendar import carrier_http
from flight_calendar.common import die

S7_MANAGE_ORDER_BASE = "https://myb.s7.ru/myb/manage-order"


def clean(value: Any) -> bool:
    return value not in (None, "", [])


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first_value(obj: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = obj.get(key)
        if clean(value):
            return value
    return None


def parse_s7_source(url: str | None, booking_id: str | None, passenger_id: str | None) -> tuple[str, str, str]:
    """Parse an S7 manage-order URL or explicit values.

    ``bookingId`` and ``passengerId`` are private booking credentials; errors
    intentionally describe only missing/invalid fields, never the submitted URL.
    """
    booking_url = url.strip() if url else None
    if booking_url:
        parsed = urlparse(booking_url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        booking_id = booking_id or (qs.get("bookingId") or qs.get("booking_id") or [None])[0]
        passenger_id = passenger_id or (qs.get("passengerId") or qs.get("passenger_id") or [None])[0]
    if not booking_id or not passenger_id:
        die("provide S7 manage-order URL containing bookingId and passengerId")

    booking = str(booking_id).strip().upper()
    passenger = str(passenger_id).strip()
    if not re.fullmatch(r"[A-Z0-9]{5,8}", booking):
        die("S7 bookingId format looks invalid")
    if not re.fullmatch(r"[^\s/?#&=]{2,128}", passenger):
        die("S7 passengerId format looks invalid")
    if not booking_url:
        booking_url = S7_MANAGE_ORDER_BASE + "?" + urlencode({"bookingId": booking, "passengerId": passenger})
    return booking, passenger, booking_url


def browser_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    return carrier_http.browser_headers(
        {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Origin": "https://myb.s7.ru",
            "Referer": S7_MANAGE_ORDER_BASE,
            "Cache-Control": "no-cache",
            **(extra or {}),
        }
    )


def _response_text_or_die(response: Any, label: str) -> str:
    status = int(getattr(response, "status_code", 0) or 0)
    content_type = getattr(response, "headers", {}).get("Content-Type", "") if getattr(response, "headers", None) else ""
    if status >= 400:
        raise carrier_http.TransportError(f"{label} returned HTTP {status} ({content_type})")
    return str(getattr(response, "text", "") or "")


def _attr(tag: str, name: str) -> str | None:
    match = re.search(rf"\b{name}\s*=\s*(['\"])(.*?)\1", tag, flags=re.IGNORECASE | re.DOTALL)
    return html.unescape(match.group(2)) if match else None


def _first_form(html_text: str) -> tuple[str, dict[str, str]]:
    form_match = re.search(r"<form\b(?P<tag>[^>]*)>(?P<body>.*?)</form>", html_text, flags=re.IGNORECASE | re.DOTALL)
    if not form_match:
        die("S7 manage-order response did not contain an auto-submit form")
    action = _attr(form_match.group("tag"), "action")
    if not action:
        die("S7 manage-order form has no action")
    fields: dict[str, str] = {}
    for input_match in re.finditer(r"<input\b[^>]*>", form_match.group("body"), flags=re.IGNORECASE | re.DOTALL):
        tag = input_match.group(0)
        name = _attr(tag, "name")
        if not name:
            continue
        fields[name] = _attr(tag, "value") or ""
    return action, fields


def _extract_js_array(html_text: str, var_name: str) -> list[Any]:
    marker = f"var {var_name}"
    start = html_text.find(marker)
    if start < 0:
        die(f"S7 manage-order page has no {var_name} payload")
    eq = html_text.find("=", start)
    array_start = html_text.find("[", eq)
    if eq < 0 or array_start < 0:
        die(f"S7 manage-order {var_name} payload is malformed")

    depth = 0
    quote: str | None = None
    escape = False
    array_end: int | None = None
    for index in range(array_start, len(html_text)):
        char = html_text[index]
        if quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                array_end = index + 1
                break
    if array_end is None:
        die(f"S7 manage-order {var_name} payload is unterminated")

    raw = html_text[array_start:array_end]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"S7 manage-order {var_name} payload is not valid JSON") from exc
    if not isinstance(data, list):
        die(f"S7 manage-order {var_name} payload is not a list")
    return data


def extract_airs_data(html_text: str) -> list[Any]:
    return _extract_js_array(html_text, "__r_airs_data")


def fetch_s7_order(booking_url: str, *, timeout: int = 60) -> list[Any]:
    """Fetch S7 manage-order HTML and return its embedded ``__r_airs_data``.

    Network and HTTP errors are redaction-safe: messages identify only the S7
    flow and status/exception class, not the private URL or query values.
    """
    parse_s7_source(booking_url, None, None)
    session = curl_requests.Session(impersonate=carrier_http.IMPERSONATE_TARGET)
    headers = browser_headers()
    try:
        initial = session.get(booking_url, headers=headers, timeout=timeout)
        initial_text = _response_text_or_die(initial, "S7 manage-order")
        if "__r_airs_data" in initial_text:
            return extract_airs_data(initial_text)
        action, fields = _first_form(initial_text)
        post_url = urljoin(str(getattr(initial, "url", booking_url)), action)
        post = session.post(
            post_url,
            headers=browser_headers({"Referer": str(getattr(initial, "url", booking_url)), "Content-Type": "application/x-www-form-urlencoded"}),
            data=fields,
            timeout=timeout,
            allow_redirects=True,
        )
        return extract_airs_data(_response_text_or_die(post, "S7 manage-order"))
    except carrier_http.TransportError:
        raise
    except ValueError:
        raise
    except Exception as exc:  # curl_cffi exposes several transport exception classes
        raise carrier_http.TransportError(f"S7 manage-order failed: network error ({type(exc).__name__})") from exc


def _air_from_payload(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        if isinstance(data.get("air"), dict):
            return data["air"]
        if isinstance(data.get("airs_data"), list):
            return _air_from_payload(data["airs_data"])
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("air"), dict):
                return item["air"]
    die("no S7 air order found")


def passenger_name(passenger: dict[str, Any]) -> str | None:
    name = as_dict(passenger.get("name"))
    direct = first_value(name, ["fullName", "fullNameCapitalized", "title"])
    if clean(direct):
        return str(direct).strip()
    first = first_value(name, ["firstName"]) or first_value(as_dict(passenger.get("document")), ["firstName"])
    middle = first_value(name, ["middleName"])
    last = first_value(name, ["lastName"]) or first_value(as_dict(passenger.get("document")), ["lastName"])
    parts = [last, first, middle]
    value = " ".join(str(part).strip() for part in parts if clean(part))
    return value or None


def passenger_names(air: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for passenger in air.get("passengers") or []:
        if not isinstance(passenger, dict):
            continue
        name = passenger_name(passenger)
        if name and name not in names:
            names.append(name)
    return names


def ticket_numbers(air: dict[str, Any]) -> list[str]:
    numbers: list[str] = []
    passengers = list(air.get("passengers") or [])
    for route in air.get("routes") or []:
        route_obj = as_dict(route)
        passengers.extend(route_obj.get("passengers") or [])
    for passenger in passengers:
        if not isinstance(passenger, dict):
            continue
        value = passenger.get("ticketNumber") or passenger.get("ticket_number")
        if clean(value):
            numbers.append(str(value).strip())
    return sorted(dict.fromkeys(numbers))


def collect_segments(air: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for route in air.get("routes") or []:
        route_obj = as_dict(route)
        for segment in route_obj.get("segments") or []:
            segment_obj = as_dict(segment)
            if not segment_obj:
                continue
            key = str(segment_obj.get("id") or f"{segment_obj.get('departureDate')}|{segment_obj.get('arrivalDate')}|{segment_obj.get('flightRph')}")
            if key in seen:
                continue
            seen.add(key)
            out.append(segment_obj)
    return out


def airport_code(point: dict[str, Any]) -> str:
    return str(first_value(point, ["code", "iata", "airportCode"]) or "").strip().upper()


def airport_city(point: dict[str, Any]) -> str | None:
    value = first_value(point, ["cityName", "city", "name"])
    return str(value).strip() if clean(value) else None


def local_datetime(value: Any) -> str:
    text = str(value or "").strip().replace(" ", "T", 1)
    if "T" not in text:
        return text
    return text[:16]


def timezone_for(segment: dict[str, Any], field: str, airport: str, tz_map: dict[str, str]) -> str | None:
    value = str(segment.get(field) or "").strip()
    if "/" in value:
        return value
    return tz_map.get(airport)


def airline_code(airline: dict[str, Any]) -> str:
    return str(first_value(airline, ["displayCode", "code", "iata"]) or "S7").strip().upper()


def flight_number(segment: dict[str, Any]) -> str:
    marketing = as_dict(segment.get("marketingAirline"))
    operating = as_dict(segment.get("operatingAirline"))
    raw = str(
        first_value(marketing, ["flightNumber", "number"])
        or first_value(operating, ["flightNumber", "number"])
        or segment.get("flightRph")
        or ""
    ).strip().upper().replace(" ", "")
    if not raw:
        die("S7 segment has no flight number")
    if re.match(r"^[A-Z0-9]{2}\d+", raw):
        return raw
    return f"{airline_code(marketing or operating)}{raw}"


def status_text(segment: dict[str, Any], air: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in [segment.get("status"), segment.get("supplierStatus"), air.get("status")]:
        if clean(value):
            text = str(value).strip()
            if text not in parts:
                parts.append(text)
    if not parts and segment.get("confirmed") is True:
        return "confirmed"
    return " / ".join(parts) if parts else "confirmed"


def convert_to_itinerary(data: Any, tz_map: dict[str, str], booking_url: str | None = None) -> dict[str, Any]:
    air = _air_from_payload(data)
    flights: list[dict[str, Any]] = []
    missing_tz: set[str] = set()

    for segment in collect_segments(air):
        dep_point = as_dict(segment.get("departureAirport"))
        arr_point = as_dict(segment.get("arrivalAirport"))
        dep_code = airport_code(dep_point)
        arr_code = airport_code(arr_point)
        dep_tz = timezone_for(segment, "departureTimeZone", dep_code, tz_map)
        arr_tz = timezone_for(segment, "arrivalTimeZone", arr_code, tz_map)
        for code, tzid in ((dep_code, dep_tz), (arr_code, arr_tz)):
            if code and not tzid:
                missing_tz.add(code)
        if missing_tz:
            continue

        dep_local = local_datetime(segment.get("departureDate"))
        arr_local = local_datetime(segment.get("arrivalDate"))
        if not dep_code or not arr_code or not dep_local or not arr_local:
            die("S7 segment is missing route or local time fields")

        departure: dict[str, Any] = {"airport": dep_code, "local": dep_local, "tz": dep_tz}
        dep_city = airport_city(dep_point)
        if dep_city:
            departure["city"] = dep_city
        arrival: dict[str, Any] = {"airport": arr_code, "local": arr_local, "tz": arr_tz}
        arr_city = airport_city(arr_point)
        if arr_city:
            arrival["city"] = arr_city

        flight: dict[str, Any] = {
            "flight_number": flight_number(segment),
            "departure": departure,
            "arrival": arrival,
            "status": status_text(segment, air),
        }
        aircraft_name = first_value(as_dict(segment.get("aircraft")), ["name", "title", "code"])
        if clean(aircraft_name):
            flight["aircraft"] = str(aircraft_name).strip()
        flights.append(flight)

    if missing_tz:
        codes = ", ".join(sorted(missing_tz))
        die(f"missing timezone for airport(s): {codes}; rerun with --tz CODE=Area/City")
    if not flights:
        die("no flight segments found in S7 response")

    itinerary: dict[str, Any] = {
        "schema_version": "flight-calendar-ics-itinerary.v1",
        "flights": flights,
    }
    pnr = str(first_value(air, ["pnr", "orderNumber", "code"]) or "").strip().upper()
    if pnr:
        itinerary["pnr"] = pnr
    passengers = passenger_names(air)
    if passengers:
        itinerary["passengers"] = passengers
    tickets = ticket_numbers(air)
    if tickets:
        itinerary["ticket_number"] = ", ".join(tickets)
    if booking_url:
        itinerary["booking_url"] = booking_url
    return itinerary
