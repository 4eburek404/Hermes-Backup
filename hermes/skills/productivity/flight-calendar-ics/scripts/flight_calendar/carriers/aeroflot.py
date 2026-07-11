#!/usr/bin/env python3
"""Fetch Aeroflot manage-booking data and convert it to flight-calendar-ics JSON.

Input can be a direct/manage URL containing pnrKey/pnrLocator or those two
values passed explicitly by internal callers. The script does not print PNR,
passenger names, ticket numbers, or full source URLs. It always writes the
Aeroflot booking URL into the requested JSON/ICS output so imported calendar
events retain a direct booking link on any device.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from flight_calendar import carrier_http
from flight_calendar.common import die


AEROFLOT_BASE = "https://www.aeroflot.ru"
AEROFLOT_APP_URL = AEROFLOT_BASE + "/sb/pnr/app/ru-ru"
AEROFLOT_PNR_API = AEROFLOT_BASE + "/se/api/app/pnr/view/v3"


def pnr_query_params_from_url(booking_url: str) -> dict[str, list[str]]:
    """Extract PNR query parameters from both normal and SPA-fragment URLs."""
    parsed = urlparse(booking_url)
    params = parse_qs(parsed.query)
    if parsed.fragment and "?" in parsed.fragment:
        fragment_query = parsed.fragment.split("?", 1)[1]
        for key, values in parse_qs(fragment_query).items():
            params.setdefault(key, values)
    return params


def normalize_locator(locator: str | None) -> str:
    if not locator:
        die("PNR locator is required")
    locator = locator.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{5,8}", locator):
        die("PNR locator format looks invalid")
    return locator


def normalize_pnr_key(key: str | None) -> str:
    if not key:
        die("PNR key is required")
    key = key.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64,256}", key):
        die("PNR key format looks invalid")
    return key


def build_aeroflot_booking_url(locator: str, key: str) -> str:
    return (
        AEROFLOT_APP_URL
        + "#/pnr?"
        + urlencode({"pnr_key": key, "pnr_locator": locator})
    )


def parse_pnr_source(
    url: str | None, locator: str | None, key: str | None
) -> tuple[str, str, str]:
    booking_url = url.strip() if url else None
    if booking_url:
        qs = pnr_query_params_from_url(booking_url)
        locator = (
            locator or (qs.get("pnrLocator") or qs.get("pnr_locator") or [None])[0]
        )
        key = key or (qs.get("pnrKey") or qs.get("pnr_key") or [None])[0]
    if not locator or not key:
        die(
            "provide --url containing pnrKey/pnrLocator or both --pnr-locator and --pnr-key"
        )
    locator = normalize_locator(locator)
    key = normalize_pnr_key(key)
    if not booking_url:
        booking_url = build_aeroflot_booking_url(locator, key)
    return locator, key, booking_url


def post_aeroflot_pnr_json(
    payload: dict[str, Any], *, timeout: int = 45, referer: str | None = None
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    status, content_type, text = carrier_http.request_raw(
        AEROFLOT_PNR_API,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-App-Identity": "0",
            "Origin": AEROFLOT_BASE,
            "Referer": referer or AEROFLOT_APP_URL,
        },
        body=body,
        timeout=timeout,
        label="Aeroflot PNR API",
    )
    if "text/html" in content_type or text.lstrip().startswith("<!"):
        if "ngenix" in text.lower() or "проверка вашего веб-браузера" in text.lower():
            die(
                "Aeroflot returned an Ngenix browser-check page; retry later or fetch via a browser session"
            )
        die(f"Aeroflot returned HTML instead of JSON (HTTP {status})")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        die(f"Aeroflot returned non-JSON response (HTTP {status}): {exc}")
    if not isinstance(obj, dict):
        die(f"Aeroflot returned non-object JSON response (HTTP {status})")
    return obj


def pnr_api_error_type(obj: dict[str, Any]) -> str:
    err = obj.get("error") or {}
    if isinstance(err, dict):
        return str(err.get("type") or err.get("value") or "unknown error")
    return str(err or "unknown error")


def require_success_data(obj: dict[str, Any]) -> dict[str, Any]:
    if not obj.get("success"):
        die(f"Aeroflot PNR API returned success=false: {pnr_api_error_type(obj)}")
    data = obj.get("data")
    if not isinstance(data, dict):
        die("Aeroflot PNR API response has no data object")
    return data


def fetch_aeroflot_pnr(locator: str, key: str, *, timeout: int = 45) -> dict[str, Any]:
    obj = post_aeroflot_pnr_json(
        {"pnr_locator": locator, "pnr_key": key, "lang": "ru", "country": "ru"},
        timeout=timeout,
        referer=AEROFLOT_APP_URL,
    )
    return require_success_data(obj)


def first_ticket_number(data: dict[str, Any]) -> str | None:
    for pax in data.get("passengers") or []:
        for ticket in (pax.get("ticketing_documents") or {}).get("tickets") or []:
            number = ticket.get("number")
            if number:
                return str(number)
    return None


def passenger_names(data: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for pax in data.get("passengers") or []:
        name = " ".join(
            str(x) for x in [pax.get("last_name"), pax.get("first_name")] if x
        )
        if name:
            names.append(name)
    return names


def clean(value: Any) -> Any:
    return None if value in (None, "", []) else value


def _endpoint(
    location: dict[str, Any], *, airport: str, local: Any, tz: str
) -> dict[str, Any]:
    endpoint: dict[str, Any] = {
        "airport": airport,
        "local": str(local or "").replace(" ", "T"),
        "tz": tz,
    }
    city = clean(location.get("city_name"))
    if city:
        endpoint["city"] = str(city)
    return endpoint


def convert_to_itinerary(
    data: dict[str, Any], tz_map: dict[str, str], booking_url: str | None = None
) -> dict[str, Any]:
    ticket_number = first_ticket_number(data)
    flights: list[dict[str, Any]] = []
    missing_tz: set[str] = set()

    for leg in data.get("legs") or []:
        for seg in leg.get("segments") or []:
            dep = seg.get("origin") or {}
            arr = seg.get("destination") or {}
            dep_code = str(dep.get("airport_code") or "").upper()
            arr_code = str(arr.get("airport_code") or "").upper()
            for code in [dep_code, arr_code]:
                if code and code not in tz_map:
                    missing_tz.add(code)
            if missing_tz:
                continue

            airline_code = seg.get("airline_code") or "SU"
            flight_number = f"{airline_code}{seg.get('flight_number')}"
            flight: dict[str, Any] = {
                "flight_number": flight_number,
                "departure": _endpoint(
                    dep,
                    airport=dep_code,
                    local=seg.get("departure"),
                    tz=tz_map[dep_code],
                ),
                "arrival": _endpoint(
                    arr, airport=arr_code, local=seg.get("arrival"), tz=tz_map[arr_code]
                ),
                "status": "confirmed"
                if seg.get("status_code") == "HK"
                else (seg.get("status_name") or "confirmed"),
            }
            aircraft = clean(seg.get("aircraft_type_name"))
            if aircraft:
                flight["aircraft"] = str(aircraft)
            flights.append(flight)

    if missing_tz:
        codes = ", ".join(sorted(missing_tz))
        die(f"missing timezone for airport(s): {codes}; rerun with --tz CODE=Area/City")
    if not flights:
        die("no flight segments found in Aeroflot response")

    itinerary: dict[str, Any] = {
        "schema_version": "flight-calendar-ics-itinerary.v1",
        "flights": flights,
    }
    pnr = clean(data.get("pnr_locator"))
    passengers = passenger_names(data)
    if pnr:
        itinerary["pnr"] = str(pnr)
    if passengers:
        itinerary["passengers"] = passengers
    if ticket_number:
        itinerary["ticket_number"] = ticket_number
    if booking_url:
        itinerary["booking_url"] = booking_url
    return itinerary
