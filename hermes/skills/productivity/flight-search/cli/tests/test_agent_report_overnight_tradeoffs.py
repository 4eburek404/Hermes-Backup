from __future__ import annotations

import unittest

from helpers import CliSubprocessMixin


def leg_offer(
    offer_id: str,
    origin: str,
    destination: str,
    departure_at: str,
    arrival_at: str,
    price: int,
    flight_number: str,
) -> dict:
    return {
        "id": offer_id,
        "origin": origin,
        "destination": destination,
        "departure_airport": origin,
        "arrival_airport": destination,
        "departure_at": departure_at,
        "arrival_at": arrival_at,
        "price": price,
        "currency": "RUB",
        "segments": [
            {
                "origin": origin,
                "destination": destination,
                "departure_at": departure_at,
                "arrival_at": arrival_at,
                "flight_number": flight_number,
                "carrier": flight_number[:2],
            }
        ],
    }


class AgentReportOvernightTradeoffTests(CliSubprocessMixin, unittest.TestCase):
    def test_overnight_long_wait_is_visible_tradeoff_not_risk_penalty(self) -> None:
        payload = {
            "segment_results": [
                {
                    "direction": "outbound",
                    "leg": "origin_to_hub",
                    "query": {"origin": "TLS", "destination": "IST", "date": "2026-06-18", "currency": "RUB"},
                    "offers": [
                        leg_offer(
                            "tls-ist-evening",
                            "TLS",
                            "IST",
                            "2026-06-18T18:50:00+02:00",
                            "2026-06-18T23:25:00+03:00",
                            18000,
                            "TK1806",
                        )
                    ],
                },
                {
                    "direction": "outbound",
                    "leg": "hub_to_destination",
                    "query": {"origin": "IST", "destination": "SVX", "date": "2026-06-19", "currency": "RUB"},
                    "offers": [
                        leg_offer(
                            "ist-svx-next-day",
                            "IST",
                            "SVX",
                            "2026-06-19T12:50:00+03:00",
                            "2026-06-19T19:55:00+05:00",
                            17802,
                            "SU631",
                        )
                    ],
                },
            ]
        }

        assembled = self._assemble(payload, "--agent-report")
        report = assembled["data"]["agent_report"]
        option = report["recommended_options"][0]
        connection = option["connections"][0]

        tradeoff_codes = {item["code"] for item in connection.get("tradeoffs", [])}
        self.assertIn("long_wait", tradeoff_codes)
        self.assertIn("overnight_wait", tradeoff_codes)

        connection_risk_codes = {item["code"] for item in connection["risk"]["reasons"]}
        self.assertNotIn("long_layover", connection_risk_codes)
        self.assertNotIn("night_connection", connection_risk_codes)

        answer_text = "\n".join(report["answer_lines"]).lower()
        self.assertIn("connection trade-off", answer_text)
        self.assertIn("overnight", answer_text)
        self.assertIn("long wait", answer_text)


if __name__ == "__main__":
    unittest.main()
