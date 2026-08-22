from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from flights_cli.commands.diagnose import command_diagnose_plan
from flights_cli.pipeline.search_request import search_request_from_payload
from flights_cli.store import Store
from helpers import build_search_plan, future_departure_date


class UnifiedRoutePlanningTests(unittest.TestCase):
    def assert_diagnose_plan_matches_live_plan(self, request: dict) -> None:
        expected = build_search_plan(search_request_from_payload(request), Store())
        with tempfile.TemporaryDirectory() as tmp_dir:
            request_path = Path(tmp_dir) / "request.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            diagnostic = command_diagnose_plan(
                argparse.Namespace(request=str(request_path)), Store()
            )
        self.assertEqual(diagnostic["plan"], expected)

    def test_ru_domestic_one_way(self) -> None:
        depart = future_departure_date()
        self.assert_diagnose_plan_matches_live_plan(
            {
                "schema_version": "flight_search_request.v3",
                "origin": "SVX",
                "destination": "KUF",
                "depart_date": depart.isoformat(),
            }
        )

    def test_ru_touching_international_return_trip(self) -> None:
        depart = future_departure_date()
        self.assert_diagnose_plan_matches_live_plan(
            {
                "schema_version": "flight_search_request.v3",
                "origin": "SVX",
                "destination": "CDG",
                "depart_date": depart.isoformat(),
                "return_date": (depart + timedelta(days=7)).isoformat(),
            }
        )

    def test_global_non_ru(self) -> None:
        depart = future_departure_date()
        self.assert_diagnose_plan_matches_live_plan(
            {
                "schema_version": "flight_search_request.v3",
                "origin": "BER",
                "destination": "MAD",
                "depart_date": depart.isoformat(),
            }
        )

    def test_direct_only(self) -> None:
        depart = future_departure_date()
        self.assert_diagnose_plan_matches_live_plan(
            {
                "schema_version": "flight_search_request.v3",
                "origin": "SVX",
                "destination": "KUF",
                "depart_date": depart.isoformat(),
                "route_options": {"max_connections": 0, "tier2_max_connections": 0},
            }
        )

    def test_manual_hubs(self) -> None:
        depart = future_departure_date()
        self.assert_diagnose_plan_matches_live_plan(
            {
                "schema_version": "flight_search_request.v3",
                "origin": "SVX",
                "destination": "LON",
                "depart_date": depart.isoformat(),
                "route_options": {
                    "routing_strategy": "hub-list",
                    "hubs": ["IST", "DXB"],
                },
            }
        )

    def test_city_code_first(self) -> None:
        depart = future_departure_date()
        self.assert_diagnose_plan_matches_live_plan(
            {
                "schema_version": "flight_search_request.v3",
                "origin": "SVX",
                "destination": "MOW",
                "depart_date": depart.isoformat(),
            }
        )

    def test_date_window(self) -> None:
        depart = future_departure_date()
        self.assert_diagnose_plan_matches_live_plan(
            {
                "schema_version": "flight_search_request.v3",
                "origin": "SVX",
                "destination": "KUF",
                "depart_date": depart.isoformat(),
                "route_options": {
                    "max_connections": 0,
                    "tier2_max_connections": 0,
                    "date_window_end": (depart + timedelta(days=2)).isoformat(),
                },
            }
        )


if __name__ == "__main__":
    unittest.main()
