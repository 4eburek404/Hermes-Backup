from __future__ import annotations

import unittest

from flights_cli.domain.stop_metrics import stop_tier


class StopPolicyTests(unittest.TestCase):
    def test_stop_tier_metrics(self) -> None:
        self.assertEqual(stop_tier(0), "T0_DIRECT")
        self.assertEqual(stop_tier(1), "T1_ONE_STOP")
        self.assertEqual(stop_tier(2), "T2_TWO_STOP")
        self.assertEqual(stop_tier(3), "T3_THREE_PLUS")


if __name__ == "__main__":
    unittest.main()
