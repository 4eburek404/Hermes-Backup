from __future__ import annotations

import unittest

from flights_cli.commands.search import live_assembly_options_from_search_request
from flights_cli.errors import CliError
from flights_cli.pipeline.options import search_request_to_options


REQUEST = {
    "schema_version": "flight_search_request.v1",
    "origin": "svx",
    "destination": "lon",
    "depart_date": "2026-07-20",
    "return_date": "2026-07-27",
    "currency": "rub",
    "profile": "business",
    "ticketing": "single",
    "provider_policy": "auto",
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
        "use_gateway_discovery_for_fallback_hubs": True,
        "gateway_discovery_limit": 5,
        "gateway_probe_batch_size": 2,
        "gateway_probe_max_batches": 3,
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
        "search_wave_max_waves": 4,
        "search_wave_probe_limit": 8,
        "search_wave_top_k": 6,
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
    def test_search_request_to_options_maps_request_fields(self) -> None:
        options = search_request_to_options(REQUEST)

        expected = {
            "origin": "SVX",
            "destination": "LON",
            "depart_date": "2026-07-20",
            "return_date": "2026-07-27",
            "hubs": ("IST", "DXB"),
            "ticketing": "single",
            "profile": "business",
            "only_carriers": ("SU",),
            "prefer_carriers": ("TK",),
            "aggregate_control_carriers": ("SU", "TK"),
            "agent_report": True,
        }
        self.assertEqual(options.route.origin, expected["origin"])
        self.assertEqual(options.route.destination, expected["destination"])
        self.assertEqual(options.route.depart_date, expected["depart_date"])
        self.assertEqual(options.route.return_date, expected["return_date"])
        self.assertEqual(options.route.hubs, expected["hubs"])
        self.assertTrue(options.route.use_gateway_discovery_for_fallback_hubs)
        self.assertEqual(options.route.gateway_discovery_limit, 5)
        self.assertEqual(options.route.gateway_probe_batch_size, 2)
        self.assertEqual(options.route.gateway_probe_max_batches, 3)
        self.assertEqual(options.ticketing, expected["ticketing"])
        self.assertEqual(options.profile, expected["profile"])
        self.assertEqual(options.filters.only_carriers, expected["only_carriers"])
        self.assertEqual(options.filters.prefer_carriers, expected["prefer_carriers"])
        self.assertEqual(
            options.evidence.aggregate_control_carriers,
            expected["aggregate_control_carriers"],
        )
        self.assertEqual(options.evidence.search_wave_max_waves, 4)
        self.assertEqual(options.evidence.search_wave_probe_limit, 8)
        self.assertEqual(options.evidence.search_wave_top_k, 6)
        self.assertEqual(options.output.agent_report, expected["agent_report"])

    def test_search_app_adapter_matches_typed_request_adapter(self) -> None:
        self.assertEqual(
            live_assembly_options_from_search_request(REQUEST),
            search_request_to_options(REQUEST),
        )

    def test_search_app_rejects_non_business_profile(self) -> None:
        with self.assertRaises(CliError):
            live_assembly_options_from_search_request({**REQUEST, "profile": "safe"})

    def test_search_app_rejects_removed_both_provider_policy(self) -> None:
        with self.assertRaises(CliError):
            live_assembly_options_from_search_request(
                {**REQUEST, "provider_policy": "both"}
            )

    def test_search_request_maps_request_constraints(self) -> None:
        request = {
            "schema_version": "flight_search_request.v1",
            "origin": "nte",
            "destination": "svx",
            "depart_date": "2026-07-09",
            "filters": {"only_carriers": ["AF"], "prefer_carriers": ["TK"]},
            "constraints": {
                "first_departure_after": "15:00",
                "must_include_airports": ["ams"],
                "only_carriers": ["kl"],
                "preferred_carriers": ["af"],
            },
        }
        options = search_request_to_options(request)

        self.assertEqual(options.constraints.first_departure_after, "15:00")
        self.assertEqual(options.constraints.must_include_airports, ("AMS",))
        self.assertEqual(options.constraints.only_carriers, ("KL",))
        self.assertEqual(options.constraints.preferred_carriers, ("AF",))
        self.assertEqual(options.filters.only_carriers, ("AF",))
        self.assertEqual(options.effective_only_carriers(), ("AF", "KL"))
        self.assertEqual(options.effective_prefer_carriers(), ("TK", "AF"))
        self.assertEqual(live_assembly_options_from_search_request(request), options)

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
        self.assertEqual(options.profile, "business")
        self.assertEqual(options.ticketing, "separate")
        self.assertEqual(options.evidence.provider_policy, "auto")
        self.assertTrue(options.output.agent_report)
        self.assertTrue(options.output.agent_brief)

    def test_search_request_preserves_explicit_zero_values(self) -> None:
        options = search_request_to_options(
            {
                "schema_version": "flight_search_request.v1",
                "origin": "svx",
                "destination": "dme",
                "depart_date": "2026-08-15",
                "route_options": {
                    "coverage_control_limit": 0,
                    "min_same_airport_min": 0,
                    "min_cross_airport_min": 0,
                    "max_connections": 0,
                    "tier2_max_connections": 0,
                    "gateway_discovery_limit": 0,
                    "gateway_probe_batch_size": 0,
                    "gateway_probe_max_batches": 0,
                },
                "evidence": {
                    "aggregate_control_limit": 0,
                    "live_cache_ttl_seconds": 0,
                    "direct_route_index_ttl_seconds": 0,
                },
                "output": {
                    "include_segment_results": 0,
                    "include_candidates": 0,
                    "include_ranked_candidates": 0,
                    "include_rejected_pairs": 0,
                    "include_filtered": 0,
                    "max_candidates": 0,
                    "max_reasons": 0,
                },
            }
        )

        self.assertEqual(options.route.max_connections, 0)
        self.assertEqual(options.route.tier2_max_connections, 0)
        self.assertEqual(options.route.min_same_airport_min, 0)
        self.assertEqual(options.route.min_cross_airport_min, 0)
        self.assertEqual(options.route.gateway_discovery_limit, 0)
        self.assertEqual(options.route.gateway_probe_batch_size, 0)
        self.assertEqual(options.route.gateway_probe_max_batches, 0)
        self.assertEqual(options.evidence.coverage_control_limit, 0)
        self.assertEqual(options.evidence.aggregate_control_limit, 0)
        self.assertEqual(options.evidence.live_cache_ttl_seconds, 0)
        self.assertEqual(options.evidence.direct_route_index_ttl_seconds, 0)
        self.assertEqual(options.output.include_segment_results, 0)
        self.assertEqual(options.output.include_candidates, 0)
        self.assertEqual(options.output.include_ranked_candidates, 0)
        self.assertEqual(options.output.include_rejected_pairs, 0)
        self.assertEqual(options.output.include_filtered, 0)
        self.assertEqual(options.output.max_candidates, 0)
        self.assertEqual(options.output.max_reasons, 0)


if __name__ == "__main__":
    unittest.main()
