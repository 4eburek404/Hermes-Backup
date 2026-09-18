"""Compact public contract for flight-calendar-ics."""

from __future__ import annotations

import copy
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CLI = SCRIPTS / "flight_calendar_ics.py"
TEMPLATE = ROOT / "templates" / "itinerary.example.json"
sys.path.insert(0, str(ROOT / "specs"))

from cli_envelope import assert_valid_cli_envelope


def minimal_itinerary() -> dict[str, object]:
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
        enriched = itinerary_contract.enrich_itinerary_timezones(
            itinerary, {"SVO": "Europe/Moscow", "SVX": "Asia/Yekaterinburg"}
        )
        itinerary_contract.validate_itinerary_semantics(enriched)

        unknown_fields = []
        root_payload = copy.deepcopy(itinerary)
        root_payload["unexpected_root"] = "legacy"
        unknown_fields.append(("root", root_payload))
        flight_payload = copy.deepcopy(itinerary)
        flight_payload["flights"][0]["unexpected_flight"] = "legacy"  # type: ignore[index]
        unknown_fields.append(("flight", flight_payload))
        endpoint_payload = copy.deepcopy(itinerary)
        endpoint_payload["flights"][0]["departure"]["unexpected_endpoint"] = "legacy"  # type: ignore[index]
        unknown_fields.append(("endpoint", endpoint_payload))

        for location, payload in unknown_fields:
            with (
                self.subTest(location=location),
                self.assertRaisesRegex(ValueError, "unknown field"),
            ):
                itinerary_contract.validate_itinerary_schema(payload)

    def test_template_is_neutral_minimal_and_valid(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from flight_calendar import itinerary_contract

        self.assertTrue(TEMPLATE.is_file())
        data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        itinerary_contract.validate_itinerary_schema(data)
        serialized = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("Aeroflot", serialized)
        self.assertNotIn("Аэрофлот", serialized)


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
            source.write_text(
                json.dumps(minimal_itinerary(), ensure_ascii=False), encoding="utf-8"
            )
            before = {
                path.relative_to(tmp_path)
                for path in tmp_path.rglob("*")
                if path.is_file()
            }

            result = self.run_cli(
                "--json",
                "build",
                "--input",
                str(source),
                "--output",
                str(output),
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            assert_valid_cli_envelope(self, payload)
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
            after = {
                path.relative_to(tmp_path)
                for path in tmp_path.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after - before, {output.relative_to(tmp_path)})

    def test_public_cli_rejects_legacy_surface_and_private_url_arg(self) -> None:
        for args in [
            ("--json", "build"),
            ("--json", "build", "--url", "https://private.example/secret"),
        ]:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertNotEqual(result.returncode, 0)
                payload = json.loads(result.stdout)
                assert_valid_cli_envelope(self, payload)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["error"]["code"], "usage_error")
                self.assertNotIn("private.example", result.stdout)
                self.assertNotIn("secret", result.stdout)

    def test_input_with_timezone_override_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flight-compact-tz.") as tmp:
            source = Path(tmp) / "itinerary.json"
            source.write_text(
                json.dumps(minimal_itinerary(), ensure_ascii=False), encoding="utf-8"
            )
            result = self.run_cli(
                "--json", "build", "--input", str(source), "--tz", "KUF=Europe/Samara"
            )
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            assert_valid_cli_envelope(self, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"]["code"], "usage_error")
            self.assertIn(
                "--tz is only supported with --url-file", payload["error"]["message"]
            )

    def test_unexpected_exception_returns_internal_error_and_exit_one(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from flight_calendar import parser

        stdout = io.StringIO()
        with (
            mock.patch.object(
                parser, "command_build", side_effect=RuntimeError("synthetic failure")
            ),
            contextlib.redirect_stdout(stdout),
        ):
            code = parser.main(["--json", "build", "--input", "itinerary.json"])

        self.assertEqual(code, 1)
        payload = json.loads(stdout.getvalue())
        assert_valid_cli_envelope(self, payload)
        self.assertEqual(
            payload,
            {
                "ok": False,
                "error": {
                    "code": "internal_error",
                    "message": "RuntimeError: synthetic failure",
                },
            },
        )

if __name__ == "__main__":
    unittest.main()
