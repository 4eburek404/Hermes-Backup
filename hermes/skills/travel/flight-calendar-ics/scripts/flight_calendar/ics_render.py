#!/usr/bin/env python3
"""Generate RFC 5545 .ics files from structured flight itinerary JSON.

Uses the icalendar library for RFC 5545 compliance and line folding. Each
VEVENT stores DTSTART/DTEND in UTC while the short SUMMARY keeps local times.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

from icalendar import Calendar, Event

from flight_calendar import itinerary_contract
from flight_calendar.passenger_display import display_passenger_name

UTC = dt.timezone.utc


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [
            str(item).strip()
            for item in value
            if not itinerary_contract.is_placeholder(item)
        ]
    if itinerary_contract.is_placeholder(value):
        return []
    return [str(value).strip()]


def stable_uid(flight: dict[str, Any], pnr: str | None) -> str:
    dep = flight.get("departure", {})
    arr = flight.get("arrival", {})
    pieces = [
        str(pnr or ""),
        str(flight.get("flight_number", "")),
        str(dep.get("local", "")),
        str(dep.get("airport", "")),
        str(arr.get("airport", "")),
    ]
    digest = hashlib.sha256("|".join(pieces).encode("utf-8")).hexdigest()[:24]
    return f"flight-{digest}@hermes-agent.local"


def endpoint_city(endpoint: dict[str, Any], fallback_airport: str) -> str:
    if not itinerary_contract.is_placeholder(endpoint.get("city")):
        return str(endpoint.get("city")).strip()
    return fallback_airport.strip().upper()


def segment_route_time_label(
    dep_dt: dt.datetime,
    arr_dt: dt.datetime,
    dep_city: str,
    arr_city: str,
    *,
    separator: str,
) -> str:
    return f"{dep_dt:%d.%m} {dep_city} {separator} {arr_city} {dep_dt:%H:%M} {arr_dt:%H:%M}"


def primary_passenger_label(passenger: Any) -> str:
    if itinerary_contract.is_placeholder(passenger):
        return ""
    return display_passenger_name(str(passenger).strip())


def format_ticket_number(value: Any) -> str:
    import re

    raw_parts = normalize_list(value)
    formatted: list[str] = []
    for raw in raw_parts:
        for part in re.split(r"\s*,\s*", raw):
            text = part.strip()
            if not text:
                continue
            digits = re.sub(r"\s+", "", text)
            if digits.isdigit() and len(digits) > 3:
                formatted.append(f"{digits[:3]} {digits[3:]}")
            else:
                formatted.append(text)
    return ", ".join(formatted)


def build_event(
    flight: dict[str, Any],
    *,
    calendar: dict[str, Any],
) -> tuple[Event, dict[str, Any]]:
    """Build a single VEVENT as an icalendar Event object + summary dict."""
    flight_number = flight["flight_number"]
    dep = flight["departure"]
    arr = flight["arrival"]
    dep_airport = dep["airport"].upper()
    arr_airport = arr["airport"].upper()
    dep_dt = itinerary_contract.parse_local_datetime(
        dep["local"],
        dep["tz"],
        f"flight {flight_number}.departure",
    )
    arr_dt = itinerary_contract.parse_local_datetime(
        arr["local"],
        arr["tz"],
        f"flight {flight_number}.arrival",
    )

    pnr = calendar.get("pnr")
    booking_url = (
        None
        if itinerary_contract.is_placeholder(calendar.get("booking_url"))
        else str(calendar.get("booking_url")).strip()
    )
    ticket_number = format_ticket_number(calendar.get("ticket_number"))
    dep_city = endpoint_city(dep, dep_airport)
    arr_city = endpoint_city(arr, arr_airport)
    title_route = segment_route_time_label(
        dep_dt, arr_dt, dep_city, arr_city, separator="-"
    )
    description_route = segment_route_time_label(
        dep_dt, arr_dt, dep_city, arr_city, separator="->"
    )
    passenger = primary_passenger_label(calendar.get("passenger"))
    summary = " ".join(part for part in [passenger, title_route] if part)
    # Build description
    desc_lines: list[str] = []
    if not itinerary_contract.is_placeholder(pnr):
        desc_lines.append(f"Код брони: {str(pnr).strip()}")
    if ticket_number:
        desc_lines.append(f"Билет: {ticket_number}")
    desc_lines.append(description_route)
    if not itinerary_contract.is_placeholder(flight.get("aircraft")):
        desc_lines.append(f"Самолет: {str(flight.get('aircraft')).strip()}")
    if booking_url:
        desc_lines.append(f"Бронирование: {booking_url}")
    description = "\n".join(desc_lines)

    uid = stable_uid(flight, str(calendar.get("pnr") or ""))

    event = Event()
    event.add("summary", summary)
    event.add("dtstart", dep_dt.astimezone(UTC))
    event.add("dtend", arr_dt.astimezone(UTC))
    event.add("uid", uid)
    event.add("description", description)

    summary_info = {
        "flight_number": flight_number,
        "route": f"{dep_airport}->{arr_airport}",
        "departure_local": dep.get("local"),
        "arrival_local": arr.get("local"),
        "dtstart_utc": dep_dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "dtend_utc": arr_dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ"),
    }
    return event, summary_info


def build_calendar(
    data: dict[str, Any], *, no_alarms: bool = False
) -> tuple[str, list[dict[str, Any]]]:
    """Build a complete VCALENDAR string.

    Returns (ics_text, summaries) where ics_text is a valid RFC 5545 string
    and summaries is a list of per-flight info dicts.
    """
    flights = data["flights"]

    events: list[Event] = []
    summaries: list[dict[str, Any]] = []
    for flight in flights:
        event, info = build_event(
            flight,
            calendar=data,
        )
        events.append(event)
        summaries.append(info)

    cal = Calendar()
    cal.add("version", "2.0")
    cal.add("prodid", "-//Flight Calendar//EN")
    for event in events:
        cal.add_component(event)

    ics_text = cal.to_ical().decode("utf-8")
    return ics_text, summaries


def validate_ics_text(text: str, expected_events: int) -> None:
    """Validate generated ICS text for structural correctness."""
    if "BEGIN:VCALENDAR" not in text or "END:VCALENDAR" not in text:
        raise ValueError("generated text is not a VCALENDAR")

    # Parse with icalendar for deep validation
    try:
        Calendar.from_ical(text)
    except Exception as exc:
        raise ValueError(f"generated ICS is not valid RFC 5545: {exc}")

    event_count = text.count("BEGIN:VEVENT")
    if event_count != expected_events:
        raise ValueError(f"VEVENT count mismatch: expected {expected_events}, got {event_count}")

    # Check for placeholder-like text in the output
    bad = [word for word in ("TBD", "UNKNOWN", "None", "null") if word in text]
    if bad:
        raise ValueError(f"generated ICS contains placeholder-like text: {', '.join(bad)}")
