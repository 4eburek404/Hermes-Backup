"""Contract test for WP-8: shared carrier HTTP transport.

Locks the privacy and reliability contract of ``flight_calendar.carrier_http``:
error messages never contain URLs or credentials, transient failures are
retried with backoff, HTTP 4xx is never retried, carriers no longer hand-roll
urlopen plumbing, and doctor reports the required curl_cffi transport.
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
CARRIERS = SCRIPTS / "flight_calendar" / "carriers"
CLI = SCRIPTS / "flight_calendar_ics.py"

SECRET_URL = "https://api.example.test/v1/pnr?pnr=SECRETPNR&lastName=SECRETNAME"


def load_carrier_http():
    script_dir = str(SCRIPTS.resolve())
    old_path = list(sys.path)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    try:
        return importlib.import_module("flight_calendar.carrier_http")
    finally:
        sys.path[:] = old_path


class CarrierHttpTransportContract(unittest.TestCase):
    def setUp(self) -> None:
        self.http = load_carrier_http()
        self._original_fetch = self.http._fetch_once

    def tearDown(self) -> None:
        self.http._fetch_once = self._original_fetch

    def test_public_api_and_transport_detection(self) -> None:
        for name in ["request_raw", "request_text", "request_json", "browser_headers", "active_transport", "TransportError"]:
            self.assertTrue(hasattr(self.http, name), name)
        self.assertEqual(self.http.active_transport(), "curl_cffi")
        self.assertTrue(issubclass(self.http.TransportError, ValueError))

    def test_missing_curl_cffi_fails_fast_with_install_hint(self) -> None:
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        script = """
import importlib.abc
import sys

class BlockCurlCffi(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "curl_cffi" or fullname.startswith("curl_cffi."):
            raise ImportError("blocked for contract test")
        return None

sys.meta_path.insert(0, BlockCurlCffi())
sys.path.insert(0, "scripts")
try:
    import flight_calendar.carrier_http
except ImportError as exc:
    print(str(exc))
    raise SystemExit(0)
raise SystemExit("carrier_http imported without curl_cffi")
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=SKILL_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("requires curl_cffi", result.stdout)
        self.assertIn("python -m pip install curl_cffi", result.stdout)

    def test_transient_network_errors_are_retried_with_backoff(self) -> None:
        attempts, naps = [], []

        def flaky(url, *, method, headers, body, timeout):
            attempts.append(1)
            if len(attempts) < 3:
                raise OSError("temporary failure")
            return 200, "application/json", '{"ok": true}'

        self.http._fetch_once = flaky
        data = self.http.request_json(SECRET_URL, label="Test API", sleep=naps.append)
        self.assertEqual(data, {"ok": True})
        self.assertEqual(len(attempts), 3)
        self.assertEqual(len(naps), 2)
        self.assertLess(naps[0], naps[1], "backoff must grow")

    def test_http_5xx_is_retried_then_succeeds(self) -> None:
        attempts = []

        def flaky(url, *, method, headers, body, timeout):
            attempts.append(1)
            if len(attempts) == 1:
                return 502, "text/html", "bad gateway"
            return 200, "application/json", '{"ok": 1}'

        self.http._fetch_once = flaky
        data = self.http.request_json(SECRET_URL, label="Test API", sleep=lambda _s: None)
        self.assertEqual(data, {"ok": 1})
        self.assertEqual(len(attempts), 2)

    def test_http_4xx_is_not_retried_and_message_is_redaction_safe(self) -> None:
        attempts = []

        def not_found(url, *, method, headers, body, timeout):
            attempts.append(1)
            return 404, "application/json", '{"error": "nope"}'

        self.http._fetch_once = not_found
        with self.assertRaises(self.http.TransportError) as ctx:
            self.http.request_json(SECRET_URL, label="Test API", sleep=lambda _s: None)
        self.assertEqual(len(attempts), 1, "4xx must not be retried")
        message = str(ctx.exception)
        self.assertIn("Test API", message)
        self.assertIn("404", message)
        for secret in ["SECRETPNR", "SECRETNAME", "api.example.test", SECRET_URL]:
            self.assertNotIn(secret, message)

    def test_persistent_network_failure_message_is_redaction_safe(self) -> None:
        def down(url, *, method, headers, body, timeout):
            raise OSError("no route to host")

        self.http._fetch_once = down
        with self.assertRaises(self.http.TransportError) as ctx:
            self.http.request_text(SECRET_URL, label="Test API", sleep=lambda _s: None)
        message = str(ctx.exception)
        self.assertIn("Test API", message)
        for secret in ["SECRETPNR", "SECRETNAME", "api.example.test"]:
            self.assertNotIn(secret, message)

    def test_request_raw_returns_error_bodies_for_caller_side_sniffing(self) -> None:
        # Anti-bot interstitials (e.g. Ngenix) arrive as HTML with 403/503;
        # callers like the Aeroflot adapter must receive the body to detect them.
        def blocked(url, *, method, headers, body, timeout):
            return 403, "text/html", "<!doctype html>ngenix browser check"

        self.http._fetch_once = blocked
        status, content_type, text = self.http.request_raw(SECRET_URL, label="Test API", sleep=lambda _s: None)
        self.assertEqual(status, 403)
        self.assertIn("ngenix", text)


class CarriersUseSharedTransportContract(unittest.TestCase):
    def test_shared_transport_has_no_urllib_http_fallback(self) -> None:
        source = (SCRIPTS / "flight_calendar" / "carrier_http.py").read_text(encoding="utf-8")
        self.assertNotIn("urlopen", source)
        self.assertNotIn("urllib.request", source)
        self.assertNotIn('return "urllib"', source)

    def test_carriers_do_not_hand_roll_urlopen(self) -> None:
        offenders = []
        for path in sorted(CARRIERS.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            if "urlopen" in source or "urllib.request" in source:
                offenders.append(path.name)
        self.assertEqual(offenders, [], f"carriers must use flight_calendar.carrier_http: {offenders}")

    def test_doctor_reports_active_http_transport(self) -> None:
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run(
            [sys.executable, str(CLI), "--json", "doctor"],
            cwd=SKILL_ROOT, env=env, text=True, capture_output=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)["data"]
        self.assertEqual(data.get("http_transport"), "curl_cffi")


if __name__ == "__main__":
    unittest.main()
