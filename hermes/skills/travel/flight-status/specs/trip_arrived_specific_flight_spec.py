#!/usr/bin/env python3
"""Executable CLI specification for one completed specific flight.

Required behavior
-----------------
Given Trip.com's saved real response for SU1401 on 2026-09-25, requesting that
specific operation through the public CLI returns its normalized identity,
status, scheduled times, and actual times in JSON. The actual-time requirement
here applies only to this evidence-backed Arrived operation.

Only the external HTTP request is replaced with the checked-in response. The
public CLI entry point and its JSON output remain real production behavior.

Run from the skill root:

    python3 specs/trip_arrived_specific_flight_spec.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from curl_cffi import requests


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "trip_board.py"
FIXTURE = (
    ROOT
    / "specs"
    / "fixtures"
    / "trip"
    / "trip_com_su1401_2026-09-25_arrived.html"
)
OPERATING_DATE = "2026-09-25"
EXPECTED_SOURCE_URL = "https://www.trip.com/flights/status-SU1401/"


def load_cli():
    spec = importlib.util.spec_from_file_location("trip_board", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TripArrivedSpecificFlightSpecification(unittest.TestCase):
    def test_cli_returns_normalized_arrived_operation_as_json(self) -> None:
        """A specific-flight lookup needs only its number and operating date."""
        trip_board = load_cli()
        response = SimpleNamespace(
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=FIXTURE.read_text(encoding="utf-8"),
        )
        not_found = SimpleNamespace(
            status_code=404,
            headers={"content-type": "text/html; charset=utf-8"},
            text="Unexpected Trip.com source URL",
        )
        requested_urls: list[str | None] = []

        def get_specific_flight_page(*args, **kwargs):
            url = args[0] if args else kwargs.get("url")
            requested_urls.append(url)
            return response if url == EXPECTED_SOURCE_URL else not_found

        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            mock.patch.object(requests, "get", side_effect=get_specific_flight_page),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            try:
                code = trip_board.main(
                    ["--flight", "SU1401", "--date", OPERATING_DATE, "--json"]
                )
            except SystemExit as exc:
                code = int(exc.code or 0)

        self.assertEqual(
            requested_urls,
            [EXPECTED_SOURCE_URL],
            "Specific-flight lookup must request only its expected source URL; "
            f"observed URLs={requested_urls!r}, CLI exit={code}, "
            f"stdout={stdout.getvalue()!r}, stderr={stderr.getvalue()!r}",
        )
        self.assertEqual(code, 0, stdout.getvalue() + stderr.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(stdout.getvalue())
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["date"], OPERATING_DATE)
        self.assertEqual(len(payload["rows"]), 1)

        operation = payload["rows"][0]
        self.assertEqual(
            operation,
            {
                "flight_number": "SU1401",
                "departure_airport": "SVX",
                "arrival_airport": "SVO",
                "status": "Arrived",
                "scheduled": {"departure": "13:10", "arrival": "13:50"},
                "actual": {"departure": "13:58", "arrival": "14:06"},
            },
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
