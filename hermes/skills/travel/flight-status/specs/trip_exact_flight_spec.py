#!/usr/bin/env python3
"""Executable specification for exact-flight lookup on the Trip.com airport board.

Required behavior
-----------------
Given an airport, direction, operating date, and exact flight number, the public
Trip.com CLI must return that operation when it is present in the source board
even if it falls outside the first 24 rows of the initial board slice.

The initial 24-row presentation limit is not evidence that the flight is absent.
The caller must not need browser automation to recover an operation that is
already available in the Trip.com board data.

Run from the skill root:

    python3 specs/trip_exact_flight_spec.py

Only the external Trip.com page fetch is replaced with fixed source data. The
CLI argument handling, board parsing, exact-flight selection, and JSON result
remain production behavior.
"""

from __future__ import annotations

import base64
import contextlib
from datetime import datetime, timedelta
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "trip_board.py"

TARGET_FLIGHT = "SU1405"
TARGET_TIME = "20:50"


def load_module():
    spec = importlib.util.spec_from_file_location("trip_board", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_board_fixture() -> tuple[str, str]:
    """Return a board where the requested flight is the 25th eligible row."""

    local_now = datetime.now().astimezone()
    operating_date = local_now.date().isoformat()
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)

    rows: list[dict[str, object]] = []
    for index in range(24):
        departure = local_midnight + timedelta(hours=12, minutes=index * 10)
        rows.append(
            {
                "flightNo": f"ZZ{index + 1000}",
                "airlineName": "Fixture Air",
                "departTerminal": "A",
                "flightState": 1,
                "arrivalCityName": f"Fixture City {index + 1}",
                "plannedDepartTime": departure.strftime("%H:%M"),
                "plannedDepartTimeStamp": int(departure.timestamp() * 1000),
            }
        )

    target_departure = local_midnight + timedelta(hours=20, minutes=50)
    rows.append(
        {
            "flightNo": TARGET_FLIGHT,
            "airlineName": "Aeroflot",
            "departTerminal": "A",
            "flightState": 1,
            "arrivalCityName": "Moscow",
            "plannedDepartTime": TARGET_TIME,
            "plannedDepartTimeStamp": int(target_departure.timestamp() * 1000),
        }
    )

    payload = {
        "moduleName": "statusList",
        "currentDate": operating_date,
        "data": {
            "airportCode": "SVX",
            "airportName": "Koltsovo",
            "dateOptions": ["Yesterday", "Today", "Tomorrow"],
            "defaultSelectedTime": "00:00",
            "timeOptionsWithMinutes": [{"label": "00:00", "minutes": 0}],
            "i18n": {"Scheduled": "Scheduled"},
            "originData": {"flightStatusByAirport": rows},
            "arrivalsData": {"flightStatusByAirport": []},
        },
    }
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    html = (
        "<html><script>"
        f"var tplB64='eA==';var pr='{encoded}';var w=window;"
        "</script></html>"
    )
    return html, operating_date


def run_cli(module, argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            code = module.main(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, stdout.getvalue(), stderr.getvalue()


class TripExactFlightSpecification(unittest.TestCase):
    def test_exact_flight_is_found_beyond_initial_24_row_slice(self) -> None:
        """Exact lookup must not turn the board presentation limit into not-found."""

        trip_board = load_module()
        html, operating_date = source_board_fixture()

        with mock.patch.object(
            trip_board,
            "fetch_trip_page",
            return_value=html,
        ):
            code, stdout, stderr = run_cli(
                trip_board,
                [
                    "SVX",
                    "--direction",
                    "departures",
                    "--flight",
                    TARGET_FLIGHT,
                    "--date",
                    operating_date,
                    "--json",
                ],
            )

        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(stderr, "")

        payload = json.loads(stdout)
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["airport"], "SVX")
        self.assertEqual(payload["direction"], "departures")
        self.assertEqual(payload["date"], operating_date)

        self.assertEqual(
            payload["rows"],
            [
                {
                    "time": TARGET_TIME,
                    "flight_number": TARGET_FLIGHT,
                    "route_point": "Moscow",
                    "airline": "Aeroflot",
                    "terminal": "A",
                    "status": "Scheduled",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
