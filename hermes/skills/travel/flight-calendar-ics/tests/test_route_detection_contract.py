"""Route detection contract for compact URL sources."""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


class RouteDetectionContractTests(unittest.TestCase):
    def test_s7_manage_order_with_required_params_detects_s7(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        args = argparse.Namespace(
            url=None,
            url_file=None,
        )

        route = infer_build_route(
            args,
            url_override="https://myb.s7.ru/myb/manage-order?bookingId=ABC123&passengerId=ivanov",
        )

        self.assertEqual(route["route"], "s7")

    def test_unknown_host_with_s7_fields_is_route_unknown(self) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override=(
                    "https://evil.example/manage-order"
                    "?bookingId=ABC123&passengerId=ivanov"
                ),
            )

        self.assertEqual(ctx.exception.code, "route_unknown")
        self.assertNotIn("evil.example", str(ctx.exception))
        self.assertNotIn("ABC123", str(ctx.exception))
        self.assertNotIn("ivanov", str(ctx.exception))

    def test_unknown_host_with_ural_fields_is_route_unknown(self) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override=(
                    "https://evil.example/manage-order"
                    "?pnrNumber=ABC123&lastName=IVANOV"
                ),
            )

        self.assertEqual(ctx.exception.code, "route_unknown")
        self.assertNotIn("evil.example", str(ctx.exception))
        self.assertNotIn("ABC123", str(ctx.exception))
        self.assertNotIn("IVANOV", str(ctx.exception))

    def test_unknown_host_with_utair_fields_is_route_unknown(self) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override=(
                    "https://evil.example/manage-order"
                    "?rloc=ABC123&last_name=IVANOV"
                ),
            )

        self.assertEqual(ctx.exception.code, "route_unknown")
        self.assertNotIn("evil.example", str(ctx.exception))
        self.assertNotIn("ABC123", str(ctx.exception))
        self.assertNotIn("IVANOV", str(ctx.exception))

    def test_unknown_host_with_aeroflot_fields_is_route_unknown(self) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override=(
                    "https://evil.example/pnr"
                    "?pnr_key=" + "0" * 64 + "&pnr_locator=ABC123"
                ),
            )

        self.assertEqual(ctx.exception.code, "route_unknown")
        self.assertNotIn("evil.example", str(ctx.exception))
        self.assertNotIn("ABC123", str(ctx.exception))
        self.assertNotIn("0" * 64, str(ctx.exception))

    def test_unknown_host_with_redwings_fragment_is_route_unknown(self) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override=(
                    "https://evil.example/#/find/ABC123/ACCESS_KEY/Submit"
                ),
            )

        self.assertEqual(ctx.exception.code, "route_unknown")
        self.assertNotIn("evil.example", str(ctx.exception))
        self.assertNotIn("ABC123", str(ctx.exception))
        self.assertNotIn("ACCESS_KEY", str(ctx.exception))

    def test_unknown_tracker_wrapper_with_nested_ural_url_is_route_unknown(
        self,
    ) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        nested_ural_url = (
            "https://service.uralairlines.ru/?pnr=ABC123&lastName=IVANOV"
        )
        wrapper_url = (
            "https://tracker.example/click?u="
            + quote(nested_ural_url, safe="")
        )

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override=wrapper_url,
            )

        self.assertEqual(ctx.exception.code, "route_unknown")
        self.assertNotIn("tracker.example", str(ctx.exception))
        self.assertNotIn("service.uralairlines.ru", str(ctx.exception))
        self.assertNotIn("ABC123", str(ctx.exception))
        self.assertNotIn("IVANOV", str(ctx.exception))

    def test_arbitrary_wrapper_with_nested_supported_url_is_route_unknown(self) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        aeroflot_url = (
            "https://www.aeroflot.ru/sb/pnr/app/ru-ru"
            "#/pnr?pnr_key=" + "0" * 64 + "&pnr_locator=ABC123"
        )
        wrapper_url = "https://wrapper.example/?next=" + quote(aeroflot_url, safe="")

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override=wrapper_url,
            )

        self.assertEqual(ctx.exception.code, "route_unknown")
        self.assertNotIn("wrapper.example", str(ctx.exception))
        self.assertNotIn("www.aeroflot.ru", str(ctx.exception))
        self.assertNotIn("ABC123", str(ctx.exception))
        self.assertNotIn("0" * 64, str(ctx.exception))

    def test_s7_manage_order_without_required_params_is_insufficient_and_redacted(
        self,
    ) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override="https://myb.s7.ru/myb/manage-order?bookingId=ABC123",
            )

        self.assertEqual(ctx.exception.code, "route_input_insufficient")
        self.assertNotIn("ABC123", str(ctx.exception))
        self.assertNotIn("bookingId=", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
