from __future__ import annotations

import unittest

from flights_cli.domain.stop_policy import (
    BUSINESS_DEFAULT_STOP_POLICY,
    StopPolicy,
    filter_provider_offers,
    offer_stop_metrics,
    resolve_stop_policy,
    select_best_stop_tier,
    stop_tier,
)


class StopPolicyTests(unittest.TestCase):
    def test_direct_only_zero_cap_does_not_claim_two_stop_tier(self) -> None:
        policy = resolve_stop_policy(
            max_connections=0,
            tier2_max_connections=0,
        )

        self.assertFalse(policy.allow_two_stop_tier)
        self.assertEqual(policy.preferred_max_connections, 0)
        self.assertEqual(policy.tier2_max_connections, 0)
        self.assertEqual(policy.hard_max_connections, 0)

    def test_request_limits_resolve_once_without_default_policy_override(self) -> None:
        policy = resolve_stop_policy(
            max_connections=1,
            tier2_max_connections=3,
        )

        self.assertEqual(policy.preferred_max_connections, 1)
        self.assertEqual(policy.hard_max_connections, 3)
        self.assertEqual(policy.tier2_max_connections, 3)
        self.assertFalse(policy.suppress_three_plus)

    def test_stop_policy_clamps_programmatic_limits_to_three_connections(self) -> None:
        policy = resolve_stop_policy(
            max_connections=4,
            tier2_max_connections=9,
        )

        self.assertEqual(policy.preferred_max_connections, 3)
        self.assertEqual(policy.hard_max_connections, 3)
        self.assertFalse(policy.suppress_three_plus)

    def test_stop_tier_metrics(self) -> None:
        self.assertEqual(stop_tier(0), "T0_DIRECT")
        self.assertEqual(stop_tier(1), "T1_ONE_STOP")
        self.assertEqual(stop_tier(2), "T2_TWO_STOP")
        self.assertEqual(stop_tier(3), "T3_THREE_PLUS")

    def test_stop_policy_selects_preferred_tier_before_frontier(self) -> None:
        one_stop = {"id": "one", "journeys": [{"segments": [{}, {}]}]}
        two_stop = {"id": "two", "journeys": [{"segments": [{}, {}, {}]}]}

        selected = select_best_stop_tier(
            [two_stop, one_stop], preferred_max_connections=1
        )

        self.assertEqual(selected, [one_stop])

    def test_provider_filter_uses_typed_hard_cap(self) -> None:
        policy = StopPolicy(name="one_stop_only", hard_max_connections=1)
        one_stop = {
            "id": "one-stop",
            "segments": [
                {"origin": "SVX", "destination": "SVO"},
                {"origin": "SVO", "destination": "AMS"},
            ],
        }
        two_stop = {
            "id": "two-stop",
            "segments": [
                {"origin": "SVX", "destination": "SVO"},
                {"origin": "SVO", "destination": "IST"},
                {"origin": "IST", "destination": "AMS"},
            ],
        }
        filtered, stats = filter_provider_offers([two_stop, one_stop], policy=policy)

        self.assertEqual(filtered, [one_stop])
        self.assertEqual(stats["raw_offer_count"], 2)
        self.assertEqual(stats["suppressed_three_plus_count"], 1)
        self.assertEqual(BUSINESS_DEFAULT_STOP_POLICY.hard_max_connections, 2)

    def test_flat_round_trip_segments_are_counted_per_direction(self) -> None:
        metrics = offer_stop_metrics(
            {
                "segments": [
                    {"direction": "outbound"},
                    {"direction": "outbound"},
                    {"direction": "return"},
                    {"direction": "return"},
                    {"direction": "return"},
                ]
            }
        )

        self.assertEqual(metrics["connection_counts_by_journey"], [1, 2])
        self.assertEqual(metrics["max_connections_per_journey"], 2)
        self.assertEqual(metrics["stop_tier"], "T2_TWO_STOP")


if __name__ == "__main__":
    unittest.main()
