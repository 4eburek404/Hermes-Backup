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

The scenarios call the documented ``--json build --url <booking-url>``
contract through the public parser entry point. Only the external HTTP transport
is replaced, so route detection, adapter parsing, itinerary conversion,
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
from typing import Any
from unittest import mock

from cli_envelope import assert_valid_cli_envelope


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
LEGACY_AEROFLOT_BOOKING_URL = (
    "https://www.aeroflot.ru/ru-ru/pnr/?pnrKey="
    + "0" * 64
    + "&pnrLocator=ABC123"
)
REPRESENTATIVE_FIXTURE_TEXT = FIXTURE_PATH.read_text(encoding="utf-8")
RAW_REDIRECT_URL = "https://click.mail.utair.io/private-token?x=secret"
UNTRUSTED_REDIRECT_URL = (
    "https://evil.example/order-manage?rloc=ABC123&last_name=IVANOV"
)
S7_UNTRUSTED_PATH_URL = (
    "https://myb.s7.ru/random?bookingId=ABC123&passengerId=ivanov"
)


def run_cli(
    url: str,
    output: Path | None = None,
    tz: str | None = None,
) -> tuple[int, str, str]:
    from flight_calendar import parser

    return _run_parser(parser, ["--json", "build", "--url", url], output, tz)


