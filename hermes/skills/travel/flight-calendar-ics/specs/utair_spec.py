#!/usr/bin/env python3
"""Executable specification for the Utair booking-URL integration.

Scope
-----
This file specifies only the Utair carrier contract:

    Utair URL -> route/credentials -> Utair API -> normalized itinerary

The general URL process remains specified in ``specs/url_cli_spec.py``. This
spec also owns the Utair-specific public redirect-to-ICS scenario.

Run from the skill root::

    python3 specs/utair_spec.py

Only the external HTTP transport is replaced.  URL redirect handling, route
detection, Utair request construction, API response handling, itinerary
conversion, and itinerary validation remain real.
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
from typing import Any
from urllib.parse import parse_qs, urlparse
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE_PATH = ROOT / "specs" / "fixtures" / "utair" / "orders-v3.json"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "specs"))

from cli_envelope import assert_valid_cli_envelope

UTAIR_WEB_BASE = "https://www.utair.ru"
UTAIR_REDIRECT_URL = "https://click.mail.utair.io/z9suvw/fixture-token"
UTAIR_HTTP_REDIRECT_URL = "http://click.mail.utair.io/private-http-token?secret=private"
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
            return (
                200,
                "application/json; charset=utf-8",
                json.dumps(
                    {"access_token": SYNTHETIC_ACCESS_TOKEN, "token_type": "Bearer"}
                ),
            )
        if url.startswith(UTAIR_ORDERS_ENDPOINT + "?"):
            return 200, "application/json; charset=utf-8", UTAIR_FIXTURE_TEXT
        raise AssertionError(f"unexpected Utair endpoint: {url.split('?', 1)[0]}")

    return request_raw


class UtairCarrierSpecification(unittest.TestCase):
    """Behavior required from supported Utair booking URLs."""

    def test_redirect_url_routes_and_normalizes_credentials(self) -> None:
        """The real click-mail shape resolves to the Utair manage URL contract."""
        from flight_calendar.carriers.utair import resolve_utair_booking_redirect
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
            resolved_url = resolve_utair_booking_redirect(UTAIR_REDIRECT_URL)

        self.assertEqual(urlparse(resolved_url).hostname, "www.utair.ru")
        route = infer_build_route(
            argparse.Namespace(url=None, url_file=None), url_override=resolved_url
        )
        self.assertEqual(route["route"], "utair")

        locator, surname, normalized_url = utair.parse_utair_source(resolved_url)
        self.assertEqual(locator, EXPECTED_LOCATOR)
        self.assertEqual(surname, EXPECTED_SURNAME)
        self.assertEqual(normalized_url, UTAIR_DIRECT_URL)

    def test_public_redirect_url_builds_valid_ics_without_private_output(self) -> None:
        """The public CLI completes the real redirect-to-ICS Utair flow."""
        from flight_calendar import carrier_http, ics_render, parser

        class RedirectResponse:
            status_code = 307
            headers = {"Location": UTAIR_DIRECT_URL}

        with tempfile.TemporaryDirectory(prefix="flight-redirect-stdout.") as tmp:
            tmp_path = Path(tmp)
            url_file = tmp_path / "url.txt"
            output = tmp_path / "trip.ics"
            url_file.write_text(UTAIR_REDIRECT_URL, encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                mock.patch.object(
                    carrier_http._requests,
                    "request",
                    return_value=RedirectResponse(),
                ),
                mock.patch.object(
                    carrier_http,
                    "request_raw",
                    side_effect=fixture_http_response([]),
                ),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                code = parser.main(
                    [
                        "--json",
                        "build",
                        "--url-file",
                        str(url_file),
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(code, 0, stderr.getvalue() + stdout.getvalue())
            payload = json.loads(stdout.getvalue())
            assert_valid_cli_envelope(self, payload)
            self.assertIs(payload["ok"], True)
            self.assertEqual(payload["media"], f"MEDIA:{output}")
            self.assertIsInstance(payload["segments_count"], int)
            self.assertGreater(payload["segments_count"], 0)
            self.assertTrue(output.is_file())

            ics_text = output.read_text(encoding="utf-8")
            ics_render.validate_ics_text(
                ics_text, expected_events=payload["segments_count"]
            )
            self.assertEqual(ics_text.count("BEGIN:VEVENT"), payload["segments_count"])

        emitted = stdout.getvalue() + stderr.getvalue()
        for private_value in (
            UTAIR_REDIRECT_URL,
            "fixture-token",
            UTAIR_DIRECT_URL,
            "ABC123",
            "EXAMPLE",
            SYNTHETIC_ACCESS_TOKEN,
        ):
            self.assertNotIn(private_value, emitted)

    def test_http_redirect_wrapper_fails_closed_before_transport(self) -> None:
        """HTTP Utair wrappers fail before private booking data reaches transport."""
        from flight_calendar import carrier_http, parser

        with tempfile.TemporaryDirectory(prefix="flight-http-redirect-stdout.") as tmp:
            url_file = Path(tmp) / "url.txt"
            url_file.write_text(UTAIR_HTTP_REDIRECT_URL, encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()

            transport_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

            def fail_transport(*args: object, **kwargs: object) -> None:
                transport_calls.append((args, kwargs))
                raise AssertionError("wrapper transport must not be called")

            with (
                mock.patch.object(
                    carrier_http._requests,
                    "request",
                    side_effect=fail_transport,
                ),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                code = parser.main(
                    ["--json", "build", "--url-file", str(url_file)]
                )

        self.assertEqual(code, 2, f"transport_calls={len(transport_calls)}")
        self.assertEqual(transport_calls, [])
        payload = json.loads(stdout.getvalue())
        assert_valid_cli_envelope(self, payload)
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "redirect_resolution_failed")
        emitted = stdout.getvalue() + stderr.getvalue()
        for private_value in (
            UTAIR_HTTP_REDIRECT_URL,
            "private-http-token",
            "secret=private",
        ):
            self.assertNotIn(private_value, emitted)

    def test_direct_site_url_routes_without_redirect_and_normalizes_credentials(
        self,
    ) -> None:
        """The observed site URL is already a carrier booking URL."""
        from flight_calendar import carrier_http
        from flight_calendar.carriers import utair
        from flight_calendar.route_detection import infer_build_route
        from flight_calendar.carriers.utair import resolve_utair_booking_redirect

        parsed = urlparse(UTAIR_SITE_DIRECT_URL)
        self.assertEqual(parsed.hostname, "www.utair.ru")
        self.assertEqual(parsed.path, "/order-manage")
        query = parse_qs(parsed.query)
        self.assertEqual(query["rloc"], ["SITE123"])
        self.assertEqual(query["last_name"], ["EXAMPLE"])

        with mock.patch.object(
            carrier_http,
            "resolve_redirect_url",
            side_effect=AssertionError("direct Utair URL must not be fetched"),
        ):
            resolved_url = resolve_utair_booking_redirect(UTAIR_SITE_DIRECT_URL)

        self.assertEqual(resolved_url, UTAIR_SITE_DIRECT_URL)
        route = infer_build_route(
            argparse.Namespace(url=None, url_file=None), url_override=resolved_url
        )
        self.assertEqual(route["route"], "utair")
        locator, surname, normalized_url = utair.parse_utair_source(resolved_url)
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
        self.assertEqual(order_query["filters[passenger_lastname]"], [EXPECTED_SURNAME])
        order_headers = orders["headers"]
        self.assertIsInstance(order_headers, dict)
        self.assertEqual(
            order_headers["Authorization"], f"Bearer {SYNTHETIC_ACCESS_TOKEN}"
        )

    def test_sanitized_fixture_becomes_valid_expected_itinerary(self) -> None:
        """The actual response shape produces the normalized itinerary contract."""
        from flight_calendar import itinerary_contract
        from flight_calendar.carriers import utair

        api_response = json.loads(UTAIR_FIXTURE_TEXT)
        itinerary = utair.convert_to_itinerary(
            api_response,
            booking_url=UTAIR_DIRECT_URL,
        )

        itinerary_contract.validate_itinerary_schema(itinerary)
        enriched = itinerary_contract.enrich_itinerary_timezones(
            itinerary, {"SVX": "Asia/Yekaterinburg", "KUF": "Europe/Samara"}
        )
        itinerary_contract.validate_itinerary_semantics(enriched)
        self.assertEqual(itinerary["pnr"], EXPECTED_LOCATOR)
        self.assertEqual(itinerary["passenger"], "EXAMPLE TEST")
        self.assertEqual(itinerary["ticket_number"], "0000000000000")
        self.assertEqual(itinerary["booking_url"], UTAIR_DIRECT_URL)

        self.assertEqual(
            itinerary["flights"],
            [
                {
                    "flight_number": "UT9999",
                    "departure": {
                        "airport": "SVX",
                        "city": "Екатеринбург",
                        "local": "2037-09-21T11:50",
                    },
                    "arrival": {
                        "airport": "KUF",
                        "city": "Самара",
                        "local": "2037-09-21T13:10",
                    },
                    "aircraft": "ATR 72",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
