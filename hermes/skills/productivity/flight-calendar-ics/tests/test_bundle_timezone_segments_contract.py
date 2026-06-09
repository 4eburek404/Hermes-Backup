#!/usr/bin/env python3
"""Bundle, timezone, and segment helper contracts for flight-calendar-ics."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class BundleTimezoneSegmentsContractTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self._old_path = list(sys.path)
        script_dir = str(SCRIPTS.resolve())
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)

    def tearDown(self) -> None:
        sys.path[:] = self._old_path

    def test_bundle_helpers_create_private_dir_and_canonical_paths(self) -> None:
        from flight_calendar.bundle import (
            BUNDLE_ENVELOPE_NAME,
            BUNDLE_ICS_NAME,
            BUNDLE_ITINERARY_NAME,
            bundle_paths,
            create_private_output_dir,
            file_mode,
        )

        process: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory(prefix="flight-bundle-root.") as tmp:
            output_dir = Path(tmp) / "bundle"
            created = create_private_output_dir(output_dir, process)
            paths = bundle_paths(created)

            self.assertEqual(created, output_dir)
            self.assertEqual(file_mode(created), "700")
            self.assertEqual(process, [{"step": "create_output_bundle", "status": "ok"}])
            self.assertEqual(paths["json"].name, BUNDLE_ITINERARY_NAME)
            self.assertEqual(paths["ics"].name, BUNDLE_ICS_NAME)
            self.assertEqual(paths["envelope"].name, BUNDLE_ENVELOPE_NAME)

    def test_require_private_mode_reports_wrong_mode_without_mutating_file(self) -> None:
        from flight_calendar.bundle import file_mode, require_private_mode
        from flight_calendar.envelope import CliFailure

        with tempfile.TemporaryDirectory(prefix="flight-mode-test.") as tmp:
            path = Path(tmp) / "artifact.json"
            path.write_text("{}\n", encoding="utf-8")
            os.chmod(path, 0o644)

            with self.assertRaises(CliFailure) as caught:
                require_private_mode(path)

            self.assertIn("mode 644", str(caught.exception))
            self.assertEqual(file_mode(path), "644")

    def test_timezone_helpers_use_bundled_catalog_and_record_process_step(self) -> None:
        from flight_calendar.timezones import add_timezone_map_step, build_timezone_map, load_travelpayouts_airport_timezones

        overrides = {"SVX": "Asia/Yekaterinburg"}
        catalog = load_travelpayouts_airport_timezones()
        tz_map = build_timezone_map(overrides)
        process: list[dict[str, object]] = []
        add_timezone_map_step(process, catalog, overrides_count=len(overrides))

        self.assertEqual(tz_map["SVX"], "Asia/Yekaterinburg")
        self.assertIn("DME", catalog)
        self.assertEqual(process[0]["step"], "load_timezone_map")
        self.assertEqual(process[0]["status"], "ok")
        self.assertEqual(process[0]["catalog_source"], "skill-bundled-travelpayouts-airport-timezones")
        self.assertEqual(process[0]["overrides_count"], 1)
        self.assertGreater(process[0]["catalog_timezones_count"], 0)

    def test_segment_summaries_keep_only_calendar_safe_fields(self) -> None:
        from flight_calendar.segments import itinerary_flight_segments, safe_segment_summary

        raw_summary = {
            "flight_number": "SU 1234",
            "route": "SVX->SVO",
            "dtstart_utc": "20260608T010000Z",
            "dtend_utc": "20260608T030000Z",
            "booking_reference": "PRIVATE",
            "passenger": "PRIVATE",
        }
        self.assertEqual(
            safe_segment_summary(raw_summary),
            {
                "flight_number": "SU 1234",
                "route": "SVX->SVO",
                "dtstart_utc": "20260608T010000Z",
                "dtend_utc": "20260608T030000Z",
            },
        )

        itinerary = {
            "flights": [
                {
                    "flight_number": "SU 1234",
                    "departure": {"airport": "SVX", "local": "2026-06-08T06:00:00+05:00"},
                    "arrival": {"airport": "SVO", "local": "2026-06-08T08:00:00+03:00"},
                    "passenger_name": "PRIVATE",
                }
            ]
        }
        self.assertEqual(
            itinerary_flight_segments(itinerary),
            [
                {
                    "flight_number": "SU 1234",
                    "route": "SVX->SVO",
                    "departure_local": "2026-06-08T06:00:00+05:00",
                    "arrival_local": "2026-06-08T08:00:00+03:00",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
