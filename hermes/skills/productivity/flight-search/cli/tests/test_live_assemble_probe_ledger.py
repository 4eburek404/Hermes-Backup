from __future__ import annotations

import argparse
import unittest
from unittest.mock import patch

from flights_cli.orchestrators.live_assemble import run_live_route_assembly
from flights_cli.store import Store


def live_args(**overrides: object) -> argparse.Namespace:
    values = {
        "max_segment_searches": 10,
        "only_carrier": [],
        "prefer_carrier": [],
        "provider_policy": "kupibilet",
        "live_cache_ttl_seconds": 0,
        "no_live_cache": True,
        "direct_route_index_ttl_seconds": 0,
        "no_direct_route_intel": True,
        "include_segment_results": 0,
        "aggregate_control_limit": 0,
        "agent_report": False,
        "agent_brief": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class LiveAssembleProbeLedgerTests(unittest.TestCase):
    def test_city_pair_controls_are_planned_and_finalized_by_runtime_ledger(self) -> None:
        plan = {
            "origin": "SVX",
            "destination": "CDG",
            "dates": {"depart": "2026-08-16", "return": None},
            "currency": "RUB",
            "profile": "business",
            "ticketing": "separate",
            "routing_strategy": "auto",
            "hubs": [],
            "route_graph": {"nodes": [], "edges": [], "strategy": "auto"},
            "route_families": [],
            "segments": [],
            "coverage_mode": "targeted",
            "coverage_limits": {},
            "coverage_controls": [
                {
                    "type": "city_pair_direct",
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "CDG",
                    "date": "2026-08-16",
                    "negative_evidence": "city_pair_direct_not_executable_by_provider",
                }
            ],
            "metrics": {"segment_search_count": 0},
        }

        with (
            patch("flights_cli.orchestrators.live_assemble.build_live_route_segment_plan", return_value=plan),
            patch("flights_cli.orchestrators.live_assemble.empty_assembled_result", return_value={}),
            patch("flights_cli.orchestrators.live_assemble.run_aggregate_controls", return_value=[]),
            patch("flights_cli.orchestrators.live_assemble.hub_viability_summary", return_value=[]),
        ):
            result = run_live_route_assembly(live_args(), Store())

        ledger = result["live_search"]["probe_ledger"]
        self.assertEqual([item["type"] for item in ledger["planned_controls"]], ["city_pair_direct"])
        self.assertEqual([item["type"] for item in ledger["not_executed_controls"]], ["city_pair_direct"])
        self.assertEqual(ledger["not_executed_controls"][0]["execution_state"], "not_executed")
        self.assertTrue(ledger["completeness"]["all_planned_controls_have_terminal_state"])


if __name__ == "__main__":
    unittest.main()
