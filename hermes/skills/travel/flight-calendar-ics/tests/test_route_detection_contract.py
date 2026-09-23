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
    def _assert_route_unknown(self, url: str) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override=url,
            )

        self.assertEqual(ctx.exception.code, "route_unknown")

    def test_aeroflot_requires_https_exact_host_and_app_path(self) -> None:
        key = "0" * 64
        cases = (
            "http://www.aeroflot.ru/sb/pnr/app/ru-ru"
            f"?pnr_key={key}&pnr_locator=ABC123",
            "https://foo.aeroflot.ru/sb/pnr/app/ru-ru"
            f"?pnr_key={key}&pnr_locator=ABC123",
            "https://www.aeroflot.ru/random"
            f"?pnr_key={key}&pnr_locator=ABC123",
        )
        for url in cases:
            with self.subTest(url=url.split("?", 1)[0]):
                self._assert_route_unknown(url)

    def test_ural_requires_https_exact_service_host(self) -> None:
        cases = (
            "http://service.uralairlines.ru/?pnr=ABC123&lastName=IVANOV",
            "https://foo.uralairlines.ru/?pnr=ABC123&lastName=IVANOV",
        )
        for url in cases:
            with self.subTest(url=url.split("?", 1)[0]):
                self._assert_route_unknown(url)

    def test_utair_direct_requires_https_exact_host_and_manage_path(self) -> None:
        cases = (
            "http://www.utair.ru/order-manage?rloc=ABC123&last_name=IVANOV",
            "https://foo.utair.ru/order-manage?rloc=ABC123&last_name=IVANOV",
            "https://www.utair.ru/random-path?rloc=ABC123&last_name=IVANOV",
        )
        for url in cases:
            with self.subTest(url=url.split("?", 1)[0]):
                self._assert_route_unknown(url)

    def test_redwings_requires_https_exact_host_and_booking_path(self) -> None:
        cases = (
            "http://flyredwings.com/booking/#/find/ABC123/ACCESS_KEY/Submit",
            "https://foo.flyredwings.com/booking/#/find/ABC123/ACCESS_KEY/Submit",
            "https://wz.webskyx.com/booking/#/find/ABC123/ACCESS_KEY/Submit",
            "https://flyredwings.com/random#/find/ABC123/ACCESS_KEY/Submit",
        )
        for url in cases:
            with self.subTest(url=url.split("#", 1)[0]):
                self._assert_route_unknown(url)

    def test_s7_requires_https_exact_host_and_manage_order_path(self) -> None:
        cases = (
            "http://myb.s7.ru/myb/manage-order?bookingId=ABC123&passengerId=ivanov",
            "https://www.s7.ru/myb/manage-order?bookingId=ABC123&passengerId=ivanov",
            "https://foo.s7.ru/myb/manage-order?bookingId=ABC123&passengerId=ivanov",
            "https://myb.s7.ru/random?bookingId=ABC123&passengerId=ivanov",
        )
        for url in cases:
            with self.subTest(url=url.split("?", 1)[0]):
                self._assert_route_unknown(url)

    def test_aeroflot_fingerprint_routes_without_credentials(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        base = "https://www.aeroflot.ru/sb/pnr/app/ru-ru"
        for url in (base, base + "?tracking=campaign", base + "#/pnr"):
            with self.subTest(url=url):
                route = infer_build_route(
                    argparse.Namespace(url=None, url_file=None),
                    url_override=url,
                )
                self.assertEqual(route["route"], "aeroflot")

    def test_aeroflot_wrong_path_remains_unknown_without_credentials(self) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override=(
                    "https://www.aeroflot.ru/random"
                ),
            )

        self.assertEqual(ctx.exception.code, "route_unknown")

    def test_trusted_fingerprints_route_without_source_data(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        cases = (
            ("https://service.uralairlines.ru/", "ural"),
            ("https://www.utair.ru/order-manage", "utair"),
            ("https://flyredwings.com/booking/", "redwings"),
            ("https://myb.s7.ru/myb/manage-order", "s7"),
        )
        for url, expected_route in cases:
            with self.subTest(url=url):
                route = infer_build_route(
                    argparse.Namespace(url=None, url_file=None),
                    url_override=url,
                )
                self.assertEqual(route["route"], expected_route)

    def test_utair_mail_wrapper_is_not_a_carrier_fingerprint(self) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override="https://click.mail.utair.io/z9suvw/SYNTHETIC_TOKEN",
            )
        self.assertEqual(ctx.exception.code, "route_unknown")

    def test_ural_canonical_source_remains_ural(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        route = infer_build_route(
            argparse.Namespace(url=None, url_file=None),
            url_override=(
                "https://service.uralairlines.ru/services"
                "?pnr=ABC123&lastName=IVANOV"
            ),
        )

        self.assertEqual(route["route"], "ural")

    def test_mail_wrapper_is_not_a_carrier_fingerprint(self) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        target = (
            "https://service.uralairlines.ru/services"
            "?pnr=ABC123&lastName=IVANOV"
        )
        wrapper = (
            "https://tn-hgl.mckx.ru/c/SYNTHETIC_A/SYNTHETIC_B/SYNTHETIC_C/"
            f"?u={quote(target, safe='')}"
        )
        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override=wrapper,
            )
        self.assertEqual(ctx.exception.code, "route_unknown")

    def test_redwings_canonical_find_source_remains_redwings(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        route = infer_build_route(
            argparse.Namespace(url=None, url_file=None),
            url_override=(
                "https://flyredwings.com/booking/"
                "#/find/ABC123/ACCESS_KEY/Submit"
            ),
        )

        self.assertEqual(route["route"], "redwings")

    def test_redwings_order_fragment_still_routes_to_adapter(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        route = infer_build_route(
            argparse.Namespace(url=None, url_file=None),
            url_override="https://flyredwings.com/booking/#/booking/ORDER123/order",
        )

        self.assertEqual(route["route"], "redwings")

    def test_s7_manage_order_fingerprint_detects_s7(self) -> None:
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

    def test_s7_manage_order_without_required_params_still_detects_s7(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        route = infer_build_route(
            argparse.Namespace(url=None, url_file=None),
            url_override="https://myb.s7.ru/myb/manage-order?bookingId=ABC123",
        )

        self.assertEqual(route["route"], "s7")


if __name__ == "__main__":
    unittest.main()
