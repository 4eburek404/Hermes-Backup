#!/usr/bin/env python3
"""Fetch Aeroflot manage-booking data and convert it to flight-calendar-ics JSON."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from flight_calendar import carrier_http
from flight_calendar.errors import CliFailure



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
        raise ValueError("PNR locator is required")
    locator = locator.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{5,8}", locator):
        raise ValueError("PNR locator format looks invalid")
    return locator


def normalize_pnr_key(key: str | None) -> str:
    if not key:
        raise ValueError("PNR key is required")
    key = key.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64,256}", key):
        raise ValueError("PNR key format looks invalid")
    return key


def parse_pnr_source(booking_url: str) -> tuple[str, str, str]:
    booking_url = booking_url.strip()
    qs = pnr_query_params_from_url(booking_url)
    locator = (qs.get("pnrLocator") or qs.get("pnr_locator") or [None])[0]
    key = (qs.get("pnrKey") or qs.get("pnr_key") or [None])[0]
    if not locator or not key:
        raise CliFailure(
            "Aeroflot booking URL is missing required PNR credentials",
            code="route_input_insufficient",
        )
    locator = normalize_locator(locator)
    key = normalize_pnr_key(key)
    return locator, key, booking_url


def fetch_aeroflot_pnr(locator: str, key: str, *, timeout: int = 45) -> dict[str, Any]:
    payload = {"pnr_locator": locator, "pnr_key": key, "lang": "ru", "country": "ru"}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    status, content_type, text = carrier_http.request_raw(
        AEROFLOT_PNR_API,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-App-Identity": "0",
            "Origin": AEROFLOT_BASE,
            "Referer": AEROFLOT_APP_URL,
        },
        body=body,
        timeout=timeout,
        label="Aeroflot PNR API",
    )
    if "text/html" in content_type or text.lstrip().startswith("<!"):
        if "ngenix" in text.lower() or "проверка вашего веб-браузера" in text.lower():
            raise ValueError(
                "Aeroflot returned an Ngenix browser-check page; retry later or fetch via a browser session"
            )
        raise ValueError(f"Aeroflot returned HTML instead of JSON (HTTP {status})")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Aeroflot returned non-JSON response (HTTP {status}): {exc}")
    if not isinstance(obj, dict):
        raise ValueError(f"Aeroflot returned non-object JSON response (HTTP {status})")
    if not obj.get("success"):
        err = obj.get("error") or {}
        if isinstance(err, dict):
            error_type = str(err.get("type") or err.get("value") or "unknown error")
        else:
            error_type = str(err or "unknown error")
        raise ValueError(f"Aeroflot PNR API returned success=false: {error_type}")
    data = obj.get("data")
    if not isinstance(data, dict):
        raise ValueError("Aeroflot PNR API response has no data object")
    return data


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


def _endpoint(location: dict[str, Any], *, airport: str, local: Any) -> dict[str, Any]:
    endpoint: dict[str, Any] = {
        "airport": airport,
        "local": str(local or "").replace(" ", "T"),
    }
    city = clean(location.get("city_name"))
    if city:
        endpoint["city"] = str(city)
    return endpoint


def convert_to_itinerary(
    data: dict[str, Any], booking_url: str | None = None
) -> dict[str, Any]:
    ticket_number = first_ticket_number(data)
    flights: list[dict[str, Any]] = []

    for leg in data.get("legs") or []:
        for seg in leg.get("segments") or []:
            dep = seg.get("origin") or {}
            arr = seg.get("destination") or {}
            dep_code = str(dep.get("airport_code") or "").upper()
            arr_code = str(arr.get("airport_code") or "").upper()

            airline_code = seg.get("airline_code") or "SU"
            flight_number = f"{airline_code}{seg.get('flight_number')}"
            flight: dict[str, Any] = {
                "flight_number": flight_number,
                "departure": _endpoint(
                    dep,
                    airport=dep_code,
                    local=seg.get("departure"),
                ),
                "arrival": _endpoint(arr, airport=arr_code, local=seg.get("arrival")),
            }
            aircraft = clean(seg.get("aircraft_type_name"))
            if aircraft:
                flight["aircraft"] = str(aircraft)
            flights.append(flight)

    if not flights:
        raise ValueError("no flight segments found in Aeroflot response")

    itinerary: dict[str, Any] = {
        "flights": flights,
    }
    pnr = clean(data.get("pnr_locator"))
    passengers = passenger_names(data)
    if pnr:
        itinerary["pnr"] = str(pnr)
    if passengers:
        itinerary["passenger"] = passengers[0]
    if ticket_number:
        itinerary["ticket_number"] = ticket_number
    if booking_url:
        itinerary["booking_url"] = booking_url
    return itinerary
