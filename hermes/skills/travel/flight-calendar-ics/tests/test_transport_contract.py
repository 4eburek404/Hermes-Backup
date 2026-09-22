"""Carrier HTTP owns the concrete HTTP engine and session mechanics."""

from __future__ import annotations

import ast
import contextlib
import sys
import unittest
from pathlib import Path
from typing import cast
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TransportContractTests(unittest.TestCase):
    def test_request_raw_uses_curl_cffi_with_browser_impersonation(self) -> None:
        from flight_calendar import carrier_http

        observed: dict[str, object] = {}

        class FakeResponse:
            status_code = 200
            headers = {"Content-Type": "application/json"}
            text = "{}"

        def fake_request(method: str, url: str, **kwargs: object) -> FakeResponse:
            observed.update(method=method, url=url, **kwargs)
            return FakeResponse()

        with mock.patch.object(
            carrier_http._requests, "request", side_effect=fake_request
        ):
            result = carrier_http.request_raw(
                "https://carrier.example/api",
                method="POST",
                headers={"X-Test": "1"},
                body=b"{}",
                timeout=17,
                sleep=lambda _seconds: None,
            )

        self.assertEqual(result, (200, "application/json", "{}"))
        self.assertEqual(observed["method"], "POST")
        self.assertEqual(observed["url"], "https://carrier.example/api")
        self.assertEqual(observed["data"], b"{}")
        self.assertEqual(observed["timeout"], 17)
        self.assertEqual(observed["impersonate"], "chrome")
        headers = cast(dict[str, str], observed["headers"])
        self.assertEqual(headers["X-Test"], "1")

    def test_session_requests_keep_engine_details_inside_transport(self) -> None:
        from flight_calendar import carrier_http

        calls: list[dict[str, object]] = []

        class FakeResponse:
            status_code = 200
            headers = {"Content-Type": "text/html"}
            text = "<form></form>"
            url = "https://carrier.example/final"

        class FakeSession:
            def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
                calls.append({"method": method, "url": url, **kwargs})
                return FakeResponse()

            def close(self) -> None:
                calls.append({"closed": True})

        with mock.patch.object(
            carrier_http._requests, "Session", return_value=FakeSession()
        ) as session_factory:
            with carrier_http.open_session() as session:
                result = carrier_http.request_session_raw(
                    session,
                    "https://carrier.example/start",
                    method="POST",
                    headers={"X-Test": "1"},
                    body={"field": "value"},
                    timeout=17,
                    sleep=lambda _seconds: None,
                )

        session_factory.assert_called_once_with(impersonate="chrome")
        self.assertEqual(result.url, "https://carrier.example/final")
        self.assertEqual(calls[-1], {"closed": True})
        self.assertEqual(calls[0]["method"], "POST")
        self.assertEqual(calls[0]["url"], "https://carrier.example/start")
        self.assertEqual(calls[0]["data"], {"field": "value"})
        self.assertEqual(calls[0]["timeout"], 17)
        self.assertEqual(calls[0]["allow_redirects"], True)

    def test_carrier_modules_do_not_import_concrete_http_engine(self) -> None:
        carriers = ROOT / "scripts" / "flight_calendar" / "carriers"
        forbidden = {"curl_cffi", "requests", "httpx", "urllib3", "aiohttp"}
        for path in sorted(carriers.glob("*.py")):
            if path.name == "__init__.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module.split(".", 1)[0])
            self.assertTrue(
                forbidden.isdisjoint(imports),
                f"{path.name} imports a concrete HTTP engine: {sorted(forbidden & set(imports))}",
            )

    def test_s7_form_flow_uses_one_shared_session(self) -> None:
        from flight_calendar import carrier_http
        from flight_calendar.carriers import s7

        initial_url = "https://myb.s7.ru/myb/manage-order"
        form_html = '<form action="/submit"><input name="bookingId" value="ABC123"></form>'
        payload_html = 'var __r_airs_data = [{"air": {}}];'
        responses = iter(
            (
                carrier_http.TransportResponse(
                    200,
                    "text/html",
                    form_html,
                    initial_url,
                    {"Content-Type": "text/html"},
                ),
                carrier_http.TransportResponse(
                    200,
                    "text/html",
                    payload_html,
                    "https://myb.s7.ru/submit",
                    {"Content-Type": "text/html"},
                ),
            )
        )
        observed: list[dict[str, object]] = []

        def request_session(_session: object, url: str, **kwargs: object):
            observed.append({"url": url, **kwargs})
            return next(responses)

        fake_session = object()
        with (
            mock.patch.object(
                carrier_http,
                "open_session",
                return_value=contextlib.nullcontext(fake_session),
            ),
            mock.patch.object(
                carrier_http,
                "request_session_raw",
                side_effect=request_session,
            ),
        ):
            result = s7.fetch_s7_order(initial_url)

        self.assertEqual(result, [{"air": {}}])
        self.assertEqual(len(observed), 2)
        self.assertEqual(observed[0]["url"], initial_url)
        self.assertEqual(observed[0].get("method", "GET"), "GET")
        self.assertEqual(observed[1]["url"], "https://myb.s7.ru/submit")
        self.assertEqual(observed[1]["method"], "POST")
        self.assertEqual(observed[1]["body"], {"bookingId": "ABC123"})


if __name__ == "__main__":
    unittest.main()
