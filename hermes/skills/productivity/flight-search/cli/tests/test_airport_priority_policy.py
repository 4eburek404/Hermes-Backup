from __future__ import annotations

import unittest

from flights_cli.orchestrators.search_plan_builder import build_route_context
from flights_cli.store import Store
from helpers import live_assembly_args


def live_args(**overrides: object):
    defaults = {
        "origin": "IST",
        "destination": "LON",
        "depart_date": "2026-08-12",
        "return_date": None,
        "hub": None,
        "routing_strategy": "auto",
        "origin_airport": None,
        "destination_airport": None,
        "currency": "RUB",
        "only_carrier": [],
        "exclude_carrier": [],
        "prefer_carrier": [],
        "avoid_carrier": [],
        "ticketing": "separate",
        "profile": "business",
        "min_same_airport_min": 120,
        "min_cross_airport_min": 300,
        "max_airports_per_city": 6,
        "coverage_mode": "targeted",
        "coverage_control": None,
        "coverage_control_limit": 12,
        "outbound_second_leg_day_offset": None,
        "return_second_leg_day_offset": None,
        "segment_limit": 30,
        "timeout": 60,
        "aggregate_control_limit": 0,
        "aggregate_control_carrier": None,
        "max_segment_searches": 300,
        "fail_fast": False,
        "live_cache_ttl_seconds": 0,
        "no_live_cache": True,
        "provider_policy": "auto",
    }
    defaults.update(overrides)
    return live_assembly_args(**defaults)


class AirportPriorityPolicyTests(unittest.TestCase):
    def test_domestic_mow_round_trip_does_not_add_intra_moscow_hub_fallback(
        self,
    ) -> None:
        plan = build_route_context(
            live_args(origin="SVX", destination="MOW", return_date="2026-08-19"),
            Store(),
        )

        self.assertNotIn("segments", plan)


if __name__ == "__main__":
    unittest.main()
