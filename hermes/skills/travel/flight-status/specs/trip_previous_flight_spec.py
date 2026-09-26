#!/usr/bin/env python3
"""Executable public-CLI specification for Trip.com Previous Flight data.

Run from the skill root:
    python3 specs/trip_previous_flight_spec.py

Only Trip.com HTTP responses are replaced by saved Russian SU fixtures. The
public CLI, operation selection, normalization, and combined result are real.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import re
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "trip_board.py"
FIXTURES = ROOT / "specs" / "fixtures" / "trip"
MAIN_FIXTURE = FIXTURES / "trip_com_su1524_2026-09-26_previous_flight.html"
PREVIOUS_FIXTURE = FIXTURES / "trip_com_su1857_2026-09-25_enroute.html"
NO_PREVIOUS_FIXTURE = FIXTURES / "trip_com_su1401_2026-09-25_arrived.html"
STALE_PREINFO_CHILD_FIXTURE = FIXTURES / "trip_com_su1094_2026-09-25_arrived_fragment.html"


def load_cli():
    spec = importlib.util.spec_from_file_location("trip_board", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_cli(module, flight_number: str, operating_date: str, responses):
    stdout, stderr = io.StringIO(), io.StringIO()
    requested_flights: list[str] = []

    def fetch(flight: str, *, timeout: int = 30) -> str:
        requested_flights.append(flight)
        response = responses.get(flight)
        if isinstance(response, Exception):
            raise response
        if response is None:
            raise AssertionError(f"Unexpected flight lookup: {flight}")
        return response

    with (
        mock.patch.object(module, "fetch_specific_flight_page", side_effect=fetch),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        try:
            code = module.main(
                ["--flight", flight_number, "--date", operating_date, "--json"]
            )
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, stdout.getvalue(), stderr.getvalue(), requested_flights


class TripPreviousFlightSpecification(unittest.TestCase):
    def test_cli_returns_main_and_previous_flight_operational_data(self) -> None:
        cli = load_cli()
        code, stdout, stderr, _ = run_cli(
            cli,
            "SU1524",
            "2026-09-26",
            {
                "SU1524": MAIN_FIXTURE.read_text(encoding="utf-8"),
                "SU1857": PREVIOUS_FIXTURE.read_text(encoding="utf-8"),
            },
        )
        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(stderr, "")
        result = json.loads(stdout)
        self.assertIs(result["ok"], True)
        self.assertEqual(result["date"], "2026-09-26")
        self.assertEqual(result["rows"][0]["flight_number"], "SU1524")
        self.assertEqual(
            result["previous_flight"],
            {
                "flight_number": "SU1857",
                "date": "2026-09-25",
                "departure_airport": "GYD",
                "arrival_airport": "SVO",
                "status": "En route",
                "scheduled": {"departure": "19:50", "arrival": "22:30"},
                "current": {"departure": "20:20", "arrival": "22:25"},
            },
        )

    def test_incomplete_previous_page_keeps_scheduled_values_without_eta(self) -> None:
        cli = load_cli()
        own_page = PREVIOUS_FIXTURE.read_text(encoding="utf-8")
        for key in ("status_info_status", "status_info_dep_time", "status_info_arr_time"):
            own_page = re.sub(
                rf'(<[^>]*test-item="{key}"[^>]*>).*?(</[^>]+>)',
                r"\1\2",
                own_page,
                flags=re.DOTALL,
            )
        code, stdout, stderr, _ = run_cli(
            cli,
            "SU1524",
            "2026-09-26",
            {
                "SU1524": MAIN_FIXTURE.read_text(encoding="utf-8"),
                "SU1857": own_page,
            },
        )
        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(stderr, "")
        previous = json.loads(stdout)["previous_flight"]
        self.assertEqual(previous["flight_number"], "SU1857")
        self.assertEqual(previous["departure_airport"], "GYD")
        self.assertEqual(previous["arrival_airport"], "SVO")
        self.assertEqual(previous["scheduled"], {"departure": "19:50", "arrival": "22:30"})
        for unsupported in ("status", "current", "actual"):
            self.assertNotIn(unsupported, previous)

    def test_cli_preserves_result_when_no_previous_flight_is_present(self) -> None:
        cli = load_cli()
        code, stdout, stderr, requested = run_cli(
            cli,
            "SU1401",
            "2026-09-25",
            {"SU1401": NO_PREVIOUS_FIXTURE.read_text(encoding="utf-8")},
        )
        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(stderr, "")
        result = json.loads(stdout)
        self.assertNotIn("previous_flight", result)
        self.assertEqual(requested, ["SU1401"])
        self.assertEqual(
            result["rows"][0],
            {
                "flight_number": "SU1401",
                "departure_airport": "SVX",
                "arrival_airport": "SVO",
                "status": "Arrived",
                "scheduled": {"departure": "13:10", "arrival": "13:50"},
                "actual": {"departure": "13:58", "arrival": "14:06"},
            },
        )

    def test_child_page_status_wins_when_parent_preinfo_is_stale(self) -> None:
        """Child operational data is authoritative over stale parent preInfo."""
        cli = load_cli()
        child_html = STALE_PREINFO_CHILD_FIXTURE.read_text(encoding="utf-8")
        real_parse = cli.parse_specific_flight

        # Captured Trip.com evidence for 2026-09-25:
        # SU1095 preInfo identified SU1094 as Scheduled with scheduled arrival
        # 13:55, while SU1094's own page reported Arrived with actual arrival
        # 13:31. Only the fields needed for this precedence contract are kept.
        parent_result = {
            "ok": True,
            "date": "2026-09-25",
            "rows": [
                {
                    "flight_number": "SU1095",
                    "scheduled": {"departure": "14:55"},
                }
            ],
            "_previous_flight": {
                "flight_number": "SU1094",
                "status": "Scheduled",
                "departure_city": "Moscow (MOW)",
                "arrival_city": "Chelyabinsk (CEK)",
                "scheduled": {"arrival": "13:55"},
            },
        }

        def parse(html, *, flight_number, operating_date, allow_incomplete=False):
            if flight_number == "SU1095":
                self.assertEqual(html, "PARENT_SU1095")
                self.assertEqual(operating_date, "2026-09-25")
                self.assertIs(allow_incomplete, False)
                return parent_result
            return real_parse(
                html,
                flight_number=flight_number,
                operating_date=operating_date,
                allow_incomplete=allow_incomplete,
            )

        with mock.patch.object(cli, "parse_specific_flight", side_effect=parse):
            code, stdout, stderr, requested = run_cli(
                cli,
                "SU1095",
                "2026-09-25",
                {
                    "SU1095": "PARENT_SU1095",
                    "SU1094": child_html,
                },
            )

        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(stderr, "")
        self.assertEqual(requested, ["SU1095", "SU1094"])
        previous = json.loads(stdout)["previous_flight"]
        self.assertEqual(
            previous,
            {
                "flight_number": "SU1094",
                "date": "2026-09-25",
                "departure_airport": "SVO",
                "arrival_airport": "CEK",
                "status": "Arrived",
                "scheduled": {"arrival": "13:55"},
                "actual": {"arrival": "13:31"},
            },
        )

    def test_unavailable_previous_page_keeps_only_confirmed_preinfo(self) -> None:
        cli = load_cli()
        code, stdout, stderr, _ = run_cli(
            cli,
            "SU1524",
            "2026-09-26",
            {
                "SU1524": MAIN_FIXTURE.read_text(encoding="utf-8"),
                "SU1857": cli.TripBoardError("trip_network_error"),
            },
        )
        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(stderr, "")
        result = json.loads(stdout)
        self.assertIs(result["ok"], True)
        previous = result["previous_flight"]
        self.assertEqual(previous["flight_number"], "SU1857")
        self.assertEqual(previous["scheduled"], {"arrival": "22:30"})
        for unsupported in ("status", "current", "actual"):
            self.assertNotIn(unsupported, previous)


if __name__ == "__main__":
    unittest.main(verbosity=2)
