#!/usr/bin/env python3
"""Generate RFC 5545 .ics files from structured flight itinerary JSON.

Uses the icalendar library for RFC 5545 serialization and line folding.
Each VEVENT carries absolute UTC DTSTART/DTEND values. Human-facing event
text still uses the airport-local times from the source itinerary.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from icalendar import Alarm, Calendar, Event, vText

from flight_calendar import itinerary_contract

UTC = dt.timezone.utc


def die(message: str, code: int = 2) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def require_text(obj: dict[str, Any], key: str, context: str) -> str:
    value = obj.get(key)
    if itinerary_contract.is_placeholder(value):
        die(f"missing required field: {context}.{key}")
    return str(value).strip()


def parse_local(value: str, tzid: str | None, context: str) -> dt.datetime:
    """Parse a local datetime string and attach IANA timezone."""
    if itinerary_contract.is_placeholder(value):
        die(f"missing required local datetime: {context}.local")
    raw = str(value).strip()
    normalized = raw.replace(" ", "T", 1)
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        die(f"invalid datetime for {context}.local: {raw!r}; use YYYY-MM-DDTHH:MM")

    if parsed.tzinfo is not None:
        return parsed

    if itinerary_contract.is_placeholder(tzid):
        die(f"missing required timezone: {context}.tz (IANA TZID, e.g. Europe/Moscow)")
    try:
        zone = ZoneInfo(str(tzid).strip())
    except ZoneInfoNotFoundError:
        die(f"unknown timezone for {context}.tz: {tzid!r}")
    return parsed.replace(tzinfo=zone)


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if not itinerary_contract.is_placeholder(item)]
    if itinerary_contract.is_placeholder(value):
        return []
    return [str(value).strip()]


def stable_uid(flight: dict[str, Any], booking_reference: str | None) -> str:
    dep = flight.get("departure", {})
    arr = flight.get("arrival", {})
    pieces = [
        str(booking_reference or ""),
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


def segment_route_time_label(dep_dt: dt.datetime, arr_dt: dt.datetime, dep_city: str, arr_city: str, *, separator: str) -> str:
    return f"{dep_dt:%d.%m} {dep_city} {separator} {arr_city} {dep_dt:%H:%M} {arr_dt:%H:%M}"


def primary_passenger_label(passengers: list[str]) -> str:
    return passengers[0].strip() if passengers else ""


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


def parse_alarm_minutes(value: Any, *, no_alarms: bool = False) -> list[int]:
    """Normalize VALARM offsets with clean validation errors."""
    raw_alarms = [] if no_alarms else (value if value is not None else [1440, 180])
    alarms: list[int] = []
    for idx, item in enumerate(normalize_list(raw_alarms), start=1):
        try:
            minutes = int(item)
        except (TypeError, ValueError):
            die(f"invalid alarm minutes value at alarms_minutes[{idx}]: {item!r}; use positive integers")
        if minutes <= 0:
            die(f"alarm minutes must be positive at alarms_minutes[{idx}], got {minutes}")
        alarms.append(minutes)
    return alarms


def build_event(
    flight: dict[str, Any],
    *,
    calendar: dict[str, Any],
    now_utc: dt.datetime,
    alarms_minutes: list[int],
) -> tuple[Event, dict[str, Any]]:
    """Build a single VEVENT as an icalendar Event object + summary dict."""
    flight_number = require_text(flight, "flight_number", "flight")
    dep = flight.get("departure") or {}
    arr = flight.get("arrival") or {}
    if not isinstance(dep, dict) or not isinstance(arr, dict):
        die(f"flight {flight_number}: departure and arrival must be objects")

    dep_airport = require_text(dep, "airport", f"flight {flight_number}.departure").upper()
    arr_airport = require_text(arr, "airport", f"flight {flight_number}.arrival").upper()
    dep_tz = require_text(dep, "tz", f"flight {flight_number}.departure")
    arr_tz = require_text(arr, "tz", f"flight {flight_number}.arrival")
    dep_dt = parse_local(require_text(dep, "local", f"flight {flight_number}.departure"), dep_tz, f"flight {flight_number}.departure")
    arr_dt = parse_local(require_text(arr, "local", f"flight {flight_number}.arrival"), arr_tz, f"flight {flight_number}.arrival")

    # Cross-timezone sanity: arrival must be after departure in UTC
    if arr_dt.astimezone(UTC) <= dep_dt.astimezone(UTC):
        die(
            f"flight {flight_number}: arrival must be after departure after timezone conversion "
            f"({dep_dt.isoformat()} -> {arr_dt.isoformat()})"
        )

    booking_reference = flight.get("pnr") or calendar.get("booking_reference")
    passengers = normalize_list(flight.get("passengers") or calendar.get("passengers"))
    links = normalize_list(flight.get("links") or flight.get("url") or calendar.get("links"))
    ticket_number = format_ticket_number(flight.get("ticket_number") or calendar.get("ticket_number"))
    dep_city = endpoint_city(dep, dep_airport)
    arr_city = endpoint_city(arr, arr_airport)
    title_route = segment_route_time_label(dep_dt, arr_dt, dep_city, arr_city, separator="-")
    description_route = segment_route_time_label(dep_dt, arr_dt, dep_city, arr_city, separator="->")
    passenger = primary_passenger_label(passengers)
    summary = " ".join(part for part in [passenger, title_route] if part)
    location = f"{dep_city} → {arr_city}"

    # Build description
    desc_lines: list[str] = []
    if not itinerary_contract.is_placeholder(booking_reference):
        desc_lines.append(f"PNR: {str(booking_reference).strip()}")
    if ticket_number:
        desc_lines.append(f"Билет: {ticket_number}")
    desc_lines.append(description_route)
    if not itinerary_contract.is_placeholder(flight.get("aircraft")):
        desc_lines.append(f"Самолет: {str(flight.get('aircraft')).strip()}")
    if links:
        desc_lines.append(f"Бронирование: {links[0]}")
    description = "\n".join(desc_lines)

    raw_status = str(flight.get("status") or "confirmed").strip().lower()
    status_map = {
        "confirmed": "CONFIRMED",
        "cancelled": "CANCELLED",
        "canceled": "CANCELLED",
        "tentative": "TENTATIVE",
    }
    ical_status = status_map.get(raw_status, "CONFIRMED")

    uid = stable_uid(flight, str(calendar.get("booking_reference") or ""))
    dep_dt_utc = dep_dt.astimezone(UTC)
    arr_dt_utc = arr_dt.astimezone(UTC)

    # Build Event using icalendar modern API
    event_kwargs: dict[str, Any] = {
        "summary": summary,
        "start": dep_dt_utc,
        "end": arr_dt_utc,
        "location": location,
        "description": description,
        "uid": uid,
        "stamp": now_utc,
        "created": now_utc,
        "last_modified": now_utc,
        "status": ical_status,
        "transparency": "OPAQUE",
        "categories": ["Travel", "Flight"],
    }
    if links:
        event_kwargs["url"] = links[0]

    event = Event.new(**event_kwargs)

    # Add VALARM subcomponents
    for minutes in alarms_minutes:
        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("trigger", dt.timedelta(minutes=-minutes))
        alarm.add("description", f"Flight {flight_number} {dep_city}→{arr_city}")
        event.add_component(alarm)

    summary_info = {
        "flight_number": flight_number,
        "route": f"{dep_airport}->{arr_airport}",
        "departure_local": dep.get("local"),
        "arrival_local": arr.get("local"),
        "dtstart_utc": dep_dt_utc.strftime("%Y%m%dT%H%M%SZ"),
        "dtend_utc": arr_dt_utc.strftime("%Y%m%dT%H%M%SZ"),
    }
    return event, summary_info


def build_calendar(data: dict[str, Any], *, no_alarms: bool = False) -> tuple[str, list[dict[str, Any]]]:
    """Build a complete VCALENDAR string with UTC VEVENT timestamps.

    Returns (ics_text, summaries) where ics_text is a valid RFC 5545 string
    and summaries is a list of per-flight info dicts.
    """
    flights = data.get("flights")
    if not isinstance(flights, list) or not flights:
        die("input JSON must contain a non-empty flights array")
    for idx, flight in enumerate(flights, start=1):
        if not isinstance(flight, dict):
            die(f"flights[{idx}] must be an object")

    calendar_name = str(data.get("calendar_name") or "Flights").strip()
    alarms_minutes = parse_alarm_minutes(data.get("alarms_minutes"), no_alarms=no_alarms)

    now_utc = dt.datetime.now(tz=UTC).replace(microsecond=0)

    events: list[Event] = []
    summaries: list[dict[str, Any]] = []
    for flight in flights:
        event, info = build_event(
            flight,
            calendar=data,
            now_utc=now_utc,
            alarms_minutes=alarms_minutes,
        )
        events.append(event)
        summaries.append(info)

    cal = Calendar.new(
        subcomponents=events,
        prodid="-//Hermes Agent//Flight Calendar ICS//EN",
    )
    cal["x-wr-calname"] = vText(calendar_name)
    cal["method"] = vText("PUBLISH")
    cal["calscale"] = vText("GREGORIAN")

    ics_text = cal.to_ical().decode("utf-8")
    return ics_text, summaries


def validate_ics_text(text: str, expected_events: int) -> None:
    """Validate generated ICS text for structural correctness."""
    if "BEGIN:VCALENDAR" not in text or "END:VCALENDAR" not in text:
        die("generated text is not a VCALENDAR")

    # Parse with icalendar for deep validation
    try:
        cal = Calendar.from_ical(text)
    except Exception as exc:
        die(f"generated ICS is not valid RFC 5545: {exc}")

    event_count = text.count("BEGIN:VEVENT")
    if event_count != expected_events:
        die(f"VEVENT count mismatch: expected {expected_events}, got {event_count}")

    # Check for placeholder-like text in the output
    bad = [word for word in ("TBD", "UNKNOWN", "None", "null") if word in text]
    if bad:
        die(f"generated ICS contains placeholder-like text: {', '.join(bad)}")


def load_input(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        die(f"input file not found: {path}")
    except json.JSONDecodeError as exc:
        die(f"invalid JSON in {path}: {exc}")
    if not isinstance(data, dict):
        die("input JSON root must be an object")
    return data
