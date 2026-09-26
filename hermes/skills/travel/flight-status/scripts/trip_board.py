#!/usr/bin/env python3
"""Read the current Trip.com airport board without browser automation."""

from __future__ import annotations

import argparse
import base64
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
import json
import math
import re
import sys
from typing import Any


TRIP_STATUS_URL = "https://www.trip.com/flights/status/{airport}/"
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


class _SpecificFlightHTML(HTMLParser):
    """Collect marked fields both globally and within each operation card."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fields: dict[str, list[str]] = {}
        self.attributes: list[str] = []
        self.cards: list[dict[str, Any]] = []
        self.stack: list[
            tuple[str, str | None, list[str] | None, dict[str, Any] | None, bool]
        ] = []
        self.active_card: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        self.attributes.extend(value or "" for value in values.values())
        classes = (values.get("class") or "").split()
        is_card = tag == "div" and "flight-status-card-item-container" in classes
        if is_card:
            self.active_card = {"attributes": [], "fields": {}}
        if self.active_card is not None:
            self.active_card["attributes"].extend(
                value or "" for value in values.values()
            )
        key = values.get("test-item")
        self.stack.append(
            (tag, key, [] if key else None, self.active_card, is_card)
        )

    def handle_data(self, data: str) -> None:
        for _, _, chunks, _, _ in self.stack:
            if chunks is not None:
                chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        match = next(
            (index for index in range(len(self.stack) - 1, -1, -1)
             if self.stack[index][0] == tag),
            None,
        )
        if match is None:
            return
        closed = self.stack[match:]
        del self.stack[match:]
        for _, key, chunks, card, is_card in reversed(closed):
            if key is not None and chunks is not None:
                value = "".join(chunks).strip()
                self.fields.setdefault(key, []).append(value)
                if card is not None:
                    card["fields"].setdefault(key, []).append(value)
            if is_card and card is not None:
                self.cards.append(card)
                if self.active_card is card:
                    self.active_card = None


def parse_specific_flight(
    html: str,
    *,
    flight_number: str,
    operating_date: str,
    allow_incomplete: bool = False,
) -> dict[str, Any]:
    if "challenge validation" in html.lower():
        raise TripBoardError("trip_antibot_challenge")

    page = _SpecificFlightHTML()
    page.feed(html)

    def identity(values: list[str]) -> tuple[str | None, str | None]:
        metadata = " ".join(values)
        found_flight = re.search(r"\bfno=([A-Z0-9]+)\b", metadata, re.IGNORECASE)
        found_date = re.search(r"\bfd=(\d{4}-\d{2}-\d{2})\b", metadata)
        return (
            found_flight.group(1).upper() if found_flight else None,
            found_date.group(1) if found_date else None,
        )

    selected_date = operating_date
    fields: dict[str, list[str]]
    if page.cards:
        matching_cards = []
        for card in page.cards:
            card_flight, card_date = identity(card["attributes"])
            if card_flight == flight_number:
                matching_cards.append((card_date, card))
        if not matching_cards:
            raise TripBoardError("flight_not_found", flight_number)
        selected = next(
            (
                card
                for card_date, card in matching_cards
                if card_date == operating_date
            ),
            None,
        )
        if selected is None:
            raise TripBoardError("trip_operating_date_mismatch")
        fields = selected["fields"]
    else:
        found_flight, found_date = identity(page.attributes)
        if found_flight is None or found_date is None:
            raise TripBoardError("trip_parser_changed")
        if found_flight != flight_number:
            raise TripBoardError("flight_not_found", flight_number)
        if found_date != operating_date:
            raise TripBoardError("trip_operating_date_mismatch")
        fields = page.fields

    def field(name: str) -> str:
        values = fields.get(name)
        if not values or not values[0]:
            raise TripBoardError("trip_parser_changed")
        return values[0]

    if allow_incomplete:
        def optional_field(name: str) -> str | None:
            values = fields.get(name)
            return values[0] if values and values[0] else None

        operation: dict[str, Any] = {"flight_number": flight_number}
        for field_name, result_name in (
            ("status_info_dep_city", "departure_airport"),
            ("status_info_arr_city", "arrival_airport"),
        ):
            city = optional_field(field_name)
            airport = re.search(r"\(([A-Z]{3})\)", city or "")
            if airport:
                operation[result_name] = airport.group(1)

        scheduled: dict[str, str] = {}
        for field_name, side in (
            ("status_info_dep_scheduletime", "departure"),
            ("status_info_arr_scheduletime", "arrival"),
        ):
            value = optional_field(field_name)
            match = re.search(r"Scheduled:\s*(\d{2}:\d{2})", value or "")
            if match:
                scheduled[side] = match.group(1)
        if scheduled:
            operation["scheduled"] = scheduled

        status = optional_field("status_info_status")
        if status:
            operation["status"] = status
        displayed_times = {
            side: optional_field(field_name)
            for field_name, side in (
                ("status_info_dep_time", "departure"),
                ("status_info_arr_time", "arrival"),
            )
        }
        displayed_times = {
            side: value for side, value in displayed_times.items() if value
        }
        if displayed_times:
            operation["actual" if status == "Arrived" else "current"] = displayed_times

        return {
            "ok": True,
            "date": selected_date,
            "source": {
                "name": "Trip.com",
                "data_provider": "VariFlight",
                "kind": "specific_flight",
                "url": f"https://www.trip.com/flights/status-{flight_number}/",
            },
            "observed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "rows": [operation],
        }

    departure_city = field("status_info_dep_city")
    arrival_city = field("status_info_arr_city")
    departure_airport = re.search(r"\(([A-Z]{3})\)", departure_city)
    arrival_airport = re.search(r"\(([A-Z]{3})\)", arrival_city)
    if departure_airport is None or arrival_airport is None:
        raise TripBoardError("trip_parser_changed")

    departure_schedule = re.search(
        r"Scheduled:\s*(\d{2}:\d{2})", field("status_info_dep_scheduletime")
    )
    arrival_schedule = re.search(
        r"Scheduled:\s*(\d{2}:\d{2})", field("status_info_arr_scheduletime")
    )
    if departure_schedule is None or arrival_schedule is None:
        raise TripBoardError("trip_parser_changed")

    status = field("status_info_status")
    operation: dict[str, Any] = {
        "flight_number": flight_number,
        "departure_airport": departure_airport.group(1),
        "arrival_airport": arrival_airport.group(1),
        "status": status,
        "scheduled": {
            "departure": departure_schedule.group(1),
            "arrival": arrival_schedule.group(1),
        },
    }
    displayed_times = {
        "departure": field("status_info_dep_time"),
        "arrival": field("status_info_arr_time"),
    }
    if status == "Arrived":
        operation["actual"] = displayed_times
    else:
        operation["current"] = displayed_times

    result = {
        "ok": True,
        "date": selected_date,
        "source": {
            "name": "Trip.com",
            "data_provider": "VariFlight",
            "kind": "specific_flight",
            "url": f"https://www.trip.com/flights/status-{flight_number}/",
        },
        "observed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "rows": [operation],
    }

    previous_numbers = page.fields.get("status_preinfo_flightno") or []
    previous_number = previous_numbers[0].strip().upper() if previous_numbers else ""
    if re.fullmatch(r"[A-Z0-9]+", previous_number):
        previous_flight: dict[str, Any] = {"flight_number": previous_number}
        departure_values = page.fields.get("status_preinfo_depcity") or []
        arrival_values = page.fields.get("status_preinfo_arrcity") or []
        if departure_values and departure_values[0]:
            previous_flight["departure_city"] = departure_values[0]
        if arrival_values and arrival_values[0]:
            previous_flight["arrival_city"] = arrival_values[0]
        schedule_values = page.fields.get("status_preinfo_scheduletime") or []
        if schedule_values:
            scheduled_arrival = re.search(
                r"Scheduled:\s*(\d{2}:\d{2})", schedule_values[0]
            )
            if scheduled_arrival:
                previous_flight["scheduled"] = {"arrival": scheduled_arrival.group(1)}
        result["_previous_flight"] = previous_flight
    return result


def _is_valid_timestamp(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 0 < value <= MAX_JAVASCRIPT_TIMESTAMP_MS
    if isinstance(value, float):
        return math.isfinite(value) and 0 < value <= MAX_JAVASCRIPT_TIMESTAMP_MS
    return False


def _row_for_direction(
    row: dict[str, Any], direction: str, i18n: dict[str, Any]
) -> dict[str, Any]:
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


def parse_trip_board(
    html: str,
    *,
    airport: str,
    direction: str,
    exact_flight: str | None = None,
    operating_date: str | None = None,
    observed_at: str | None = None,
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

    if (exact_flight is None) != (operating_date is None):
        raise TripBoardError("exact_flight_and_date_required_together")
    if operating_date is not None:
        try:
            requested_date = date.fromisoformat(operating_date)
        except ValueError as exc:
            raise TripBoardError("invalid_operating_date") from exc
        if requested_date.isoformat() != operating_date:
            raise TripBoardError("invalid_operating_date")
        if requested_date != current_date:
            raise TripBoardError("trip_operating_date_mismatch")
    if exact_flight is not None and not exact_flight.strip():
        raise TripBoardError("invalid_flight_number")

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

    if exact_flight is not None:
        selected_rows = [
            row for row in raw_rows if _clean(row.get("flightNo")) == exact_flight
        ]
        if not selected_rows:
            raise TripBoardError("flight_not_found", exact_flight)
    else:
        selected_rows = list(raw_rows)

    i18n = data.get("i18n") if isinstance(data.get("i18n"), dict) else {}
    rows = [_row_for_direction(row, direction, i18n) for row in selected_rows]
    if exact_flight is not None:
        for result_row, source_row in zip(rows, selected_rows):
            result_row["scheduled"] = {
                "departure": _clean(source_row.get("plannedDepartTime")),
                "arrival": _clean(source_row.get("plannedArrivalTime")),
            }
            result_row["current"] = {
                "departure": _clean(source_row.get("finalDepartTime")),
                "arrival": _clean(source_row.get("finalArrivalTime")),
            }

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
    route_header = "Origin" if result.get("direction") == "arrivals" else "Destination"

    lines = [
        f"{airport} — {direction} — {date_value}",
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


def fetch_specific_flight_page(flight_number: str, *, timeout: int = 30) -> str:
    url = f"https://www.trip.com/flights/status-{flight_number}/"
    try:
        from curl_cffi import requests
    except ModuleNotFoundError as exc:
        raise TripBoardError("missing_dependency", "curl_cffi") from exc

    try:
        response = requests.get(url, impersonate="chrome", timeout=timeout)
    except Exception as exc:
        raise TripBoardError("trip_network_error", type(exc).__name__) from exc

    if response.status_code == 404:
        raise TripBoardError("flight_not_found", flight_number)
    if response.status_code != 200:
        raise TripBoardError("trip_http_error", str(response.status_code))
    return response.text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read the current Trip.com airport arrivals/departures board."
    )
    parser.add_argument(
        "airport",
        nargs="?",
        help="Three-letter airport IATA code for airport-board lookup, e.g. SVO",
    )
    parser.add_argument(
        "--direction",
        choices=("arrivals", "departures"),
        help="Board direction to return",
    )
    parser.add_argument("--flight", help="Return one exact flight number")
    parser.add_argument(
        "--date", help="Operating date for --flight, in YYYY-MM-DD format"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument(
        "--timeout", type=int, default=30, help="HTTP timeout in seconds"
    )
    return parser


def _previous_flight_date(
    main_date: str,
    main_departure: str | None,
    previous_arrival: str | None,
) -> str | None:
    if not main_departure or not previous_arrival:
        return None
    try:
        departure_time = datetime.strptime(main_departure, "%H:%M").time()
        arrival_time = datetime.strptime(previous_arrival, "%H:%M").time()
        operation_date = date.fromisoformat(main_date)
    except ValueError:
        return None
    if arrival_time > departure_time:
        operation_date -= timedelta(days=1)
    return operation_date.isoformat()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.flight is not None and args.date is not None:
            if not args.flight.strip():
                raise TripBoardError("invalid_flight_number")
            flight_number = args.flight.strip().upper()
            if re.fullmatch(r"[A-Z0-9]+", flight_number) is None:
                raise TripBoardError("invalid_flight_number")

            if args.airport is None and args.direction is None:
                try:
                    requested_date = date.fromisoformat(args.date)
                except ValueError as exc:
                    raise TripBoardError("invalid_operating_date") from exc
                if requested_date.isoformat() != args.date:
                    raise TripBoardError("invalid_operating_date")
                html = fetch_specific_flight_page(
                    flight_number, timeout=args.timeout
                )
                result = parse_specific_flight(
                    html,
                    flight_number=flight_number,
                    operating_date=args.date,
                )
                previous_flight = result.pop("_previous_flight", None)
                if previous_flight is not None:
                    result["previous_flight"] = previous_flight
                    main_departure = result["rows"][0].get("scheduled", {}).get(
                        "departure"
                    )
                    previous_date = _previous_flight_date(
                        result["date"],
                        main_departure,
                        previous_flight.get("scheduled", {}).get("arrival"),
                    )
                    if previous_date is not None:
                        try:
                            previous_html = fetch_specific_flight_page(
                                previous_flight["flight_number"], timeout=args.timeout
                            )
                            previous_result = parse_specific_flight(
                                previous_html,
                                flight_number=previous_flight["flight_number"],
                                operating_date=previous_date,
                                allow_incomplete=True,
                            )
                        except TripBoardError:
                            pass
                        else:
                            operation = previous_result["rows"][0]
                            operation["date"] = previous_result["date"]
                            if "scheduled" not in operation:
                                operation["scheduled"] = previous_flight.get("scheduled", {})
                            elif (
                                not operation["scheduled"].get("arrival")
                                and previous_flight.get("scheduled", {}).get("arrival")
                            ):
                                operation["scheduled"]["arrival"] = previous_flight[
                                    "scheduled"
                                ]["arrival"]
                            result["previous_flight"] = operation
            else:
                if args.airport is None or args.direction is None:
                    raise TripBoardError("airport_and_direction_required")
                airport = normalize_iata(args.airport)
                html = fetch_trip_page(airport, timeout=args.timeout)
                result = parse_trip_board(
                    html,
                    airport=airport,
                    direction=args.direction,
                    exact_flight=flight_number,
                    operating_date=args.date,
                )
        else:
            if args.flight is not None or args.date is not None:
                raise TripBoardError("exact_flight_and_date_required_together")
            if args.airport is None or args.direction is None:
                raise TripBoardError("airport_and_direction_required")
            airport = normalize_iata(args.airport)
            html = fetch_trip_page(airport, timeout=args.timeout)
            result = parse_trip_board(
                html,
                airport=airport,
                direction=args.direction,
            )
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
