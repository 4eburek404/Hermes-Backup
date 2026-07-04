from __future__ import annotations

import unittest

from flights_cli.domain.stop_metrics import candidate_stop_metrics, stop_tier


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
        segments.append(
            segment(
                origin,
                destination,
                f"{base_day}T{dep_hour:02d}:00:00+00:00",
                f"{base_day}T{arr_hour:02d}:00:00+00:00",
                f"SU{100 + index}",
            )
        )
    return {
        "id": identifier,
        "price": price,
        "currency": "RUB",
        "ticketing": "single",
        "journeys": [{"direction": "outbound", "segments": segments}],
    }


class StopPolicyTests(unittest.TestCase):
    def test_stop_tier_metrics(self) -> None:
        self.assertEqual(stop_tier(0), "T0_DIRECT")
        self.assertEqual(stop_tier(1), "T1_ONE_STOP")
        self.assertEqual(stop_tier(2), "T2_TWO_STOP")
        self.assertEqual(stop_tier(3), "T3_THREE_PLUS")
        self.assertEqual(
            candidate_stop_metrics(
                candidate("three", ["SVX", "EVN", "MXP", "LIN", "AMS"], 1)
            )["stop_tier"],
            "T3_THREE_PLUS",
        )


if __name__ == "__main__":
    unittest.main()
