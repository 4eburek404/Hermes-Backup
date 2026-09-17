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
sys.path.insert(0, str(SCRIPTS))

DIRECT_UTAIR_URL = (
    "https://www.utair.ru/order-manage?rloc=ABC123&last_name=IVANOV"
)
RAW_UTAIR_CLICK_URL = "https://click.mail.utair.io/private-token?x=secret"
UNTRUSTED_REDIRECT = (
    "https://evil.example/order-manage?rloc=ABC123&last_name=IVANOV"
)


def minimal_itinerary() -> dict[str, object]:
    return {
        "schema_version": "flight-calendar-ics-itinerary.v1",
        "pnr": "ABC123",
        "passengers": ["IVANOV"],
        "booking_url": DIRECT_UTAIR_URL,
        "flights": [
            {
                "flight_number": "UT123",
                "departure": {
                    "airport": "VKO",
                    "local": "2026-10-01T09:00",
                    "tz": "Europe/Moscow",
                },
                "arrival": {
                    "airport": "SVX",
                    "local": "2026-10-01T13:30",
                    "tz": "Asia/Yekaterinburg",
                },
                "status": "confirmed",
            }
        ],
    }


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


class BookingUrlCliSpecification(unittest.TestCase):
    """Behavior required from the public URL build route."""

    def test_given_supported_direct_url_when_build_succeeds_then_media_is_returned(self) -> None:
        """Given a supported direct booking URL, a successful build returns one ICS artifact."""
        from flight_calendar import parser

        with tempfile.TemporaryDirectory(prefix="flight-calendar-spec.") as tmp:
            output = Path(tmp) / "trip.ics"
            with (
                mock.patch.object(parser.utair, "fetch_utair_token", return_value="token"),
                mock.patch.object(
                    parser.utair,
                    "fetch_utair_orders",
                    return_value={"orders": [{"segments": []}]},
                ),
                mock.patch.object(
                    parser.utair,
                    "convert_to_itinerary",
                    return_value=minimal_itinerary(),
                ),
            ):
                code, stdout, stderr = run_cli(DIRECT_UTAIR_URL, output)

            self.assertEqual(code, 0, stdout + stderr)
            payload = json.loads(stdout)
            self.assertIs(payload["ok"], True)
            self.assertEqual(payload["media"], f"MEDIA:{output}")
            self.assertEqual(payload["segments_count"], 1)
            self.assertIs(payload["no_further_action_needed"], True)
            self.assertTrue(output.is_file())

            emitted = stdout + stderr
            self.assertNotIn("ABC123", emitted)
            self.assertNotIn("IVANOV", emitted)
            self.assertNotIn("utair.ru/order-manage", emitted)

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

    def test_given_successful_build_when_result_is_emitted_then_private_url_is_not_in_cli_output(self) -> None:
        """Credential-bearing booking URLs may be embedded in ICS, but never emitted by the CLI envelope."""
        from flight_calendar import parser

        with tempfile.TemporaryDirectory(prefix="flight-calendar-spec.") as tmp:
            output = Path(tmp) / "trip.ics"
            with (
                mock.patch.object(parser.utair, "fetch_utair_token", return_value="token"),
                mock.patch.object(
                    parser.utair,
                    "fetch_utair_orders",
                    return_value={"orders": [{"segments": []}]},
                ),
                mock.patch.object(
                    parser.utair,
                    "convert_to_itinerary",
                    return_value=minimal_itinerary(),
                ),
            ):
                code, stdout, stderr = run_cli(DIRECT_UTAIR_URL, output)

        self.assertEqual(code, 0, stdout + stderr)
        emitted = stdout + stderr
        self.assertNotIn(DIRECT_UTAIR_URL, emitted)
        self.assertNotIn("rloc=", emitted)
        self.assertNotIn("last_name=", emitted)


if __name__ == "__main__":
    unittest.main(verbosity=2)
