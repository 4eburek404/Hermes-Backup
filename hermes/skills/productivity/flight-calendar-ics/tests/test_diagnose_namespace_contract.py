#!/usr/bin/env python3
"""diagnose namespace CLI contracts for flight-calendar-ics."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "flight_calendar_ics.py"
SCHEMA = ROOT / "schemas" / "cli-envelope.v1.schema.json"


class DiagnoseNamespaceContractTests(unittest.TestCase):
    maxDiff = None

    def _run_json(self, *args: str) -> dict:
        result = subprocess.run(
            [sys.executable, str(CLI), "--json", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        payload = json.loads(result.stdout)
        from jsonschema import Draft202012Validator

        Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(payload)
        return payload

    def test_diagnose_doctor_returns_schema_valid_read_only_diagnostic_envelope(self) -> None:
        payload = self._run_json("diagnose", "doctor")

        self.assertEqual(payload["schema_version"], "flight-calendar-ics-cli.v1")
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["command"], "diagnose")
        self.assertEqual(payload["data"]["surface"], "diagnostic")
        self.assertEqual(payload["data"]["subcommand"], "doctor")
        self.assertEqual(payload["data"]["write_performed"], False)
        self.assertIn("diagnose doctor", payload["data"]["command_registry"]["diagnostic"])
        self.assertIn("maint contracts", payload["data"]["command_registry"]["maintenance"])
        self.assertEqual(
            [step["step"] for step in payload["process"]],
            ["parse_args", "load_input", "no_write", "emit_json"],
        )
        self.assertEqual(payload["process"][1]["status"], "skipped")

    def test_diagnose_validate_writes_nothing_and_reports_safe_segments(self) -> None:
        payload = self._run_json("diagnose", "validate", "--input", "templates/aeroflot-itinerary.example.json")

        self.assertEqual(payload["command"], "diagnose")
        self.assertEqual(payload["data"]["surface"], "diagnostic")
        self.assertEqual(payload["data"]["subcommand"], "validate")
        self.assertGreaterEqual(payload["data"]["segments_count"], 1)
        self.assertEqual(payload["data"]["write_performed"], False)
        self.assertEqual([step["step"] for step in payload["process"]][-2:], ["no_write", "emit_json"])

    def test_diagnose_route_detect_writes_nothing_and_redacts_source_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="flight-diagnose-route.") as tmp:
            url_file = Path(tmp) / "source-url.txt"
            url_file.write_text(
                "https://www.aeroflot.ru/sb/pnr/app/ru-ru?pnrLocator=ABC123&pnrKey=SECRETKEY123\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(CLI), "--json", "diagnose", "route-detect", "--url-file", str(url_file)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        serialized = result.stdout
        self.assertNotIn("ABC123", serialized)
        self.assertNotIn("SECRETKEY123", serialized)
        payload = json.loads(serialized)
        from jsonschema import Draft202012Validator

        Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(payload)
        self.assertEqual(payload["command"], "diagnose")
        self.assertEqual(payload["data"]["surface"], "diagnostic")
        self.assertEqual(payload["data"]["subcommand"], "route-detect")
        self.assertEqual(payload["data"]["write_performed"], False)
        self.assertEqual(payload["data"]["route_detection"]["route"], "aeroflot")
        self.assertIn("host:aeroflot.ru", payload["data"]["route_detection"]["evidence"])

    def test_diagnose_timezone_inspect_reports_catalog_metadata_without_mutation(self) -> None:
        payload = self._run_json("diagnose", "timezone", "inspect")

        self.assertEqual(payload["command"], "diagnose")
        self.assertEqual(payload["data"]["surface"], "diagnostic")
        self.assertEqual(payload["data"]["subcommand"], "timezone inspect")
        self.assertEqual(payload["data"]["write_performed"], False)
        self.assertGreater(payload["data"]["airports_count"], 0)
        self.assertGreater(payload["data"]["timezones_count"], 0)
        self.assertTrue(payload["data"]["sample_airports"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
