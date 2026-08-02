#!/usr/bin/env python3
"""Query the official Sheremetyevo timetable by exact flight and date."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from http.client import HTTPException
import json
import re
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SVO_TIMETABLE_URL = "https://www.svo.aero/bitrix/timetable/"


class SheremetyevoError(RuntimeError):
    """A named, user-safe Sheremetyevo timetable failure."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        message = code if detail is None else f"{code}: {detail}"
        super().__init__(message)


def normalize_flight_number(value: str) -> str:
    flight_number = re.sub(r"[\s-]+", "", value.strip().upper())
    if re.fullmatch(r"[A-Z0-9]{2}[0-9]{1,4}[A-Z]?", flight_number) is None:
        raise SheremetyevoError("invalid_flight_number")
    if not any(character.isalpha() for character in flight_number[:2]):
        raise SheremetyevoError("invalid_flight_number")
    return flight_number


def normalize_operating_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise SheremetyevoError("invalid_date") from exc
    if parsed.isoformat() != value:
        raise SheremetyevoError("invalid_date")
    return value


def normalize_timeout(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SheremetyevoError("invalid_timeout")
    return value


def query_url(flight_number: str) -> str:
    query = urlencode(
        {
            "search": normalize_flight_number(flight_number),
            "perPage": 9999,
            "page": 0,
        }
    )
    return f"{SVO_TIMETABLE_URL}?{query}"


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SheremetyevoError("svo_parser_changed")
    text = value.strip()
    return text or None


def _parse_aware_datetime(value: Any) -> datetime | None:
    text = _optional_text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SheremetyevoError("svo_parser_changed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SheremetyevoError("svo_parser_changed")
    return parsed


def _airport(raw_airport: Any) -> dict[str, str | None]:
    if not isinstance(raw_airport, dict):
        raise SheremetyevoError("svo_parser_changed")
    airport = {
        "iata": _optional_text(raw_airport.get("iata")),
        "city": _optional_text(raw_airport.get("city")),
        "airport": _optional_text(raw_airport.get("airport")),
        "timezone": _optional_text(raw_airport.get("timezone")),
    }
    timezone_name = airport["timezone"]
    if timezone_name is None:
        raise SheremetyevoError("svo_parser_changed")
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise SheremetyevoError("svo_parser_changed") from exc
    return airport


def _localized_timestamp(
    value: Any,
    airport: dict[str, str | None],
) -> str | None:
    timestamp = _parse_aware_datetime(value)
    if timestamp is None:
        return None
    timezone_name = airport.get("timezone")
    if timezone_name is not None:
        timestamp = timestamp.astimezone(ZoneInfo(timezone_name))
    return timestamp.isoformat(timespec="seconds")


def _row_identity(raw_row: Any) -> tuple[dict[str, Any], str, str]:
    if not isinstance(raw_row, dict):
        raise SheremetyevoError("svo_parser_changed")
    carrier = raw_row.get("co")
    if not isinstance(carrier, dict):
        raise SheremetyevoError("svo_parser_changed")
    carrier_code = _optional_text(carrier.get("code"))
    flight_digits = _optional_text(raw_row.get("flt"))
    if carrier_code is None or flight_digits is None:
        raise SheremetyevoError("svo_parser_changed")
    try:
        flight_number = normalize_flight_number(f"{carrier_code}{flight_digits}")
    except SheremetyevoError as exc:
        raise SheremetyevoError("svo_parser_changed") from exc

    operation = _parse_aware_datetime(raw_row.get("dat"))
    if operation is None:
        raise SheremetyevoError("svo_parser_changed")
    return raw_row, flight_number, operation.date().isoformat()


def parse_timetable(
    payload: object,
    *,
    flight_number: str,
    operating_date: str,
    source_updated_at: str | None = None,
) -> dict[str, Any]:
    requested_flight = normalize_flight_number(flight_number)
    requested_date = normalize_operating_date(operating_date)
    if not isinstance(payload, dict):
        raise SheremetyevoError("svo_parser_changed")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise SheremetyevoError("svo_parser_changed")

    matching_rows = []
    for raw_item in raw_items:
        row, row_flight, row_date = _row_identity(raw_item)
        if row_flight == requested_flight and row_date == requested_date:
            matching_rows.append(row)

    if not matching_rows:
        raise SheremetyevoError("svo_flight_not_found")
    if len(matching_rows) != 1:
        raise SheremetyevoError("svo_ambiguous_flight", str(len(matching_rows)))

    row = matching_rows[0]
    direction_code = _optional_text(row.get("ad"))
    direction = {"D": "departure", "A": "arrival"}.get(direction_code or "")
    if direction is None:
        raise SheremetyevoError("svo_parser_changed")

    carrier = row["co"]
    origin = _airport(row.get("mar1"))
    destination = _airport(row.get("mar2"))
    updated_at = _optional_text(source_updated_at)
    # SVO's t_st/t_et describe the event at SVO; t_st_mar is the scheduled
    # timestamp at the remote end, so arrival rows need the opposite mapping.
    if direction == "departure":
        scheduled_departure = row.get("t_st")
        revised_departure = row.get("t_et")
        scheduled_arrival = row.get("t_st_mar")
        revised_arrival = None
    else:
        scheduled_departure = row.get("t_st_mar")
        revised_departure = None
        scheduled_arrival = row.get("t_st")
        revised_arrival = row.get("t_et")

    return {
        "ok": True,
        "flight_number": requested_flight,
        "date": requested_date,
        "direction": direction,
        "airline": _optional_text(carrier.get("name")),
        "route": {"origin": origin, "destination": destination},
        "schedule": {
            "departure": _localized_timestamp(scheduled_departure, origin),
            "revised_departure": _localized_timestamp(revised_departure, origin),
            "arrival": _localized_timestamp(scheduled_arrival, destination),
            "revised_arrival": _localized_timestamp(revised_arrival, destination),
        },
        "terminal": _optional_text(row.get("term")),
        "gate": _optional_text(row.get("gate_id")),
        "check_in": {
            "desks": _optional_text(row.get("chin_id")),
            "opens_at": _localized_timestamp(row.get("estimated_chin_start"), origin),
            "closes_at": _localized_timestamp(row.get("estimated_chin_finish"), origin),
        },
        "status": {
            "ru": _optional_text(row.get("vip_status_rus")),
            "en": _optional_text(row.get("vip_status_eng")),
        },
        "source": {
            "name": "Sheremetyevo International Airport",
            "kind": "official_airport_board",
            "url": query_url(requested_flight),
            "updated_at": updated_at,
        },
    }


def fetch_timetable(
    flight_number: str,
    *,
    timeout: int = 30,
) -> tuple[object, str | None]:
    timeout = normalize_timeout(timeout)
    url = query_url(flight_number)
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            body = response.read()
            updated_at = response.headers.get("X-Date-Update")
    except HTTPError as exc:
        raise SheremetyevoError("svo_http_error", str(exc.code)) from exc
    except (URLError, TimeoutError, OSError, HTTPException) as exc:
        raise SheremetyevoError("svo_network_error", type(exc).__name__) from exc

    if status != 200:
        raise SheremetyevoError("svo_http_error", str(status))
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SheremetyevoError("svo_invalid_json") from exc
    return payload, updated_at


def _display_time(value: str | None, timezone_name: str | None) -> str:
    if value is None:
        return "--"
    timestamp = datetime.fromisoformat(value)
    if timezone_name is not None:
        timestamp = timestamp.astimezone(ZoneInfo(timezone_name))
    zone = timestamp.tzname() or timestamp.strftime("%z")
    return f"{timestamp:%H:%M} {zone}"


def render_text(result: dict[str, Any]) -> str:
    route = result.get("route") or {}
    origin = route.get("origin") or {}
    destination = route.get("destination") or {}
    schedule = result.get("schedule") or {}
    check_in = result.get("check_in") or {}
    status = result.get("status") or {}
    source = result.get("source") or {}

    status_text = status.get("ru") or status.get("en") or "status not shown"
    origin_timezone = origin.get("timezone")
    destination_timezone = destination.get("timezone")
    departure = _display_time(schedule.get("departure"), origin_timezone)
    arrival = _display_time(schedule.get("arrival"), destination_timezone)
    check_in_start = _display_time(check_in.get("opens_at"), origin_timezone)
    check_in_finish = _display_time(check_in.get("closes_at"), origin_timezone)
    check_in_zone = check_in_start.rsplit(" ", 1)[-1] if check_in_start != "--" else ""
    if check_in_start != "--" and check_in_finish != "--":
        start_time = check_in_start.rsplit(" ", 1)[0]
        finish_time = check_in_finish.rsplit(" ", 1)[0]
        check_in_window = f"{start_time}–{finish_time} {check_in_zone}"
    else:
        check_in_window = "not shown"

    lines = [
        f"{result.get('flight_number')} — {result.get('date')} — {status_text}",
        "Route: "
        f"{origin.get('iata') or '---'} {origin.get('city') or '--'} → "
        f"{destination.get('iata') or '---'} {destination.get('city') or '--'}",
        f"Scheduled: {departure} → {arrival}",
    ]
    revised_departure = schedule.get("revised_departure")
    if revised_departure is not None:
        lines.append(
            f"Revised departure: {_display_time(revised_departure, origin_timezone)}"
        )
    revised_arrival = schedule.get("revised_arrival")
    if revised_arrival is not None:
        lines.append(
            f"Revised arrival: {_display_time(revised_arrival, destination_timezone)}"
        )
    lines.extend(
        [
            "Terminal / gate: "
            f"{result.get('terminal') or 'not assigned'} / "
            f"{result.get('gate') or 'not assigned'}",
            "Check-in: "
            f"{check_in_window}; desks {check_in.get('desks') or 'not assigned'}",
            "Source: Sheremetyevo official airport board",
            f"Updated: {source.get('updated_at') or '--'}",
            f"URL: {source.get('url') or '--'}",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query the official Sheremetyevo timetable by flight and date."
    )
    parser.add_argument("flight", help="Flight number, e.g. SU1404")
    parser.add_argument(
        "--date",
        required=True,
        help="Operating date in YYYY-MM-DD format",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument(
        "--timeout", type=int, default=30, help="HTTP timeout in seconds"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        flight_number = normalize_flight_number(args.flight)
        operating_date = normalize_operating_date(args.date)
        timeout = normalize_timeout(args.timeout)
        payload, updated_at = fetch_timetable(flight_number, timeout=timeout)
        result = parse_timetable(
            payload,
            flight_number=flight_number,
            operating_date=operating_date,
            source_updated_at=updated_at,
        )
    except SheremetyevoError as exc:
        if args.json:
            print(
                json.dumps(
                    {"ok": False, "error": {"code": exc.code, "detail": exc.detail}},
                    ensure_ascii=False,
                )
            )
        else:
            print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
