#!/usr/bin/env python3
"""Executable specification for the public booking-URL CLI contract.

Scope
-----
This file specifies externally observable CLI behavior for the booking-URL
route.  It deliberately does not specify internal module names, file layout,
or implementation structure.

Run from the skill root:

    python3 specs/url_cli_spec.py

Agent trajectory requirements (for example, "do not open a browser before the
CLI" and "stop after successful media delivery") belong to trajectory evaluate,
not to this CLI specification.
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
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE_PATH = ROOT / "specs" / "fixtures" / "aeroflot" / "pnr-view-v3.json"
sys.path.insert(0, str(SCRIPTS))

AEROFLOT_BASE = "https://www.aeroflot.ru"
AEROFLOT_APP_URL = AEROFLOT_BASE + "/sb/pnr/app/ru-ru"
AEROFLOT_PNR_API = AEROFLOT_BASE + "/se/api/app/pnr/view/v3"
# These values are the sanitized fixture credentials, not a real booking.
SYNTHETIC_LOCATOR = "ABC123"
SYNTHETIC_KEY = "0" * 64
AEROFLOT_SPA_URL = (
    f"{AEROFLOT_APP_URL}#/pnr?pnr_key={SYNTHETIC_KEY}"
    f"&pnr_locator={SYNTHETIC_LOCATOR}"
)
AEROFLOT_QUERY_URL = (
    f"{AEROFLOT_APP_URL}?pnrKey={SYNTHETIC_KEY}"
    f"&pnrLocator={SYNTHETIC_LOCATOR}&utm_source=spec"
)
AEROFLOT_FIXTURE_TEXT = FIXTURE_PATH.read_text(encoding="utf-8")

RAW_UTAIR_CLICK_URL = "https://click.mail.utair.io/private-token?x=secret"
UNTRUSTED_REDIRECT = (
    "https://evil.example/order-manage?rloc=ABC123&last_name=IVANOV"
)


def run_cli(url: str, output: Path | None = None) -> tuple[int, str, str]:
    from flight_calendar import parser

    with tempfile.NamedTemporaryFile("w", encoding="utf-8") as source:
        source.write(url)
        source.flush()
        argv = ["--json", "build", "--url-file", source.name]
        if output is not None:
            argv.extend(["--output", str(output), "--no-alarms"])

        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = parser.main(argv)

    return code, stdout.getvalue(), stderr.getvalue()


def fixture_http_response(observed: list[dict[str, object]]):
    """Replace only carrier_http.request_raw with the checked-in API response."""

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


class BookingUrlCliSpecification(unittest.TestCase):
    """Behavior required from the public URL build route."""

    def assert_aeroflot_route(self, url: str) -> None:
        from flight_calendar.route_detection import infer_build_route

        route = infer_build_route(
            argparse.Namespace(url=None, url_file=None), url_override=url
        )
        self.assertEqual(route["route"], "aeroflot")

    def assert_aeroflot_build(
        self,
        url: str,
        output: Path,
        observed: list[dict[str, object]],
        stdout: str,
        stderr: str,
        code: int,
    ) -> None:
        self.assertEqual(code, 0, stdout + stderr)
        payload = json.loads(stdout)
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["media"], f"MEDIA:{output}")
        self.assertEqual(payload["segments_count"], 2)
        self.assertIs(payload["no_further_action_needed"], True)
        self.assertTrue(output.is_file())

        self.assertEqual(len(observed), 1)
        request = observed[0]
        self.assertEqual(request["url"], AEROFLOT_PNR_API)
        self.assertEqual(request["method"], "POST")
        request_body = request["body"]
        assert isinstance(request_body, bytes)
        self.assertEqual(
            json.loads(request_body.decode("utf-8")),
            {
                "pnr_locator": SYNTHETIC_LOCATOR,
                "pnr_key": SYNTHETIC_KEY,
                "lang": "ru",
                "country": "ru",
            },
        )

        from flight_calendar import ics_render

        ics_text = output.read_text(encoding="utf-8")
        ics_render.validate_ics_text(ics_text, expected_events=2)
        self.assertEqual(ics_text.count("BEGIN:VEVENT"), 2)

        emitted = stdout + stderr
        for private_value in (url, SYNTHETIC_LOCATOR, SYNTHETIC_KEY):
            self.assertNotIn(private_value, emitted)
        self.assertNotIn("pnr_key=", emitted)
        self.assertNotIn("pnrKey=", emitted)
        self.assertNotIn("pnr_locator=", emitted)
        self.assertNotIn("pnrLocator=", emitted)

    def test_given_aeroflot_spa_snake_case_url_when_build_runs_then_real_fixture_pipeline_returns_media(
        self,
    ) -> None:
        """The SPA URL reaches Aeroflot conversion and ICS rendering unchanged."""
        from flight_calendar import carrier_http

        self.assert_aeroflot_route(AEROFLOT_SPA_URL)
        with tempfile.TemporaryDirectory(prefix="flight-calendar-spec.") as tmp:
            output = Path(tmp) / "spa-trip.ics"
            observed: list[dict[str, object]] = []
            with mock.patch.object(
                carrier_http,
                "request_raw",
                side_effect=fixture_http_response(observed),
            ):
                code, stdout, stderr = run_cli(AEROFLOT_SPA_URL, output)

            self.assert_aeroflot_build(
                AEROFLOT_SPA_URL, output, observed, stdout, stderr, code
            )

    def test_given_aeroflot_query_camel_case_url_when_build_runs_then_real_fixture_pipeline_returns_media(
        self,
    ) -> None:
        """The query URL with tracking parameters reaches the same real pipeline."""
        from flight_calendar import carrier_http

        self.assert_aeroflot_route(AEROFLOT_QUERY_URL)
        with tempfile.TemporaryDirectory(prefix="flight-calendar-spec.") as tmp:
            output = Path(tmp) / "query-trip.ics"
            observed: list[dict[str, object]] = []
            with mock.patch.object(
                carrier_http,
                "request_raw",
                side_effect=fixture_http_response(observed),
            ):
                code, stdout, stderr = run_cli(AEROFLOT_QUERY_URL, output)

            self.assert_aeroflot_build(
                AEROFLOT_QUERY_URL, output, observed, stdout, stderr, code
            )

    def test_given_known_mail_redirect_when_target_is_untrusted_then_build_fails_closed(self) -> None:
        """Known mail redirects must not continue when they resolve outside the trusted carrier target."""
        from flight_calendar import carrier_http

        with mock.patch.object(
            carrier_http,
            "resolve_redirect_url",
            return_value=UNTRUSTED_REDIRECT,
        ):
            code, stdout, stderr = run_cli(RAW_UTAIR_CLICK_URL)

        self.assertNotEqual(code, 0)
        payload = json.loads(stdout)
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "redirect_resolution_failed")

        emitted = stdout + stderr
        for private_token in (
            "private-token",
            "secret",
            "ABC123",
            "IVANOV",
            "evil.example",
        ):
            self.assertNotIn(private_token, emitted)

    def test_given_one_url_source_when_cli_runs_then_source_contract_is_machine_readable(self) -> None:
        """A URL build failure is returned as structured JSON rather than an uncontrolled traceback."""
        from flight_calendar import parser

        with mock.patch.object(
            parser,
            "infer_build_route",
            side_effect=parser.CliFailure("source fingerprint not recognized", code="route_unknown"),
        ):
            code, stdout, stderr = run_cli("https://example.invalid/booking")

        self.assertNotEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(
            payload,
            {
                "ok": False,
                "error": {
                    "code": "route_unknown",
                    "message": "source fingerprint not recognized",
                },
            },
        )
        self.assertEqual(stderr, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
