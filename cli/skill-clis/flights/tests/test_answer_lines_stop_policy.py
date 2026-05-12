from __future__ import annotations

import unittest

from flights_cli.services.agent_report import build_answer_lines


def make_report() -> dict:
    return {
        "recommended_options": [
            {
                "id": "recommended",
                "price_text": "10000 RUB",
                "elapsed": "2h",
                "segments": [
                    {
                        "direction": "outbound",
                        "flight_number": "SU232",
                        "origin": "SVX",
                        "destination": "DEL",
                    }
                ],
            }
        ],
        "priority_options": [],
        "aggregate_controls": [],
        "provider_failures": [],
        "through_fare_checks": [],
        "stop_policy": {
            "name": "business_default",
            "preferred_max_connections": 1,
            "fallback_max_connections": 2,
            "hard_max_connections": 2,
            "allow_two_stop_fallback": True,
            "suppress_three_plus": True,
        },
        "stop_policy_diagnostics": {
            "preferred_candidate_count": 1,
            "two_stop_candidate_count": 0,
            "used_fallback_two_stop": False,
            "used_two_stop_fallback": False,
            "three_plus_suppressed_count": 1,
            "two_stop_suppressed_because_preferred_exists": 0,
            "suppressed_by_policy_count": 1,
            "garbage_options_hidden_from_answer": True,
        },
    }


class AnswerLinesStopPolicyTests(unittest.TestCase):
    def test_answer_lines_do_not_explain_suppressed_garbage_routes(self) -> None:
        lines = build_answer_lines(make_report())
        forbidden = [
            "крайне дешевые",
            "сложные маршруты",
            "3+ пересадки",
            "Ереван и Милан",
        ]
        for phrase in forbidden:
            self.assertTrue(
                all(phrase.lower() not in line.lower() for line in lines),
                f"found forbidden phrase in answer lines: {phrase}",
            )


if __name__ == "__main__":
    unittest.main()
