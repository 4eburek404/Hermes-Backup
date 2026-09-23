#!/usr/bin/env python3
"""Executable specification for raw booking-URL routing.

Required behavior:

    raw URL -> carrier selection -> same raw URL -> selected carrier adapter

The router may inspect only as much source structure as needed to identify the
carrier. It does not unwrap, redirect, canonicalize, or otherwise replace the
user's URL before provider dispatch. Carrier-specific source handling belongs
to the selected provider.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


URAL_DIRECT = (
    "https://service.uralairlines.ru/services"
    "?pnr=ABC123&lastName=IVANOV"
)
URAL_WRAPPER = (
    "https://tn-hgl.mckx.ru/c/SYNTHETIC_A/SYNTHETIC_B/SYNTHETIC_C/"
    f"?u={quote(URAL_DIRECT, safe='')}"
)
UTAIR_DIRECT = (
    "https://www.utair.ru/order-manage"
    "?rloc=ABC123&last_name=IVANOV"
)
UTAIR_WRAPPER = "https://click.mail.utair.io/z9suvw/SYNTHETIC_TOKEN"


def _minimal_itinerary() -> dict[str, object]:
    return {
        "flights": [
            {
                "flight_number": "XX1",
                "departure": {
                    "airport": "SVX",
                    "local": "2037-01-01T10:00",
                },
                "arrival": {
                    "airport": "DME",
                    "local": "2037-01-01T10:30",
                },
            }
        ]
    }


class ProviderRoutingSpecification(unittest.TestCase):
    def test_router_identifies_supported_carrier_sources_from_raw_url(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        cases = (
            (
                "https://www.aeroflot.ru/sb/pnr/app/ru-ru"
                "?pnr_locator=ABC123&pnr_key=" + "0" * 64,
                "aeroflot",
            ),
            (URAL_DIRECT, "ural"),
            (URAL_WRAPPER, "ural"),
            (UTAIR_DIRECT, "utair"),
            (UTAIR_WRAPPER, "utair"),
            (
                "https://flyredwings.com/booking/"
                "#/find/ABC123/ACCESS_KEY/Submit",
                "redwings",
            ),
            (
                "https://flyredwings.com/booking/"
                "#/booking/800345630/order",
                "redwings",
            ),
            (
                "https://myb.s7.ru/myb/manage-order"
                "?bookingId=ABC123&passengerId=ivanov",
                "s7",
            ),
        )

        for raw_url, expected in cases:
            with self.subTest(expected=expected):
                route = infer_build_route(
                    argparse.Namespace(url=None, url_file=None),
                    url_override=raw_url,
                )
                self.assertEqual(route["route"], expected)

    def test_ural_wrapper_reaches_ural_adapter_unchanged(self) -> None:
        from flight_calendar import parser
        from flight_calendar.carriers import ural

        observed: list[str] = []

        def build(raw_url: str) -> dict[str, object]:
            observed.append(raw_url)
            return _minimal_itinerary()

        with tempfile.TemporaryDirectory(prefix="provider-routing-ural.") as tmp:
            output = Path(tmp) / "flight.ics"
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                mock.patch.object(ural, "build_itinerary", side_effect=build),
                mock.patch.object(
                    parser,
                    "build_timezone_map",
                    return_value={
                        "SVX": "Asia/Yekaterinburg",
                        "DME": "Europe/Moscow",
                    },
                ),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                code = parser.main(
                    [
                        "--json",
                        "build",
                        "--url",
                        URAL_WRAPPER,
                        "--output",
                        str(output),
                    ]
                )

        self.assertEqual(code, 0, stdout.getvalue() + stderr.getvalue())
        self.assertEqual(observed, [URAL_WRAPPER])
        payload = json.loads(stdout.getvalue())
        self.assertIs(payload["ok"], True)

    def test_utair_wrapper_reaches_utair_adapter_before_redirect_resolution(self) -> None:
        from flight_calendar import carrier_http, parser
        from flight_calendar.carriers import utair

        observed: list[str] = []

        def build(raw_url: str) -> dict[str, object]:
            observed.append(raw_url)
            return _minimal_itinerary()

        with tempfile.TemporaryDirectory(prefix="provider-routing-utair.") as tmp:
            output = Path(tmp) / "flight.ics"
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                mock.patch.object(utair, "build_itinerary", side_effect=build),
                mock.patch.object(
                    carrier_http,
                    "resolve_redirect_url",
                    side_effect=AssertionError(
                        "redirect resolution must not happen before provider dispatch"
                    ),
                ),
                mock.patch.object(
                    parser,
                    "build_timezone_map",
                    return_value={
                        "SVX": "Asia/Yekaterinburg",
                        "DME": "Europe/Moscow",
                    },
                ),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                code = parser.main(
                    [
                        "--json",
                        "build",
                        "--url",
                        UTAIR_WRAPPER,
                        "--output",
                        str(output),
                    ]
                )

        self.assertEqual(code, 0, stdout.getvalue() + stderr.getvalue())
        self.assertEqual(observed, [UTAIR_WRAPPER])
        payload = json.loads(stdout.getvalue())
        self.assertIs(payload["ok"], True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
