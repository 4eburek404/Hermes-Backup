from __future__ import annotations

from collections import Counter
import unittest
from typing import Any

from flights_cli.orchestrators.live_route_assembly import build_live_route_segment_plan
from flights_cli.store import Store
from helpers import live_assembly_args


REQUIRED_SEGMENT_FIELDS = {"direction", "leg", "origin", "destination", "date", "route_family"}


def value(item: Any) -> str:
    return str(getattr(item, "value", item))


def segment_key(segment: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        value(segment.get("direction")),
        value(segment.get("leg")),
        value(segment.get("origin")).upper(),
        value(segment.get("destination")).upper(),
        value(segment.get("date")),
        value(segment.get("route_family")),
    )


def route_family_ids(plan: dict[str, Any]) -> set[str]:
    return {value(family.get("id")) for family in plan.get("route_families") or []}


def segment_family_ids(plan: dict[str, Any]) -> set[str]:
    return {value(segment.get("route_family")) for segment in plan.get("segments") or []}


def coverage_control_types(plan: dict[str, Any]) -> set[str]:
    return {value(control.get("type")) for control in plan.get("coverage_controls") or []}


class RoutePlanContractTests(unittest.TestCase):
    def build_plan(self, **overrides: Any) -> dict[str, Any]:
        return build_live_route_segment_plan(live_assembly_args(**overrides), Store())

    def assert_valid_route_plan(self, plan: dict[str, Any], *, round_trip: bool) -> None:
        segments = plan.get("segments") or []
        self.assertGreater(len(segments), 0)
        self.assertEqual(plan["metrics"]["segment_search_count"], len(segments))
        self.assertEqual(len(plan["route_graph"]["edges"]), len(segments))
        self.assertEqual(set(plan["route_graph"]["families"]), segment_family_ids(plan))
        self.assertFalse(segment_family_ids(plan) - route_family_ids(plan))

        keys = [segment_key(segment) for segment in segments]
        duplicate_keys = [key for key, count in Counter(keys).items() if count > 1]
        self.assertEqual(duplicate_keys, [])

        for segment in segments:
            self.assertFalse(REQUIRED_SEGMENT_FIELDS - set(segment))
            self.assertNotEqual(segment["origin"], segment["destination"])

        directions = {value(segment.get("direction")) for segment in segments}
        self.assertIn("outbound", directions)
        if round_trip:
            self.assertIn("return", directions)
            self.assertIsNotNone(plan["dates"]["return"])
        else:
            self.assertNotIn("return", directions)
            self.assertIsNone(plan["dates"]["return"])

    def test_core_route_plan_scenarios(self) -> None:
        scenarios = [
            {
                "name": "direct-only round-trip",
                "round_trip": True,
                "overrides": {
                    "origin": "SVX",
                    "destination": "CDG",
                    "depart_date": "2026-08-15",
                    "return_date": "2026-08-19",
                    "max_connections": 0,
                    "tier2_max_connections": 0,
                    "no_direct_route_intel": True,
                    "no_live_cache": True,
                },
                "expect": {
                    "strategy": "ru-priority",
                    "direct_only": True,
                    "segment_families": {"direct_inventory"},
                    "coverage_types": {"exact_airport_direct"},
                },
            },
            {
                "name": "direct-only date window",
                "round_trip": False,
                "overrides": {
                    "origin": "SVX",
                    "destination": "CDG",
                    "depart_date": "2026-08-15",
                    "return_date": None,
                    "max_connections": 0,
                    "tier2_max_connections": 0,
                    "date_window_end": "2026-08-20",
                    "no_direct_route_intel": True,
                    "no_live_cache": True,
                },
                "expect": {
                    "strategy": "ru-priority",
                    "direct_only": True,
                    "segment_families": {"direct_inventory"},
                    "dates": {"2026-08-15", "2026-08-16", "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20"},
                    "coverage_types": {"exact_airport_direct"},
                },
            },
            {
                "name": "ru-priority round-trip",
                "round_trip": True,
                "overrides": {
                    "routing_strategy": "ru-priority",
                    "origin": "SVX",
                    "destination": "CDG",
                    "depart_date": "2026-08-15",
                    "return_date": "2026-08-19",
                    "no_direct_route_intel": True,
                    "no_live_cache": True,
                },
                "expect": {
                    "strategy": "ru-priority",
                    "direct_only": False,
                    "required_families": {
                        "direct_control",
                        "ist_direct",
                        "ist_shared_destination",
                        "moscow_gateway_control",
                        "dxb_direct",
                    },
                    "coverage_types": {"exact_airport_direct", "full_route_aggregate", "carrier_aggregate"},
                },
            },
            {
                "name": "domestic-ru one-way",
                "round_trip": False,
                "overrides": {
                    "routing_strategy": "domestic-ru",
                    "origin": "SVX",
                    "destination": "LED",
                    "depart_date": "2026-08-15",
                    "return_date": None,
                    "no_direct_route_intel": True,
                    "no_live_cache": True,
                },
                "expect": {
                    "strategy": "domestic-ru",
                    "direct_only": False,
                    "segment_families": {"domestic_ru"},
                    "excluded_hubs": {"IST", "DXB"},
                    "coverage_types": {"exact_airport_direct", "full_route_aggregate", "carrier_aggregate"},
                },
            },
            {
                "name": "manual hub-list round-trip",
                "round_trip": True,
                "overrides": {
                    "routing_strategy": "hub-list",
                    "origin": "NCE",
                    "destination": "HND",
                    "depart_date": "2026-08-15",
                    "return_date": "2026-08-19",
                    "hub": ["IST"],
                    "no_direct_route_intel": True,
                    "no_live_cache": True,
                },
                "expect": {
                    "strategy": "hub-list",
                    "hubs": ["IST"],
                    "required_families": {"hub_list"},
                    "coverage_types": {"exact_airport_direct", "full_route_aggregate", "carrier_aggregate"},
                },
            },
            {
                "name": "global auto hub-list",
                "round_trip": False,
                "overrides": {
                    "routing_strategy": "auto",
                    "origin": "BER",
                    "destination": "MAD",
                    "depart_date": "2026-08-15",
                    "return_date": None,
                    "no_direct_route_intel": True,
                    "no_live_cache": True,
                },
                "expect": {
                    "strategy": "hub-list",
                    "direct_only": False,
                    "required_families": {"direct_control", "hub_list"},
                    "excluded_families": {"moscow_gateway_control"},
                    "excluded_hubs": {"SVO", "DME", "VKO"},
                },
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario["name"]):
                plan = self.build_plan(**scenario["overrides"])
                expected = scenario["expect"]
                self.assert_valid_route_plan(plan, round_trip=bool(scenario["round_trip"]))
                self.assertEqual(plan["routing_strategy"], expected["strategy"])
                if "direct_only" in expected:
                    self.assertEqual(plan["direct_only"], expected["direct_only"])
                if "hubs" in expected:
                    self.assertEqual(plan["hubs"], expected["hubs"])
                if "segment_families" in expected:
                    self.assertEqual(segment_family_ids(plan), expected["segment_families"])
                if "required_families" in expected:
                    self.assertTrue(expected["required_families"].issubset(segment_family_ids(plan)))
                if "excluded_families" in expected:
                    self.assertFalse(expected["excluded_families"] & segment_family_ids(plan))
                if "excluded_hubs" in expected:
                    self.assertFalse(expected["excluded_hubs"] & set(plan.get("hubs") or []))
                if "dates" in expected:
                    dates = {segment["date"] for segment in plan["segments"]}
                    self.assertEqual(dates, expected["dates"])
                if "coverage_types" in expected:
                    self.assertEqual(coverage_control_types(plan), expected["coverage_types"])


if __name__ == "__main__":
    unittest.main()
