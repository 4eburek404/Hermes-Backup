"""Redirect resolution and single-source URL flow regressions."""

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
sys.path.insert(0, str(SCRIPTS))

RAW_CLICK_URL = "https://click.mail.utair.io/private-token?x=secret"
DIRECT_UTAIR_URL = "https://www.utair.ru/order-manage?rloc=ABC123&last_name=IVANOV"
DIRECT_S7_URL = "https://myb.s7.ru/myb/manage-order?bookingId=ABC123&passengerId=ivanov"
NORMALIZED_S7_URL = (
    "https://myb.s7.ru/myb/manage-order?bookingId=ABC123&passengerId=IVANOV"
)
PRIVATE_RESOLVED_URL = "https://evil.example/order-manage?rloc=ABC123&last_name=IVANOV"
HTTP_UTAIR_URL = "http://www.utair.ru/order-manage?rloc=ABC123&last_name=IVANOV"
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


def minimal_itinerary(booking_url: str = DIRECT_UTAIR_URL) -> dict[str, object]:
    return {
        "schema_version": "flight-calendar-ics-itinerary.v1",
        "pnr": "ABC123",
        "passengers": ["IVANOV"],
        "booking_url": booking_url,
        "flights": [
            {
                "flight_number": "UT123",
                "departure": {
                    "airport": "VKO",
                    "local": "2026-06-01T09:00",
                    "tz": "Europe/Moscow",
                },
                "arrival": {
                    "airport": "SVX",
                    "local": "2026-06-01T13:30",
                    "tz": "Asia/Yekaterinburg",
                },
                "status": "confirmed",
            }
        ],
    }


