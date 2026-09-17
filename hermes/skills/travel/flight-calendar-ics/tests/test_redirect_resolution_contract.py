"""Redirect resolution and single-source URL flow regressions."""

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

RAW_CLICK_URL = "https://click.mail.utair.io/private-token?x=secret"
DIRECT_UTAIR_URL = "https://www.utair.ru/order-manage?rloc=ABC123&last_name=EXAMPLE"
PRIVATE_RESOLVED_URL = "https://evil.example/order-manage?rloc=ABC123&last_name=IVANOV"
HTTP_UTAIR_URL = "http://www.utair.ru/order-manage?rloc=ABC123&last_name=IVANOV"
UTAIR_FIXTURE_PATH = ROOT / "specs" / "fixtures" / "utair" / "orders-v3.json"
UTAIR_FIXTURE_TEXT = UTAIR_FIXTURE_PATH.read_text(encoding="utf-8")
UTAIR_OAUTH_ENDPOINT = "https://b.utair.ru/oauth/token"
UTAIR_ORDERS_ENDPOINT = "https://b.utair.ru/api/v3/orders"
SYNTHETIC_ACCESS_TOKEN = "synthetic-access-token"
REDACTED_TOKENS = (
    "click.mail.utair.io",
    "utair.ru/order-manage",
    "rloc",
    "last_name",
    "ABC123",
    "secret",
)


def assert_private_tokens_redacted(testcase: unittest.TestCase, text: str) -> None:
    for token in REDACTED_TOKENS:
        testcase.assertNotIn(token, text)


class RedirectResolutionContractTests(unittest.TestCase):
    def test_click_mail_utair_redirect_must_resolve_to_https_utair_host(self) -> None:
        from flight_calendar.errors import CliFailure
        from flight_calendar.redirect_resolution import resolve_known_booking_redirect

        for resolved_url in (PRIVATE_RESOLVED_URL, HTTP_UTAIR_URL):
            with self.subTest(resolved_url=resolved_url):
                with mock.patch(
                    "flight_calendar.redirect_resolution.carrier_http.resolve_redirect_url",
                    return_value=resolved_url,
                ):
                    with self.assertRaises(CliFailure) as ctx:
                        resolve_known_booking_redirect(RAW_CLICK_URL)

                self.assertEqual(ctx.exception.code, "redirect_resolution_failed")
                message = str(ctx.exception)
                assert_private_tokens_redacted(self, message)
                self.assertNotIn("evil.example", message)

    def test_click_mail_utair_transport_failure_is_redacted_cli_error(self) -> None:
        from flight_calendar import carrier_http, parser

        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as handle:
            handle.write(RAW_CLICK_URL)
            handle.flush()
            stdout = io.StringIO()
            with (
                mock.patch(
                    "flight_calendar.redirect_resolution.carrier_http.resolve_redirect_url",
                    side_effect=carrier_http.TransportError(
                        "known booking redirect failed: network error (TimeoutError)"
                    ),
                ),
                contextlib.redirect_stdout(stdout),
            ):
                code = parser.main(["--json", "build", "--url-file", handle.name])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"]["code"], "redirect_resolution_failed")
        serialized = json.dumps(payload, ensure_ascii=False)
        assert_private_tokens_redacted(self, serialized)

    def test_click_mail_utair_503_becomes_redacted_cli_failure(self) -> None:
        from flight_calendar import carrier_http
        from flight_calendar.errors import CliFailure
        from flight_calendar.redirect_resolution import resolve_known_booking_redirect

        class FakeResponse:
            status_code = 503
            headers: dict[str, str] = {}

        def fake_request(method: str, url: str, **kwargs: object) -> FakeResponse:
            self.assertEqual(method, "GET")
            self.assertEqual(url, RAW_CLICK_URL)
            self.assertEqual(kwargs.get("allow_redirects"), False)
            self.assertEqual(kwargs.get("max_redirects"), 0)
            return FakeResponse()

        with mock.patch.object(
            carrier_http._requests, "request", side_effect=fake_request
        ):
            with self.assertRaises(CliFailure) as cli_ctx:
                resolve_known_booking_redirect(RAW_CLICK_URL)

        self.assertEqual(cli_ctx.exception.code, "redirect_resolution_failed")
        assert_private_tokens_redacted(self, str(cli_ctx.exception))


    def test_cli_success_stdout_does_not_expose_raw_or_resolved_private_url(
        self,
    ) -> None:
        from flight_calendar import carrier_http, ics_render, parser

        def utair_api_fixture(
            url: str,
            *,
            method: str = "GET",
            headers: dict[str, str] | None = None,
            body: bytes | None = None,
            timeout: int = 45,
            label: str = "HTTP request",
            sleep: object = None,
        ) -> tuple[int, str, str]:
            del method, headers, body, timeout, label, sleep
            if url == UTAIR_OAUTH_ENDPOINT:
                return 200, "application/json; charset=utf-8", json.dumps(
                    {"access_token": SYNTHETIC_ACCESS_TOKEN, "token_type": "Bearer"}
                )
            if url.startswith(UTAIR_ORDERS_ENDPOINT + "?"):
                return 200, "application/json; charset=utf-8", UTAIR_FIXTURE_TEXT
            raise AssertionError(f"unexpected Utair endpoint: {url.split('?', 1)[0]}")

        class RedirectResponse:
            status_code = 307
            headers = {"Location": DIRECT_UTAIR_URL}

        with tempfile.TemporaryDirectory(prefix="flight-redirect-stdout.") as tmp:
            tmp_path = Path(tmp)
            url_file = tmp_path / "url.txt"
            output = tmp_path / "trip.ics"
            url_file.write_text(RAW_CLICK_URL, encoding="utf-8")
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
                    side_effect=utair_api_fixture,
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
                        "--no-alarms",
                    ]
                )

            self.assertEqual(code, 0, stderr.getvalue() + stdout.getvalue())
            payload = json.loads(stdout.getvalue())
            self.assertIs(payload["ok"], True)
            self.assertEqual(payload["media"], f"MEDIA:{output}")
            self.assertIsInstance(payload["segments_count"], int)
            self.assertGreater(payload["segments_count"], 0)
            self.assertTrue(output.is_file())

            ics_text = output.read_text(encoding="utf-8")
            ics_render.validate_ics_text(
                ics_text, expected_events=payload["segments_count"]
            )

        emitted = stdout.getvalue() + stderr.getvalue()
        for private_value in (
            RAW_CLICK_URL,
            "private-token",
            "secret",
            DIRECT_UTAIR_URL,
            "ABC123",
            "EXAMPLE",
            SYNTHETIC_ACCESS_TOKEN,
        ):
            self.assertNotIn(private_value, emitted)


