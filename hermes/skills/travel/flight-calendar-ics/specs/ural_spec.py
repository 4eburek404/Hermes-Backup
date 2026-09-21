#!/usr/bin/env python3
"""Executable specification for the public Ural Airlines URL process.

The spec checks observable source, configuration, transport, key-generation,
conversion, and privacy contracts.  External HTTP is replaced only at the
transport boundary; the adapter and canonical converter remain real.

Run from the skill root with ``python3 specs/ural_spec.py``.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "specs" / "fixtures" / "ural"
sys.path.insert(0, str(SCRIPTS))

BOOKING_URL = "https://service.uralairlines.ru/?pnr=ABC123&lastName=IVANOV"
SYNTHETIC_FRONTEND = "https://ural-frontend.test/"
SYNTHETIC_API = "https://ural-api.test/api/"
ROOT_HTML = """
<html><head>
<script src="/12345/js/app.synthetic.js"></script>
<link href="/12345/css/app.synthetic.css">
</head><body></body></html>
"""
ENV_JSON = {"API_URL": SYNTHETIC_API, "API_KEY": "synthetic-api-key-001"}
RESERVATION_TEXT = (FIXTURES / "reservation.json").read_text(encoding="utf-8")


def _args(url: str) -> argparse.Namespace:
    return argparse.Namespace(url=url, url_file=None, input=None)


def _response_for(url: str, *, method: str = "GET") -> tuple[int, str, str]:
    parsed = urlparse(url)
    if method != "GET":
        raise AssertionError(f"unexpected method: {method}")
    if url == SYNTHETIC_FRONTEND:
        return 200, "text/html", ROOT_HTML
    if parsed.path == "/12345/env/env.json":
        return 200, "application/json", json.dumps(ENV_JSON)
    if parsed.path == "/api/settings/CurrentDateUtc":
        return 200, "text/plain", "1700000000"
    if parsed.path == "/api/Reservation":
        return 200, "application/json", RESERVATION_TEXT
    raise AssertionError(f"unexpected synthetic endpoint: {parsed.path}")


class UralSourceSpecification(unittest.TestCase):
    def test_trusted_exact_https_host_routes_without_credentials(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        for url in (
            "https://service.uralairlines.ru/",
            "https://service.uralairlines.ru/?utm_source=synthetic",
        ):
            with self.subTest(url=url):
                self.assertEqual(infer_build_route(_args(url))["route"], "ural")

    def test_router_does_not_know_ural_credential_aliases(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        self.assertEqual(
            infer_build_route(
                _args("https://service.uralairlines.ru/?pnrnumber=ABC123")
            )["route"],
            "ural",
        )

    def test_adapter_owns_aliases_and_ignores_tracking_parameters(self) -> None:
        from flight_calendar.carriers import ural

        cases = (
            "pnr=abc123&lastName=ivanov",
            "pnrNumber=abc123&lastname=ivanov&utm_source=synthetic",
            "pnrnumber=abc123&surname=ivanov&utm_campaign=synthetic",
        )
        for query in cases:
            with self.subTest(query=query):
                locator, surname, normalized = ural.parse_ural_source(
                    f"{SYNTHETIC_FRONTEND}?{query}"
                )
                self.assertEqual((locator, surname), ("ABC123", "IVANOV"))
                if "utm_" in query:
                    self.assertIn("utm_", normalized)

    def test_missing_and_invalid_credentials_fail_before_network_without_leak(self) -> None:
        from flight_calendar.carriers import ural
        from flight_calendar.errors import CliFailure

        for url, expected in (
            ("https://service.uralairlines.ru/", "route_input_insufficient"),
            (
                "https://service.uralairlines.ru/?pnr=BAD&lastName=IVANOV",
                "validation_error",
            ),
        ):
            with self.subTest(url=url):
                with mock.patch.object(ural.carrier_http, "request_raw") as request:
                    try:
                        ural.parse_ural_source(url)
                    except CliFailure as exc:
                        self.assertEqual(exc.code, expected)
                        message = str(exc)
                    except ValueError as exc:
                        self.assertEqual(expected, "validation_error")
                        message = str(exc)
                    else:  # pragma: no cover - assertion guard
                        self.fail("source credentials unexpectedly accepted")
                    request.assert_not_called()
                    self.assertNotIn("service.uralairlines.ru", message)
                    self.assertNotIn("ABC123", message)
                    self.assertNotIn("IVANOV", message)


class UralConfigurationAndProtocolSpecification(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="ural-spec-cache.")
        self.cache_patch = mock.patch.dict(
            os.environ, {"FLIGHT_CALENDAR_CACHE_DIR": self.tempdir.name}
        )
        self.cache_patch.start()

    def tearDown(self) -> None:
        self.cache_patch.stop()
        self.tempdir.cleanup()

    def test_cache_miss_uses_root_and_versioned_env_then_direct_reservation(self) -> None:
        from flight_calendar import carrier_http
        from flight_calendar.carriers import ural

        calls: list[dict[str, Any]] = []

        def transport(url: str, **kwargs: Any) -> tuple[int, str, str]:
            calls.append({"url": url, "method": kwargs.get("method", "GET"), "headers": kwargs.get("headers", {})})
            return _response_for(url, method=kwargs.get("method", "GET"))

        with mock.patch.object(carrier_http, "request_raw", side_effect=transport):
            result = ural.fetch_ural_reservation(
                "ABC123", "IVANOV", frontend_base=SYNTHETIC_FRONTEND
            )

        self.assertTrue(result["success"])
        paths = [urlparse(call["url"]).path for call in calls]
        self.assertEqual(paths, ["/", "/12345/env/env.json", "/api/settings/CurrentDateUtc", "/api/Reservation"])
        self.assertTrue(all(call["method"] == "GET" for call in calls))
        self.assertFalse(any(path.endswith(".js") for path in paths))
        self.assertNotIn("Session", " ".join(paths))
        self.assertTrue((Path(self.tempdir.name) / "ural-deployment.json").is_file())
        cached = (Path(self.tempdir.name) / "ural-deployment.json").read_text(encoding="utf-8")
        self.assertNotIn("ABC123", cached)
        self.assertNotIn("IVANOV", cached)

    def test_cache_hit_skips_frontend_and_env_but_keeps_clock_and_reservation(self) -> None:
        from flight_calendar import carrier_http
        from flight_calendar.carriers import ural

        first_calls: list[str] = []

        def first_transport(url: str, **kwargs: Any) -> tuple[int, str, str]:
            first_calls.append(url)
            return _response_for(url, method=kwargs.get("method", "GET"))

        with mock.patch.object(carrier_http, "request_raw", side_effect=first_transport):
            ural.fetch_ural_reservation("ABC123", "IVANOV", frontend_base=SYNTHETIC_FRONTEND)

        second_calls: list[str] = []

        def second_transport(url: str, **kwargs: Any) -> tuple[int, str, str]:
            second_calls.append(url)
            return _response_for(url, method=kwargs.get("method", "GET"))

        with mock.patch.object(carrier_http, "request_raw", side_effect=second_transport):
            ural.fetch_ural_reservation("ABC123", "IVANOV", frontend_base=SYNTHETIC_FRONTEND)

        self.assertEqual(len(first_calls), 4)
        self.assertEqual(
            [urlparse(url).path for url in second_calls],
            ["/api/settings/CurrentDateUtc", "/api/Reservation"],
        )

    def test_explicit_refresh_reloads_root_and_env_without_booking_data(self) -> None:
        from flight_calendar import carrier_http
        from flight_calendar.carriers import ural

        def bootstrap(url: str, **kwargs: Any) -> tuple[int, str, str]:
            return _response_for(url, method=kwargs.get("method", "GET"))

        with mock.patch.object(carrier_http, "request_raw", side_effect=bootstrap):
            ural.load_deployment_config(SYNTHETIC_FRONTEND)

        refresh_calls: list[str] = []

        def refresh_transport(url: str, **kwargs: Any) -> tuple[int, str, str]:
            refresh_calls.append(url)
            return _response_for(url, method=kwargs.get("method", "GET"))

        with mock.patch.object(carrier_http, "request_raw", side_effect=refresh_transport):
            ural.load_deployment_config(SYNTHETIC_FRONTEND, refresh=True)

        self.assertEqual(
            [urlparse(url).path for url in refresh_calls],
            ["/", "/12345/env/env.json"],
        )

    def test_cached_deployment_credentials_are_owner_only(self) -> None:
        from flight_calendar import carrier_http
        from flight_calendar.carriers import ural

        cache_dir = Path(self.tempdir.name) / "nested-cache"
        with mock.patch.dict(os.environ, {"FLIGHT_CALENDAR_CACHE_DIR": str(cache_dir)}):
            def bootstrap(url: str, **kwargs: Any) -> tuple[int, str, str]:
                return _response_for(url, method=kwargs.get("method", "GET"))

            with mock.patch.object(carrier_http, "request_raw", side_effect=bootstrap):
                ural.load_deployment_config(SYNTHETIC_FRONTEND)

        cache_file = cache_dir / "ural-deployment.json"
        self.assertEqual(stat.S_IMODE(cache_dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(cache_file.stat().st_mode), 0o600)

    def test_clock_sync_failure_falls_back_to_zero_without_skipping_reservation(self) -> None:
        from flight_calendar import carrier_http
        from flight_calendar.carriers import ural

        calls: list[str] = []

        def transport(url: str, **kwargs: Any) -> tuple[int, str, str]:
            calls.append(urlparse(url).path)
            if urlparse(url).path == "/api/settings/CurrentDateUtc":
                raise carrier_http.TransportError("clock sync unavailable")
            return _response_for(url, method=kwargs.get("method", "GET"))

        with mock.patch.object(carrier_http, "request_raw", side_effect=transport):
            result = ural.fetch_ural_reservation(
                "ABC123", "IVANOV", frontend_base=SYNTHETIC_FRONTEND
            )

        self.assertTrue(result["success"])
        self.assertEqual(calls[-1], "/api/Reservation")


    def test_malformed_bootstrap_configuration_is_controlled_and_private_safe(self) -> None:
        from flight_calendar import carrier_http
        from flight_calendar.carriers import ural

        cases = (
            ("<html><script src='/no-version/app.js'></script></html>", json.dumps(ENV_JSON)),
            (ROOT_HTML, json.dumps({"API_URL": SYNTHETIC_API})),
            (ROOT_HTML, json.dumps({"API_KEY": "synthetic-api-key-001"})),
            (ROOT_HTML, json.dumps({"API_URL": "not-a-url", "API_KEY": "synthetic-api-key-001"})),
            (ROOT_HTML, json.dumps({"API_URL": SYNTHETIC_API, "API_KEY": ""})),
        )
        for html, env_text in cases:
            with self.subTest(env_text=env_text):
                calls = 0

                def transport(url: str, **kwargs: Any) -> tuple[int, str, str]:
                    nonlocal calls
                    calls += 1
                    if url == SYNTHETIC_FRONTEND:
                        return 200, "text/html", html
                    return 200, "application/json", env_text

                with mock.patch.object(carrier_http, "request_raw", side_effect=transport):
                    with self.assertRaises(ValueError) as ctx:
                        ural.fetch_ural_reservation(
                            "ABC123", "IVANOV", frontend_base=SYNTHETIC_FRONTEND
                        )
                self.assertGreaterEqual(calls, 1)
                self.assertNotIn("ABC123", str(ctx.exception))
                self.assertNotIn("IVANOV", str(ctx.exception))
                self.assertNotIn("API_KEY", str(ctx.exception))

    def test_reservation_uses_get_query_and_api_key_without_session(self) -> None:
        from flight_calendar import carrier_http
        from flight_calendar.carriers import ural

        observed: dict[str, Any] = {}

        def transport(url: str, **kwargs: Any) -> tuple[int, str, str]:
            if urlparse(url).path == "/api/Reservation":
                observed.update(url=url, method=kwargs.get("method"), headers=kwargs.get("headers", {}))
            return _response_for(url, method=kwargs.get("method", "GET"))

        with mock.patch.object(carrier_http, "request_raw", side_effect=transport):
            ural.fetch_ural_reservation(
                "ABC123", "IVANOV", frontend_base=SYNTHETIC_FRONTEND
            )

        self.assertEqual(observed["method"], "GET")
        self.assertEqual(parse_qs(urlparse(observed["url"]).query), {"pnrNumber": ["ABC123"], "lastName": ["IVANOV"]})
        self.assertIn("X-Api-Key", observed["headers"])
        self.assertTrue(observed["headers"]["X-Api-Key"])
        self.assertNotIn("X-Session", observed["headers"])
        self.assertNotIn("Session", observed["url"])


class UralKeyAndClockSpecification(unittest.TestCase):
    def test_fixed_vectors_are_python_only_deterministic_contract(self) -> None:
        from flight_calendar.carriers.ural import generate_api_key_header

        vectors = json.loads((FIXTURES / "key-vectors.json").read_text(encoding="utf-8"))
        for vector in vectors:
            with self.subTest(time=vector["time"], diff=vector["diff"], key=vector["key"][:4]):
                self.assertEqual(
                    generate_api_key_header(vector["key"], vector["time"], vector["diff"]),
                    vector["output"],
                )

    def test_key_generator_has_no_http_dependency_and_clock_is_separate(self) -> None:
        from flight_calendar import carrier_http
        from flight_calendar.carriers import ural

        with mock.patch.object(carrier_http, "request_raw", side_effect=AssertionError("network")):
            value = ural.generate_api_key_header("synthetic-key", 1700000000000, 0)
        self.assertTrue(value)

        with (
            mock.patch.object(ural, "http_json", return_value=1700000000),
            mock.patch.object(ural.time, "time", return_value=1699999999),
        ):
            self.assertEqual(ural.compute_timestamp_diff(SYNTHETIC_API), 1000)


class UralConversionSpecification(unittest.TestCase):
    def test_sanitized_reservation_wrapper_converts_round_trip_to_two_flights(self) -> None:
        from flight_calendar.carriers import ural

        raw = json.loads(RESERVATION_TEXT)
        itinerary = ural.convert_to_itinerary(
            raw, booking_url="https://service.uralairlines.ru/"
        )
        self.assertEqual(len(itinerary["flights"]), 2)
        first, second = itinerary["flights"]
        self.assertEqual(
            (first["flight_number"], first["departure"], first["arrival"], first["aircraft"]),
            ("U6 273", {"airport": "DME", "local": "2026-09-21T08:25"}, {"airport": "SVX", "local": "2026-09-21T12:55"}, "Airbus A320"),
        )
        self.assertEqual(
            (second["flight_number"], second["departure"], second["arrival"], second["aircraft"]),
            ("U6 270", {"airport": "SVX", "local": "2026-09-24T20:30"}, {"airport": "DME", "local": "2026-09-24T21:00"}, "Airbus A321"),
        )
        self.assertEqual(itinerary["pnr"], "ABC123")
        self.assertEqual(itinerary["passenger"], "SANITIZED PASSENGER")
        self.assertEqual(itinerary["ticket_number"], "0000000000000")


class UralCliPrivacySpecification(unittest.TestCase):
    def test_bootstrap_failure_is_redacted_at_public_json_cli_boundary(self) -> None:
        from flight_calendar import carrier_http, parser

        private_url = "https://service.uralairlines.ru/?pnr=ABC123&lastName=IVANOV"

        def transport(url: str, **kwargs: Any) -> tuple[int, str, str]:
            if url == "https://service.uralairlines.ru/":
                return 200, "text/html", ROOT_HTML
            return 200, "application/json", json.dumps(
                {"API_URL": "not-a-url", "API_KEY": "synthetic-api-key-001"}
            )

        stdout = io.StringIO()
        with (
            mock.patch.object(carrier_http, "request_raw", side_effect=transport),
            mock.patch.object(parser, "build_timezone_map", return_value={}),
        ):
            with contextlib.redirect_stdout(stdout):
                code = parser.main(["--json", "build", "--url", private_url])

        self.assertEqual(code, 2)
        emitted = stdout.getvalue()
        self.assertNotIn(private_url, emitted)
        self.assertNotIn("ABC123", emitted)
        self.assertNotIn("IVANOV", emitted)
        self.assertNotIn("not-a-url", emitted)


if __name__ == "__main__":
    unittest.main()
