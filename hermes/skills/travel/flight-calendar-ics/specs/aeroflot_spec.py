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

import argparse
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
SYNTHETIC_KEY = "0" * 64
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

    def test_supported_url_shapes_route_and_normalize_credentials(self) -> None:
        """SPA and query forms accept their aliases and ignore tracking fields."""
        from flight_calendar.carriers import aeroflot
        from flight_calendar.route_detection import infer_build_route

        cases = (
            (AEROFLOT_SPA_URL, EXPECTED_LOCATOR),
            (AEROFLOT_QUERY_URL, EXPECTED_LOCATOR),
        )
        for url, expected_locator in cases:
            with self.subTest(url_shape="spa" if "#" in url else "query"):
                route = infer_build_route(
                    argparse.Namespace(url=None, url_file=None), url_override=url
                )
                self.assertEqual(route["route"], "aeroflot")

                locator, key, normalized_url = aeroflot.parse_pnr_source(
                    url, None, None
                )
                self.assertEqual(locator, expected_locator)
                self.assertEqual(key, SYNTHETIC_KEY)
                self.assertEqual(normalized_url, url)

    def test_aeroflot_api_request_uses_the_supported_protocol_and_fixture(self) -> None:
        """Parsed credentials are sent to the documented Aeroflot API contract."""
        from flight_calendar import carrier_http
        from flight_calendar.carriers import aeroflot

        locator, key, _normalized_url = aeroflot.parse_pnr_source(
            AEROFLOT_QUERY_URL, None, None
        )
        observed: list[dict[str, object]] = []
        with mock.patch.object(
            carrier_http,
            "request_raw",
            side_effect=fixture_http_response(observed),
        ):
            data = aeroflot.fetch_aeroflot_pnr(locator, key)

        self.assertEqual(len(observed), 1)
        request = observed[0]
        self.assertEqual(request["url"], AEROFLOT_PNR_API)
        self.assertEqual(request["method"], "POST")
        self.assertEqual(
            request["headers"],
            {
                "Content-Type": "application/json",
                "X-App-Identity": "0",
                "Origin": AEROFLOT_BASE,
                "Referer": AEROFLOT_APP_URL,
            },
        )
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
        self.assertEqual(data["pnr_locator"], EXPECTED_LOCATOR)
        self.assertEqual(len(data["legs"]), 2)

    def test_aeroflot_fixture_becomes_valid_expected_itinerary(self) -> None:
        """The sanitized API response produces the expected normalized flights."""
        from flight_calendar import itinerary_contract
        from flight_calendar.carriers import aeroflot

        api_response = json.loads(AEROFLOT_FIXTURE_TEXT)
        data = aeroflot.require_success_data(api_response)
        itinerary = aeroflot.convert_to_itinerary(
            data,
            {"SVX": "Asia/Yekaterinburg", "SVO": "Europe/Moscow"},
            booking_url=AEROFLOT_SPA_URL,
        )

        itinerary_contract.validate_itinerary_schema(itinerary)
        itinerary_contract.validate_itinerary_semantics(itinerary)
        self.assertEqual(
            itinerary["schema_version"], "flight-calendar-ics-itinerary.v1"
        )
        self.assertEqual(itinerary["pnr"], EXPECTED_LOCATOR)
        self.assertEqual(itinerary["passengers"], ["Example Alex", "Test Maria"])
        self.assertEqual(itinerary["ticket_number"], "000000")
        self.assertEqual(itinerary["booking_url"], AEROFLOT_SPA_URL)

        flights = itinerary["flights"]
        self.assertEqual(len(flights), 2)
        self.assertEqual(
            flights,
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
                    "status": "confirmed",
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
                    "status": "confirmed",
                    "aircraft": "Boeing 737-800",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
