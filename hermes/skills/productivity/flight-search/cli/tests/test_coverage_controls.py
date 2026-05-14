from __future__ import annotations

import argparse
import unittest

from flights_cli.cli import build_parser
from flights_cli.orchestrators.kb_assemble import build_kupibilet_route_segment_plan
from flights_cli.orchestrators.route_plan import build_route_plan
from flights_cli.store import Store


def route_args(**overrides: object) -> argparse.Namespace:
    values = {
        "origin": "SVX",
        "destination": "MUC",
        "depart_date": "2026-08-12",
        "return_date": "2026-08-19",
        "hub": None,
        "routing_strategy": "auto",
        "origin_airport": None,
        "destination_airport": None,
        "currency": "RUB",
        "direct_only": False,
        "ticketing": "separate",
        "profile": "business",
        "min_same_airport_min": 120,
        "min_cross_airport_min": 300,
        "max_airports_per_city": 6,
        "coverage_mode": "targeted",
        "coverage_control": None,
        "coverage_control_limit": 12,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def live_args(**overrides: object) -> argparse.Namespace:
    values = vars(route_args()).copy()
    values.update(
        {
            "outbound_second_leg_day_offset": None,
            "return_second_leg_day_offset": None,
            "segment_limit": 30,
            "timeout": 60,
            "limit_per_pair": 10,
            "candidate_pool_limit": 5000,
            "max_candidates": 50,
            "max_reasons": 5,
            "include_candidates": 5,
            "include_ranked_candidates": 5,
            "include_rejected_pairs": 20,
            "include_segment_results": 0,
            "aggregate_control_limit": 0,
            "aggregate_control_carrier": None,
            "max_segment_searches": 300,
            "fail_fast": False,
            "live_cache_ttl_seconds": 0,
            "no_live_cache": True,
            "direct_route_index_ttl_seconds": 0,
            "no_direct_route_intel": True,
            "agent_report": False,
            "agent_mode": False,
            "agent_brief": False,
        }
    )
    values.update(overrides)
    return argparse.Namespace(**values)


class CoverageControlsTests(unittest.TestCase):
    def test_dubai_city_scope_is_dxb_primary_dwc_secondary_without_shj(self) -> None:
        result = build_route_plan(route_args(destination="Dubai", return_date=None), Store())

        self.assertEqual(result["destination_airports"], ["DXB", "DWC"])
        self.assertNotIn("SHJ", result["destination_airports"])
        self.assertEqual(result["airport_scope"]["destination"]["scope"], "dubai_default")
        self.assertEqual(result["airport_scope"]["destination"]["excluded_by_default"], ["SHJ"])
        self.assertIn("DWC", result["route_graph"]["nodes"])

    def test_explicit_dxb_stays_exact_airport_not_city_scope(self) -> None:
        result = build_route_plan(route_args(destination="DXB", return_date=None), Store())

        self.assertEqual(result["destination_airports"], ["DXB"])
        self.assertEqual(result["airport_scope"]["destination"]["scope"], "explicit_or_single_airport")

    def test_auto_routing_uses_domestic_ru_strategy_without_international_hubs(self) -> None:
        result = build_route_plan(route_args(destination="KUF"), Store())

        self.assertEqual(result["routing_strategy"], "domestic-ru")
        self.assertEqual(result["hub_source"], "domestic-ru")
        self.assertTrue(set(result["hubs"]).issubset({"SVO", "DME", "VKO"}))
        self.assertFalse({"IST", "DXB", "SHJ"} & set(result["hubs"]))
        segment_airports = {segment["origin"] for segment in result["segments"]} | {segment["destination"] for segment in result["segments"]}
        self.assertFalse({"IST", "DXB", "SHJ"} & segment_airports)
        self.assertIn("domestic_ru", {family["id"] for family in result["route_families"]})

    def test_domestic_ru_round_trip_route_plan_aligns_return_segments_and_controls(self) -> None:
        result = build_route_plan(route_args(destination="KUF", return_date="2026-08-19"), Store())

        return_segments = [segment for segment in result["segments"] if segment["direction"] == "return"]
        direct_return_segments = [segment for segment in return_segments if segment["leg"] == "direct_return"]
        self.assertTrue(direct_return_segments)
        self.assertTrue(all(segment.get("route_family") == "domestic_ru" for segment in return_segments))
        self.assertIn(
            ("KUF", "SVX"),
            {(segment["origin"], segment["destination"]) for segment in direct_return_segments},
        )
        self.assertIn(
            ("KUF", "SVX"),
            {
                (edge["origin"], edge["destination"])
                for edge in result["route_graph"]["edges"]
                if edge["direction"] == "return" and edge["leg"] == "direct_return"
            },
        )
        self.assertIn(
            ("return", "KUF", "SVX"),
            {
                (control["direction"], control["origin"], control["destination"])
                for control in result["coverage_controls"]
                if control["type"] == "exact_airport_direct"
            },
        )

    def test_route_plan_exposes_route_graph_and_targeted_coverage_controls(self) -> None:
        result = build_route_plan(route_args(destination="CDG", return_date="2026-08-19"), Store())

        self.assertEqual(result["coverage_mode"], "targeted")
        self.assertIn("route_graph", result)
        self.assertGreaterEqual(len(result["route_graph"]["edges"]), len(result["segments"]))
        controls = {control["type"] for control in result["coverage_controls"]}
        self.assertIn("exact_airport_direct", controls)
        self.assertIn("full_route_aggregate", controls)
        self.assertIn("carrier_aggregate", controls)
        self.assertEqual(result["coverage_limits"]["live_fanout"], "bounded_by_max_segment_searches")

    def test_live_plan_uses_same_route_graph_contract_as_route_plan(self) -> None:
        result = build_kupibilet_route_segment_plan(live_args(destination="CDG", return_date="2026-08-19"), Store())

        self.assertEqual(result["coverage_mode"], "targeted")
        self.assertIn("route_graph", result)
        self.assertEqual(result["route_graph"]["strategy"], result["routing_strategy"])
        self.assertGreaterEqual(len(result["route_graph"]["edges"]), len(result["segments"]))
        self.assertIn("coverage_controls", result)
    def test_parser_accepts_documented_coverage_control_flags_and_reports_limit(self) -> None:
        args = build_parser().parse_args(
            [
                "route",
                "plan",
                "SVX",
                "CDG",
                "--depart-date",
                "2026-08-16",
                "--return-date",
                "2026-08-19",
                "--coverage-mode",
                "targeted",
                "--coverage-control",
                "carrier_aggregate:SU",
                "--coverage-control-limit",
                "4",
            ]
        )

        result = build_route_plan(args, Store())

        self.assertEqual(args.coverage_control, ["carrier_aggregate:SU"])
        self.assertEqual(result["coverage_limits"]["coverage_control_limit"], 4)
        self.assertEqual(result["coverage_limits"]["requested_controls"], ["carrier_aggregate:SU"])
        self.assertLessEqual(len(result["coverage_controls"]), 4)
        self.assertIn("carrier_aggregate", {control["type"] for control in result["coverage_controls"]})


if __name__ == "__main__":
    unittest.main()
