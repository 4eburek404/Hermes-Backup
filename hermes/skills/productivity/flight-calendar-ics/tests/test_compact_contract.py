"""Compact public contract for flight-calendar-ics."""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CLI = SCRIPTS / "flight_calendar_ics.py"
TEMPLATE = ROOT / "templates" / "itinerary.example.json"

ROOT_FIELDS = {"schema_version", "pnr", "passengers", "ticket_number", "booking_url", "flights"}
FLIGHT_FIELDS = {"flight_number", "departure", "arrival", "aircraft", "status"}
ENDPOINT_FIELDS = {"airport", "city", "local", "tz"}
REMOVED_ROOT_FIELDS = {
    "booking_reference",
    "calendar_name",
    "alarms_minutes",
    "links",
    "source",
    "notes",
    "extensions",
}
REMOVED_FLIGHT_FIELDS = {
    "pnr",
    "ticket_number",
    "passengers",
    "carrier",
    "carrier_code",
    "operating_carrier",
    "seat",
    "baggage",
    "cabin",
    "fare",
    "notes",
    "url",
    "links",
    "extensions",
}
REMOVED_ENDPOINT_FIELDS = {"terminal", "gate"}


def minimal_itinerary() -> dict[str, object]:
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


class CompactContractTests(unittest.TestCase):
    maxDiff = None

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PYTHONPATH": str(SCRIPTS)}
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env=env,
            timeout=30,
        )

    def test_schema_allows_only_minimal_fields(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from flight_calendar import itinerary_contract

        itinerary = minimal_itinerary()
        itinerary_contract.validate_itinerary_schema(itinerary)
        itinerary_contract.validate_itinerary_semantics(itinerary)

        for field in REMOVED_ROOT_FIELDS:
            payload = copy.deepcopy(itinerary)
            payload[field] = "legacy"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "unknown field"):
                itinerary_contract.validate_itinerary_schema(payload)

        for field in REMOVED_FLIGHT_FIELDS:
            payload = copy.deepcopy(itinerary)
            payload["flights"][0][field] = "legacy"  # type: ignore[index]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "unknown field"):
                itinerary_contract.validate_itinerary_schema(payload)

        for field in REMOVED_ENDPOINT_FIELDS:
            payload = copy.deepcopy(itinerary)
            payload["flights"][0]["departure"][field] = "legacy"  # type: ignore[index]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "unknown field"):
                itinerary_contract.validate_itinerary_schema(payload)

    def test_template_is_neutral_minimal_and_valid(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from flight_calendar import itinerary_contract

        self.assertTrue(TEMPLATE.exists())
        self.assertFalse((ROOT / "templates" / "aeroflot-itinerary.example.json").exists())
        data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        itinerary_contract.validate_itinerary_schema(data)
        self.assertLessEqual(set(data), ROOT_FIELDS)
        self.assertLessEqual(set(data["flights"][0]), FLIGHT_FIELDS)
        self.assertLessEqual(set(data["flights"][0]["departure"]), ENDPOINT_FIELDS)
        self.assertLessEqual(set(data["flights"][0]["arrival"]), ENDPOINT_FIELDS)
        serialized = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("Aeroflot", serialized)
        self.assertNotIn("Аэрофлот", serialized)
        globally_removed = (REMOVED_ROOT_FIELDS | REMOVED_FLIGHT_FIELDS | REMOVED_ENDPOINT_FIELDS) - {
            "pnr",
            "passengers",
            "ticket_number",
        }
        for field in sorted(globally_removed):
            self.assertNotIn(f'"{field}"', serialized)

    def test_renderer_keeps_compact_russian_calendar_entry(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from flight_calendar import ics_render

        ics_text, summaries = ics_render.build_calendar(minimal_itinerary(), no_alarms=True)
        unfolded = ics_text.replace("\r\n ", "").replace("\n ", "")
        self.assertEqual(len(summaries), 1)
        self.assertIn("SUMMARY:Константин Орлов 01.06 Москва - Екатеринбург 09:15 13:45", unfolded)
        self.assertIn("DESCRIPTION:Код брони: ABC123\\nБилет: 555 2400000000", unfolded)
        self.assertIn("01.06 Москва -> Екатеринбург 09:15 13:45", unfolded)
        self.assertIn("Самолет: Boeing 737", unfolded)
        self.assertIn("Бронирование: https://carrier.example/manage", unfolded)
        self.assertIn("LOCATION:Москва → Екатеринбург", unfolded)
        self.assertIn("DTSTART:20260601T061500Z", unfolded)
        self.assertIn("DTEND:20260601T084500Z", unfolded)
        self.assertNotIn("PNR:", unfolded)
        self.assertNotIn("Seat", unfolded)
        self.assertNotIn("Baggage", unfolded)
        self.assertNotIn("Терминал", unfolded)

    def test_passenger_display_normalizes_latin_names_to_cyrillic(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from flight_calendar.passenger_display import display_passenger_name

        cases = {
            "KONSTANTIN ORLOV": "Константин Орлов",
            "ORLOV KONSTANTIN": "Орлов Константин",
            "Ivanov Ivan": "Иванов Иван",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(display_passenger_name(raw), expected)

    def test_cli_build_input_writes_only_ics_and_short_stdout(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flight-compact-cli.") as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "itinerary.json"
            output = tmp_path / "trip.ics"
            source.write_text(json.dumps(minimal_itinerary(), ensure_ascii=False), encoding="utf-8")

            result = self.run_cli("--json", "build", "--input", str(source), "--output", str(output), "--no-alarms")

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(
                payload,
                {
                    "ok": True,
                    "media": f"MEDIA:{output}",
                    "segments_count": 1,
                    "no_further_action_needed": True,
                },
            )
            self.assertTrue(output.exists())
            self.assertFalse((tmp_path / "flights.ics").exists())
            self.assertFalse((tmp_path / "itinerary.json.json").exists())
            self.assertFalse((tmp_path / "envelope.json").exists())
            self.assertNotIn("process", result.stdout)
            self.assertNotIn("agent_handoff", result.stdout)

    def test_public_cli_rejects_legacy_surface_and_private_url_arg(self) -> None:
        for args in [
            ("--json", "doctor"),
            ("--json", "diagnose", "doctor"),
            ("--json", "maint", "contracts"),
            ("--json", "build", "auto"),
            ("--json", "build", "make"),
            ("--json", "build", "aeroflot"),
            ("--json", "build", "--output-dir", "/tmp/out"),
            ("--json", "--full-envelope", "build"),
            ("--json", "build", "--url", "https://private.example/secret"),
        ]:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertNotEqual(result.returncode, 0)
                payload = json.loads(result.stdout)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["error"]["code"], "usage_error")
                self.assertNotIn("private.example", result.stdout)
                self.assertNotIn("secret", result.stdout)

    def test_input_with_timezone_override_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flight-compact-tz.") as tmp:
            source = Path(tmp) / "itinerary.json"
            source.write_text(json.dumps(minimal_itinerary(), ensure_ascii=False), encoding="utf-8")
            result = self.run_cli("--json", "build", "--input", str(source), "--tz", "KUF=Europe/Samara")
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload, {"ok": False, "error": {"code": "usage_error", "message": "--tz is only supported with --url-file"}})

    def test_only_compact_carrier_reference_remains(self) -> None:
        references = ROOT / "references"
        carriers = references / "carriers.md"
        self.assertTrue(carriers.exists())
        self.assertEqual(
            sorted(path.relative_to(references).as_posix() for path in references.rglob("*") if path.is_file()),
            ["carriers.md"],
        )
        text = carriers.read_text(encoding="utf-8")
        self.assertIn("--json build", text)
        self.assertNotIn("--json build auto", text)
        self.assertNotIn("core/", text)

    def test_legacy_modules_are_removed(self) -> None:
        for name in ["bundle.py", "maintenance.py", "privacy.py", "contracts.py", "build_command.py", "carrier_adapters.py", "segments.py"]:
            self.assertFalse((SCRIPTS / "flight_calendar" / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
