#!/usr/bin/env python3
"""Executable specification for the canonical itinerary input route.

Run from the skill root::

    python3 specs/itinerary_input_spec.py

The specification exercises only the public ``--json build --input`` CLI.  The
itinerary JSON is an internal intermediate format; these cases pin its current
canonical shape and the observable ICS artifact.
"""

from __future__ import annotations

from typing import Any
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from icalendar import Calendar


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CLI = SCRIPTS / "flight_calendar_ics.py"


def minimal_itinerary() -> dict[str, Any]:
    return {
        "passenger": "KONSTANTIN ORLOV",
        "pnr": "ABC123",
        "ticket_number": "5552400000000",
        "booking_url": "https://carrier.example/manage",
        "flights": [
            {
                "flight_number": "SU1234",
                "departure": {
                    "airport": "SVO",
                    "city": "Москва",
                    "local": "2026-06-01T09:15",
                },
                "arrival": {
                    "airport": "SVX",
                    "city": "Екатеринбург",
                    "local": "2026-06-01T13:45",
                },
                "aircraft": "Boeing 737",
            }
        ],
    }


def run_cli(
    itinerary: dict[str, object], output: Path
) -> tuple[subprocess.CompletedProcess[str], Path]:
    source = output.with_suffix(".json")
    source.write_text(json.dumps(itinerary, ensure_ascii=False), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(SCRIPTS)}
    result = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--json",
            "build",
            "--input",
            str(source),
            "--output",
            str(output),
            "--no-alarms",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
        timeout=30,
    )
    return result, source


class ItineraryInputSpecification(unittest.TestCase):
    def test_minimal_itinerary_builds_one_utc_event_and_keeps_data(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flight-itinerary-spec.") as tmp:
            output = Path(tmp) / "trip.ics"
            result, _source = run_cli(minimal_itinerary(), output)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["ok"], True)
            self.assertEqual(payload["segments_count"], 1)
            self.assertTrue(output.is_file())

            calendar = Calendar.from_ical(output.read_bytes())
            events = calendar.walk("VEVENT")
            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual(
                event.decoded("DTSTART").strftime("%Y%m%dT%H%M%SZ"), "20260601T061500Z"
            )
            self.assertEqual(
                event.decoded("DTEND").strftime("%Y%m%dT%H%M%SZ"), "20260601T084500Z"
            )
            rendered = (
                output.read_text(encoding="utf-8")
                .replace("\r\n ", "")
                .replace("\n ", "")
            )
            for value in (
                "Boeing 737",
                "Код брони: ABC123",
                "Билет: 555 2400000000",
                "Бронирование: https://carrier.example/manage",
                "Москва → Екатеринбург",
            ):
                self.assertIn(value, rendered.replace("\r\n ", ""))

    def test_multiple_segments_build_multiple_events_with_catalog_timezones(
        self,
    ) -> None:
        itinerary = minimal_itinerary()
        itinerary["flights"] = [
            itinerary["flights"][0],
            {
                "flight_number": "SU5678",
                "departure": {
                    "airport": "SVX",
                    "city": "Екатеринбург",
                    "local": "2026-06-01T15:00",
                },
                "arrival": {
                    "airport": "SVO",
                    "city": "Москва",
                    "local": "2026-06-01T17:30",
                },
                "aircraft": "Airbus A320",
            },
        ]

        with tempfile.TemporaryDirectory(prefix="flight-itinerary-spec.") as tmp:
            output = Path(tmp) / "segments.ics"
            result, _source = run_cli(itinerary, output)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["segments_count"], 2)
            calendar = Calendar.from_ical(output.read_bytes())
            events = calendar.walk("VEVENT")
            self.assertEqual(len(events), 2)
            self.assertEqual(
                {
                    event.decoded("DTSTART").strftime("%Y%m%dT%H%M%SZ")
                    for event in events
                },
                {"20260601T061500Z", "20260601T100000Z"},
            )

    def test_unknown_airport_fails_closed_without_creating_ics(self) -> None:
        itinerary = minimal_itinerary()
        itinerary["flights"][0]["arrival"]["airport"] = "ZZZ"  # type: ignore[index]

        with tempfile.TemporaryDirectory(prefix="flight-itinerary-spec.") as tmp:
            output = Path(tmp) / "unknown.ics"
            result, _source = run_cli(itinerary, output)

            self.assertEqual(result.returncode, 2)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"]["code"], "validation_error")
            self.assertIn("missing timezone", payload["error"]["message"])
            self.assertIn("ZZZ", payload["error"]["message"])
            self.assertFalse(output.exists())

    def test_arrival_not_after_departure_fails_through_public_cli(self) -> None:
        itinerary = minimal_itinerary()
        itinerary["flights"][0]["departure"]["local"] = "2026-06-01T13:45"  # type: ignore[index]
        itinerary["flights"][0]["arrival"]["local"] = "2026-06-01T09:15"  # type: ignore[index]

        with tempfile.TemporaryDirectory(prefix="flight-itinerary-spec.") as tmp:
            output = Path(tmp) / "invalid-order.ics"
            result, _source = run_cli(itinerary, output)

            self.assertEqual(result.returncode, 2)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"]["code"], "validation_error")
            self.assertIn("arrival must be after departure", payload["error"]["message"])
            self.assertFalse(output.exists())

    def test_lexically_valid_impossible_local_datetime_fails_through_public_cli(
        self,
    ) -> None:
        itinerary = minimal_itinerary()
        itinerary["flights"][0]["departure"]["local"] = "2026-02-30T09:15"  # type: ignore[index]

        with tempfile.TemporaryDirectory(prefix="flight-itinerary-spec.") as tmp:
            output = Path(tmp) / "impossible-date.ics"
            result, _source = run_cli(itinerary, output)

            self.assertEqual(result.returncode, 2)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"]["code"], "validation_error")
            message = payload["error"]["message"]
            self.assertIn("local datetime", message)
            self.assertNotIn("canonical pattern", message)
            self.assertFalse(output.exists())

    def test_removed_fields_are_rejected_as_unknown(self) -> None:
        cases: dict[str, dict[str, Any]] = {}

        schema_version = minimal_itinerary()
        schema_version["schema_version"] = "flight-calendar-ics-itinerary.v1"
        cases["schema_version"] = schema_version

        status = minimal_itinerary()
        status["flights"][0]["status"] = "confirmed"  # type: ignore[index]
        cases["status"] = status

        tz = minimal_itinerary()
        tz["flights"][0]["departure"]["tz"] = "Europe/Moscow"  # type: ignore[index]
        cases["tz"] = tz

        passengers = minimal_itinerary()
        passengers["passengers"] = ["KONSTANTIN ORLOV"]
        cases["passengers"] = passengers

        for name, candidate in cases.items():
            with (
                self.subTest(field=name),
                tempfile.TemporaryDirectory(prefix="flight-itinerary-spec.") as tmp,
            ):
                output = Path(tmp) / "rejected.ics"
                result, _source = run_cli(copy.deepcopy(candidate), output)
                self.assertNotEqual(result.returncode, 0)
                payload = json.loads(result.stdout)
                self.assertFalse(payload["ok"])
                self.assertIn("unknown field", payload["error"]["message"])
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
