"""Carrier HTTP must use the required curl_cffi transport without urllib fallback."""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TransportContractTests(unittest.TestCase):
    def test_curl_cffi_is_required_transport(self) -> None:
        from flight_calendar import carrier_http

        self.assertEqual(carrier_http.active_transport(), "curl_cffi")
        source = inspect.getsource(carrier_http)
        self.assertNotIn("urlopen", source)
        self.assertNotIn("urllib.request", source)
        self.assertNotIn("except ImportError", source)


if __name__ == "__main__":
    unittest.main()
