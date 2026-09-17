#!/usr/bin/env python3
"""Executable specification for the Utair booking-URL integration.

Scope
-----
This file specifies only the Utair carrier contract:

    Utair URL -> route/credentials -> Utair API -> normalized itinerary

The general URL process, ICS rendering, artifact validation, and CLI success
 envelope are specified in ``specs/url_cli_spec.py`` and are not repeated here.

Run from the skill root::

    python3 specs/utair_spec.py

Only the external HTTP transport is replaced.  URL redirect handling, route
detection, Utair request construction, API response handling, itinerary
conversion, and itinerary validation remain real.
"""

from __future__ import annotations

import argparse
import json
import sys
import unittest
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE_PATH = ROOT / "specs" / "fixtures" / "utair" / "orders-v3.json"
sys.path.insert(0, str(SCRIPTS))

UTAIR_WEB_BASE = "https://www.utair.ru"
UTAIR_REDIRECT_URL = "https://click.mail.utair.io/z9suvw/fixture-token"
UTAIR_DIRECT_URL = (
    UTAIR_WEB_BASE
    + "/order-manage?rloc=ABC123&last_name=EXAMPLE"
    + "&utm_source=mail&utm_campaign=booking"
)
# Sanitized shape observed in the second, direct-from-site URL.
UTAIR_SITE_DIRECT_URL = (
    UTAIR_WEB_BASE
    + "/order-manage?rloc=SITE123&last_name=EXAMPLE"
    + "&utm_source=booking_success&utm_campaign=mail_link"
)
UTAIR_OAUTH_ENDPOINT = "https://b.utair.ru/oauth/token"
UTAIR_ORDERS_ENDPOINT = "https://b.utair.ru/api/v3/orders"
EXPECTED_LOCATOR = "ABC123"
EXPECTED_SURNAME = "EXAMPLE"
SYNTHETIC_ACCESS_TOKEN = "synthetic-access-token"
UTAIR_FIXTURE_TEXT = FIXTURE_PATH.read_text(encoding="utf-8")


def fixture_http_response(observed: list[dict[str, Any]]):
    """Replace only Utair's external API transport with checked-in data."""

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
        if url == UTAIR_OAUTH_ENDPOINT:
            return 200, "application/json; charset=utf-8", json.dumps(
                {"access_token": SYNTHETIC_ACCESS_TOKEN, "token_type": "Bearer"}
            )
        if url.startswith(UTAIR_ORDERS_ENDPOINT + "?"):
            return 200, "application/json; charset=utf-8", UTAIR_FIXTURE_TEXT
        raise AssertionError(f"unexpected Utair endpoint: {url.split('?', 1)[0]}")

    return request_raw


