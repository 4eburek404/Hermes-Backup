"""Regression tests for deduplicated datetime parsing and arrival/departure validation.

These tests verify that:
1. arrival <= departure after timezone conversion is rejected by contract validation
2. direct ics_render.build_calendar() call also rejects such an itinerary
3. local datetime with Z/offset is not accepted by the public JSON Schema contract
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _valid_itinerary() -> dict[str, object]:
    """Return a minimal valid itinerary (SVO→SVX, 09:15→13:45 local)."""
    return {
        "schema_version": "flight-calendar-ics-itinerary.v1",
        "pnr": "ABC123",
        "passengers": ["KONSTANTIN ORLOV"],
        "ticket_number": "5552400000000",
        "booking_url": "https://carrier.example/manage",
        "flights": [
            {
                "flight_number": "SU1234",
                "departure": {
                    "airport": "SVO",
                    "city": "Москва",
                    "local": "2026-06-01T09:15",
                    "tz": "Europe/Moscow",
                },
                "arrival": {
                    "airport": "SVX",
                    "city": "Екатеринбург",
                    "local": "2026-06-01T13:45",
                    "tz": "Asia/Yekaterinburg",
                },
                "aircraft": "Boeing 737",
                "status": "confirmed",
            }
        ],
    }


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

    def test_arrival_before_departure_cross_tz_rejected(self) -> None:
        """Arrival before departure after timezone conversion must be rejected."""
        from flight_calendar import itinerary_contract

        itinerary = _valid_itinerary()
        # 13:45 Moscow (10:45 UTC) -> 09:15 Yekaterinburg (04:15 UTC)
        itinerary["flights"][0]["departure"]["local"] = "2026-06-01T13:45"
        itinerary["flights"][0]["arrival"]["local"] = "2026-06-01T09:15"
        with self.assertRaisesRegex(ValueError, "arrival must be after departure"):
            itinerary_contract.validate_itinerary_semantics(itinerary)

    def test_valid_itinerary_passes(self) -> None:
        from flight_calendar import itinerary_contract

        itinerary = _valid_itinerary()
        # Should not raise
        itinerary_contract.validate_itinerary_semantics(itinerary)


class BuildCalendarRejectsTests(unittest.TestCase):
    """Renderer-level: ics_render.build_calendar() also rejects bad arrival/departure."""

    maxDiff = None

    def test_build_calendar_rejects_arrival_before_departure(self) -> None:
        """Direct build_calendar() call must reject arrival <= departure."""
        from flight_calendar import ics_render

        itinerary = _valid_itinerary()
        itinerary["flights"][0]["departure"]["local"] = "2026-06-01T13:45"
        itinerary["flights"][0]["arrival"]["local"] = "2026-06-01T09:15"
        itinerary["flights"][0]["arrival"]["tz"] = "Europe/Moscow"
        with self.assertRaises(SystemExit):
            ics_render.build_calendar(itinerary, no_alarms=True)

    def test_build_calendar_rejects_arrival_equal_departure_cross_tz(self) -> None:
        """Direct build_calendar() call must reject arrival == departure in UTC."""
        from flight_calendar import ics_render

        itinerary = _valid_itinerary()
        itinerary["flights"][0]["departure"]["local"] = "2026-06-01T09:15"
        itinerary["flights"][0]["arrival"]["local"] = "2026-06-01T11:15"
        with self.assertRaises(SystemExit):
            ics_render.build_calendar(itinerary, no_alarms=True)

    def test_build_calendar_accepts_valid_itinerary(self) -> None:
        """Direct build_calendar() call must succeed for valid itinerary."""
        from flight_calendar import ics_render

        itinerary = _valid_itinerary()
        ics_text, summaries = ics_render.build_calendar(itinerary, no_alarms=True)
        self.assertEqual(len(summaries), 1)
        self.assertIn("BEGIN:VCALENDAR", ics_text)


class ZOffsetSchemaRejectionTests(unittest.TestCase):
    """JSON Schema must reject local datetimes with Z or offset — no public contract expansion."""

    maxDiff = None

    def test_schema_rejects_z_suffix(self) -> None:
        from flight_calendar import itinerary_contract

        itinerary = _valid_itinerary()
        itinerary["flights"][0]["departure"]["local"] = "2026-06-01T09:15Z"
        with self.assertRaisesRegex(ValueError, "schema validation failed"):
            itinerary_contract.validate_itinerary_schema(itinerary)

    def test_schema_rejects_explicit_offset(self) -> None:
        from flight_calendar import itinerary_contract

        itinerary = _valid_itinerary()
        itinerary["flights"][0]["arrival"]["local"] = "2026-06-01T13:45+05:00"
        with self.assertRaisesRegex(ValueError, "schema validation failed"):
            itinerary_contract.validate_itinerary_schema(itinerary)

    def test_schema_accepts_naive_local_with_seconds(self) -> None:
        from flight_calendar import itinerary_contract

        itinerary = _valid_itinerary()
        itinerary["flights"][0]["departure"]["local"] = "2026-06-01T09:15:00"
        itinerary_contract.validate_itinerary_schema(itinerary)

    def test_schema_accepts_space_separator(self) -> None:
        from flight_calendar import itinerary_contract

        itinerary = _valid_itinerary()
        itinerary["flights"][0]["departure"]["local"] = "2026-06-01 09:15"
        itinerary_contract.validate_itinerary_schema(itinerary)


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

    def test_build_calendar_rejects_z_suffix_without_schema(self) -> None:
        """Direct build_calendar() call must reject Z even without schema validation."""
        from flight_calendar import ics_render

        itinerary = _valid_itinerary()
        itinerary["flights"][0]["departure"]["local"] = "2026-06-01T09:15Z"
        with self.assertRaises(SystemExit):
            ics_render.build_calendar(itinerary, no_alarms=True)

    def test_build_calendar_rejects_offset_without_schema(self) -> None:
        """Direct build_calendar() call must reject +offset even without schema validation."""
        from flight_calendar import ics_render

        itinerary = _valid_itinerary()
        itinerary["flights"][0]["arrival"]["local"] = "2026-06-01T13:45+05:00"
        with self.assertRaises(SystemExit):
            ics_render.build_calendar(itinerary, no_alarms=True)


if __name__ == "__main__":
    unittest.main()