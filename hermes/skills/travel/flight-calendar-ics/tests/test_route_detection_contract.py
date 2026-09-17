"""Route detection contract for compact URL sources."""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


class RouteDetectionContractTests(unittest.TestCase):
    def test_s7_manage_order_without_required_params_is_insufficient_and_redacted(
        self,
    ) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        args = argparse.Namespace(
            url=None,
            url_file=None,
        )

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                args,
                url_override="https://myb.s7.ru/myb/manage-order?bookingId=ABC123",
            )

        self.assertEqual(ctx.exception.code, "route_input_insufficient")
        self.assertNotIn("ABC123", str(ctx.exception))
        self.assertNotIn("bookingId=", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
