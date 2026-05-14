from __future__ import annotations

import unittest

from flights_cli.reporting.provider_aggregate_projector import aggregate_control_summary, provider_aggregate_candidate_options


def offer(identifier: str, changes: int) -> dict:
    return {
        "id": identifier,
        "price": 10000 + changes,
        "currency": "RUB",
        "change_count": changes,
        "duration_min": 400,
        "flight_numbers": [identifier.upper()],
        "carriers": ["SU"],
        "segments": [{"flight_number": identifier.upper(), "carrier": "SU", "origin": "SVX", "destination": "AMS", "departure_at": "2026-06-01T06:00:00+00:00", "arrival_at": "2026-06-01T10:00:00+00:00"}],
    }


def controls(top_offers: list[dict] | None = None) -> list[dict]:
    return [
        aggregate_control_summary(
            {
                "direction": "outbound",
                "origin": "SVX",
                "destination": "AMS",
                "date": "2026-06-01",
                "status": "ok",
                "provider": "kupibilet",
                "filters": {},
                "offer_count": 4,
                "raw_variant_count": 4,
                "top_offers": top_offers or [offer("direct", 0), offer("one-stop", 1), offer("two-stop", 2)],
                "error": None,
            }
        )
    ]


class ProviderAggregateStopPolicyTests(unittest.TestCase):
    def test_two_stop_projected_only_without_preferred_and_three_stop_never_projected(self) -> None:
        preferred = provider_aggregate_candidate_options(controls(), preferred_available=True)
        fallback = provider_aggregate_candidate_options(controls([offer("two-stop", 2)]), preferred_available=False)
        with_three_plus = provider_aggregate_candidate_options(
            controls([offer("direct", 0), offer("three-stop", 3), offer("one-stop", 1)]),
            preferred_available=False,
        )

        self.assertEqual([item["id"] for item in preferred], ["provider-aggregate:outbound:direct", "provider-aggregate:outbound:one-stop"])
        self.assertEqual([item["id"] for item in fallback], ["provider-aggregate:outbound:two-stop"])
        self.assertEqual([item["id"] for item in with_three_plus], ["provider-aggregate:outbound:direct", "provider-aggregate:outbound:one-stop"])
        self.assertTrue(all(item["stop_tier"] != "T3_THREE_PLUS" for item in preferred + fallback + with_three_plus))


if __name__ == "__main__":
    unittest.main()
