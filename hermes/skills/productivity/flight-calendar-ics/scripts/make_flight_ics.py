#!/usr/bin/env python3
"""Generate RFC 5545 .ics files from structured flight itinerary JSON.

The script uses only Python stdlib. It writes UTC DTSTART/DTEND values after
converting ticket-local times with IANA TZIDs via zoneinfo.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = dt.timezone.utc
PLACEHOLDERS = {"", "tbd", "todo", "unknown", "none", "null", "n/a", "na", "?"}


def secure_write_text(path: Path, text: str) -> None:
    """Write itinerary/ICS artifacts as owner-only files even under permissive umask."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    finally:
        try:
            os.chmod(path, 0o600)
        except FileNotFoundError:
            pass


def die(message: str, code: int = 2) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def is_placeholder(value: Any) -> bool:
    return value is None or str(value).strip().lower() in PLACEHOLDERS


def require_text(obj: dict[str, Any], key: str, context: str) -> str:
    value = obj.get(key)
    if is_placeholder(value):
        die(f"missing required field: {context}.{key}")
    return str(value).strip()


def parse_local(value: str, tzid: str | None, context: str) -> dt.datetime:
    if is_placeholder(value):
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

    if is_placeholder(tzid):
        die(f"missing required timezone: {context}.tz (IANA TZID, e.g. Europe/Moscow)")
    try:
        zone = ZoneInfo(str(tzid).strip())
    except ZoneInfoNotFoundError:
        die(f"unknown timezone for {context}.tz: {tzid!r}")
    return parsed.replace(tzinfo=zone)


def utc_stamp(value: dt.datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def display_dt(value: dt.datetime, tzid: str | None) -> str:
    tz_label = str(tzid).strip() if not is_placeholder(tzid) else str(value.tzinfo or "")
    return value.strftime("%Y-%m-%d %H:%M") + (f" {tz_label}" if tz_label else "")


def ical_escape(value: Any) -> str:
    text = str(value)
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", "\\n")
    return text


def fold_line(line: str, limit: int = 75) -> str:
    """Fold an iCalendar content line without splitting UTF-8 characters."""
    if len(line.encode("utf-8")) <= limit:
        return line
    chunks: list[str] = []
    current = ""
    for char in line:
        candidate = current + char
        if current and len(candidate.encode("utf-8")) > limit:
            chunks.append(current)
            current = " " + char
        else:
            current = candidate
    if current:
        chunks.append(current)
    return "\r\n".join(chunks)


def prop(name: str, value: Any) -> str:
    return f"{name}:{ical_escape(value)}"


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if not is_placeholder(item)]
    if is_placeholder(value):
        return []
    return [str(value).strip()]


def route_label(flight: dict[str, Any]) -> str:
    dep = flight.get("departure", {})
    arr = flight.get("arrival", {})
    return f"{str(dep.get('airport', '')).strip().upper()}→{str(arr.get('airport', '')).strip().upper()}"


def duration_trigger(minutes: int) -> str:
    if minutes <= 0:
        die(f"alarm minutes must be positive, got {minutes}")
    return f"-PT{minutes}M"


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


def add_if(parts: list[str], label: str, value: Any) -> None:
    if is_placeholder(value):
        return
    if isinstance(value, list):
        clean = [str(item).strip() for item in value if not is_placeholder(item)]
        if clean:
            parts.append(f"{label}: {', '.join(clean)}")
    else:
        parts.append(f"{label}: {str(value).strip()}")


