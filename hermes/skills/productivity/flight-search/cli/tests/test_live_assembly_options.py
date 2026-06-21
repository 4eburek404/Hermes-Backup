from __future__ import annotations

import argparse
import unittest

from flights_cli.apps.search import live_assembly_args_from_search_request
from flights_cli.pipeline.options import argparse_args_to_options, search_request_to_options


REQUEST = {
    "schema_version": "flight_search_request.v1",
    "origin": "svx",
    "destination": "lon",
    "depart_date": "2026-07-20",
    "return_date": "2026-07-27",
    "currency": "rub",
    "profile": "safe",
    "ticketing": "single",
    "provider_policy": "both",
    "route_options": {
        "routing_strategy": "hub-list",
        "hubs": ["IST", "DXB"],
        "origin_airports": ["SVX"],
        "destination_airports": ["LHR"],
        "max_airports_per_city": 3,
        "coverage_mode": "full",
        "coverage_controls": ["exact_airport_direct"],
        "coverage_control_limit": 7,
        "min_same_airport_min": 150,
        "min_cross_airport_min": 360,
        "stop_policy": "debug-all",
        "date_window_end": "2026-07-22",
        "max_connections": 0,
        "tier2_max_connections": 0,
    },
    "filters": {
        "only_carriers": ["SU"],
        "exclude_carriers": ["ZZ"],
        "prefer_carriers": ["TK"],
        "avoid_carriers": ["XX"],
    },
    "evidence": {
        "segment_limit": 11,
        "timeout": 42,
        "outbound_second_leg_day_offsets": [0, 1],
        "return_second_leg_day_offsets": [0, 2],
        "aggregate_control_limit": 4,
        "aggregate_control_carriers": ["SU", "TK"],
        "max_segment_searches": 99,
        "fail_fast": True,
        "live_cache_ttl_seconds": 123,
        "no_live_cache": True,
        "direct_route_index_ttl_seconds": 456,
        "no_direct_route_intel": True,
        "fli_mcp_url": "http://127.0.0.1:9999/mcp",
    },
    "output": {
        "include_stop_policy_diagnostics": True,
        "limit_per_pair": 2,
        "candidate_pool_limit": 111,
        "max_candidates": 9,
        "max_reasons": 3,
        "include_candidates": 4,
        "include_ranked_candidates": 5,
        "include_rejected_pairs": 6,
        "include_segment_results": 7,
        "agent_brief": False,
        "include_filtered": 8,
    },
}


class LiveAssemblyOptionsTests(unittest.TestCase):
    def test_search_request_to_options_matches_legacy_namespace_adapter(self) -> None:
        options = search_request_to_options(REQUEST)
        namespace = options.to_argparse_namespace()
        legacy = live_assembly_args_from_search_request(REQUEST)

        for field in vars(namespace):
            with self.subTest(field=field):
                self.assertEqual(getattr(namespace, field), getattr(legacy, field))

    def test_argparse_args_to_options_round_trips_live_assembly_namespace(self) -> None:
        legacy = live_assembly_args_from_search_request(REQUEST)

        self.assertEqual(argparse_args_to_options(legacy), search_request_to_options(REQUEST))

    def test_search_request_defaults_are_explicit_in_typed_options(self) -> None:
        options = search_request_to_options(
            {
                "schema_version": "flight_search_request.v1",
                "origin": "svx",
                "destination": "lon",
                "depart_date": "2026-07-20",
            }
        )

        self.assertEqual(options.command_name, "search")
        self.assertEqual(options.route.origin, "SVX")
        self.assertEqual(options.route.destination, "LON")
        self.assertEqual(options.currency, "RUB")
        self.assertEqual(options.profile, "balanced")
        self.assertEqual(options.ticketing, "separate")
        self.assertEqual(options.evidence.provider_policy, "auto")
        self.assertTrue(options.output.agent_report)
        self.assertTrue(options.output.agent_brief)

    def test_argparse_args_to_options_keeps_cli_command_name_and_agent_report_flag(self) -> None:
        args = argparse.Namespace(
            command_name="diagnose plan",
            origin="SVX",
            destination="LON",
            depart_date="2026-07-20",
            agent_report=False,
        )

        options = argparse_args_to_options(args)

        self.assertEqual(options.command_name, "diagnose plan")
        self.assertFalse(options.output.agent_report)


if __name__ == "__main__":
    unittest.main()
