#!/usr/bin/env python3
"""Route detection contract tests for flight-calendar-ics build auto."""
from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def build_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "input": None,
        "url": None,
        "url_file": None,
        "pnr_locator": None,
        "pnr_key": None,
        "last_name": None,
        "first_name": None,
        "pnr": None,
        "access_code": None,
        "rloc": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class RouteDetectionContractTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self._old_path = list(sys.path)
        script_dir = str(SCRIPTS.resolve())
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)

    def tearDown(self) -> None:
        sys.path[:] = self._old_path

    def test_canonical_itinerary_input_routes_to_make(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        result = infer_build_route(build_args(input=Path("/private/itinerary.json")))

        self.assertEqual(result["mode"], "auto")
        self.assertEqual(result["route"], "make")
        self.assertEqual(result["confidence"], 1.0)
        self.assertEqual(result["evidence"], ["input_kind:canonical_itinerary_json"])

    def test_known_host_route_wins_over_generic_query_field_names(self) -> None:
        from flight_calendar.route_detection import infer_build_route

        result = infer_build_route(
            build_args(url="https://www.utair.ru/manage?pnr=ABC123&lastName=ORLOV")
        )

        self.assertEqual(result["route"], "utair")
        self.assertEqual(result["confidence"], 1.0)
        self.assertIn("host:utair.ru", result["evidence"])
        self.assertIn("query_field:pnr", result["evidence"])
        self.assertIn("query_field:lastName", result["evidence"])

    def test_first_url_from_args_reads_private_file_first_line_and_rejects_double_source(self) -> None:
        from flight_calendar.envelope import CliFailure
        from flight_calendar.route_detection import first_url_from_args

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write("https://example.invalid/first\nhttps://example.invalid/second\n")
            url_file = Path(handle.name)
        try:
            self.assertEqual(first_url_from_args(build_args(url_file=url_file)), "https://example.invalid/first")
            with self.assertRaises(CliFailure) as caught:
                first_url_from_args(build_args(url="https://example.invalid/direct", url_file=url_file))
        finally:
            url_file.unlink(missing_ok=True)

        self.assertEqual(caught.exception.code, "usage_error")
        self.assertIn("either --url or --url-file", str(caught.exception))

    def test_ambiguous_generic_credentials_require_explicit_route(self) -> None:
        from flight_calendar.envelope import CliFailure
        from flight_calendar.route_detection import infer_build_route

        with self.assertRaises(CliFailure) as caught:
            infer_build_route(build_args(pnr="ABC123", last_name="ORLOV"))

        self.assertEqual(caught.exception.code, "route_ambiguous")
        self.assertEqual(caught.exception.details["safe_candidates"], ["ural", "utair"])
        self.assertEqual(caught.exception.details["required_disambiguation"], ["explicit route or carrier URL"])

    def test_redwings_order_page_is_insufficient_without_find_fragment(self) -> None:
        from flight_calendar.envelope import CliFailure
        from flight_calendar.route_detection import infer_build_route

        with self.assertRaises(CliFailure) as caught:
            infer_build_route(build_args(url="https://booking.flyredwings.com/#/booking/ABC123/order"))

        self.assertEqual(caught.exception.code, "route_input_insufficient")
        self.assertEqual(caught.exception.details["route"], "redwings")
        self.assertIn("direct find link", str(caught.exception))
        self.assertNotIn("ABC123", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
