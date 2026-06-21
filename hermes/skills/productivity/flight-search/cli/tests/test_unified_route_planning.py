from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from flights_cli.apps.diagnose import command_diagnose_plan
from flights_cli.apps.search import live_assembly_options_from_search_request, normalize_search_request
from flights_cli.orchestrators.live_assemble import build_live_route_segment_plan
from flights_cli.store import Store


def segment_signature(plan: dict) -> list[tuple[str, str, str, str, str, str]]:
    return [
        (
            str(segment.get("direction")),
            str(segment.get("leg")),
            str(segment.get("origin")),
            str(segment.get("destination")),
            str(segment.get("date")),
            str(segment.get("route_family")),
        )
        for segment in plan.get("segments") or []
    ]


class UnifiedRoutePlanningTests(unittest.TestCase):
    def assert_diagnose_plan_matches_live_plan(self, request: dict) -> None:
        normalized = normalize_search_request(request)
        expected = build_live_route_segment_plan(live_assembly_options_from_search_request(normalized), Store())
        with tempfile.TemporaryDirectory() as tmp_dir:
            request_path = Path(tmp_dir) / "request.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            actual = command_diagnose_plan(argparse.Namespace(request=str(request_path)), Store())["plan"]

        self.assertEqual(actual["routing_strategy"], expected["routing_strategy"])
        self.assertEqual(actual["routing_profile"], expected["routing_profile"])
        self.assertEqual(actual["hubs"], expected["hubs"])
        self.assertEqual(actual["metrics"], expected["metrics"])
        self.assertEqual(segment_signature(actual), segment_signature(expected))

    def test_ru_domestic_one_way(self) -> None:
        self.assert_diagnose_plan_matches_live_plan(
            {
                "schema_version": "flight_search_request.v1",
                "origin": "SVX",
                "destination": "KUF",
                "depart_date": "2026-08-15",
            }
        )

    def test_ru_touching_international_return_trip(self) -> None:
        self.assert_diagnose_plan_matches_live_plan(
            {
                "schema_version": "flight_search_request.v1",
                "origin": "SVX",
                "destination": "CDG",
                "depart_date": "2026-08-15",
                "return_date": "2026-08-22",
            }
        )

    def test_global_non_ru(self) -> None:
        self.assert_diagnose_plan_matches_live_plan(
            {
                "schema_version": "flight_search_request.v1",
                "origin": "BER",
                "destination": "MAD",
                "depart_date": "2026-08-15",
            }
        )

    def test_direct_only(self) -> None:
        self.assert_diagnose_plan_matches_live_plan(
            {
                "schema_version": "flight_search_request.v1",
                "origin": "SVX",
                "destination": "KUF",
                "depart_date": "2026-08-15",
                "route_options": {"max_connections": 0, "tier2_max_connections": 0},
            }
        )

    def test_manual_hubs(self) -> None:
        self.assert_diagnose_plan_matches_live_plan(
            {
                "schema_version": "flight_search_request.v1",
                "origin": "SVX",
                "destination": "LON",
                "depart_date": "2026-08-15",
                "route_options": {"routing_strategy": "hub-list", "hubs": ["IST", "DXB"]},
            }
        )

    def test_city_code_first(self) -> None:
        self.assert_diagnose_plan_matches_live_plan(
            {
                "schema_version": "flight_search_request.v1",
                "origin": "SVX",
                "destination": "MOW",
                "depart_date": "2026-08-15",
            }
        )

    def test_date_window(self) -> None:
        self.assert_diagnose_plan_matches_live_plan(
            {
                "schema_version": "flight_search_request.v1",
                "origin": "SVX",
                "destination": "KUF",
                "depart_date": "2026-08-15",
                "route_options": {
                    "max_connections": 0,
                    "tier2_max_connections": 0,
                    "date_window_end": "2026-08-17",
                },
            }
        )


if __name__ == "__main__":
    unittest.main()