def build_event(
    flight: dict[str, Any],
    *,
    calendar: dict[str, Any],
    now_utc: dt.datetime,
    alarms_minutes: list[int],
) -> tuple[list[str], dict[str, Any]]:
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

    dep_utc = dep_dt.astimezone(UTC)
    arr_utc = arr_dt.astimezone(UTC)
    if arr_utc <= dep_utc:
        die(
            f"flight {flight_number}: arrival must be after departure after timezone conversion "
            f"({utc_stamp(dep_dt)} -> {utc_stamp(arr_dt)})"
        )

    carrier = str(flight.get("carrier") or "").strip()
    summary = f"{flight_number} {dep_airport}→{arr_airport}"
    if carrier:
        summary += f" ({carrier})"

    booking_reference = flight.get("pnr") or calendar.get("booking_reference")
    passengers = normalize_list(flight.get("passengers") or calendar.get("passengers"))
    links = normalize_list(flight.get("links") or flight.get("url") or calendar.get("links"))

    route_parts = []
    dep_bits = [dep_airport]
    arr_bits = [arr_airport]
    if not is_placeholder(dep.get("city")):
        dep_bits.append(str(dep.get("city")).strip())
    if not is_placeholder(dep.get("terminal")):
        dep_bits.append(f"terminal {str(dep.get('terminal')).strip()}")
    if not is_placeholder(arr.get("city")):
        arr_bits.append(str(arr.get("city")).strip())
    if not is_placeholder(arr.get("terminal")):
        arr_bits.append(f"terminal {str(arr.get('terminal')).strip()}")
    route_parts.append("Departure: " + ", ".join(dep_bits))
    route_parts.append("Arrival: " + ", ".join(arr_bits))

    desc: list[str] = []
    add_if(desc, "Flight", f"{carrier + ' ' if carrier else ''}{flight_number}")
    add_if(desc, "Route", f"{dep_airport} → {arr_airport}")
    desc.extend(route_parts)
    add_if(desc, "Departure local", display_dt(dep_dt, dep_tz))
    add_if(desc, "Arrival local", display_dt(arr_dt, arr_tz))
    add_if(desc, "Booking reference/PNR", booking_reference)
    add_if(desc, "Passengers", passengers)
    add_if(desc, "Ticket number", flight.get("ticket_number") or calendar.get("ticket_number"))
    add_if(desc, "Seat", flight.get("seat"))
    add_if(desc, "Baggage", flight.get("baggage"))
    add_if(desc, "Cabin", flight.get("cabin"))
    add_if(desc, "Fare", flight.get("fare"))
    add_if(desc, "Aircraft", flight.get("aircraft"))
    add_if(desc, "Status", flight.get("status") or "confirmed")
    add_if(desc, "Notes", flight.get("notes") or calendar.get("notes"))
    add_if(desc, "Links", links)
    description = "\n".join(desc)

    raw_status = str(flight.get("status") or "confirmed").strip().lower()
    status_map = {
        "confirmed": "CONFIRMED",
        "cancelled": "CANCELLED",
        "canceled": "CANCELLED",
        "tentative": "TENTATIVE",
    }
    ical_status = status_map.get(raw_status, "CONFIRMED")

    lines = [
        "BEGIN:VEVENT",
        prop("UID", stable_uid(flight, str(calendar.get("booking_reference") or ""))),
        prop("DTSTAMP", utc_stamp(now_utc)),
        prop("CREATED", utc_stamp(now_utc)),
        prop("LAST-MODIFIED", utc_stamp(now_utc)),
        prop("SUMMARY", summary),
        prop("LOCATION", f"{dep_airport} → {arr_airport}"),
        prop("DESCRIPTION", description),
        prop("DTSTART", utc_stamp(dep_dt)),
        prop("DTEND", utc_stamp(arr_dt)),
        prop("STATUS", ical_status),
        prop("TRANSP", "OPAQUE"),
        "CATEGORIES:Travel,Flight",
    ]
    if links:
        lines.append(prop("URL", links[0]))

    for minutes in alarms_minutes:
        lines.extend(
            [
                "BEGIN:VALARM",
                prop("ACTION", "DISPLAY"),
                prop("DESCRIPTION", f"Flight {flight_number} {dep_airport}→{arr_airport}"),
                prop("TRIGGER", duration_trigger(int(minutes))),
                "END:VALARM",
            ]
        )
    lines.append("END:VEVENT")

    summary_info = {
        "flight_number": flight_number,
        "route": f"{dep_airport}->{arr_airport}",
        "dtstart_utc": utc_stamp(dep_dt),
        "dtend_utc": utc_stamp(arr_dt),
    }
    return lines, summary_info


def build_calendar(data: dict[str, Any], *, no_alarms: bool = False) -> tuple[str, list[dict[str, Any]]]:
    flights = data.get("flights")
    if not isinstance(flights, list) or not flights:
        die("input JSON must contain a non-empty flights array")
    for idx, flight in enumerate(flights, start=1):
        if not isinstance(flight, dict):
            die(f"flights[{idx}] must be an object")

    calendar_name = str(data.get("calendar_name") or "Flights").strip()
    alarms_minutes = parse_alarm_minutes(data.get("alarms_minutes"), no_alarms=no_alarms)

    now_utc = dt.datetime.now(tz=UTC).replace(microsecond=0)
    raw_lines = [
        "BEGIN:VCALENDAR",
        prop("PRODID", "-//Hermes Agent//Flight Calendar ICS//EN"),
        prop("VERSION", "2.0"),
        prop("CALSCALE", "GREGORIAN"),
        prop("METHOD", "PUBLISH"),
        prop("X-WR-CALNAME", calendar_name),
        prop("X-WR-TIMEZONE", "UTC"),
    ]
    summaries: list[dict[str, Any]] = []
    for flight in flights:
        event_lines, info = build_event(
            flight,
            calendar=data,
            now_utc=now_utc,
            alarms_minutes=alarms_minutes,
        )
        raw_lines.extend(event_lines)
        summaries.append(info)
    raw_lines.append("END:VCALENDAR")
    folded = "\r\n".join(fold_line(line) for line in raw_lines) + "\r\n"
    return folded, summaries


def validate_ics_text(text: str, expected_events: int) -> None:
    if "BEGIN:VCALENDAR" not in text or "END:VCALENDAR" not in text:
        die("generated text is not a VCALENDAR")
    event_count = text.count("BEGIN:VEVENT")
    if event_count != expected_events:
        die(f"VEVENT count mismatch: expected {expected_events}, got {event_count}")
    if re.search(r"DT(?:START|END)(?:;[^:]+)?:\d{8}T\d{6}(?!Z)", text):
        die("generated DTSTART/DTEND contains non-UTC datetime")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate .ics calendar files from flight itinerary JSON.")
    parser.add_argument("--input", "-i", required=True, type=Path, help="Path to itinerary JSON")
    parser.add_argument("--output", "-o", type=Path, help="Output .ics path; defaults to input basename")
    parser.add_argument("--check-only", action="store_true", help="Validate input and print normalized segments without writing")
    parser.add_argument("--no-alarms", action="store_true", help="Do not add VALARM reminders")
    args = parser.parse_args(argv)

    data = load_input(args.input)
    ics_text, summaries = build_calendar(data, no_alarms=args.no_alarms)
    validate_ics_text(ics_text, len(summaries))

    if args.check_only:
        print(json.dumps({"ok": True, "segments": summaries}, ensure_ascii=False, indent=2))
        return 0

    output = args.output or args.input.with_suffix(".ics")
    secure_write_text(output, ics_text)
    print(f"OK: wrote {output} ({len(summaries)} segment(s))")
    for item in summaries:
        print(f"- {item['flight_number']} {item['route']} {item['dtstart_utc']} -> {item['dtend_utc']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
