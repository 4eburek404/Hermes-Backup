#!/usr/bin/env python3
"""Executable specification for the Aeroflot booking-URL integration.

Scope
-----
This file specifies only the Aeroflot carrier contract:

    Aeroflot URL -> route/credentials -> Aeroflot API -> normalized itinerary

The general URL process, ICS rendering, artifact validation, and CLI success
envelope are specified in ``specs/url_cli_spec.py`` and are not repeated here.

Run from the skill root:

    python3 specs/aeroflot_spec.py

The HTTP transport boundary is replaced with the checked-in sanitized API
fixture.  URL parsing, route detection, Aeroflot request construction, API
response handling, itinerary conversion, and itinerary validation remain real.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE_PATH = ROOT / "specs" / "fixtures" / "aeroflot" / "pnr-view-v3.json"
sys.path.insert(0, str(SCRIPTS))

AEROFLOT_BASE = "https://www.aeroflot.ru"
AEROFLOT_APP_URL = AEROFLOT_BASE + "/sb/pnr/app/ru-ru"
AEROFLOT_PNR_API = AEROFLOT_BASE + "/se/api/app/pnr/view/v3"
SYNTHETIC_KEY = "5da7002148b11050a6a14aaf19c109248a0dd95cb94d03a91a1fb124765b00d7"
EXPECTED_LOCATOR = "ABC123"
AEROFLOT_SPA_URL = (
    f"{AEROFLOT_APP_URL}#/pnr?pnr_key={SYNTHETIC_KEY}&pnr_locator={EXPECTED_LOCATOR}"
)
AEROFLOT_QUERY_URL = (
    f"{AEROFLOT_APP_URL}?pnrKey={SYNTHETIC_KEY}"
    "&pnrLocator=abc123&utm_source=spec&campaign=tracking"
)
AEROFLOT_FIXTURE_TEXT = FIXTURE_PATH.read_text(encoding="utf-8")


def fixture_http_response(observed: list[dict[str, object]]):
    """Replace only Aeroflot's external HTTP transport with the fixture."""

    def request_raw(
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: int = 45,
        label: str = "HTTP request",
        sleep: object = None,
    ) -> tuple[int, str, str]:
        observed.append(
            {
                "url": url,
                "method": method,
                "headers": headers,
                "body": body,
                "timeout": timeout,
                "label": label,
                "sleep": sleep,
            }
        )
        return 200, "application/json; charset=utf-8", AEROFLOT_FIXTURE_TEXT

    return request_raw


