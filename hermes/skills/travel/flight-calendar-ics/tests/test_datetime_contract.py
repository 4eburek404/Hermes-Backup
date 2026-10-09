"""Contract and renderer tests for canonical datetime handling."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _valid_itinerary() -> dict[str, object]:
    """Return a minimal valid itinerary (SVO→SVX, 09:15→13:45 local)."""
    itinerary = {
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
    from flight_calendar import itinerary_contract

    return itinerary_contract.enrich_itinerary_timezones(
        itinerary, {"SVO": "Europe/Moscow", "SVX": "Asia/Yekaterinburg"}
    )


class ArrAfterDepartureContractTests(unittest.TestCase):
    """Contract-level: validate_itinerary_semantics rejects arrival <= departure."""

    maxDiff = None

    def test_arrival_before_departure_same_tz_rejected(self) -> None:
        from flight_calendar import itinerary_contract

        itinerary = _valid_itinerary()
        # Swap: arrival earlier than departure in the same timezone
        itinerary["flights"][0]["departure"]["local"] = "2026-06-01T13:45"
        itinerary["flights"][0]["arrival"]["local"] = "2026-06-01T09:15"
        itinerary["flights"][0]["arrival"]["tz"] = "Europe/Moscow"
        with self.assertRaisesRegex(ValueError, "arrival must be after departure"):
            itinerary_contract.validate_itinerary_semantics(itinerary)

    def test_arrival_equal_departure_cross_tz_rejected(self) -> None:
        """Arrival and departure at the same UTC instant must be rejected."""
        from flight_calendar import itinerary_contract

        itinerary = _valid_itinerary()
        # 09:15 Moscow (06:15 UTC) == 11:15 Yekaterinburg (06:15 UTC)
        itinerary["flights"][0]["departure"]["local"] = "2026-06-01T09:15"
        itinerary["flights"][0]["arrival"]["local"] = "2026-06-01T11:15"
        with self.assertRaisesRegex(ValueError, "arrival must be after departure"):
            itinerary_contract.validate_itinerary_semantics(itinerary)


class RendererDatetimeTests(unittest.TestCase):
    """Renderer-level datetime conversion for validated, enriched input."""

    maxDiff = None

    def test_build_calendar_accepts_supported_local_datetime_forms(self) -> None:
        """The renderer accepts the schema's naive local datetime forms."""
        from flight_calendar import ics_render

        cases = (
            ("2026-06-01T09:15:00", "2026-06-01T13:45:00"),
            ("2026-06-01 09:15", "2026-06-01 13:45"),
        )
        for departure, arrival in cases:
            with self.subTest(departure=departure):
                itinerary = _valid_itinerary()
                itinerary["flights"][0]["departure"]["local"] = departure  # type: ignore[index]
                itinerary["flights"][0]["arrival"]["local"] = arrival  # type: ignore[index]
                ics_text, summaries = ics_render.build_calendar(itinerary)
                self.assertEqual(len(summaries), 1)
                self.assertIn("BEGIN:VCALENDAR", ics_text)


class ParseLocalDatetimeRejectsAwareTests(unittest.TestCase):
    """The canonical helper must reject Z/offset independently of JSON Schema."""

    maxDiff = None

    def test_parse_local_datetime_rejects_z_suffix(self) -> None:
        from flight_calendar import itinerary_contract

        with self.assertRaisesRegex(ValueError, "without timezone offset"):
            itinerary_contract.parse_local_datetime(
                "2026-06-01T09:15Z",
                "Europe/Moscow",
                "flights[0].departure",
            )

    def test_parse_local_datetime_rejects_explicit_offset(self) -> None:
        from flight_calendar import itinerary_contract

        with self.assertRaisesRegex(ValueError, "without timezone offset"):
            itinerary_contract.parse_local_datetime(
                "2026-06-01T09:15+03:00",
                "Europe/Moscow",
                "flights[0].departure",
            )

if __name__ == "__main__":
    unittest.main()
