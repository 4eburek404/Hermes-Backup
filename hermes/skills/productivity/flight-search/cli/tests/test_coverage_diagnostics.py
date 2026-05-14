from __future__ import annotations

import unittest

from flights_cli.services.agent_report import build_agent_report
from flights_cli.services.agent_report_contract import validate_agent_report


def base_payload() -> dict:
    return {
        "profile": "business",
        "assembly": {
            "ranked_output_count": 0,
            "ranked_total_count": 0,
            "candidate_count": 0,
            "candidate_pool_truncated": False,
        },
        "ranked_candidates": [],
        "frontier_candidates": [],
        "rejected_pairs": [],
        "live_search": {
            "provider_policy": "kupibilet",
            "plan": {
                "origin": "SVX",
                "destination": "CDG",
                "origin_airports": ["SVX"],
                "destination_airports": ["CDG"],
                "dates": {"depart": "2026-08-16", "return": "2026-08-19"},
                "routing_strategy": "ru-priority",
                "coverage_mode": "targeted",
                "coverage_controls": [
                    {"type": "exact_airport_direct", "direction": "outbound", "origin": "SVX", "destination": "CDG", "date": "2026-08-16"},
                    {"type": "full_route_aggregate", "direction": "outbound", "origin": "SVX", "destination": "CDG", "date": "2026-08-16"},
                    {"type": "carrier_aggregate", "direction": "outbound", "origin": "SVX", "destination": "CDG", "date": "2026-08-16", "carrier": "SU"},
                ],
            },
            "hub_viability": [],
            "segment_searches": [
                {
                    "direction": "outbound",
                    "leg": "direct_outbound",
                    "origin": "SVX",
                    "destination": "CDG",
                    "date": "2026-08-16",
                    "provider": "kupibilet",
                    "status": "ok",
                    "reason": None,
                    "offer_count": 0,
                    "cache_status": "live",
                },
                {
                    "direction": "outbound",
                    "leg": "origin_to_hub",
                    "origin": "SVX",
                    "destination": "DXB",
                    "date": "2026-08-16",
                    "provider": None,
                    "status": "skipped",
                    "reason": "priority_route_viable",
                    "offer_count": 0,
                },
            ],
            "aggregate_controls": [
                {
                    "direction": "outbound",
                    "origin": "SVX",
                    "destination": "CDG",
                    "date": "2026-08-16",
                    "status": "ok",
                    "provider": "kupibilet",
                    "filters": {"direct_only": False, "only_carriers": []},
                    "offer_count": 0,
                    "raw_variant_count": 0,
                    "top_offers": [],
                    "error": None,
                }
            ],
            "failure_count": 0,
            "failures": [],
        },
    }


class CoverageDiagnosticsTests(unittest.TestCase):
    def test_agent_report_has_machine_readable_coverage_diagnostics(self) -> None:
        report = build_agent_report(base_payload())
        validate_agent_report(report)

        diagnostics = report["coverage_diagnostics"]
        self.assertEqual(diagnostics["coverage_mode"], "targeted")
        self.assertEqual(diagnostics["negative_evidence_type"], "bounded_live_controls_only")
        self.assertIn("segment_absence_is_not_route_absence", diagnostics["coverage_warnings"])
        searched_types = {item["type"] for item in diagnostics["searched_controls"]}
        self.assertIn("exact_airport_direct", searched_types)
        self.assertIn("full_route_aggregate", searched_types)
        searched_direct = [item for item in diagnostics["searched_controls"] if item["type"] == "exact_airport_direct"][0]
        self.assertEqual(searched_direct["cache_status"], "live")
        skipped = diagnostics["skipped_controls"]
        self.assertEqual(skipped[0]["reason"], "priority_route_viable")
        not_executed_types = {item["type"] for item in diagnostics["not_executed_controls"]}
        self.assertIn("carrier_aggregate", not_executed_types)
        self.assertEqual(diagnostics["completeness"]["planned_count"], diagnostics["completeness"]["terminal_count"])
        self.assertTrue(diagnostics["completeness"]["all_planned_controls_have_terminal_state"])

    def test_answer_lines_keep_coverage_diagnostics_compact(self) -> None:
        report = build_agent_report(base_payload())
        joined = " ".join(report["answer_lines"])

        self.assertIn("Coverage diagnostics", joined)
        self.assertIn("not_executed=1", joined)
        self.assertIn("Coverage is incomplete", joined)
        self.assertNotIn("searched_controls", joined)
        self.assertNotIn("skipped_controls", joined)


if __name__ == "__main__":
    unittest.main()
