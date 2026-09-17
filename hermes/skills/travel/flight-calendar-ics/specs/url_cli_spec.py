#!/usr/bin/env python3
"""Executable process specification for the public booking-URL CLI flow.

Scope
-----
This file specifies the carrier-neutral process contract:

    booking URL -> route -> validated itinerary -> valid ICS -> JSON result

The checked-in Aeroflot response is representative test data only.  Its
endpoint, request protocol, credential names, and URL shapes are specified in
``specs/aeroflot_spec.py`` instead.

Run from the skill root:

    python3 specs/url_cli_spec.py

The scenarios call the documented ``--json build --url-file`` argv contract
through the public parser entry point.  Only the external HTTP transport is
replaced, so route detection, adapter parsing, itinerary conversion,
validation, rendering, and artifact validation remain real.
"""

from __future__ import annotations

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

# Representative fixture input; the process assertions below do not depend on
# the carrier's protocol or credential field names.
REPRESENTATIVE_BOOKING_URL = (
    "https://www.aeroflot.ru/sb/pnr/app/ru-ru"
    "#/pnr?pnr_key=" + "0" * 64 + "&pnr_locator=ABC123"
)
REPRESENTATIVE_FIXTURE_TEXT = FIXTURE_PATH.read_text(encoding="utf-8")
RAW_REDIRECT_URL = "https://click.mail.utair.io/private-token?x=secret"
UNTRUSTED_REDIRECT_URL = (
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


def fixture_http_response():
    """Replace only unavoidable external HTTP with the checked-in response."""

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
        del url, method, headers, body, timeout, label, sleep
        return 200, "application/json; charset=utf-8", REPRESENTATIVE_FIXTURE_TEXT

    return request_raw


class BookingUrlProcessSpecification(unittest.TestCase):
    """Behavior required from the public URL build process."""

    def test_supported_booking_url_builds_valid_ics_and_success_result(self) -> None:
        """A supported URL produces a validated artifact and terminal result."""
        from flight_calendar import carrier_http, ics_render

        with tempfile.TemporaryDirectory(prefix="flight-calendar-process.") as tmp:
            output = Path(tmp) / "trip.ics"
            with mock.patch.object(
                carrier_http,
                "request_raw",
                side_effect=fixture_http_response(),
            ):
                code, stdout, stderr = run_cli(REPRESENTATIVE_BOOKING_URL, output)

            self.assertEqual(code, 0, stdout + stderr)
            payload = json.loads(stdout)
            self.assertIs(payload["ok"], True)
            self.assertEqual(payload["media"], f"MEDIA:{output}")
            self.assertIsInstance(payload["segments_count"], int)
            self.assertGreater(payload["segments_count"], 0)
            self.assertIs(payload["no_further_action_needed"], True)
            self.assertTrue(output.is_file())

            ics_text = output.read_text(encoding="utf-8")
            ics_render.validate_ics_text(
                ics_text, expected_events=payload["segments_count"]
            )
            self.assertEqual(ics_text.count("BEGIN:VEVENT"), payload["segments_count"])

            emitted = stdout + stderr
            self.assertNotIn(REPRESENTATIVE_BOOKING_URL, emitted)
            self.assertNotIn("ABC123", emitted)
            self.assertNotIn("0" * 64, emitted)

    def test_unknown_booking_url_returns_structured_json_error_without_leak(
        self,
    ) -> None:
        """An unsupported URL fails as machine-readable JSON, not a traceback."""
        unknown_url = "https://unknown.example/private-booking?token=secret"
        code, stdout, stderr = run_cli(unknown_url)

        self.assertNotEqual(code, 0)
        payload = json.loads(stdout)
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "route_unknown")
        self.assertEqual(stderr, "")
        emitted = stdout + stderr
        self.assertNotIn(unknown_url, emitted)
        self.assertNotIn("unknown.example", emitted)
        self.assertNotIn("secret", emitted)

    def test_untrusted_known_redirect_fails_closed_without_fallback_or_leak(
        self,
    ) -> None:
        """A known redirect wrapper cannot continue to an untrusted target."""
        from flight_calendar import carrier_http

        with mock.patch.object(
            carrier_http,
            "resolve_redirect_url",
            return_value=UNTRUSTED_REDIRECT_URL,
        ):
            code, stdout, stderr = run_cli(RAW_REDIRECT_URL)

        self.assertNotEqual(code, 0)
        payload = json.loads(stdout)
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "redirect_resolution_failed")
        emitted = stdout + stderr
        for private_value in (
            RAW_REDIRECT_URL,
            "private-token",
            "secret",
            "ABC123",
            "IVANOV",
            "evil.example",
        ):
            self.assertNotIn(private_value, emitted)


if __name__ == "__main__":
    unittest.main(verbosity=2)
