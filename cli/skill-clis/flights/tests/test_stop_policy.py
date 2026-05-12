from __future__ import annotations

import unittest

from flights_cli.domain.stop_policy import BUSINESS_DEFAULT_STOP_POLICY
from flights_cli.services.stop_policy import apply_stop_policy_frontier


def synthetic_candidate(identifier: str, segment_count: int, *, viable: bool = True) -> dict:
    return {
        "id": identifier,
        "journeys": [
            {
                "segments": [
                    {"origin": f"AAA{i}", "destination": f"AAA{i+1}"}
                    for i in range(segment_count)
                ]
            }
        ],
        "ok": viable,
    }


class StopPolicyFilterTests(unittest.TestCase):
    def test_direct_and_one_stop_keep_two_stop_when_no_preferred(self) -> None:
        candidates = [
            synthetic_candidate("two_stop", 3),
            synthetic_candidate("three_plus", 4),
            synthetic_candidate("one_stop", 2),
            synthetic_candidate("direct", 1),
        ]
        accepted, diagnostics = apply_stop_policy_frontier(candidates, BUSINESS_DEFAULT_STOP_POLICY)

        accepted_ids = {item["id"] for item in accepted}
        self.assertIn("direct", accepted_ids)
        self.assertIn("one_stop", accepted_ids)
        self.assertNotIn("two_stop", accepted_ids)
        self.assertNotIn("three_plus", accepted_ids)
        self.assertEqual(diagnostics["preferred_candidate_count"], 2)
        self.assertEqual(diagnostics["two_stop_candidate_count"], 1)
        self.assertEqual(diagnostics["three_plus_suppressed_count"], 1)
        self.assertEqual(diagnostics["two_stop_suppressed_because_preferred_exists"], 1)
        self.assertFalse(diagnostics["used_fallback_two_stop"])

    def test_two_stop_allowed_only_when_preferred_missing(self) -> None:
        candidates = [
            synthetic_candidate("three_plus", 4),
            synthetic_candidate("two_stop", 3),
        ]
        accepted, diagnostics = apply_stop_policy_frontier(candidates, BUSINESS_DEFAULT_STOP_POLICY)

        accepted_ids = {item["id"] for item in accepted}
        self.assertIn("two_stop", accepted_ids)
        self.assertNotIn("three_plus", accepted_ids)
        self.assertEqual(diagnostics["preferred_candidate_count"], 0)
        self.assertEqual(diagnostics["two_stop_candidate_count"], 1)
        self.assertTrue(diagnostics["used_fallback_two_stop"])
        self.assertEqual(diagnostics["three_plus_suppressed_count"], 1)

    def test_three_plus_always_rejected(self) -> None:
        accepted, diagnostics = apply_stop_policy_frontier(
            [synthetic_candidate("three_plus", 4)],
            BUSINESS_DEFAULT_STOP_POLICY,
        )

        self.assertEqual(accepted, [])
        self.assertEqual(diagnostics["three_plus_suppressed_count"], 1)
        self.assertEqual(diagnostics["suppressed_by_policy_count"], 1)


if __name__ == "__main__":
    unittest.main()
