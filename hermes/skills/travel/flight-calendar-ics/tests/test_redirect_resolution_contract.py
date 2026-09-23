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
sys.path.insert(0, str(ROOT / "specs"))

from cli_envelope import assert_valid_cli_envelope

RAW_CLICK_URL = "https://click.mail.utair.io/z9suvw/SYNTHETIC_TOKEN"
DIRECT_UTAIR_URL = "https://www.utair.ru/order-manage?rloc=ABC123&last_name=EXAMPLE"
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
    def test_click_mail_utair_transport_failure_is_redacted_cli_error(self) -> None:
        from flight_calendar import carrier_http, parser

        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as handle:
            handle.write(RAW_CLICK_URL)
            handle.flush()
            stdout = io.StringIO()
            with (
                mock.patch(
                    "flight_calendar.carriers.utair.carrier_http.resolve_redirect_url",
                    side_effect=carrier_http.TransportError(
                        "known booking redirect failed: network error (TimeoutError)"
                    ),
                ),
                contextlib.redirect_stdout(stdout),
            ):
                code = parser.main(["--json", "build", "--url-file", handle.name])

        payload = json.loads(stdout.getvalue())
        assert_valid_cli_envelope(self, payload)
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"]["code"], "redirect_resolution_failed")
        serialized = json.dumps(payload, ensure_ascii=False)
        assert_private_tokens_redacted(self, serialized)

    def test_click_mail_utair_503_is_redacted_public_cli_failure(self) -> None:
        from flight_calendar import carrier_http, parser

        class FakeResponse:
            status_code = 503
            headers: dict[str, str] = {}

        redirect_requests: list[tuple[str, str]] = []

        def fake_request(method: str, url: str, **kwargs: object) -> FakeResponse:
            del kwargs
            redirect_requests.append((method, url))
            return FakeResponse()

        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(
                carrier_http._requests,
                "request",
                side_effect=fake_request,
            ),
            mock.patch.object(
                carrier_http,
                "request_raw",
                side_effect=AssertionError("Utair API transport must not run"),
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = parser.main(["--json", "build", "--url", RAW_CLICK_URL])

        payload = json.loads(stdout.getvalue())
        assert_valid_cli_envelope(self, payload)
        self.assertEqual(code, 2)
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "redirect_resolution_failed")
        self.assertEqual(redirect_requests, [("GET", RAW_CLICK_URL)])
        serialized = json.dumps(payload, ensure_ascii=False) + stderr.getvalue()
        assert_private_tokens_redacted(self, serialized)
        self.assertNotIn(RAW_CLICK_URL, serialized)

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

        with mock.patch.object(
            carrier_http._requests,
            "request",
            return_value=FakeResponse(),
        ):
            with self.assertRaises(carrier_http.TransportError) as ctx:
                carrier_http.resolve_redirect_url(RAW_CLICK_URL)

        assert_private_tokens_redacted(self, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