def _run_parser(
    parser: Any,
    argv: list[str],
    output: Path | None,
    tz: str | None,
) -> tuple[int, str, str]:
    if output is not None:
        argv.extend(["--output", str(output)])
    if tz is not None:
        argv.extend(["--tz", tz])

    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
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
            assert_valid_cli_envelope(self, payload)
            self.assertIs(payload["ok"], True)
            self.assertEqual(payload["media"], f"MEDIA:{output}")
            self.assertIsInstance(payload["segments_count"], int)
            self.assertGreater(payload["segments_count"], 0)
            self.assertTrue(output.is_file())

            ics_text = output.read_text(encoding="utf-8").replace("\n ", "")
            self.assertIn(f"Бронирование: {REPRESENTATIVE_BOOKING_URL}", ics_text)
            ics_render.validate_ics_text(
                output.read_text(encoding="utf-8"), expected_events=payload["segments_count"]
            )
            self.assertEqual(ics_text.count("BEGIN:VEVENT"), payload["segments_count"])

            emitted = stdout + stderr
            self.assertNotIn(REPRESENTATIVE_BOOKING_URL, emitted)
            self.assertNotIn("ABC123", emitted)
            self.assertNotIn("0" * 64, emitted)

    def test_second_supported_aeroflot_path_builds_valid_ics_and_success_result(
        self,
    ) -> None:
        """The second supported booking path completes the public URL process."""
        from flight_calendar import carrier_http, ics_render

        with tempfile.TemporaryDirectory(prefix="flight-calendar-process.") as tmp:
            output = Path(tmp) / "second-path-trip.ics"
            with mock.patch.object(
                carrier_http,
                "request_raw",
                side_effect=fixture_http_response(),
            ):
                code, stdout, stderr = run_cli(LEGACY_AEROFLOT_BOOKING_URL, output)

            self.assertEqual(code, 0, stdout + stderr)
            payload = json.loads(stdout)
            assert_valid_cli_envelope(self, payload)
            self.assertIs(payload["ok"], True)
            self.assertEqual(payload["media"], f"MEDIA:{output}")
            self.assertEqual(payload["segments_count"], 2)
            self.assertTrue(output.is_file())
            ics_render.validate_ics_text(
                output.read_text(encoding="utf-8"), expected_events=2
            )

    def test_unknown_source_fails_closed_without_carrier_dispatch(self) -> None:
        """Unknown sources stop before any carrier adapter or network boundary."""
        from flight_calendar import carrier_http
        from flight_calendar.carriers import aeroflot, redwings, s7, ural, utair

        unknown_url = (
            "https://evil.example/manage-order"
            "?bookingId=ABC123&passengerId=ivanov"
        )
        adapter_calls: list[str] = []
        network_calls: list[str] = []

        def adapter_called(name: str):
            def record_and_stop(*args: Any, **kwargs: Any) -> None:
                del args, kwargs
                adapter_calls.append(name)
                raise RuntimeError("carrier adapter dispatch reached")

            return record_and_stop

        def network_called(*args: Any, **kwargs: Any) -> None:
            del args, kwargs
            network_calls.append("carrier_http")
            raise RuntimeError("network boundary reached")

        adapter_targets = (
            (aeroflot, "fetch_aeroflot_pnr", "aeroflot"),
            (ural, "fetch_ural_reservation", "ural"),
            (utair, "fetch_utair_token", "utair_token"),
            (utair, "fetch_utair_orders", "utair"),
            (redwings, "fetch_redwings_order", "redwings"),
            (s7, "fetch_s7_order", "s7"),
        )
        with contextlib.ExitStack() as stack:
            for module, function_name, route in adapter_targets:
                stack.enter_context(
                    mock.patch.object(
                        module,
                        function_name,
                        side_effect=adapter_called(route),
                    )
                )
            stack.enter_context(
                mock.patch.object(
                    carrier_http,
                    "request_raw",
                    side_effect=network_called,
                )
            )
            code, stdout, stderr = run_cli(unknown_url)

        self.assertEqual(
            code,
            2,
            f"adapter_calls={adapter_calls!r}; network_calls={network_calls!r}; "
            f"stdout={stdout!r}; stderr={stderr!r}",
        )
        payload = json.loads(stdout)
        assert_valid_cli_envelope(self, payload)
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "route_unknown")
        self.assertEqual(adapter_calls, [])
        self.assertEqual(network_calls, [])
        emitted = stdout + stderr
        for private_value in (
            "evil.example",
            "ABC123",
            "ivanov",
            "bookingId=",
            "passengerId=",
        ):
            self.assertNotIn(private_value, emitted)

    def test_known_host_untrusted_shape_fails_before_adapter_or_network(self) -> None:
        """A known carrier host is not enough without a trusted source shape."""
        from flight_calendar import carrier_http
        from flight_calendar.carriers import s7

        adapter_calls: list[str] = []
        network_calls: list[str] = []

        real_parse_s7_source = s7.parse_s7_source

        def adapter_parse_called(*args: Any, **kwargs: Any) -> tuple[str, str, str]:
            adapter_calls.append("s7.parse_s7_source")
            return real_parse_s7_source(*args, **kwargs)

        def network_called(*args: Any, **kwargs: Any) -> None:
            del args, kwargs
            network_calls.append("s7.Session")
            raise AssertionError("network boundary reached")

        with (
            mock.patch.object(
                s7, "parse_s7_source", side_effect=adapter_parse_called
            ),
            mock.patch.object(
                carrier_http, "request_raw", side_effect=network_called
            ),
        ):
            code, stdout, stderr = run_cli(S7_UNTRUSTED_PATH_URL)

        self.assertEqual(code, 2, stdout + stderr)
        payload = json.loads(stdout)
        assert_valid_cli_envelope(self, payload)
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "route_unknown")
        self.assertEqual(adapter_calls, [])
        self.assertEqual(network_calls, [])
        emitted = stdout + stderr
        for private_value in (
            S7_UNTRUSTED_PATH_URL,
            "myb.s7.ru",
            "ABC123",
            "ivanov",
            "bookingId=",
            "passengerId=",
        ):
            self.assertNotIn(private_value, emitted)

    def test_trusted_aeroflot_without_credentials_is_insufficient_before_network(
        self,
    ) -> None:
        """A trusted Aeroflot shape delegates credential completeness to the adapter."""
        from flight_calendar import carrier_http

        network_calls: list[str] = []

        def network_called(*args: Any, **kwargs: Any) -> None:
            del args, kwargs
            network_calls.append("carrier_http.request_raw")
            raise AssertionError("network boundary reached")

        with mock.patch.object(
            carrier_http,
            "request_raw",
            side_effect=network_called,
        ):
            code, stdout, stderr = run_cli(
                "https://www.aeroflot.ru/sb/pnr/app/ru-ru"
            )

        self.assertEqual(code, 2, stdout + stderr)
        payload = json.loads(stdout)
        assert_valid_cli_envelope(self, payload)
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "route_input_insufficient")
        self.assertEqual(network_calls, [])
        self.assertEqual(stderr, "")

    def test_present_invalid_aeroflot_value_is_validation_error_before_network(
        self,
    ) -> None:
        """Trusted fields route first; Aeroflot validates values before transport."""
        from flight_calendar import carrier_http

        invalid_value = "BAD_KEY_VALUE"
        invalid_url = (
            "https://www.aeroflot.ru/sb/pnr/app/ru-ru"
            f"?pnrKey={invalid_value}&pnrLocator=ABC123"
        )
        network_calls: list[str] = []

        def network_called(*args: Any, **kwargs: Any) -> None:
            del args, kwargs
            network_calls.append("carrier_http.request_raw")
            raise AssertionError("network boundary reached")

        with mock.patch.object(
            carrier_http,
            "request_raw",
            side_effect=network_called,
        ):
            code, stdout, stderr = run_cli(invalid_url)

        self.assertEqual(code, 2, stdout + stderr)
        payload = json.loads(stdout)
        assert_valid_cli_envelope(self, payload)
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertEqual(network_calls, [])
        emitted = stdout + stderr
        self.assertNotIn(invalid_url, emitted)
        self.assertNotIn(invalid_value, emitted)
        self.assertNotIn("ABC123", emitted)

    def test_trusted_sources_dispatch_to_adapter_validation_before_network(self) -> None:
        """Every trusted fingerprint reaches its adapter before any transport."""
        from flight_calendar import carrier_http
        from flight_calendar.carriers import redwings, s7, ural, utair

        cases = (
            (
                ural,
                "parse_ural_source",
                "https://service.uralairlines.ru/",
                "route_input_insufficient",
            ),
            (
                ural,
                "parse_ural_source",
                "https://service.uralairlines.ru/?pnr=BAD&lastName=IVANOV",
                "validation_error",
            ),
            (
                utair,
                "parse_utair_source",
                "https://www.utair.ru/order-manage",
                "route_input_insufficient",
            ),
            (
                utair,
                "parse_utair_source",
                "https://www.utair.ru/order-manage?rloc=BAD&last_name=IVANOV",
                "validation_error",
            ),
            (
                redwings,
                "parse_redwings_source",
                "https://flyredwings.com/booking/",
                "route_input_insufficient",
            ),
            (
                redwings,
                "parse_redwings_source",
                "https://flyredwings.com/booking/#/find/BAD/X/Submit",
                "validation_error",
            ),
            (
                s7,
                "parse_s7_source",
                "https://myb.s7.ru/myb/manage-order",
                "route_input_insufficient",
            ),
            (
                s7,
                "parse_s7_source",
                "https://myb.s7.ru/myb/manage-order?bookingId=BAD&passengerId=ivanov",
                "validation_error",
            ),
        )

        for module, parser_name, url, expected_code in cases:
            with self.subTest(url=url):
                adapter_calls: list[str] = []
                network_calls: list[str] = []
                parser_function = getattr(module, parser_name)

                def record_parse(*args: Any, _parser=parser_function, **kwargs: Any):
                    adapter_calls.append(parser_name)
                    return _parser(*args, **kwargs)

                def fail_network(*args: Any, **kwargs: Any) -> None:
                    del args, kwargs
                    network_calls.append("carrier_http.request_raw")
                    raise AssertionError("network boundary reached")

                with mock.patch.object(module, parser_name, side_effect=record_parse):
                    with mock.patch.object(
                        carrier_http, "request_raw", side_effect=fail_network
                    ):
                        code, stdout, stderr = run_cli(url)

                self.assertEqual(code, 2, stdout + stderr)
                payload = json.loads(stdout)
                assert_valid_cli_envelope(self, payload)
                self.assertEqual(payload["error"]["code"], expected_code)
                self.assertEqual(adapter_calls, [parser_name])
                self.assertEqual(network_calls, [])
                self.assertEqual(stderr, "")

    def test_url_sources_are_mutually_exclusive(self) -> None:
        from flight_calendar import parser

        with tempfile.TemporaryDirectory(prefix="flight-calendar-sources.") as tmp:
            url_file = Path(tmp) / "booking-url.txt"
            input_file = Path(tmp) / "itinerary.json"
            url_file.write_text(
                "https://unknown.example/private-booking?token=secret",
                encoding="utf-8",
            )
            input_file.write_text("{}", encoding="utf-8")
            cases = (
                [
                    "--url",
                    "https://unknown.example/private-booking?token=secret",
                    "--url-file",
                    str(url_file),
                ],
                [
                    "--url",
                    "https://unknown.example/private-booking?token=secret",
                    "--input",
                    str(input_file),
                ],
                ["--url-file", str(url_file), "--input", str(input_file)],
            )
            for source_args in cases:
                with self.subTest(source_args=source_args):
                    code, stdout, stderr = _run_parser(
                        parser, ["--json", "build", *source_args], None, None
                    )
                    self.assertEqual(code, 2)
                    payload = json.loads(stdout)
                    assert_valid_cli_envelope(self, payload)
                    self.assertEqual(payload["error"]["code"], "usage_error")
                    self.assertNotIn("unknown.example", stdout + stderr)
                    self.assertNotIn("secret", payload["error"]["message"])

    def test_unknown_booking_url_returns_structured_json_error_without_leak(
        self,
    ) -> None:
        """An unsupported URL fails as machine-readable JSON, not a traceback."""
        unknown_url = "https://unknown.example/private-booking?token=secret"
        code, stdout, stderr = run_cli(unknown_url)

        self.assertEqual(code, 2)
        payload = json.loads(stdout)
        assert_valid_cli_envelope(self, payload)
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
        assert_valid_cli_envelope(self, payload)
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

    def test_malformed_timezone_override_returns_usage_error(self) -> None:
        """The public URL CLI maps malformed --tz input to usage_error."""
        url = "https://www.utair.ru/order-manage?rloc=ABC123&last_name=EXAMPLE"
        code, stdout, stderr = run_cli(url, tz="broken")

        self.assertEqual(code, 2)
        payload = json.loads(stdout)
        assert_valid_cli_envelope(self, payload)
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "usage_error")
        self.assertIn("use CODE=Area/City", payload["error"]["message"])
        self.assertEqual(stderr, "")

    def test_supported_booking_url_honors_timezone_override(self) -> None:
        from flight_calendar import carrier_http

        with tempfile.TemporaryDirectory(prefix="flight-calendar-tz.") as tmp:
            output = Path(tmp) / "timezone-trip.ics"
            with mock.patch.object(
                carrier_http,
                "request_raw",
                side_effect=fixture_http_response(),
            ):
                code, stdout, stderr = run_cli(
                    REPRESENTATIVE_BOOKING_URL,
                    output,
                    tz="SVO=Asia/Yekaterinburg",
                )

            self.assertEqual(code, 0, stdout + stderr)
            self.assertEqual(stderr, "")
            self.assertIn(
                "DTEND:20370923T085000Z",
                output.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
