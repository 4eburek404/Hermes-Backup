"""Route detection contract for compact URL sources."""
from __future__ import annotations

import argparse
import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


class ExplodingUrlFile:
    def read_text(self, encoding: str = "utf-8") -> str:  # pragma: no cover - must not be called
        raise AssertionError("url_file was read despite url_override")


class RouteDetectionContractTests(unittest.TestCase):
    def test_url_override_detects_utair_without_reading_url_file(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        args = argparse.Namespace(
            input=None,
            url=None,
            url_file=ExplodingUrlFile(),
            pnr_locator=None,
            pnr_key=None,
            pnr=None,
            rloc=None,
            last_name=None,
            first_name=None,
            access_code=None,
        )

        route = infer_build_route(
            args,
            url_override="https://www.utair.ru/order-manage?rloc=ABC123&last_name=IVANOV",
        )

        self.assertEqual(route["route"], "utair")
        self.assertEqual(route["confidence"], 1.0)
        self.assertIn("host:utair.ru", route["evidence"])
        self.assertLessEqual(set(route), {"mode", "route", "confidence", "evidence"})

    def test_click_mail_utair_is_not_a_route_detection_host(self) -> None:
        import flight_calendar.route_detection as route_detection

        source = inspect.getsource(route_detection)
        self.assertNotIn("click.mail.utair.io", source)


if __name__ == "__main__":
    unittest.main()