class RedirectResolutionContractTests(unittest.TestCase):
    def test_parser_reads_url_file_once_for_direct_url(self) -> None:
        from flight_calendar import parser, route_detection

        read_count = 0

        def counted_read(path: Path) -> str:
            nonlocal read_count
            read_count += 1
            return DIRECT_UTAIR_URL

        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as handle:
            handle.write(DIRECT_UTAIR_URL)
            handle.flush()
            with (
                mock.patch.object(
                    route_detection, "read_private_text", side_effect=counted_read
                ),
                mock.patch.object(
                    parser, "fetch_utair_token", return_value="token", create=True
                ),
                mock.patch.object(
                    parser.utair, "fetch_utair_token", return_value="token"
                ),
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
                mock.patch.object(
                    parser,
                    "validate_itinerary_contract",
                    side_effect=lambda value: value,
                ),
            ):
                parser._build_itinerary_from_url_file(Path(handle.name), [])

        self.assertEqual(read_count, 1)

    def test_parser_resolves_click_url_before_route_detection_and_adapter(self) -> None:
        from flight_calendar import parser

        observed: dict[str, object] = {}

        def fake_infer(
            args: argparse.Namespace, *, url_override: str | None = None
        ) -> dict[str, object]:
            observed["route_url"] = url_override
            return {"route": "utair", "confidence": 1.0, "evidence": ["host:utair.ru"]}

        def fake_parse(
            url: str | None, rloc: str | None, last_name: str | None
        ) -> tuple[str, str, str]:
            observed["adapter_url"] = url
            return "ABC123", "IVANOV", str(url)

        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as handle:
            handle.write(RAW_CLICK_URL)
            handle.flush()
            with (
                mock.patch.object(
                    parser,
                    "resolve_known_booking_redirect",
                    return_value=DIRECT_UTAIR_URL,
                    create=True,
                ) as resolver,
                mock.patch.object(parser, "infer_build_route", side_effect=fake_infer),
                mock.patch.object(
                    parser.utair, "parse_utair_source", side_effect=fake_parse
                ),
                mock.patch.object(
                    parser.utair, "fetch_utair_token", return_value="token"
                ),
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
                mock.patch.object(
                    parser,
                    "validate_itinerary_contract",
                    side_effect=lambda value: value,
                ),
            ):
                parser._build_itinerary_from_url_file(Path(handle.name), [])

        resolver.assert_called_once_with(RAW_CLICK_URL)
        self.assertEqual(observed["route_url"], DIRECT_UTAIR_URL)
        self.assertEqual(observed["adapter_url"], DIRECT_UTAIR_URL)

    def test_parser_dispatches_s7_url_to_s7_adapter_without_network(self) -> None:
        from flight_calendar import parser

        observed: dict[str, object] = {}
        fetched_payload = [{"air": {"routes": []}}]

        def fake_parse(
            url: str | None, booking_id: str | None, passenger_id: str | None
        ) -> tuple[str, str, str]:
            observed["adapter_url"] = url
            observed["booking_id"] = booking_id
            observed["passenger_id"] = passenger_id
            return "ABC123", "ivanov", NORMALIZED_S7_URL

        def fake_fetch(url: str) -> list[dict[str, object]]:
            observed["fetch_url"] = url
            return fetched_payload

        def fake_convert(
            data: object, tz_map: dict[str, str], booking_url: str | None = None
        ) -> dict[str, object]:
            observed["convert_data"] = data
            observed["convert_tz_map"] = tz_map
            observed["convert_booking_url"] = booking_url
            return minimal_itinerary(booking_url=NORMALIZED_S7_URL)

        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as handle:
            handle.write(DIRECT_S7_URL)
            handle.flush()
            with (
                mock.patch.object(
                    parser,
                    "infer_build_route",
                    return_value={"route": "s7", "confidence": 1.0, "evidence": []},
                ),
                mock.patch.object(parser.s7, "parse_s7_source", side_effect=fake_parse),
                mock.patch.object(parser.s7, "fetch_s7_order", side_effect=fake_fetch),
                mock.patch.object(
                    parser.s7, "convert_to_itinerary", side_effect=fake_convert
                ),
                mock.patch.object(
                    parser,
                    "validate_itinerary_contract",
                    side_effect=lambda value: value,
                ),
            ):
                result = parser._build_itinerary_from_url_file(
                    Path(handle.name), ["DME=Europe/Moscow"]
                )

        self.assertEqual(observed["adapter_url"], DIRECT_S7_URL)
        self.assertIsNone(observed["booking_id"])
        self.assertIsNone(observed["passenger_id"])
        self.assertEqual(observed["fetch_url"], NORMALIZED_S7_URL)
        self.assertIs(observed["convert_data"], fetched_payload)
        self.assertEqual(observed["convert_tz_map"]["DME"], "Europe/Moscow")
        self.assertEqual(observed["convert_booking_url"], NORMALIZED_S7_URL)
        self.assertEqual(result["booking_url"], NORMALIZED_S7_URL)

    def test_direct_utair_url_is_returned_without_http_resolution(self) -> None:
        from flight_calendar.redirect_resolution import resolve_known_booking_redirect

        with mock.patch(
            "flight_calendar.redirect_resolution.carrier_http.resolve_redirect_url"
        ) as http_resolver:
            self.assertEqual(
                resolve_known_booking_redirect(DIRECT_UTAIR_URL), DIRECT_UTAIR_URL
            )

        http_resolver.assert_not_called()

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

    def test_click_mail_utair_503_without_location_becomes_redacted_cli_failure(
        self,
    ) -> None:
        from flight_calendar import carrier_http
        from flight_calendar.errors import CliFailure
        from flight_calendar.redirect_resolution import resolve_known_booking_redirect

        class FakeResponse:
            status_code = 503
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
            with self.assertRaises(carrier_http.TransportError) as transport_ctx:
                carrier_http.resolve_redirect_url(RAW_CLICK_URL)

        assert_private_tokens_redacted(self, str(transport_ctx.exception))

        with mock.patch.object(
            carrier_http._requests, "request", side_effect=fake_request
        ):
            with self.assertRaises(CliFailure) as cli_ctx:
                resolve_known_booking_redirect(RAW_CLICK_URL)

        self.assertEqual(cli_ctx.exception.code, "redirect_resolution_failed")
        assert_private_tokens_redacted(self, str(cli_ctx.exception))

    def test_cli_rejects_click_redirect_to_untrusted_location_without_route_fallback(
        self,
    ) -> None:
        from flight_calendar import parser

        for resolved_url in (PRIVATE_RESOLVED_URL, HTTP_UTAIR_URL):
            with self.subTest(resolved_url=resolved_url):
                with tempfile.NamedTemporaryFile("w", encoding="utf-8") as handle:
                    handle.write(RAW_CLICK_URL)
                    handle.flush()
                    stdout = io.StringIO()
                    with (
                        mock.patch(
                            "flight_calendar.redirect_resolution.carrier_http.resolve_redirect_url",
                            return_value=resolved_url,
                        ),
                        mock.patch.object(parser, "infer_build_route") as infer_route,
                        contextlib.redirect_stdout(stdout),
                    ):
                        code = parser.main(
                            ["--json", "build", "--url-file", handle.name]
                        )

                infer_route.assert_not_called()
                payload = json.loads(stdout.getvalue())
                self.assertEqual(code, 2)
                self.assertEqual(payload["error"]["code"], "redirect_resolution_failed")
                serialized = json.dumps(payload, ensure_ascii=False)
                assert_private_tokens_redacted(self, serialized)
                self.assertNotIn("evil.example", serialized)

    def test_cli_success_stdout_does_not_expose_raw_or_resolved_private_url(
        self,
    ) -> None:
        from flight_calendar import parser

        with tempfile.TemporaryDirectory(prefix="flight-redirect-stdout.") as tmp:
            tmp_path = Path(tmp)
            url_file = tmp_path / "url.txt"
            output = tmp_path / "trip.ics"
            url_file.write_text(RAW_CLICK_URL, encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                mock.patch.object(
                    parser,
                    "resolve_known_booking_redirect",
                    return_value=DIRECT_UTAIR_URL,
                ),
                mock.patch.object(
                    parser,
                    "infer_build_route",
                    return_value={"route": "utair", "confidence": 1.0, "evidence": []},
                ),
                mock.patch.object(
                    parser.utair,
                    "parse_utair_source",
                    return_value=("ABC123", "IVANOV", DIRECT_UTAIR_URL),
                ),
                mock.patch.object(
                    parser.utair, "fetch_utair_token", return_value="token"
                ),
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
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["media"], f"MEDIA:{output}")
        emitted = stdout.getvalue() + stderr.getvalue()
        assert_private_tokens_redacted(self, emitted)


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
            self.assertEqual(kwargs.get("impersonate"), carrier_http.IMPERSONATE_TARGET)
            self.assertIn("User-Agent", kwargs.get("headers", {}))
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
            self.assertEqual(kwargs.get("impersonate"), carrier_http.IMPERSONATE_TARGET)
            self.assertIn("User-Agent", kwargs.get("headers", {}))
            return FakeResponse()

        with mock.patch.object(
            carrier_http._requests, "request", side_effect=fake_request
        ):
            with self.assertRaises(carrier_http.TransportError) as ctx:
                carrier_http.resolve_redirect_url(RAW_CLICK_URL)

        assert_private_tokens_redacted(self, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