class CarrierHttpRedirectContractTests(unittest.TestCase):
    def test_resolve_redirect_url_reads_location_without_auto_follow_or_body(
        self,
    ) -> None:
        from flight_calendar import carrier_http

        class FakeResponse:
            status_code = 307
            headers = {"Location": DIRECT_UTAIR_URL}

            @property
            def text(self) -> str:  # pragma: no cover - must not be read
                raise AssertionError("redirect resolver must not read response.text")

        def fake_request(method: str, url: str, **kwargs: object) -> FakeResponse:
            self.assertEqual(method, "GET")
            self.assertEqual(url, RAW_CLICK_URL)
            self.assertEqual(kwargs.get("allow_redirects"), False)
            self.assertEqual(kwargs.get("max_redirects"), 0)
            return FakeResponse()

        with mock.patch.object(
            carrier_http._requests, "request", side_effect=fake_request
        ):
            self.assertEqual(
                carrier_http.resolve_redirect_url(RAW_CLICK_URL), DIRECT_UTAIR_URL
            )

    def test_resolve_redirect_url_requires_location_header_without_reading_body(
        self,
    ) -> None:
        from flight_calendar import carrier_http

        class FakeResponse:
            status_code = 307
            headers: dict[str, str] = {}

            @property
            def text(self) -> str:  # pragma: no cover - must not be read
                raise AssertionError("redirect resolver must not read response.text")

        def fake_request(method: str, url: str, **kwargs: object) -> FakeResponse:
            self.assertEqual(method, "GET")
            self.assertEqual(url, RAW_CLICK_URL)
            self.assertEqual(kwargs.get("allow_redirects"), False)
            self.assertEqual(kwargs.get("max_redirects"), 0)
            return FakeResponse()

        with mock.patch.object(
            carrier_http._requests, "request", side_effect=fake_request
        ):
            with self.assertRaises(carrier_http.TransportError) as ctx:
                carrier_http.resolve_redirect_url(RAW_CLICK_URL)

        assert_private_tokens_redacted(self, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