class UtairCarrierSpecification(unittest.TestCase):
    """Behavior required from supported Utair booking URLs."""

    def test_redirect_url_routes_and_normalizes_credentials(self) -> None:
        """The real click-mail shape resolves to the Utair manage URL contract."""
        from flight_calendar.redirect_resolution import resolve_known_booking_redirect
        from flight_calendar.route_detection import infer_build_route
        from flight_calendar import carrier_http
        from flight_calendar.carriers import utair

        class FakeResponse:
            status_code = 307
            headers = {"Location": UTAIR_DIRECT_URL}

        with mock.patch.object(
            carrier_http._requests,
            "request",
            return_value=FakeResponse(),
        ):
            resolved_url = resolve_known_booking_redirect(UTAIR_REDIRECT_URL)

        self.assertEqual(urlparse(resolved_url).hostname, "www.utair.ru")
        route = infer_build_route(
            argparse.Namespace(url=None, url_file=None), url_override=resolved_url
        )
        self.assertEqual(route["route"], "utair")

        locator, surname, normalized_url = utair.parse_utair_source(
            resolved_url, None, None
        )
        self.assertEqual(locator, EXPECTED_LOCATOR)
        self.assertEqual(surname, EXPECTED_SURNAME)
        self.assertEqual(normalized_url, UTAIR_DIRECT_URL)
        self.assertEqual(
            parse_qs(urlparse(normalized_url).query)["utm_source"], ["mail"]
        )

    def test_direct_site_url_routes_without_redirect_and_normalizes_credentials(
        self,
    ) -> None:
        """The observed site URL is already a carrier booking URL."""
        from flight_calendar import carrier_http
        from flight_calendar.carriers import utair
        from flight_calendar.route_detection import infer_build_route
        from flight_calendar.redirect_resolution import resolve_known_booking_redirect

        parsed = urlparse(UTAIR_SITE_DIRECT_URL)
        self.assertEqual(parsed.hostname, "www.utair.ru")
        self.assertEqual(parsed.path, "/order-manage")
        self.assertEqual(
            sorted(parse_qs(parsed.query)),
            ["last_name", "rloc", "utm_campaign", "utm_source"],
        )

        with mock.patch.object(
            carrier_http,
            "resolve_redirect_url",
            side_effect=AssertionError("direct Utair URL must not be fetched"),
        ):
            resolved_url = resolve_known_booking_redirect(UTAIR_SITE_DIRECT_URL)

        self.assertEqual(resolved_url, UTAIR_SITE_DIRECT_URL)
        route = infer_build_route(
            argparse.Namespace(url=None, url_file=None), url_override=resolved_url
        )
        self.assertEqual(route["route"], "utair")
        locator, surname, normalized_url = utair.parse_utair_source(
            resolved_url, None, None
        )
        self.assertEqual(locator, "SITE123")
        self.assertEqual(surname, "EXAMPLE")
        self.assertEqual(normalized_url, UTAIR_SITE_DIRECT_URL)

    def test_oauth_and_orders_requests_follow_the_real_api_contract(self) -> None:
        """Production request construction uses the observed OAuth and orders API."""
        from flight_calendar import carrier_http
        from flight_calendar.carriers import utair

        observed: list[dict[str, Any]] = []
        with mock.patch.object(
            carrier_http,
            "request_raw",
            side_effect=fixture_http_response(observed),
        ):
            token = utair.fetch_utair_token()
            data = utair.fetch_utair_orders(
                EXPECTED_LOCATOR, EXPECTED_SURNAME, token=token
            )

        self.assertEqual(token, SYNTHETIC_ACCESS_TOKEN)
        self.assertEqual(len(observed), 2)

        oauth = observed[0]
        self.assertEqual(oauth["url"], UTAIR_OAUTH_ENDPOINT)
        self.assertEqual(oauth["method"], "POST")
        oauth_headers = oauth["headers"]
        self.assertIsInstance(oauth_headers, dict)
        self.assertEqual(
            oauth_headers["Content-Type"], "application/x-www-form-urlencoded"
        )
        oauth_body = oauth["body"]
        self.assertIsInstance(oauth_body, bytes)
        self.assertEqual(
            parse_qs(oauth_body.decode("utf-8")),
            {"client_id": ["website_client"], "grant_type": ["client_credentials"]},
        )

        orders = observed[1]
        self.assertEqual(
            urlparse(str(orders["url"]))._replace(query="").geturl(),
            UTAIR_ORDERS_ENDPOINT,
        )
        self.assertEqual(orders["method"], "GET")
        order_query = parse_qs(urlparse(str(orders["url"])).query)
        self.assertEqual(order_query["filters[locator]"], [EXPECTED_LOCATOR])
        self.assertEqual(
            order_query["filters[passenger_lastname]"], [EXPECTED_SURNAME]
        )
        order_headers = orders["headers"]
        self.assertIsInstance(order_headers, dict)
        self.assertEqual(
            order_headers["Authorization"], f"Bearer {SYNTHETIC_ACCESS_TOKEN}"
        )
        self.assertEqual(list(data), ["future", "past"])
        self.assertEqual(len(utair.collect_orders(data)), 1)

    def test_sanitized_fixture_becomes_valid_expected_itinerary(self) -> None:
        """The actual response shape produces the normalized itinerary contract."""
        from flight_calendar import itinerary_contract
        from flight_calendar.carriers import utair

        api_response = json.loads(UTAIR_FIXTURE_TEXT)
        itinerary = utair.convert_to_itinerary(
            api_response,
            {"SVX": "Asia/Yekaterinburg", "KUF": "Europe/Samara"},
            booking_url=UTAIR_DIRECT_URL,
        )

        itinerary_contract.validate_itinerary_schema(itinerary)
        itinerary_contract.validate_itinerary_semantics(itinerary)
        self.assertEqual(itinerary["schema_version"], "flight-calendar-ics-itinerary.v1")
        self.assertEqual(itinerary["pnr"], EXPECTED_LOCATOR)
        self.assertEqual(itinerary["passengers"], ["EXAMPLE TEST"])
        self.assertEqual(itinerary["ticket_number"], "0000000000000")
        self.assertEqual(itinerary["booking_url"], UTAIR_DIRECT_URL)

        self.assertEqual(
            itinerary["flights"],
            [
                {
                    "flight_number": "UT281",
                    "departure": {
                        "airport": "SVX",
                        "city": "Екатеринбург",
                        "local": "2026-09-21T11:50",
                        "tz": "Asia/Yekaterinburg",
                    },
                    "arrival": {
                        "airport": "KUF",
                        "city": "Самара",
                        "local": "2026-09-21T13:10",
                        "tz": "Europe/Samara",
                    },
                    "status": "confirmed (HK)",
                    "aircraft": "ATR 72",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
