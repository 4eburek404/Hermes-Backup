from __future__ import annotations

import unittest

from flights_cli.pipeline.result_builder import build_result_projection


class ResultBuilderProjectionTests(unittest.TestCase):
    def test_v5_route_and_frontier_are_projected_once(self) -> None:
        data = {
            "live_search": {
                "plan": {
                    "schema_version": "flight_search_plan.v5",
                    "route": {
                        "origin": "SVX",
                        "destination": "AMS",
                        "origin_airports": ["SVX"],
                        "destination_airports": ["AMS"],
                        "dates": {"depart_date": "2026-08-01"},
                        "profile": "business",
                        "routing_strategy": "ru-priority",
                        "provider_policy": "auto",
                    },
                },
                "probe_ledger": {
                    "planned_probes": [],
                    "searched_probes": [],
                    "skipped_probes": [],
                    "failed_probes": [],
                    "unsupported_probes": [],
                    "not_executed_probes": [],
                    "deduped_probes": [],
                },
                "stop_policy": {
                    "name": "search_plan",
                    "preferred_max_connections": 1,
                    "tier2_max_connections": 2,
                    "hard_max_connections": 2,
                },
                "stop_policy_status": {
                    "policy": "search_plan",
                    "max_reported_connections": 1,
                    "used_two_stop_tier": False,
                    "three_plus_suppressed_count": 0,
                    "garbage_options_hidden_from_answer": False,
                },
            },
            "decision_frontier": {
                "schema_version": "flight_decision_frontier.v1",
                "options": [],
                "coverage_summary": {},
            },
        }

        result = build_result_projection(data)

        self.assertEqual(result["route"]["origin"], "SVX")
        self.assertEqual(result["route"]["destination"], "AMS")
        self.assertEqual(result["frontier"]["option_ids"], [])
        self.assertEqual(
            result["answer"]["evidence_status"]["answerability"], "answerable"
        )


if __name__ == "__main__":
    unittest.main()
