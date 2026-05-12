from __future__ import annotations

import unittest

from flights_cli.domain.stop_policy import BUSINESS_DEFAULT_STOP_POLICY
from flights_cli.orchestrators.kb_assemble import _aggregate_stop_policy_summary


class AggregateStopPolicyTests(unittest.TestCase):
    def test_provider_aggregate_with_three_plus_is_filtered_out(self) -> None:
        offers = [
            {"id": "direct", "change_count": 0},
            {"id": "one-stop", "change_count": 1},
            {"id": "two-stop", "change_count": 2},
            {"id": "three-stop", "change_count": 3},
        ]
        filtered, diagnostics = _aggregate_stop_policy_summary(offers, BUSINESS_DEFAULT_STOP_POLICY)

        filtered_ids = {item["id"] for item in filtered}
        self.assertIn("direct", filtered_ids)
        self.assertIn("one-stop", filtered_ids)
        self.assertNotIn("two-stop", filtered_ids)
        self.assertNotIn("three-stop", filtered_ids)
        self.assertEqual(diagnostics["three_plus_suppressed_count"], 1)
        self.assertEqual(diagnostics["two_stop_suppressed_because_preferred_exists"], 1)

    def test_provider_aggregate_two_stop_suppressed_without_preferred(self) -> None:
        offers = [
            {"id": "three-plus", "change_count": 3},
            {"id": "two-stop", "change_count": 2},
        ]
        filtered, diagnostics = _aggregate_stop_policy_summary(offers, BUSINESS_DEFAULT_STOP_POLICY)

        filtered_ids = [item["id"] for item in filtered]
        self.assertEqual(filtered_ids, ["two-stop"])
        self.assertEqual(diagnostics["preferred_candidate_count"], 0)
        self.assertEqual(diagnostics["two_stop_candidate_count"], 1)
        self.assertTrue(diagnostics["used_fallback_two_stop"])


if __name__ == "__main__":
    unittest.main()
