from __future__ import annotations

import unittest
from unittest.mock import patch

from flights_cli.execution.probe_dispatcher import SegmentProbeOutcome
from flights_cli.orchestrators.live_route_assembly import run_live_route_assembly
from flights_cli.store import Store
from helpers import live_assembly_args


def live_args(**overrides: object):
    defaults = {
        "origin": "SVX",
        "destination": "CDG",
        "depart_date": "2026-08-16",
        "return_date": None,
        "max_segment_searches": 10,
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
    defaults.update(overrides)
    return live_assembly_args(**defaults)


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
            patch("flights_cli.orchestrators.live_route_assembly.build_live_route_segment_plan", return_value=plan),
            patch("flights_cli.orchestrators.live_assembly_runner.empty_assembled_result", return_value={}),
            patch("flights_cli.execution.aggregate_control_runner.run_aggregate_controls", return_value=[]),
            patch("flights_cli.orchestrators.live_assembly_runner.hub_viability_summary", return_value=[]),
        ):
            result = run_live_route_assembly(live_args(), Store())

        ledger = result["live_search"]["probe_ledger"]
        self.assertEqual([item["type"] for item in ledger["planned_controls"]], ["city_pair_direct"])
        self.assertEqual([item["type"] for item in ledger["not_executed_controls"]], ["city_pair_direct"])
        self.assertEqual(ledger["not_executed_controls"][0]["execution_state"], "not_executed")
        self.assertTrue(ledger["completeness"]["all_planned_controls_have_terminal_state"])

    def test_successful_segment_search_keeps_plan_metadata(self) -> None:
        plan = {
            "origin": "SVX",
            "destination": "LON",
            "dates": {"depart": "2026-08-16", "return": None},
            "currency": "RUB",
            "profile": "business",
            "ticketing": "separate",
            "routing_strategy": "ru-priority",
            "hubs": ["IST"],
            "route_graph": {"nodes": [], "edges": [], "strategy": "ru-priority"},
            "route_families": [{"id": "ist_direct"}],
            "segments": [
                {
                    "direction": "outbound",
                    "leg": "origin_to_hub",
                    "origin": "SVX",
                    "destination": "IST",
                    "date": "2026-08-16",
                    "route_family": "ist_direct",
                    "priority": 1,
                    "preferred_carriers": ["U6", "SU", "TK"],
                }
            ],
            "coverage_mode": "targeted",
            "coverage_limits": {},
            "coverage_controls": [],
            "metrics": {"segment_search_count": 1},
        }
        outcome = SegmentProbeOutcome(summary={"status": "ok", "provider": "kupibilet", "offer_count": 1})

        with (
            patch("flights_cli.orchestrators.live_route_assembly.build_live_route_segment_plan", return_value=plan),
            patch("flights_cli.orchestrators.live_assembly_runner.dispatch_segment_probe", return_value=[outcome]),
            patch("flights_cli.orchestrators.live_assembly_runner.empty_assembled_result", return_value={}),
            patch("flights_cli.execution.aggregate_control_runner.run_aggregate_controls", return_value=[]),
            patch("flights_cli.orchestrators.live_assembly_runner.hub_viability_summary", return_value=[]),
        ):
            result = run_live_route_assembly(live_args(), Store())

        search = result["live_search"]["segment_searches"][0]
        self.assertEqual(search["route_family"], "ist_direct")
        self.assertEqual(search["priority"], 1)
        self.assertEqual(search["origin"], "SVX")
        self.assertEqual(search["destination"], "IST")
        self.assertEqual(search["leg"], "origin_to_hub")
        self.assertEqual(search["only_carriers"], [])
        self.assertEqual(search["preferred_carriers"], ["U6", "SU", "TK"])
        self.assertEqual(search["status"], "ok")


if __name__ == "__main__":
    unittest.main()
