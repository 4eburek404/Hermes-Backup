from __future__ import annotations

import unittest

from helpers import CliSubprocessMixin


class AgentReportP1MoscowControlTests(CliSubprocessMixin, unittest.TestCase):
    def test_agent_brief_surfaces_moscow_gateway_control_when_direct_is_best(self) -> None:
        def offer(offer_id: str, price: int, segments: list[dict]) -> dict:
            return {
                "id": offer_id,
                "origin": segments[0]["origin"],
                "destination": segments[-1]["destination"],
                "departure_airport": segments[0]["origin"],
                "arrival_airport": segments[-1]["destination"],
                "departure_at": segments[0]["departure_at"],
                "arrival_at": segments[-1]["arrival_at"],
                "price": price,
                "currency": "RUB",
                "segments": segments,
            }

        direct = offer(
            "direct-svx-ist",
            25000,
            [
                {
                    "origin": "SVX",
                    "destination": "IST",
                    "departure_at": "2026-06-15T07:00:00+05:00",
                    "arrival_at": "2026-06-15T09:00:00+03:00",
                    "flight_number": "SU630",
                    "carrier": "SU",
                }
            ],
        )
        via_svo = offer(
            "moscow-control-svx-svo-ist",
            42000,
            [
                {
                    "origin": "SVX",
                    "destination": "SVO",
                    "departure_at": "2026-06-15T06:00:00+05:00",
                    "arrival_at": "2026-06-15T06:40:00+03:00",
                    "flight_number": "SU1401",
                    "carrier": "SU",
                },
                {
                    "origin": "SVO",
                    "destination": "IST",
                    "departure_at": "2026-06-15T10:30:00+03:00",
                    "arrival_at": "2026-06-15T14:35:00+03:00",
                    "flight_number": "SU2136",
                    "carrier": "SU",
                },
            ],
        )
        payload = {
            "segment_results": [
                {
                    "direction": "outbound",
                    "leg": "direct_outbound",
                    "query": {"origin": "SVX", "destination": "IST", "date": "2026-06-15", "currency": "RUB"},
                    "offers": [direct, via_svo],
                }
            ]
        }

        assembled = self._assemble(
            payload,
            "--agent-brief",
            "--max-candidates",
            "1",
            "--include-ranked-candidates",
            "1",
        )
        report = assembled["data"]["agent_report"]
        moscow = next((item for item in report["priority_options"] if item.get("category") == "moscow_gateway_control"), None)

        self.assertIsNotNone(moscow)
        self.assertGreater(moscow["rank"], 1)
        self.assertEqual(moscow["detail_status"], "full")
        self.assertEqual([segment["origin"] for segment in moscow["segments"]], ["SVX", "SVO"])
        self.assertIn("Moscow gateway control", " ".join(report["answer_lines"]))


if __name__ == "__main__":
    unittest.main()
