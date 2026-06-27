from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flights_cli.reporting.projections.itinerary_display import build_itinerary_display
from flights_cli.store import Store
from tests.test_agent_report_contract import valid_report


class FlightDisplayTests(unittest.TestCase):
    def test_display_includes_layover_and_total_elapsed(self) -> None:
        report = valid_report()
        report["recommended_options"][0]["segments"] = [
            {
                "direction": "outbound",
                "flight_number": "SU1415",
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "SVX",
                "destination": "SVO",
                "departure_at": "2026-07-15T12:00:00+05:00",
                "arrival_at": "2026-07-15T12:30:00+03:00",
                "aircraft_code": "A320",
            },
            {
                "direction": "outbound",
                "flight_number": "SU2134",
                "carrier": "SU",
                "marketing_carrier": "SU",
                "operating_carrier": "SU",
                "origin": "SVO",
                "destination": "IST",
                "departure_at": "2026-07-15T15:20:00+03:00",
                "arrival_at": "2026-07-15T19:30:00+03:00",
                "aircraft_code": "B738",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = Path(tmp_dir)
            (cache / "airports_ru.json").write_text(
                json.dumps(
                    [
                        {"code": "SVX", "city_code": "SVX", "name": "Кольцово"},
                        {"code": "SVO", "city_code": "MOW", "name": "Шереметьево"},
                        {"code": "IST", "city_code": "IST", "name": "Новый (Стамбул)"},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (cache / "cities_ru.json").write_text(
                json.dumps(
                    [
                        {"code": "SVX", "name": "Екатеринбург"},
                        {"code": "IST", "name": "Стамбул"},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            display = build_itinerary_display(report, Store(cache))

        text = display["text"]
        option = display["options"][0]
        self.assertEqual(option["total_elapsed"], "9:30")
        self.assertEqual(option["connection_count"], 1)
        self.assertEqual(len(option["lines"]), 3)
        self.assertIn("SU1415", option["lines"][0])
        self.assertIn("SU2134", option["lines"][2])
        self.assertIn("2:50", option["lines"][1])
        self.assertNotIn("Новый (Стамбул)", text)

    def test_round_trip_does_not_turn_trip_gap_into_layover(self) -> None:
        report = valid_report()
        report["recommended_options"][0]["segments"] = [
            {
                "direction": "outbound",
                "flight_number": "SU1415",
                "origin": "SVX",
                "destination": "SVO",
                "departure_at": "2026-07-15T12:00:00+05:00",
                "arrival_at": "2026-07-15T12:30:00+03:00",
                "aircraft_code": "A320",
            },
            {
                "direction": "return",
                "flight_number": "SU1416",
                "origin": "SVO",
                "destination": "SVX",
                "departure_at": "2026-07-22T14:00:00+03:00",
                "arrival_at": "2026-07-22T18:25:00+05:00",
                "aircraft_code": "A320",
            },
        ]

        display = build_itinerary_display(report)
        option = display["options"][0]

        self.assertEqual(option["total_elapsed"], "туда 2:30; обратно 2:25")
        self.assertEqual(option["connection_count"], 0)
        self.assertEqual(len(option["lines"]), 4)
        self.assertIn("SU1415", option["lines"][1])
        self.assertIn("SU1416", option["lines"][3])
        self.assertNotIn("пересадка SVO", display["text"])


if __name__ == "__main__":
    unittest.main()
