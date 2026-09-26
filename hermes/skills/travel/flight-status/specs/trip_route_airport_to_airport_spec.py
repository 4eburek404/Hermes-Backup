#!/usr/bin/env python3
"""Executable specification for full-day airport-to-airport route lookup.

Required behavior
-----------------
Given an origin airport and an exact destination airport, the public Trip.com
CLI must return every matching direct departure for the source board's current
day.

This is route lookup, not the normal current airport-board slice:

- all matching rows for the day are returned;
- only the exact requested arrival airport is included;
- matching flights are ordered by scheduled departure time.

Public CLI contract:

    python3 scripts/trip_board.py SVX --destination SVO --json

The origin stays the existing positional airport argument. A route query is
therefore a minimal extension of the existing airport-board interface rather
than a second --origin input.

The controlled fixture below is composed from the checked-in real SVX Trip.com
payload shape. Only the external HTTP fetch is replaced. CLI argument handling,
payload extraction, route selection, ordering, mapping, and JSON output remain
production behavior.

Run from the skill root:

    python3 specs/trip_route_airport_to_airport_spec.py
"""

from __future__ import annotations

import base64
import contextlib
from datetime import datetime, timedelta
import importlib.util
import io
import json
from pathlib import Path
import re
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "trip_board.py"
BASE_FIXTURE = (
    ROOT
    / "specs"
    / "fixtures"
    / "trip"
    / "trip_com_svx_2026-09-25.html"
)

ORIGIN = "SVX"
DESTINATION = "SVO"
EARLY_TARGET = "ZZ9001"


