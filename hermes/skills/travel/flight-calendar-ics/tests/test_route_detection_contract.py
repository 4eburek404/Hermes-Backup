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

    def test_aeroflot_adapter_aliases_are_complete_in_query_and_spa(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        key = "0" * 64
        alias_pairs = (
            ("pnrKey", "pnrLocator"),
            ("pnrKey", "pnr_locator"),
            ("pnr_key", "pnrLocator"),
            ("pnr_key", "pnr_locator"),
        )
        for fragment in ("", "#/pnr?"):
            for key_name, locator_name in alias_pairs:
                with self.subTest(fragment=fragment, key=key_name, locator=locator_name):
                    separator = "" if fragment else "?"
                    url = (
                        "https://www.aeroflot.ru/sb/pnr/app/ru-ru"
                        + fragment
                        + separator
                        + f"{key_name}={key}&{locator_name}=ABC123"
                    )
                    route = infer_build_route(
                        argparse.Namespace(url=None, url_file=None),
                        url_override=url,
                    )
                    self.assertEqual(route["route"], "aeroflot")

    def test_aeroflot_unsupported_case_variant_is_input_insufficient(self) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override=(
                    "https://www.aeroflot.ru/sb/pnr/app/ru-ru"
                    "?PNRKEY=" + "0" * 64 + "&pnrLocator=ABC123"
                ),
            )

        self.assertEqual(ctx.exception.code, "route_input_insufficient")

    def test_ural_adapter_aliases_are_complete(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        cases = (
            ("pnr", "lastName"),
            ("pnrNumber", "lastName"),
            ("pnrnumber", "lastName"),
            ("pnr", "lastname"),
            ("pnr", "surname"),
        )
        for locator_name, surname_name in cases:
            with self.subTest(locator=locator_name, surname=surname_name):
                route = infer_build_route(
                    argparse.Namespace(url=None, url_file=None),
                    url_override=(
                        "https://service.uralairlines.ru/?"
                        f"{locator_name}=ABC123&{surname_name}=IVANOV"
                    ),
                )
                self.assertEqual(route["route"], "ural")

    def test_ural_unsupported_case_variant_is_input_insufficient(self) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override="https://service.uralairlines.ru/?PNR=ABC123&lastName=IVANOV",
            )

        self.assertEqual(ctx.exception.code, "route_input_insufficient")

    def test_utair_adapter_aliases_are_complete(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        cases = (
            ("rloc", "last_name"),
            ("RLOC", "last_name"),
            ("pnr", "last_name"),
            ("rloc", "lastName"),
            ("rloc", "lastname"),
            ("rloc", "surname"),
        )
        for locator_name, surname_name in cases:
            with self.subTest(locator=locator_name, surname=surname_name):
                route = infer_build_route(
                    argparse.Namespace(url=None, url_file=None),
                    url_override=(
                        "https://www.utair.ru/order-manage?"
                        f"{locator_name}=ABC123&{surname_name}=IVANOV"
                    ),
                )
                self.assertEqual(route["route"], "utair")

    def test_utair_unsupported_case_variant_is_input_insufficient(self) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override="https://www.utair.ru/order-manage?Rloc=ABC123&last_name=IVANOV",
            )

        self.assertEqual(ctx.exception.code, "route_input_insufficient")

    def test_s7_adapter_aliases_are_complete_independently(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        cases = (
            ("bookingId", "passengerId"),
            ("bookingId", "passenger_id"),
            ("booking_id", "passengerId"),
            ("booking_id", "passenger_id"),
        )
        for booking_name, passenger_name in cases:
            with self.subTest(booking=booking_name, passenger=passenger_name):
                route = infer_build_route(
                    argparse.Namespace(url=None, url_file=None),
                    url_override=(
                        "https://myb.s7.ru/myb/manage-order?"
                        f"{booking_name}=ABC123&{passenger_name}=ivanov"
                    ),
                )
                self.assertEqual(route["route"], "s7")

    def test_s7_unsupported_case_variant_is_input_insufficient(self) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override=(
                    "https://myb.s7.ru/myb/manage-order?"
                    "BookingId=ABC123&passengerId=ivanov"
                ),
            )

        self.assertEqual(ctx.exception.code, "route_input_insufficient")

    def test_redwings_find_fragment_without_submit_is_input_insufficient(self) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override="https://flyredwings.com/booking/#/find/ABC123/ACCESS_KEY",
            )

        self.assertEqual(ctx.exception.code, "route_input_insufficient")

    def test_ural_canonical_source_remains_ural(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        route = infer_build_route(
            argparse.Namespace(url=None, url_file=None),
            url_override=(
                "https://service.uralairlines.ru/"
                "?pnr=ABC123&lastName=IVANOV"
            ),
        )

        self.assertEqual(route["route"], "ural")

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

    def test_redwings_order_page_remains_input_insufficient(self) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.route_detection import infer_build_route

        with self.assertRaises(CliFailure) as ctx:
            infer_build_route(
                argparse.Namespace(url=None, url_file=None),
                url_override="https://flyredwings.com/booking/#/booking/ORDER123/order",
            )

        self.assertEqual(ctx.exception.code, "route_input_insufficient")

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
