from __future__ import annotations

import copy
import json
import unittest

from flights_cli.reporting.projections.itinerary_display import build_itinerary_display
from flights_cli.reporting.agent_report_projector import project_agent_report
from flights_cli.reporting.report_budget import (
    AgentReportBudget,
    apply_agent_report_budget,
    serialized_report_size,
)
from flights_cli.services.agent_report_contract import validate_agent_report
from tests.test_agent_report_contract import valid_option, valid_report


def noisy_segment(index: int) -> dict:
    return {
        "direction": "outbound",
        "flight_number": f"SU{1000 + index}",
        "carrier": "SU",
        "marketing_carrier": "SU",
        "operating_carrier": "SU",
        "origin": "SVX",
        "destination": "SVO",
        "departure_at": "2026-06-01T06:00:00+05:00",
        "arrival_at": "2026-06-01T08:30:00+03:00",
    }


def coverage_control(index: int, bucket: str) -> dict:
    return {
        "type": "carrier_aggregate",
        "direction": "outbound",
        "origin": "SVX",
        "destination": "DEL",
        "date": "2026-06-01",
        "carrier": f"S{index % 10}",
        "execution_state": bucket.replace("_controls", ""),
        "probe_id": f"probe-{index:03d}",
    }


def validate_budgeted_flat_report(report: dict) -> None:
    validate_agent_report(project_agent_report(report))


