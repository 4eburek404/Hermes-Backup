#!/usr/bin/env python3
"""Executable specification for passenger names in calendar SUMMARY.

The specification exercises the public ``--json build --input`` CLI and reads
SUMMARY from the VEVENT in the generated .ics artifact.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from icalendar import Calendar

from itinerary_input_spec import minimal_itinerary, run_cli


class PassengerDisplaySpecification(unittest.TestCase):
    def test_latin_passenger_names_render_as_natural_russian_summary(self) -> None:
        cases = {
            "ORLOV SERGEI EVGENEVICH": "Орлов Сергей Евгеньевич",
            "PETROV ALEXANDER": "Петров Александр",
            "IVANOVA OLGA": "Иванова Ольга",
        }

        for passenger, expected_name in cases.items():
            with self.subTest(passenger=passenger), tempfile.TemporaryDirectory(
                prefix="flight-passenger-display-spec."
            ) as tmp:
                output = Path(tmp) / "trip.ics"
                itinerary = minimal_itinerary()
                itinerary["passenger"] = passenger

                result, _source = run_cli(itinerary, output)

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(output.is_file())
                events = Calendar.from_ical(output.read_bytes()).walk("VEVENT")
                self.assertEqual(len(events), 1)
                self.assertEqual(
                    str(events[0]["SUMMARY"]),
                    f"{expected_name} 01.06 Москва - Екатеринбург 09:15 13:45",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
