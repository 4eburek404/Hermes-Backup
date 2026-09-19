#!/usr/bin/env python3
"""Fetch Utair manage-booking data and convert it to itinerary JSON.

Utair's order-manage page is a JavaScript SPA. The itinerary is obtained via
Utair's public API: client-credentials OAuth token, then an orders lookup by
booking locator and passenger surname. This helper keeps stdout-free functions
for the agent-facing orchestrator in ``flight_calendar_ics.py``.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from flight_calendar import carrier_http
from flight_calendar.errors import CliFailure


UTAIR_WEB_BASE = "https://www.utair.ru/"
UTAIR_API_BASE = "https://b.utair.ru/"


def clean(value: Any) -> Any:
    return None if value in (None, "", []) else value


def browser_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    return carrier_http.browser_headers(
        {
            "Origin": "https://www.utair.ru",
            "Referer": "https://www.utair.ru/order-manage",
            "Cache-Control": "no-cache",
            **(extra or {}),
        }
    )


def parse_utair_source(url: str) -> tuple[str, str, str]:
    """Parse and validate the Utair order-manage URL contract."""
    booking_url = url.strip()
    parsed = urlparse(booking_url)
    qs = parse_qs(parsed.query, keep_blank_values=False)
    rloc = (qs.get("rloc") or qs.get("RLOC") or qs.get("pnr") or [None])[0]
    last_name = (
        qs.get("last_name")
        or qs.get("lastName")
        or qs.get("lastname")
        or qs.get("surname")
        or [None]
    )[0]
    if not rloc or not last_name:
        raise CliFailure(
            "Utair booking URL is missing required credentials",
            code="route_input_insufficient",
        )

    locator = rloc.strip().upper()
    surname = last_name.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{5,8}", locator):
        raise ValueError("Utair booking locator format looks invalid")
    if not re.fullmatch(r"[A-ZА-ЯЁ' -]{2,80}", surname, flags=re.IGNORECASE):
        raise ValueError("Utair last name format looks invalid")
    return locator, surname, booking_url


def build_itinerary(booking_url: str) -> dict[str, Any]:
    locator, last_name, normalized_url = parse_utair_source(booking_url)
    token = fetch_utair_token()
    return convert_to_itinerary(
        fetch_utair_orders(locator, last_name, token=token),
        booking_url=normalized_url,
    )


def fetch_utair_token(timeout: int = 45) -> str:
    data = carrier_http.request_json(
        UTAIR_API_BASE.rstrip("/") + "/oauth/token",
        form_body={"client_id": "website_client", "grant_type": "client_credentials"},
        headers=browser_headers(),
        timeout=timeout,
        label="Utair OAuth",
    )
    if not isinstance(data, dict):
        raise ValueError("Utair OAuth response is not a JSON object")
    token = data.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("Utair OAuth response has no access_token")
    return token.strip()


def fetch_utair_orders(
    locator: str, last_name: str, *, token: str | None = None, timeout: int = 45
) -> dict[str, Any]:
    bearer = token or fetch_utair_token(timeout=timeout)
    query = urlencode(
        {"filters[locator]": locator, "filters[passenger_lastname]": last_name}
    )
    data = carrier_http.request_json(
        UTAIR_API_BASE.rstrip("/") + "/api/v3/orders?" + query,
        headers=browser_headers({"Authorization": f"Bearer {bearer}"}),
        timeout=timeout,
        label="Utair orders API",
    )
    if not isinstance(data, dict):
        raise ValueError("Utair orders API response is not a JSON object")
    if not collect_orders(data):
        raise ValueError("no Utair orders found")
    return data


def collect_orders(data: dict[str, Any]) -> list[dict[str, Any]]:
    orders: list[dict[str, Any]] = []
    for key in ("future", "past", "objects", "orders"):
        value = data.get(key)
        if isinstance(value, list):
            orders.extend(item for item in value if isinstance(item, dict))
    if not orders and any(key in data for key in ("segments", "passengers", "tickets")):
        orders.append(data)
    return orders


def local_datetime(value: Any) -> str:
    text = str(value or "").strip().replace(" ", "T", 1)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?", text):
        return text[:16]
    return text


def first_value(obj: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = obj.get(key)
        if clean(value):
            return value
    return None


def airport_code(seg: dict[str, Any], prefix: str) -> str:
    if prefix == "departure":
        keys = [
            "departure_airport_code",
            "departure_airport",
            "origin",
            "origin_code",
            "from",
            "from_code",
        ]
    else:
        keys = [
            "arrival_airport_code",
            "arrival_airport",
            "destination",
            "destination_code",
            "to",
            "to_code",
        ]
    return str(first_value(seg, keys) or "").strip().upper()


def city_name(seg: dict[str, Any], prefix: str) -> str | None:
    keys = [f"{prefix}_city", f"{prefix}_city_name"]
    value = first_value(seg, keys)
    return str(value).strip() if clean(value) else None


def segment_local(seg: dict[str, Any], prefix: str) -> str:
    keys = [
        f"{prefix}_local_iso",
        f"{prefix}_datetime",
        f"{prefix}_date_time",
        f"{prefix}_time",
        f"{prefix}_date",
        prefix,
    ]
    return local_datetime(first_value(seg, keys))


def flight_number(seg: dict[str, Any]) -> str:
    carrier = (
        str(
            first_value(
                seg, ["ak", "airline_code", "carrier_code", "marketing_carrier"]
            )
            or "UT"
        )
        .strip()
        .upper()
    )
    number = (
        str(first_value(seg, ["flight_number", "flight", "number"]) or "")
        .strip()
        .upper()
        .replace(" ", "")
    )
    if not number:
        raise ValueError("Utair segment has no flight number")
    if number.startswith(carrier):
        return number
    return f"{carrier}{number}"


def passenger_names(order: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for pax in order.get("passengers") or []:
        if not isinstance(pax, dict):
            continue
        direct = first_value(pax, ["full_name", "fullName", "name"])
        if clean(direct):
            name = str(direct).strip()
        else:
            parts = [
                pax.get("last_name") or pax.get("lastName") or pax.get("surname"),
                pax.get("first_name") or pax.get("firstName"),
            ]
            name = " ".join(str(item).strip() for item in parts if clean(item))
        if name:
            names.append(name)
    return names


def ticket_numbers(order: dict[str, Any]) -> list[str]:
    numbers: list[str] = []
    for ticket in order.get("tickets") or []:
        if isinstance(ticket, dict):
            number = first_value(
                ticket, ["ticket", "number", "ticket_number", "ticketNumber"]
            )
        else:
            number = ticket
        if clean(number):
            numbers.append(str(number).strip())
    return sorted(dict.fromkeys(numbers))


def convert_to_itinerary(
    data: dict[str, Any], booking_url: str | None = None
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Utair orders API response is not a JSON object")

    flights: list[dict[str, Any]] = []
    passengers: list[str] = []
    all_tickets: list[str] = []
    pnr: str | None = None

    orders = collect_orders(data)
    if not orders:
        raise ValueError("no Utair orders found")

    for order in orders:
        if pnr is None:
            ref = first_value(
                order,
                ["rloc", "locator", "pnr", "booking_reference", "bookingReference"],
            )
            pnr = str(ref).strip() if clean(ref) else None
        for name in passenger_names(order):
            if name not in passengers:
                passengers.append(name)
        tickets = ticket_numbers(order)
        for ticket in tickets:
            if ticket not in all_tickets:
                all_tickets.append(ticket)
        segments = order.get("segments") or order.get("flights") or []
        if not isinstance(segments, list):
            continue
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            dep_code = airport_code(seg, "departure")
            arr_code = airport_code(seg, "arrival")
            dep_local = segment_local(seg, "departure")
            arr_local = segment_local(seg, "arrival")
            if not dep_code or not arr_code or not dep_local or not arr_local:
                raise ValueError("Utair segment is missing route or local time fields")

            departure: dict[str, Any] = {
                "airport": dep_code,
                "local": dep_local,
            }
            dep_city = city_name(seg, "departure")
            if dep_city:
                departure["city"] = dep_city
            arrival: dict[str, Any] = {
                "airport": arr_code,
                "local": arr_local,
            }
            arr_city = city_name(seg, "arrival")
            if arr_city:
                arrival["city"] = arr_city
            flight: dict[str, Any] = {
                "flight_number": flight_number(seg),
                "departure": departure,
                "arrival": arrival,
            }
            aircraft = first_value(
                seg,
                [
                    "aircraft",
                    "aircraft_name",
                    "aircraftName",
                    "plane_type_name",
                    "plane_type",
                ],
            )
            if clean(aircraft):
                flight["aircraft"] = str(aircraft).strip()
            flights.append(flight)

    if not flights:
        raise ValueError("no flight segments found in Utair response")

    itinerary: dict[str, Any] = {
        "flights": flights,
    }
    if pnr:
        itinerary["pnr"] = pnr
    if passengers:
        itinerary["passenger"] = passengers[0]
    if all_tickets:
        itinerary["ticket_number"] = ", ".join(all_tickets)
    if booking_url:
        itinerary["booking_url"] = booking_url
    return itinerary
