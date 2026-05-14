from __future__ import annotations

import argparse
import unittest

from flights_cli.domain.stop_metrics import candidate_stop_metrics, stop_tier
from flights_cli.services.ranking import rank_candidate_list


def segment(origin: str, destination: str, dep: str, arr: str, flight: str) -> dict:
    return {
        "flight_number": flight,
        "carrier": flight[:2],
        "marketing_carrier": flight[:2],
        "operating_carrier": flight[:2],
        "origin": origin,
        "destination": destination,
        "departure_at": dep,
        "arrival_at": arr,
    }


def candidate(identifier: str, airports: list[str], price: int) -> dict:
    segments = []
    base_day = "2026-06-01"
    for index, (origin, destination) in enumerate(zip(airports, airports[1:]), 1):
        dep_hour = 6 + index * 3
        arr_hour = dep_hour + 1
        segments.append(segment(origin, destination, f"{base_day}T{dep_hour:02d}:00:00+00:00", f"{base_day}T{arr_hour:02d}:00:00+00:00", f"SU{100 + index}"))
    return {
        "id": identifier,
        "price": price,
        "currency": "RUB",
        "ticketing": "single",
        "journeys": [{"direction": "outbound", "segments": segments}],
    }


def rank_args(**overrides: object) -> argparse.Namespace:
    values = {
        "profile": "balanced",
        "ticketing": "single",
        "min_same_airport_min": 60,
        "min_cross_airport_min": 60,
        "max_reasons": 5,
        "only_carrier": None,
        "exclude_carrier": None,
        "prefer_carrier": None,
        "avoid_carrier": None,
        "include_filtered": 20,
        "stop_policy": "business-default",
        "max_connections": None,
        "fallback_max_connections": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class StopPolicyTests(unittest.TestCase):
    def test_stop_tier_metrics(self) -> None:
        self.assertEqual(stop_tier(0), "T0_DIRECT")
        self.assertEqual(stop_tier(1), "T1_ONE_STOP")
        self.assertEqual(stop_tier(2), "T2_TWO_STOP")
        self.assertEqual(stop_tier(3), "T3_THREE_PLUS")
        self.assertEqual(candidate_stop_metrics(candidate("three", ["SVX", "EVN", "MXP", "LIN", "AMS"], 1))["stop_tier"], "T3_THREE_PLUS")

    def test_direct_and_one_stop_exist_suppresses_two_stop(self) -> None:
        result = rank_candidate_list(
            [
                candidate("direct", ["SVX", "AMS"], 30000),
                candidate("one-stop", ["SVX", "IST", "AMS"], 25000),
                candidate("two-stop", ["SVX", "IST", "BEG", "AMS"], 10000),
            ],
            rank_args(),
        )

        self.assertEqual({item["id"] for item in result["ranked"]}, {"one-stop", "direct"})
        self.assertEqual(result["stop_policy_diagnostics"]["two_stop_suppressed_because_preferred_exists"], 1)
        self.assertFalse(result["stop_policy_diagnostics"]["used_two_stop_fallback"])

    def test_no_preferred_allows_two_stop_fallback(self) -> None:
        result = rank_candidate_list([candidate("two-stop", ["SVX", "IST", "BEG", "AMS"], 10000)], rank_args())

        self.assertEqual([item["id"] for item in result["ranked"]], ["two-stop"])
        self.assertTrue(result["stop_policy_diagnostics"]["used_two_stop_fallback"])
        self.assertEqual(result["ranked"][0]["validation_summary"]["stop_tier"], "T2_TWO_STOP")

    def test_three_plus_always_rejected_in_normal_policy(self) -> None:
        result = rank_candidate_list([candidate("garbage", ["SVX", "EVN", "MXP", "LIN", "AMS"], 1000)], rank_args())

        self.assertEqual(result["ranked"], [])
        self.assertEqual(result["stop_policy_diagnostics"]["three_plus_suppressed_count"], 1)
        self.assertEqual(result["carrier_policy"]["filtered"][0]["stop_tier"], "T3_THREE_PLUS")


if __name__ == "__main__":
    unittest.main()
