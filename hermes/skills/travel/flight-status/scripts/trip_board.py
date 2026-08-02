#!/usr/bin/env python3
"""Read the current Trip.com airport board without browser automation."""

from __future__ import annotations

import argparse
import base64
from datetime import date, datetime, timedelta, timezone
import json
import math
import re
import sys
import time
from typing import Any


TRIP_STATUS_URL = "https://www.trip.com/flights/status/{airport}/"
PAGE_SIZE = 24
MAX_JAVASCRIPT_TIMESTAMP_MS = 8_640_000_000_000_000

_STATE_I18N_KEYS = {
    1: "Scheduled",
    2: "Delayed",
    3: "Possible_Delay",
    4: "Take_Off",
    5: "Cancelled",
    6: "Arrived",
    7: "Possible_Return_Flight",
    8: "Return",
    9: "Possible_Diversion",
    10: "Alternate_Landing",
    11: "Contact_Lost",
    12: "Accident_Occurred",
    13: "Alternate_Arrival",
    14: "Alternate_Cancellation",
    15: "Return_Flight_Arrival",
    16: "Return_Trip_Canceled",
    17: "May_Cancel",
}

_STATE_FALLBACKS = {
    1: "Scheduled",
    2: "Delayed",
    3: "May be delayed",
    4: "En route",
    5: "Cancelled",
    6: "Arrived",
    7: "May return",
    8: "Returning",
    9: "May divert",
    10: "Diverted",
    11: "Contact lost",
    12: "Accident reported",
    13: "Arrived after diversion",
    14: "Cancelled after diversion",
    15: "Returned and arrived",
    16: "Returned and cancelled",
    17: "May be cancelled",
}

_PROPS_PATTERN = re.compile(
    r"var\s+pr\s*=\s*'([^']+)'\s*;\s*var\s+w\s*=\s*window",
    re.DOTALL,
)


