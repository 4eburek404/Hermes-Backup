#!/usr/bin/env python3
"""Executable specification for Trip.com scheduled/current flight times.

Scope
-----
For exact-flight lookup, the CLI must preserve the two time views that Trip.com
shows to the user:

- scheduled: the published schedule from the source's planned fields;
- current: the source's currently displayed time from its final fields.

"Current" is deliberately neutral. This contract does not reinterpret Trip.com's
final fields as actual, estimated, or revised times.

The checked-in fixture is a sanitized capture of the live SVX Trip.com /
VariFlight board for 2026-09-25 and contains two contrasting operations:

- SU1405: source status Scheduled;
- SU1437: source status Delayed.

Run from the skill root:

    python3 specs/trip_time_semantics_spec.py

Only the external page fetch is replaced with the checked-in fixture. CLI
argument handling, Trip.com payload extraction, exact-flight lookup, mapping,
and JSON output remain production behavior.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "trip_board.py"
FIXTURE = (
    ROOT
    / "specs"
    / "fixtures"
    / "trip"
    / "trip_com_svx_2026-09-25.html"
)
OPERATING_DATE = "2026-09-25"


def load_module():
    spec = importlib.util.spec_from_file_location("trip_board", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_exact_flight(module, flight_number: str) -> tuple[int, dict, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()

    with (
        mock.patch.object(
            module,
            "fetch_trip_page",
            return_value=FIXTURE.read_text(encoding="utf-8"),
        ),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        code = module.main(
            [
                "SVX",
                "--direction",
                "departures",
                "--flight",
                flight_number,
                "--date",
                OPERATING_DATE,
                "--json",
            ]
        )

    payload = json.loads(stdout.getvalue())
    return code, payload, stderr.getvalue()


class TripTimeSemanticsSpecification(unittest.TestCase):
    """Behavior required from exact-flight Trip.com JSON output."""

    def assert_exact_time_contract(
        self,
        row: dict,
        *,
        flight_number: str,
        scheduled_departure: str,
        scheduled_arrival: str,
        current_departure: str,
        current_arrival: str,
    ) -> None:
        self.assertEqual(row["flight_number"], flight_number)
        self.assertEqual(
            row["scheduled"],
            {
                "departure": scheduled_departure,
                "arrival": scheduled_arrival,
            },
        )
        self.assertEqual(
            row["current"],
            {
                "departure": current_departure,
                "arrival": current_arrival,
            },
        )

        # The source does not identify its "final" values as actual,
        # estimated, or revised. The CLI must not invent that semantics.
        for unsupported_semantics in ("actual", "estimated", "revised"):
            self.assertNotIn(unsupported_semantics, row)

    def test_scheduled_flight_preserves_scheduled_and_current_times_separately(
        self,
    ) -> None:
        """A Scheduled state does not erase a source-reported current arrival."""

        trip_board = load_module()
        code, payload, stderr = run_exact_flight(trip_board, "SU1405")

        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, "")
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["airport"], "SVX")
        self.assertEqual(payload["direction"], "departures")
        self.assertEqual(payload["date"], OPERATING_DATE)
        self.assertEqual(len(payload["rows"]), 1)

        row = payload["rows"][0]
        self.assert_exact_time_contract(
            row,
            flight_number="SU1405",
            scheduled_departure="20:50",
            scheduled_arrival="21:35",
            current_departure="20:50",
            current_arrival="21:10",
        )
        self.assertEqual(row["status"], "Scheduled")

    def test_delayed_flight_preserves_changed_current_times_separately(self) -> None:
        """A Delayed state exposes both original schedule and current times."""

        trip_board = load_module()
        code, payload, stderr = run_exact_flight(trip_board, "SU1437")

        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, "")
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["airport"], "SVX")
        self.assertEqual(payload["direction"], "departures")
        self.assertEqual(payload["date"], OPERATING_DATE)
        self.assertEqual(len(payload["rows"]), 1)

        row = payload["rows"][0]
        self.assert_exact_time_contract(
            row,
            flight_number="SU1437",
            scheduled_departure="18:50",
            scheduled_arrival="19:30",
            current_departure="22:50",
            current_arrival="23:06",
        )
        self.assertEqual(row["status"], "Delayed until 22:50")


if __name__ == "__main__":
    unittest.main(verbosity=2)