class AeroflotCarrierSpecification(unittest.TestCase):
    """Behavior required from supported Aeroflot booking URLs."""

    def test_supported_booking_url_families_use_fixture_and_normalize_itinerary(self) -> None:
        """App and locale-PNR URL families share the fixture-backed carrier flow."""
        from flight_calendar import carrier_http, itinerary_contract, parser

        app_path = "https://www.aeroflot.ru/sb/pnr/app/ru-ru"
        aliases = (
            ("pnrKey", "pnrLocator"),
            ("pnrKey", "pnr_locator"),
            ("pnr_key", "pnrLocator"),
            ("pnr_key", "pnr_locator"),
        )
        tracking = "&_ga=synthetic-ga&_k=synthetic-k&utm_source=spec&campaign=tracking"
        cases: list[tuple[str, str]] = []
        for fragment in ("", "#/pnr?"):
            for key_name, locator_name in aliases:
                separator = "" if fragment else "?"
                is_canonical_app_url = (
                    fragment == "#/pnr?"
                    and key_name == "pnr_key"
                    and locator_name == "pnr_locator"
                )
                extra = "" if is_canonical_app_url else tracking
                cases.append(
                    (
                        f"app-{fragment or 'query'}-{key_name}-{locator_name}",
                        app_path
                        + fragment
                        + separator
                        + f"{key_name}={SYNTHETIC_KEY}&{locator_name}={EXPECTED_LOCATOR}"
                        + extra,
                    )
                )
        for locale in ("ru-ru", "ru-en"):
            cases.append(
                (
                    f"locale-{locale}",
                    f"https://www.aeroflot.ru/{locale}/pnr/"
                    f"?pnrKey={SYNTHETIC_KEY}&pnrLocator={EXPECTED_LOCATOR}{tracking}",
                )
            )

        for case_name, url in cases:
            with self.subTest(case=case_name):
                observed: list[dict[str, object]] = []
                with mock.patch.object(
                    carrier_http,
                    "request_raw",
                    side_effect=fixture_http_response(observed),
                ):
                    itinerary = parser._build_itinerary_from_url(url, [])

                self.assertEqual(len(observed), 1)
                self.assertEqual(observed[0]["url"], AEROFLOT_PNR_API)
                itinerary_contract.validate_itinerary_semantics(itinerary)
                self.assertEqual(itinerary["pnr"], EXPECTED_LOCATOR)
                self.assertEqual(itinerary["booking_url"], AEROFLOT_SPA_URL)
                self.assertEqual(len(itinerary["flights"]), 2)

    def test_aeroflot_api_request_uses_the_supported_protocol_and_fixture(self) -> None:
        """The carrier flow sends the documented Aeroflot API request."""
        from flight_calendar import carrier_http, parser

        observed: list[dict[str, object]] = []
        with mock.patch.object(
            carrier_http,
            "request_raw",
            side_effect=fixture_http_response(observed),
        ):
            itinerary = parser._build_itinerary_from_url(AEROFLOT_QUERY_URL, [])

        self.assertEqual(len(observed), 1)
        request = observed[0]
        self.assertEqual(request["url"], AEROFLOT_PNR_API)
        self.assertEqual(request["method"], "POST")
        headers = request["headers"]
        self.assertIsInstance(headers, dict)
        for name, value in {
            "Content-Type": "application/json",
            "X-App-Identity": "0",
            "Origin": AEROFLOT_BASE,
            "Referer": AEROFLOT_APP_URL,
        }.items():
            self.assertEqual(headers[name], value)
        body = request["body"]
        self.assertIsInstance(body, bytes)
        self.assertEqual(
            json.loads(body.decode("utf-8")),
            {
                "pnr_locator": EXPECTED_LOCATOR,
                "pnr_key": SYNTHETIC_KEY,
                "lang": "ru",
                "country": "ru",
            },
        )
        self.assertEqual(itinerary["pnr"], EXPECTED_LOCATOR)

    def test_aeroflot_fixture_becomes_valid_expected_itinerary(self) -> None:
        """The raw fixture becomes the expected normalized itinerary."""
        from flight_calendar import carrier_http, parser

        observed: list[dict[str, object]] = []
        with mock.patch.object(
            carrier_http,
            "request_raw",
            side_effect=fixture_http_response(observed),
        ):
            itinerary = parser._build_itinerary_from_url(AEROFLOT_SPA_URL, [])

        self.assertEqual(itinerary["pnr"], EXPECTED_LOCATOR)
        self.assertEqual(itinerary["passenger"], "Example Alex")
        self.assertEqual(itinerary["ticket_number"], "000000")
        self.assertEqual(itinerary["booking_url"], AEROFLOT_SPA_URL)

        self.assertEqual(
            itinerary["flights"],
            [
                {
                    "flight_number": "SU9001",
                    "departure": {
                        "airport": "SVX",
                        "city": "Екатеринбург",
                        "local": "2037-09-23T13:30",
                        "tz": "Asia/Yekaterinburg",
                    },
                    "arrival": {
                        "airport": "SVO",
                        "city": "Москва",
                        "local": "2037-09-23T13:50",
                        "tz": "Europe/Moscow",
                    },
                    "aircraft": "Airbus A330-300",
                },
                {
                    "flight_number": "SU9002",
                    "departure": {
                        "airport": "SVO",
                        "city": "Москва",
                        "local": "2037-09-25T15:25",
                        "tz": "Europe/Moscow",
                    },
                    "arrival": {
                        "airport": "SVX",
                        "city": "Екатеринбург",
                        "local": "2037-09-25T19:50",
                        "tz": "Asia/Yekaterinburg",
                    },
                    "aircraft": "Boeing 737-800",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
