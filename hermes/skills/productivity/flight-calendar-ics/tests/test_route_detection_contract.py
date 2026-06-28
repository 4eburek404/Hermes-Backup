"""Route detection contract for compact URL sources."""

from __future__ import annotations

import argparse
import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


class ExplodingUrlFile:
    def read_text(
        self, encoding: str = "utf-8"
    ) -> str:  # pragma: no cover - must not be called
        raise AssertionError("url_file was read despite url_override")


class RouteDetectionContractTests(unittest.TestCase):
    def test_url_override_detects_utair_without_reading_url_file(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        args = argparse.Namespace(
            input=None,
            url=None,
            url_file=ExplodingUrlFile(),
            pnr_locator=None,
            pnr_key=None,
            pnr=None,
            rloc=None,
            last_name=None,
            first_name=None,
            access_code=None,
        )

        route = infer_build_route(
            args,
            url_override="https://www.utair.ru/order-manage?rloc=ABC123&last_name=IVANOV",
        )

        self.assertEqual(route["route"], "utair")
        self.assertEqual(route["confidence"], 1.0)
        self.assertIn("host:utair.ru", route["evidence"])
        self.assertLessEqual(set(route), {"mode", "route", "confidence", "evidence"})

    def test_url_override_detects_s7_manage_order_without_reading_url_file(
        self,
    ) -> None:
        from flight_calendar.route_detection import infer_build_route

        args = argparse.Namespace(
            input=None,
            url=None,
            url_file=ExplodingUrlFile(),
            pnr_locator=None,
            pnr_key=None,
            pnr=None,
            rloc=None,
            last_name=None,
            first_name=None,
            access_code=None,
        )

        route = infer_build_route(
            args,
            url_override="https://myb.s7.ru/myb/manage-order?bookingId=ABC123&passengerId=ivanov",
        )

        self.assertEqual(route["route"], "s7")
        self.assertEqual(route["confidence"], 1.0)
        self.assertIn("host:myb.s7.ru", route["evidence"])
        self.assertIn("query_field:bookingId", route["evidence"])
        self.assertIn("query_field:passengerId", route["evidence"])
        self.assertLessEqual(set(route), {"mode", "route", "confidence", "evidence"})

    def test_s7_manage_order_without_required_params_is_insufficient_and_redacted(
        self,
    ) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        args = argparse.Namespace(
            input=None,
            url=None,
            url_file=ExplodingUrlFile(),
            pnr_locator=None,
            pnr_key=None,
            pnr=None,
            rloc=None,
            last_name=None,
            first_name=None,
            access_code=None,
        )

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                args,
                url_override="https://myb.s7.ru/myb/manage-order?bookingId=ABC123",
            )

        self.assertEqual(ctx.exception.code, "route_input_insufficient")
        self.assertEqual(ctx.exception.details.get("route"), "s7")
        self.assertNotIn("ABC123", str(ctx.exception))
        self.assertNotIn("bookingId=", str(ctx.exception))

    def test_click_mail_utair_is_not_a_route_detection_host(self) -> None:
        import flight_calendar.route_detection as route_detection

        source = inspect.getsource(route_detection)
        self.assertNotIn("click.mail.utair.io", source)


if __name__ == "__main__":
    unittest.main()