class TripBoardError(RuntimeError):
    """A named, user-safe Trip.com board failure."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        message = code if not detail else f"{code}: {detail}"
        super().__init__(message)


def normalize_iata(value: str) -> str:
    airport = value.strip().upper()
    if re.fullmatch(r"[A-Z]{3}", airport) is None:
        raise TripBoardError("invalid_airport_iata")
    return airport


def source_url(airport: str) -> str:
    return TRIP_STATUS_URL.format(airport=normalize_iata(airport).lower())


def _extract_status_payload(html: str) -> dict[str, Any]:
    if "challenge validation" in html.lower():
        raise TripBoardError("trip_antibot_challenge")

    for encoded in _PROPS_PATTERN.findall(html):
        try:
            decoded = base64.b64decode(encoded, validate=True)
            payload = json.loads(decoded)
        except (ValueError, json.JSONDecodeError):
            continue
        if (
            isinstance(payload, dict)
            and payload.get("moduleName") == "statusList"
            and isinstance(payload.get("data"), dict)
        ):
            return payload

    raise TripBoardError("trip_parser_changed")


def _state_number(row: dict[str, Any]) -> int | None:
    raw_state = row.get("flightState")
    if raw_state is None:
        return None
    try:
        return int(raw_state)
    except (TypeError, ValueError):
        return None


def _status_text(
    row: dict[str, Any], i18n: dict[str, Any], direction: str
) -> str | None:
    state = _state_number(row)
    if state is None:
        return None

    key = _STATE_I18N_KEYS.get(state)
    localized = i18n.get(key) if key is not None else None
    status = str(localized or _STATE_FALLBACKS.get(state) or f"State {state}")

    if state == 2:
        time_value = (
            row.get("finalArrivalTime")
            if direction == "arrivals"
            else row.get("finalDepartTime")
        )
        template = i18n.get("delaytime")
        if time_value and template:
            return str(template).replace("${{time}}", str(time_value))

    if state == 6:
        time_value = row.get("finalArrivalTime")
        template = i18n.get("arrivetime")
        if time_value and template:
            return str(template).replace("${{time}}", str(time_value))

    return status


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_valid_timestamp(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 0 < value <= MAX_JAVASCRIPT_TIMESTAMP_MS
    if isinstance(value, float):
        return math.isfinite(value) and 0 < value <= MAX_JAVASCRIPT_TIMESTAMP_MS
    return False


def _system_local_midnight_ms(local_now: datetime) -> float:
    target = (local_now.year, local_now.month, local_now.day, 0, 0, 0)
    candidates: dict[float, tuple[int, ...]] = {}
    for is_dst in (0, 1):
        try:
            epoch = time.mktime((*target, 0, 0, is_dst))
            candidates[epoch] = time.localtime(epoch)[:6]
        except (OverflowError, OSError, ValueError):
            continue

    exact = sorted(
        epoch for epoch, wall_time in candidates.items() if wall_time == target
    )
    if exact:
        # JavaScript's "compatible" disambiguation chooses the earlier fold.
        return exact[0] * 1000

    after_gap = sorted(
        (wall_time, epoch)
        for epoch, wall_time in candidates.items()
        if wall_time > target
    )
    if after_gap:
        # For a nonexistent midnight JavaScript advances by the transition gap.
        return after_gap[0][1] * 1000
    raise TripBoardError("trip_parser_changed")


def _row_for_direction(
    row: dict[str, Any], direction: str, i18n: dict[str, Any]
) -> dict[str, str | None]:
    arrivals = direction == "arrivals"
    return {
        "time": _clean(
            row.get("plannedArrivalTime") if arrivals else row.get("plannedDepartTime")
        ),
        "flight_number": _clean(row.get("flightNo")),
        "route_point": _clean(
            row.get("departCityName") if arrivals else row.get("arrivalCityName")
        ),
        "airline": _clean(row.get("airlineName") or row.get("airlineCode")),
        "terminal": _clean(
            row.get("arrivalTerminal") if arrivals else row.get("departTerminal")
        ),
        "status": _status_text(row, i18n, direction),
    }


def _trip_filter_values(
    data: dict[str, Any],
    cutoff: str | None,
    timezone_offset_minutes: int | None,
    now: datetime | None,
) -> tuple[float, float]:
    """Reproduce Trip.com's client-side time filter for the first board page."""
    if cutoff is None or re.fullmatch(r"\d{2}:\d{2}", cutoff) is None:
        raise TripBoardError("trip_parser_changed")

    time_options = data.get("timeOptionsWithMinutes")
    if not isinstance(time_options, list):
        raise TripBoardError("trip_parser_changed")
    selected_option = next(
        (
            option
            for option in time_options
            if isinstance(option, dict) and option.get("label") == cutoff
        ),
        None,
    )
    if selected_option is None:
        raise TripBoardError("trip_parser_changed")
    selected_minutes = selected_option.get("minutes")
    if (
        isinstance(selected_minutes, bool)
        or not isinstance(selected_minutes, int)
        or not 0 <= selected_minutes < 24 * 60
    ):
        raise TripBoardError("trip_parser_changed")

    local_now = now or datetime.now().astimezone()
    if local_now.tzinfo is None or local_now.utcoffset() is None:
        raise TripBoardError("trip_parser_changed")

    if timezone_offset_minutes is None:
        utc_offset = local_now.utcoffset() or timedelta(0)
        # JavaScript Date.getTimezoneOffset() is UTC - local time at parse time.
        timezone_offset_minutes = -int(utc_offset.total_seconds() // 60)

    if now is None:
        local_midnight_ms = _system_local_midnight_ms(local_now)
    else:
        local_midnight_ms = (
            local_now.replace(
                hour=0, minute=0, second=0, microsecond=0, fold=0
            ).timestamp()
            * 1000
        )
    cutoff_ms = local_midnight_ms + selected_minutes * 60_000

    # Trip.com's bundled statusList code normalizes timestamps against UTC+8.
    adjustment_ms = (timezone_offset_minutes + 480) * 60_000
    return cutoff_ms, adjustment_ms


def parse_trip_board(
    html: str,
    *,
    airport: str,
    direction: str,
    observed_at: str | None = None,
    timezone_offset_minutes: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    airport = normalize_iata(airport)
    if direction not in {"arrivals", "departures"}:
        raise TripBoardError("invalid_direction")

    payload = _extract_status_payload(html)
    data = payload["data"]

    raw_current_date = payload.get("currentDate")
    if not isinstance(raw_current_date, str):
        raise TripBoardError("trip_parser_changed")
    try:
        current_date = date.fromisoformat(raw_current_date)
    except ValueError as exc:
        raise TripBoardError("trip_parser_changed") from exc
    if current_date.isoformat() != raw_current_date:
        raise TripBoardError("trip_parser_changed")

    raw_page_airport = data.get("airportCode")
    if not isinstance(raw_page_airport, str):
        raise TripBoardError("trip_parser_changed")
    try:
        page_airport = normalize_iata(raw_page_airport)
    except TripBoardError as exc:
        raise TripBoardError("trip_parser_changed") from exc
    if page_airport != airport:
        raise TripBoardError("trip_airport_mismatch")

    data_key = "arrivalsData" if direction == "arrivals" else "originData"
    direction_data = data.get(data_key)
    if not isinstance(direction_data, dict):
        raise TripBoardError("trip_parser_changed")
    raw_rows = direction_data.get("flightStatusByAirport")
    if not isinstance(raw_rows, list):
        raise TripBoardError("trip_parser_changed")

    timestamp_key = (
        "plannedArrivalTimeStamp"
        if direction == "arrivals"
        else "plannedDepartTimeStamp"
    )
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            raise TripBoardError("trip_parser_changed")
        state = raw_row.get("flightState")
        if (
            isinstance(state, bool)
            or not isinstance(state, int)
            or state not in range(1, 18)
        ):
            raise TripBoardError("trip_parser_changed")
        planned_timestamp = raw_row.get(timestamp_key)
        if not _is_valid_timestamp(planned_timestamp):
            raise TripBoardError("trip_parser_changed")

    cutoff = _clean(data.get("defaultSelectedTime"))
    filter_values = _trip_filter_values(data, cutoff, timezone_offset_minutes, now)
    selected_rows = []
    cutoff_ms, adjustment_ms = filter_values
    for raw_row in raw_rows:
        planned_timestamp = float(raw_row[timestamp_key])
        if planned_timestamp + adjustment_ms < cutoff_ms:
            continue
        selected_rows.append(raw_row)
        if len(selected_rows) == PAGE_SIZE:
            break

    i18n = data.get("i18n") if isinstance(data.get("i18n"), dict) else {}
    rows = [_row_for_direction(row, direction, i18n) for row in selected_rows]

    date_options = data.get("dateOptions")
    date_label = (
        _clean(date_options[1])
        if isinstance(date_options, list) and len(date_options) > 1
        else None
    )
    observation = (
        observed_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )

    return {
        "ok": True,
        "airport": airport,
        "airport_name": _clean(data.get("airportName")),
        "direction": direction,
        "date": current_date.isoformat(),
        "date_label": date_label,
        "time_from": cutoff,
        "source": {
            "name": "Trip.com",
            "data_provider": "VariFlight",
            "kind": "airport_board_aggregator",
            "url": source_url(airport),
        },
        "observed_at": observation,
        "rows": rows,
    }


def render_text(result: dict[str, Any]) -> str:
    airport = result.get("airport") or "---"
    direction = str(result.get("direction") or "board").upper()
    date_value = result.get("date_label") or result.get("date") or "current"
    time_from = result.get("time_from") or "00:00"
    route_header = "Origin" if result.get("direction") == "arrivals" else "Destination"

    lines = [
        f"{airport} — {direction} — {date_value}, from {time_from}",
        f"Time  Flight  {route_header}  Airline  Terminal  Status",
    ]
    for row in result.get("rows") or []:
        lines.append(
            "  ".join(
                [
                    row.get("time") or "--",
                    row.get("flight_number") or "--",
                    row.get("route_point") or "--",
                    row.get("airline") or "--",
                    row.get("terminal") or "--",
                    row.get("status") or "--",
                ]
            )
        )
    lines.extend(
        [
            "Source: Trip.com; data: VariFlight (third-party aggregator)",
            f"Observed: {result.get('observed_at') or '--'}",
            f"URL: {(result.get('source') or {}).get('url') or '--'}",
        ]
    )
    return "\n".join(lines)


def fetch_trip_page(airport: str, *, timeout: int = 30) -> str:
    url = source_url(airport)
    try:
        from curl_cffi import requests
    except ModuleNotFoundError as exc:
        raise TripBoardError("missing_dependency", "curl_cffi") from exc

    try:
        response = requests.get(url, impersonate="chrome", timeout=timeout)
    except Exception as exc:
        raise TripBoardError("trip_network_error", type(exc).__name__) from exc

    if response.status_code == 404:
        raise TripBoardError("airport_board_not_found")
    if response.status_code != 200:
        raise TripBoardError("trip_http_error", str(response.status_code))
    return response.text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read the current Trip.com airport arrivals/departures board."
    )
    parser.add_argument("airport", help="Three-letter airport IATA code, e.g. SVO")
    parser.add_argument(
        "--direction",
        required=True,
        choices=("arrivals", "departures"),
        help="Board direction to return",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument(
        "--timeout", type=int, default=30, help="HTTP timeout in seconds"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        airport = normalize_iata(args.airport)
        html = fetch_trip_page(airport, timeout=args.timeout)
        result = parse_trip_board(html, airport=airport, direction=args.direction)
    except TripBoardError as exc:
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
