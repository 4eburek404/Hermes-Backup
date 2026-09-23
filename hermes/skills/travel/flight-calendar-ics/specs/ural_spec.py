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
from urllib.parse import parse_qs, quote, urlparse
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "specs" / "fixtures" / "ural"
sys.path.insert(0, str(SCRIPTS))

BOOKING_URL = "https://service.uralairlines.ru/services?pnr=ABC123&lastName=IVANOV"
SYNTHETIC_FRONTEND = "https://ural-frontend.test/"
SYNTHETIC_API = "https://ural-api.test/api/"
ROOT_HTML = """
<html><head>
<script src="/12345/js/app.synthetic.js"></script>
<link href="/12345/css/app.synthetic.css">
</head><body></body></html>
"""
ENV_JSON = {"API_URL": SYNTHETIC_API, "API_KEY": "synthetic-api-key-001"}
STALE_API_KEY = "stale-api-key-001"
REFRESHED_API_KEY = "fresh-api-key-002"
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
                self.assertEqual(
                    normalized,
                    "https://service.uralairlines.ru/services?pnr=ABC123&lastName=IVANOV",
                )

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

    def _seed_cached_config(self, api_key: str) -> None:
        cache_path = Path(self.tempdir.name) / "ural-deployment.json"
        cache_path.write_text(
            json.dumps(
                {
                    "version": "12345",
                    "API_URL": SYNTHETIC_API,
                    "API_KEY": api_key,
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def _recovery_transport(
        self,
        *,
        reservation_statuses: list[int],
        refresh_failure: str | None = None,
    ) -> tuple[list[dict[str, Any]], Any]:
        from flight_calendar.carriers import ural

        calls: list[dict[str, Any]] = []
        reservation_attempt = 0
        stale_header = ural.generate_api_key_header(STALE_API_KEY, 1700000000000, 1000)
        refreshed_header = ural.generate_api_key_header(REFRESHED_API_KEY, 1700000000000, 1000)

        def transport(url: str, **kwargs: Any) -> tuple[int, str, str]:
            nonlocal reservation_attempt
            parsed = urlparse(url)
            headers = kwargs.get("headers", {})
            calls.append(
                {
                    "url": url,
                    "method": kwargs.get("method", "GET"),
                    "headers": headers,
                }
            )
            if url == SYNTHETIC_FRONTEND:
                if refresh_failure == "root":
                    return 503, "text/plain", "frontend unavailable"
                return 200, "text/html", ROOT_HTML
            if parsed.path == "/12345/env/env.json":
                if refresh_failure == "env":
                    return 503, "text/plain", "env unavailable"
                return 200, "application/json", json.dumps(
                    {"API_URL": SYNTHETIC_API, "API_KEY": REFRESHED_API_KEY}
                )
            if parsed.path == "/api/settings/CurrentDateUtc":
                return 200, "text/plain", "1700000000"
            if parsed.path == "/api/Reservation":
                reservation_attempt += 1
                expected_header = (
                    stale_header if reservation_attempt == 1 else refreshed_header
                )
                if headers.get("X-Api-Key") != expected_header:
                    raise AssertionError("unexpected X-Api-Key for recovery attempt")
                status = reservation_statuses[min(reservation_attempt - 1, len(reservation_statuses) - 1)]
                if status == 401:
                    return 401, "", ""
                if status == 200:
                    return 200, "application/json", RESERVATION_TEXT
                return status, "text/plain", "synthetic reservation failure"
            raise AssertionError(f"unexpected synthetic endpoint: {parsed.path}")

        return calls, transport

    def test_cached_auth_failure_refreshes_deployment_and_retries_once(self) -> None:
        from flight_calendar import carrier_http
        from flight_calendar.carriers import ural

        calls, transport = self._recovery_transport(reservation_statuses=[401, 200])
        self._seed_cached_config(STALE_API_KEY)
        with (
            mock.patch.object(carrier_http, "request_raw", side_effect=transport),
            mock.patch.object(ural.time, "time", return_value=1699999999),
        ):
            result = ural.fetch_ural_reservation(
                "ABC123",
                "IVANOV",
                frontend_base=SYNTHETIC_FRONTEND,
            )

        self.assertTrue(result["success"])
        paths = [urlparse(call["url"]).path for call in calls]
        reservation_indexes = [
            index for index, path in enumerate(paths) if path == "/api/Reservation"
        ]
        self.assertEqual(len(reservation_indexes), 2)
        self.assertEqual(paths.count("/"), 1)
        self.assertEqual(paths.count("/12345/env/env.json"), 1)
        self.assertNotIn("/", paths[: reservation_indexes[0]])
        self.assertLess(reservation_indexes[0], paths.index("/"))
        self.assertLess(paths.index("/"), reservation_indexes[1])

    def test_cached_auth_failure_refreshes_and_retries_at_most_once(self) -> None:
        from flight_calendar import carrier_http
        from flight_calendar.carriers import ural

        calls, transport = self._recovery_transport(reservation_statuses=[401, 401])
        self._seed_cached_config(STALE_API_KEY)
        with (
            mock.patch.object(carrier_http, "request_raw", side_effect=transport),
            mock.patch.object(ural.time, "time", return_value=1699999999),
        ):
            with self.assertRaises(carrier_http.TransportError):
                ural.fetch_ural_reservation(
                    "ABC123",
                    "IVANOV",
                    frontend_base=SYNTHETIC_FRONTEND,
                )

        paths = [urlparse(call["url"]).path for call in calls]
        self.assertEqual(paths.count("/api/Reservation"), 2)
        self.assertEqual(paths.count("/"), 1)
        self.assertEqual(paths.count("/12345/env/env.json"), 1)

    def test_non_authentication_error_does_not_refresh_cached_config(self) -> None:
        from flight_calendar import carrier_http
        from flight_calendar.carriers import ural

        calls, transport = self._recovery_transport(reservation_statuses=[404])
        self._seed_cached_config(STALE_API_KEY)
        with (
            mock.patch.object(carrier_http, "request_raw", side_effect=transport),
            mock.patch.object(ural.time, "time", return_value=1699999999),
        ):
            with self.assertRaises(carrier_http.TransportError):
                ural.fetch_ural_reservation(
                    "ABC123",
                    "IVANOV",
                    frontend_base=SYNTHETIC_FRONTEND,
                )

        paths = [urlparse(call["url"]).path for call in calls]
        self.assertEqual(paths.count("/api/Reservation"), 1)
        self.assertNotIn("/", paths)
        self.assertNotIn("/12345/env/env.json", paths)

    def test_refresh_bootstrap_failure_is_propagated_without_retry_loop(self) -> None:
        from flight_calendar import carrier_http
        from flight_calendar.carriers import ural

        for failure, expected_paths in (
            ("root", ["/api/settings/CurrentDateUtc", "/api/Reservation", "/"]),
            (
                "env",
                [
                    "/api/settings/CurrentDateUtc",
                    "/api/Reservation",
                    "/",
                    "/12345/env/env.json",
                ],
            ),
        ):
            with self.subTest(failure=failure):
                calls, transport = self._recovery_transport(
                    reservation_statuses=[401],
                    refresh_failure=failure,
                )
                self._seed_cached_config(STALE_API_KEY)
                with (
                    mock.patch.object(carrier_http, "request_raw", side_effect=transport),
                    mock.patch.object(ural.time, "time", return_value=1699999999),
                ):
                    with self.assertRaises(carrier_http.TransportError):
                        ural.fetch_ural_reservation(
                            "ABC123",
                            "IVANOV",
                            frontend_base=SYNTHETIC_FRONTEND,
                        )

                paths = [urlparse(call["url"]).path for call in calls]
                self.assertEqual(paths, expected_paths)
                self.assertEqual(paths.count("/api/Reservation"), 1)

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
            raw["data"], booking_url="https://service.uralairlines.ru/"
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
    def test_ural_mail_wrapper_builds_calendar_through_public_url_cli(self) -> None:
        from flight_calendar import carrier_http, parser

        target_url = "https://service.uralairlines.ru/services?pnr=ABC123&lastName=IVANOV&utm_source=synthetic"
        wrapper_url = (
            "https://tn-hgl.mckx.ru/c/SYNTHETIC_A/SYNTHETIC_B/SYNTHETIC_C/"
            f"?u={quote(target_url, safe='')}"
        )
        transport_calls: list[tuple[str, str]] = []

        def transport(url: str, **kwargs: Any) -> tuple[int, str, str]:
            parsed = urlparse(url)
            transport_calls.append((parsed.path, parsed.query))
            if parsed.path == "/api/settings/CurrentDateUtc":
                return 200, "text/plain", "1700000000"
            if parsed.path == "/api/Reservation":
                return 200, "application/json", RESERVATION_TEXT
            raise AssertionError("unexpected Ural transport endpoint")

        with tempfile.TemporaryDirectory(prefix="ural-wrapper-cli.") as tmp:
            cache_dir = Path(tmp) / "cache"
            cache_dir.mkdir(mode=0o700)
            (cache_dir / "ural-deployment.json").write_text(
                json.dumps(
                    {
                        "version": "12345",
                        "API_URL": SYNTHETIC_API,
                        "API_KEY": "synthetic-api-key-001",
                    }
                ),
                encoding="utf-8",
            )
            output = Path(tmp) / "flight.ics"
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                mock.patch.dict(os.environ, {"FLIGHT_CALENDAR_CACHE_DIR": str(cache_dir)}),
                mock.patch.object(carrier_http, "request_raw", side_effect=transport),
                mock.patch.object(
                    carrier_http,
                    "resolve_redirect_url",
                    side_effect=AssertionError("mail destination is already in the source URL"),
                ),
                mock.patch.object(
                    parser,
                    "build_timezone_map",
                    return_value={"DME": "Europe/Moscow", "SVX": "Asia/Yekaterinburg"},
                ),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                code = parser.main(
                    ["--json", "build", "--url", wrapper_url, "--output", str(output)]
                )

            self.assertEqual(code, 0, stdout.getvalue() + stderr.getvalue())
            payload = json.loads(stdout.getvalue())
            self.assertIs(payload["ok"], True)
            self.assertEqual(payload["media"], f"MEDIA:{output.resolve()}")
            self.assertEqual(payload["segments_count"], 2)
            self.assertTrue(output.is_file())
            ics_text = output.read_text(encoding="utf-8").replace("\n ", "")
            canonical_url = (
                "https://service.uralairlines.ru/services"
                "?pnr=ABC123&lastName=IVANOV"
            )
            self.assertIn(canonical_url, ics_text)
            self.assertNotIn("tn-hgl.mckx.ru", ics_text)
            self.assertNotIn("utm_source=", ics_text)
            self.assertEqual(
                [path for path, _query in transport_calls],
                ["/api/settings/CurrentDateUtc", "/api/Reservation"],
            )
            reservation_query = parse_qs(transport_calls[-1][1])
            self.assertEqual(
                reservation_query,
                {"pnrNumber": ["ABC123"], "lastName": ["IVANOV"]},
            )
            emitted = stdout.getvalue() + stderr.getvalue()
            for private_value in (
                wrapper_url,
                target_url,
                "ABC123",
                "IVANOV",
                "synthetic-click",
            ):
                self.assertNotIn(private_value, emitted)

    def test_ural_mail_wrapper_rejects_untrusted_shapes_and_targets(self) -> None:
        from flight_calendar import carrier_http, parser

        valid_target = "https://service.uralairlines.ru/services?pnr=ABC123&lastName=IVANOV"
        invalid_sources = (
            (
                "http://tn-hgl.mckx.ru/c/synthetic-click/?u="
                + quote(valid_target, safe=""),
                "route_unknown",
            ),
            (
                "https://tracker.example/c/synthetic-click/?u="
                + quote(valid_target, safe=""),
                "route_unknown",
            ),
            ("https://tn-hgl.mckx.ru/c/SYNTHETIC_A/SYNTHETIC_B/SYNTHETIC_C/", "route_unknown"),
            (
                "https://tn-hgl.mckx.ru/c/SYNTHETIC_A/SYNTHETIC_B/SYNTHETIC_C/?u="
                + quote(valid_target, safe="")
                + "&u="
                + quote(valid_target, safe=""),
                "route_unknown",
            ),
            (
                "https://tn-hgl.mckx.ru/c/SYNTHETIC_A/SYNTHETIC_B/SYNTHETIC_C/?u="
                + quote("https://service.uralairlines.ru/?pnr=ABC123", safe="")
                + "&lastName=IVANOV",
                "route_unknown",
            ),
            (
                "https://tn-hgl.mckx.ru/c/SYNTHETIC_A/SYNTHETIC_B/SYNTHETIC_C/?u=%ZZ",
                "route_unknown",
            ),
            (
                "https://tn-hgl.mckx.ru/c/SYNTHETIC_A/SYNTHETIC_B/SYNTHETIC_C/?u="
                + quote(valid_target.replace("https://", "http://"), safe=""),
                "route_unknown",
            ),
            (
                "https://tn-hgl.mckx.ru/c/SYNTHETIC_A/SYNTHETIC_B/SYNTHETIC_C/?u="
                + quote(valid_target.replace("service.uralairlines.ru", "evil.example"), safe=""),
                "route_unknown",
            ),
            (
                "https://tn-hgl.mckx.ru/c/SYNTHETIC_A/SYNTHETIC_B/SYNTHETIC_C/?u="
                + quote(valid_target.replace("/services?pnr=", "/unsupported?pnr="), safe=""),
                "route_unknown",
            ),
            (
                "https://tracker.example/click?u=" + quote(valid_target, safe=""),
                "route_unknown",
            ),
        )
        network_calls: list[str] = []

        def network_called(*args: Any, **kwargs: Any) -> None:
            del args, kwargs
            network_calls.append("carrier_http")
            raise AssertionError("untrusted target reached network")

        with (
            mock.patch.object(carrier_http, "request_raw", side_effect=network_called),
            mock.patch.object(carrier_http, "resolve_redirect_url", side_effect=network_called),
            mock.patch.object(parser, "build_timezone_map", return_value={}),
        ):
            for source_url, expected_code in invalid_sources:
                with self.subTest(expected_code=expected_code, source=source_url.split("?", 1)[0]):
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        code = parser.main(["--json", "build", "--url", source_url])
                    self.assertEqual(code, 2, stdout.getvalue() + stderr.getvalue())
                    payload = json.loads(stdout.getvalue())
                    self.assertIs(payload["ok"], False)
                    self.assertEqual(payload["error"]["code"], expected_code)
                    emitted = stdout.getvalue() + stderr.getvalue()
                    for private_value in (source_url, "ABC123", "IVANOV", "evil.example"):
                        self.assertNotIn(private_value, emitted)

        self.assertEqual(network_calls, [])

    def test_bootstrap_failure_is_redacted_at_public_json_cli_boundary(self) -> None:
        from flight_calendar import carrier_http, parser

        private_url = "https://service.uralairlines.ru/services?pnr=ABC123&lastName=IVANOV"

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
