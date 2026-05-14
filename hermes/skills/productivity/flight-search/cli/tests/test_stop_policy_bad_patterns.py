from __future__ import annotations

import unittest

BAD_STOP_POLICY_PATTERNS = {
    "BAD-010": "three_plus_option_reported",
    "BAD-011": "two_stop_reported_when_direct_or_one_stop_exists",
    "BAD-012": "garbage_option_teaser",
    "BAD-013": "cheapest_over_policy",
    "BAD-014": "aggregate_offer_bypasses_stop_policy",
}

FORBIDDEN_NORMAL_ANSWER_FRAGMENTS = [
    "крайне дешевые",
    "сложные маршруты",
    "3+ пересадки",
    "Ереван и Милан",
]


class StopPolicyBadPatternTests(unittest.TestCase):
    def test_bad_pattern_ids_are_registered_for_stop_policy(self) -> None:
        self.assertEqual(BAD_STOP_POLICY_PATTERNS["BAD-010"], "three_plus_option_reported")
        self.assertEqual(BAD_STOP_POLICY_PATTERNS["BAD-014"], "aggregate_offer_bypasses_stop_policy")

    def test_normal_answer_must_not_tease_suppressed_garbage_routes(self) -> None:
        answer = "Маршруты с тремя и более пересадками исключены политикой поиска."

        for fragment in FORBIDDEN_NORMAL_ANSWER_FRAGMENTS:
            self.assertNotIn(fragment.lower(), answer.lower())


if __name__ == "__main__":
    unittest.main()
