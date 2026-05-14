from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flights_cli.reporting.flight_display import build_flight_display
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
            display = build_flight_display(report, Store(cache))

        text = display["text"]
        self.assertIn("всего 9:30", text)
        self.assertIn("пересадка Шереметьево 2:50", text)
        self.assertIn("SU1415 15JUL Екатеринбург - Шереметьево 12:00 - 12:30 борт A320 в полете 2:30", text)
        self.assertIn("SU2134 15JUL Шереметьево - Стамбул 15:20 - 19:30 борт B738 в полете 4:10", text)

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

        display = build_flight_display(report)

        self.assertIn("всего туда 2:30; обратно 2:25", display["text"])
        self.assertIn("туда: всего 2:30, пересадок 0", display["text"])
        self.assertIn("обратно: всего 2:25, пересадок 0", display["text"])
        self.assertNotIn("пересадка SVO", display["text"])


if __name__ == "__main__":
    unittest.main()
