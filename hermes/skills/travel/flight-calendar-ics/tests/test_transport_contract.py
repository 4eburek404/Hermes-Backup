"""Carrier HTTP uses the required curl_cffi transport boundary."""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