class AgentReportBudgetTests(unittest.TestCase):
    def test_budgeted_summary_only_options_keep_compact_display_without_stale_flight_lines(
        self,
    ) -> None:
        report = valid_report()
        full_option = copy.deepcopy(valid_option())
        full_option["id"] = "option-full"
        full_option["rank"] = 1
        full_option["price_text"] = "10 000 RUB"
        summary_option = copy.deepcopy(valid_option())
        summary_option["id"] = "option-summary"
        summary_option["rank"] = 2
        summary_option["price_text"] = "12 000 RUB"
        summary_option["elapsed_min"] = 540
        summary_option["elapsed"] = "9h"
        summary_option["max_connections_per_journey"] = 1
        summary_option["segments"] = [
            {
                "direction": "outbound",
                "flight_number": "U6123",
                "carrier": "U6",
                "origin": "SVX",
                "destination": "IST",
                "departure_at": "2026-06-01T10:00:00+05:00",
                "arrival_at": "2026-06-01T13:00:00+03:00",
            },
            {
                "direction": "outbound",
                "flight_number": "TK1985",
                "carrier": "TK",
                "origin": "IST",
                "destination": "LHR",
                "departure_at": "2026-06-01T15:00:00+03:00",
                "arrival_at": "2026-06-01T17:00:00+01:00",
            },
        ]
        report["recommended_options"] = [full_option, summary_option]
        report["display"] = build_itinerary_display(report)
        self.assertIn("U6123", report["display"]["text"])
        self.assertIn("пересадка IST", report["display"]["text"])

        budgeted = apply_agent_report_budget(report, AgentReportBudget(max_bytes=1))

        validate_budgeted_flat_report(budgeted)
        full_display = next(
            option
            for option in budgeted["display"]["options"]
            if option["id"] == "option-full"
        )
        summary_display = next(
            option
            for option in budgeted["display"]["options"]
            if option["id"] == "option-summary"
        )
        self.assertEqual(budgeted["recommended_options"][0]["detail_status"], "full")
        self.assertEqual(
            budgeted["recommended_options"][1]["detail_status"], "summary_only"
        )
        self.assertEqual(budgeted["recommended_options"][1]["segments"], [])
        self.assertIn("SU232", full_display["text"])
        self.assertNotIn("U6123", summary_display["text"])
        self.assertNotIn("TK1985", summary_display["text"])
        self.assertNotIn("пересадка", summary_display["text"].lower())
        self.assertNotIn("SVX - IST", summary_display["text"])
        self.assertNotIn("IST - LHR", summary_display["text"])

    def test_huge_report_is_bounded_and_records_omitted_counts(self) -> None:
        report = valid_report()
        report["recommended_options"] = []
        for index in range(14):
            option = valid_option()
            option["id"] = f"option-{index}"
            option["rank"] = index + 1
            option["segments"] = [noisy_segment(index + offset) for offset in range(18)]
            report["recommended_options"].append(option)
        report["priority_options"] = []
        for index in range(20):
            option = valid_option()
            option["id"] = f"priority-{index}"
            option["rank"] = index + 20
            option["category"] = "priority_control"
            option["segments"] = [
                noisy_segment(index + 200 + offset) for offset in range(18)
            ]
            report["priority_options"].append(option)
        report["segment_searches"] = [
            {
                "direction": "outbound",
                "leg": "x",
                "origin": "SVX",
                "destination": "DEL",
                "date": "2026-06-01",
                "provider": "kupibilet",
                "status": "ok",
                "reason": None,
                "offer_count": 0,
            }
            for _ in range(60)
        ]
        report["provider_failures"] = [
            {
                "direction": "outbound",
                "leg": "x",
                "origin": "SVX",
                "destination": "DEL",
                "date": "2026-06-01",
                "provider": "fli",
                "error": {"type": "timeout", "message": "x"},
            }
            for _ in range(25)
        ]
        report["coverage_diagnostics"].update(
            {
                "planned_controls": [
                    coverage_control(index, "planned_controls") for index in range(80)
                ],
                "searched_controls": [
                    coverage_control(index, "searched_controls") for index in range(40)
                ],
                "skipped_controls": [
                    coverage_control(index, "skipped_controls") for index in range(30)
                ],
                "failed_controls": [
                    coverage_control(index, "failed_controls") for index in range(5)
                ],
                "not_supported_controls": [
                    coverage_control(index, "not_supported_controls")
                    for index in range(6)
                ],
                "not_executed_controls": [
                    coverage_control(index, "not_executed_controls")
                    for index in range(8)
                ],
                "deduped_controls": [
                    coverage_control(index, "deduped_controls") for index in range(10)
                ],
            }
        )
        report["answer_lines"] = (
            ["Best CLI-ranked option: 10 000 RUB risk=good/1 elapsed=2h."]
            + [f"line {index}" for index in range(30)]
            + [
                "Priority control: priority_control rank=20 10 000 RUB elapsed=2h.",
                "Provider failure: FLI failed on 25 segment search(es).",
                "Through-fare check required: verify SU SVX->DEL on airline/GDS before pricing it as separate legs.",
                "Do not treat cached or segment-search absence as proof that a through fare, direct flight, or protected ticket does not exist.",
            ]
        )

        budgeted = apply_agent_report_budget(report, AgentReportBudget(max_bytes=65536))

        validate_budgeted_flat_report(budgeted)
        self.assertLessEqual(serialized_report_size(budgeted), 65536)
        self.assertIn("omitted_counts", budgeted)
        self.assertGreater(budgeted["omitted_counts"]["recommended_options"], 0)
        self.assertGreater(budgeted["omitted_counts"]["coverage_controls"], 0)
        self.assertTrue(budgeted["recommended_options"][0]["segments"])
        self.assertEqual(budgeted["recommended_options"][1]["segments"], [])
        self.assertEqual(
            budgeted["recommended_options"][1]["detail_status"], "summary_only"
        )
        self.assertGreater(budgeted["omitted_counts"]["option_segments"], 0)
        serialized = json.dumps(budgeted, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("raw_payload", serialized)
        self.assertNotIn("raw_variants", serialized)
        self.assertNotIn('"response"', serialized)

    def test_regular_truncation_does_not_strip_non_primary_segments(self) -> None:
        report = valid_report()
        report["status"]["output_limits"] = {
            "catalog_limit": 12,
            "direct_catalog_limit": 30,
        }
        report["recommended_options"] = []
        for index in range(14):
            option = valid_option()
            option["id"] = f"option-{index}"
            option["segments"] = [noisy_segment(index)]
            report["recommended_options"].append(option)

        budgeted = apply_agent_report_budget(report, AgentReportBudget(max_bytes=65536))

        validate_budgeted_flat_report(budgeted)
        self.assertEqual(len(budgeted["recommended_options"]), 12)
        self.assertTrue(
            all(option["segments"] for option in budgeted["recommended_options"])
        )
        self.assertEqual(budgeted["omitted_counts"]["recommended_options"], 2)

    def test_direct_mode_keeps_all_recommended_schedule_options(self) -> None:
        report = valid_report()
        report["status"] = {"direct_mode": {"outbound": True}}
        report["recommended_options"] = []
        for index in range(7):
            option = valid_option()
            option["id"] = f"direct-{index}"
            option["rank"] = index + 1
            option["segments"] = [noisy_segment(index)]
            option["max_connections_per_journey"] = 0
            report["recommended_options"].append(option)

        budgeted = apply_agent_report_budget(report, AgentReportBudget(max_bytes=65536))

        validate_budgeted_flat_report(budgeted)
        self.assertEqual(len(budgeted["recommended_options"]), 7)
        self.assertNotIn("recommended_options", budgeted.get("omitted_counts", {}))

    def test_answer_line_trim_preserves_constraint_conflict_caveat(self) -> None:
        report = valid_report()
        conflict_line = (
            "прямых рейсов после 15:00 нет; прямые есть утром — показаны ниже."
        )
        report["answer_lines"] = (
            ["Best CLI-ranked option: 10 000 RUB risk=good/1 elapsed=2h."]
            + [f"line {index}" for index in range(20)]
            + [conflict_line]
        )

        budgeted = apply_agent_report_budget(report, AgentReportBudget(max_answer_lines=3))

        self.assertIn(conflict_line, budgeted["answer_lines"])
        self.assertLessEqual(len(budgeted["answer_lines"]), 3)

    def test_budget_prioritizes_blocking_controls_before_provider_boundaries(
        self,
    ) -> None:
        report = valid_report()
        report["coverage_diagnostics"].update(
            {
                "failed_controls": [
                    coverage_control(index, "failed_controls") for index in range(2)
                ],
                "not_supported_controls": [
                    coverage_control(index, "not_supported_controls")
                    for index in range(4)
                ],
                "not_executed_controls": [
                    coverage_control(index, "not_executed_controls")
                    for index in range(4)
                ],
            }
        )

        budgeted = apply_agent_report_budget(
            report, AgentReportBudget(max_coverage_controls=5)
        )

        validate_budgeted_flat_report(budgeted)
        diagnostics = budgeted["coverage_diagnostics"]
        self.assertEqual(len(diagnostics["failed_controls"]), 2)
        self.assertEqual(len(diagnostics["not_executed_controls"]), 3)
        self.assertEqual(diagnostics["not_supported_controls"], [])
        self.assertEqual(budgeted["omitted_counts"]["coverage_controls"], 6)


if __name__ == "__main__":
    unittest.main()
