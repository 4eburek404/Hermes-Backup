from __future__ import annotations

import unittest

from helpers import CliSubprocessMixin


def offer(offer_id: str, departure_at: str, arrival_at: str, price: int, flight_number: str) -> dict:
    return {
        "id": offer_id,
        "origin": "SVX",
        "destination": "IST",
        "departure_airport": "SVX",
        "arrival_airport": "IST",
        "departure_at": departure_at,
        "arrival_at": arrival_at,
        "price": price,
        "currency": "RUB",
        "segments": [
            {
                "origin": "SVX",
                "destination": "IST",
                "departure_at": departure_at,
                "arrival_at": arrival_at,
                "flight_number": flight_number,
                "carrier": flight_number[:2],
            }
        ],
    }


class AgentReportP0CompletenessTests(CliSubprocessMixin, unittest.TestCase):
    def test_agent_report_keeps_cheapest_recommendation_details_beyond_top_n(self) -> None:
        payload = {
            "segment_results": [
                {
                    "direction": "outbound",
                    "leg": "direct_outbound",
                    "query": {"origin": "SVX", "destination": "IST", "date": "2026-06-15", "currency": "RUB"},
                    "offers": [
                        offer("fast-expensive", "2026-06-15T08:00:00+05:00", "2026-06-15T10:00:00+03:00", 50000, "SU100"),
                        offer("middle", "2026-06-15T09:00:00+05:00", "2026-06-15T12:00:00+03:00", 30000, "SU200"),
                        offer("cheap-slow", "2026-06-15T06:00:00+05:00", "2026-06-15T13:00:00+03:00", 10000, "SU300"),
                    ],
                }
            ]
        }

        assembled = self._assemble(
            payload,
            "--agent-report",
            "--max-candidates",
            "1",
            "--include-ranked-candidates",
            "1",
        )
        data = assembled["data"]
        report = data["agent_report"]

        self.assertEqual([item["rank"] for item in data["ranked"]], [1])
        self.assertEqual(data["recommendations"]["cheapest_acceptable"]["rank"], 3)

        options_by_category = {option.get("category"): option for option in report["recommended_options"]}
        self.assertIn("cheapest_acceptable", options_by_category)
        cheapest = options_by_category["cheapest_acceptable"]
        self.assertEqual(cheapest["rank"], 3)
        self.assertEqual(cheapest.get("detail_status"), "full")
        self.assertEqual([segment["flight_number"] for segment in cheapest["segments"]], ["SU300"])
        self.assertIn("Cheapest acceptable", "\n".join(report["answer_lines"]))


if __name__ == "__main__":
    unittest.main()