def load_module():
    spec = importlib.util.spec_from_file_location("trip_board", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _decode_payload(html: str) -> dict:
    match = re.search(
        r"var\s+pr\s*=\s*'([^']+)'\s*;\s*var\s+w\s*=\s*window",
        html,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError("Trip.com statusList payload not found in fixture")
    return json.loads(base64.b64decode(match.group(1), validate=True))


def _encode_payload(payload: dict) -> str:
    encoded = base64.b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return (
        "<html><script>"
        f"var tplB64='eA==';var pr='{encoded}';var w=window;"
        "</script></html>"
    )


def _timestamp_ms(operating_date: str, clock: str) -> int:
    return int(
        datetime.fromisoformat(
            f"{operating_date}T{clock}:00+05:00"
        ).timestamp()
        * 1000
    )


def route_fixture() -> tuple[str, str, dict]:
    """Compose route-selection evidence on the real saved Trip.com payload shape."""

    payload = _decode_payload(BASE_FIXTURE.read_text(encoding="utf-8"))
    operating_date = payload["currentDate"]
    data = payload["data"]
    real_rows = list(data["originData"]["flightStatusByAirport"])

    # Include exact-airport and different-city non-matches so route filtering is
    # proved independently of the source row order.
    filler_rows = []
    for flight_no, destination, city_code, city_name, clock in (
        ("FX1000", "DME", "MOW", "Moscow", "16:20"),
        ("FX1001", "LED", "LED", "Saint Petersburg", "16:30"),
    ):
        departure = datetime.fromisoformat(
            f"{operating_date}T{clock}:00+05:00"
        )
        filler_rows.append(
            {
                "flightNo": flight_no,
                "airlineCode": "FX",
                "airlineName": "Fixture Air",
                "departTerminal": "A",
                "arrivalTerminal": "A",
                "flightState": 1,
                "arrivalCityCode": city_code,
                "arrivalCityName": city_name,
                "departAirportCode": ORIGIN,
                "arrivalAirportCode": destination,
                "plannedDepartTime": departure.strftime("%H:%M"),
                "plannedArrivalTime": (
                    departure + timedelta(hours=2)
                ).strftime("%H:%M"),
                "plannedDepartTimeStamp": int(departure.timestamp() * 1000),
                "plannedArrivalTimeStamp": int(
                    (departure + timedelta(hours=2)).timestamp() * 1000
                ),
            }
        )

    early_target = {
        "flightNo": EARLY_TARGET,
        "airlineCode": "ZZ",
        "airlineName": "Fixture Air",
        "departTerminal": "A",
        "arrivalTerminal": "B",
        "flightState": 6,
        "arrivalCityCode": "MOW",
        "arrivalCityName": "Moscow",
        "departAirportCode": ORIGIN,
        "arrivalAirportCode": DESTINATION,
        "plannedDepartTime": "06:00",
        "plannedArrivalTime": "06:45",
        "plannedDepartTimeStamp": _timestamp_ms(operating_date, "06:00"),
        "plannedArrivalTimeStamp": _timestamp_ms(operating_date, "06:45"),
    }

    # Deliberately keep raw source order unsuitable for the required route
    # presentation: non-matches first, then the early completed target, then the
    # two real saved SVX -> SVO rows (18:50 and 20:50).
    rows = filler_rows + [early_target] + real_rows
    data["originData"]["flightStatusByAirport"] = rows

    return _encode_payload(payload), operating_date, payload


def run_cli(module, argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            code = module.main(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, stdout.getvalue(), stderr.getvalue()


class TripAirportRouteSpecification(unittest.TestCase):
    def test_fixture_proves_full_day_route_preconditions(self) -> None:
        """The controlled source data actually exercises cutoff and row-limit risks."""

        _, operating_date, payload = route_fixture()
        data = payload["data"]
        rows = data["originData"]["flightStatusByAirport"]

        self.assertEqual(operating_date, "2026-09-25")
        self.assertEqual(data["airportCode"], ORIGIN)
        target_rows = [
            row
            for row in rows
            if row.get("departAirportCode") == ORIGIN
            and row.get("arrivalAirportCode") == DESTINATION
        ]
        self.assertEqual(len(target_rows), 3)

        early = next(row for row in rows if row.get("flightNo") == EARLY_TARGET)
        self.assertEqual(early["flightState"], 6)

        self.assertTrue(
            any(row.get("arrivalAirportCode") == "DME" for row in rows)
        )
        self.assertTrue(
            any(
                row.get("arrivalAirportCode") == "LED"
                and row.get("arrivalCityCode") == "LED"
                for row in rows
            )
        )

    def test_public_cli_returns_all_exact_airport_route_flights_for_the_day(
        self,
    ) -> None:
        """SVX --destination SVO returns the full exact-airport route, in time order."""

        trip_board = load_module()
        html, operating_date, _ = route_fixture()

        with mock.patch.object(
            trip_board,
            "fetch_trip_page",
            return_value=html,
        ):
            code, stdout, stderr = run_cli(
                trip_board,
                [ORIGIN, "--destination", DESTINATION, "--json"],
            )

        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(stderr, "")

        result = json.loads(stdout)
        self.assertIs(result["ok"], True)
        self.assertEqual(result["airport"], ORIGIN)
        self.assertEqual(result["direction"], "departures")
        self.assertEqual(result["date"], operating_date)
        self.assertEqual(result["destination"], DESTINATION)

        rows = result["rows"]
        self.assertEqual(
            [row["flight_number"] for row in rows],
            [EARLY_TARGET, "SU1437", "SU1405"],
        )

        expected = {
            EARLY_TARGET: {
                "airline": "Fixture Air",
                "scheduled": {"departure": "06:00", "arrival": "06:45"},
                "status": "Arrived",
            },
            "SU1437": {
                "airline": "Aeroflot",
                "scheduled": {"departure": "18:50", "arrival": "19:30"},
                "status": "Delayed until 22:50",
            },
            "SU1405": {
                "airline": "Aeroflot",
                "scheduled": {"departure": "20:50", "arrival": "21:35"},
                "status": "Scheduled",
            },
        }

        for row in rows:
            self.assertEqual(row["departure_airport"], ORIGIN)
            self.assertEqual(row["arrival_airport"], DESTINATION)
            contract = expected[row["flight_number"]]
            self.assertEqual(row["airline"], contract["airline"])
            self.assertEqual(row["scheduled"], contract["scheduled"])
            self.assertEqual(row["status"], contract["status"])

        self.assertNotIn("DME", {row["arrival_airport"] for row in rows})
        self.assertNotIn("LED", {row["arrival_airport"] for row in rows})


if __name__ == "__main__":
    unittest.main(verbosity=2)
