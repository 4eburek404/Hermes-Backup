#!/usr/bin/env python3
"""Contract tests for the flight-calendar-ics single CLI entrypoint.

These tests intentionally exercise the CLI as an external agent-facing process:
- one Python executable entrypoint;
- machine-readable JSON envelope;
- deterministic process trace;
- private booking data stays out of stdout/stderr.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "flight_calendar_ics.py"
MAKE = ROOT / "scripts" / "make_flight_ics.py"
AEROFLOT = ROOT / "scripts" / "aeroflot_pnr_to_itinerary.py"
TEMPLATE = ROOT / "templates" / "aeroflot-itinerary.example.json"
SCHEMA = ROOT / "schemas" / "cli-envelope.v1.schema.json"


class FlightCalendarIcsCliContractTests(unittest.TestCase):
    maxDiff = None

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
        )

    def parse_stdout_json(self, result: subprocess.CompletedProcess[str]) -> dict:
        try:
            obj = json.loads(result.stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - assertion helper
            self.fail(
                f"stdout is not valid JSON: {exc}\n"
                f"exit={result.returncode}\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
            )
        self.assertIsInstance(obj, dict)
        return obj

    def assert_envelope(self, obj: dict, *, ok: bool, command: str) -> None:
        self.assertEqual(obj.get("schema_version"), "flight-calendar-ics-cli.v1")
        self.assertEqual(obj.get("ok"), ok)
        self.assertEqual(obj.get("command"), command)
        self.assertIsInstance(obj.get("process"), list)
        self.assertTrue(obj["process"], "process trace must not be empty")
        for step in obj["process"]:
            self.assertIsInstance(step.get("step"), str)
            self.assertIn(step.get("status"), {"ok", "error", "skipped"})
        if ok:
            self.assertNotIn("error", obj)
            self.assertIsInstance(obj.get("data"), dict)
        else:
            self.assertIsInstance(obj.get("error"), dict)
            self.assertIsInstance(obj["error"].get("code"), str)
            self.assertIsInstance(obj["error"].get("message"), str)

    def test_doctor_json_describes_single_entrypoint_and_commands(self) -> None:
        result = self.run_cli("--json", "doctor")

        self.assertEqual(result.returncode, 0, result.stderr)
        obj = self.parse_stdout_json(result)
        self.assert_envelope(obj, ok=True, command="doctor")
        self.assertEqual(obj["data"]["entrypoint"], str(CLI))
        self.assertEqual(obj["data"]["entrypoint_kind"], "single-python-executable")
        self.assertGreaterEqual(set(obj["data"]["commands"]), {"doctor", "validate", "make", "aeroflot"})
        self.assertIn("load_input", [step["step"] for step in obj["process"]])
        self.assertIn("emit_json", [step["step"] for step in obj["process"]])

    def test_cli_envelope_schema_documents_machine_contract(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

        self.assertEqual(schema["$id"], "https://hermes-agent.local/schemas/flight-calendar-ics-cli.v1.json")
        self.assertEqual(schema["title"], "flight-calendar-ics CLI envelope v1")
        self.assertGreaterEqual(set(schema["required"]), {"schema_version", "ok", "command", "process"})
        properties = schema["properties"]
        self.assertEqual(properties["schema_version"]["const"], "flight-calendar-ics-cli.v1")
        self.assertIn("doctor", properties["command"]["enum"])
        self.assertIn("make", properties["command"]["enum"])
        self.assertIn("validate", properties["command"]["enum"])
        self.assertIn("aeroflot", properties["command"]["enum"])
        self.assertIn("data", properties)
        self.assertIn("error", properties)

    def test_make_json_writes_private_ics_and_redacted_process_summary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "trip.ics"
            result = self.run_cli("--json", "make", "--input", str(TEMPLATE), "--output", str(output))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.exists())
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            obj = self.parse_stdout_json(result)
            self.assert_envelope(obj, ok=True, command="make")
            self.assertEqual(obj["data"]["segments_count"], 2)
            self.assertEqual(obj["data"]["ics_path"], str(output))
            self.assertEqual([s["route"] for s in obj["data"]["segments"]], ["SVO->LED", "LED->SVO"])
            self.assertEqual(
                [step["step"] for step in obj["process"]],
                ["parse_args", "load_input", "build_calendar", "validate_ics", "write_output", "emit_json"],
            )
            combined_output = result.stdout + result.stderr
            for private_value in ["ABC123", "Ivan Ivanov", "5552400000000", "pnrKey"]:
                self.assertNotIn(private_value, combined_output)

    def test_validate_json_is_check_only_and_machine_readable(self) -> None:
        result = self.run_cli("--json", "validate", "--input", str(TEMPLATE))

        self.assertEqual(result.returncode, 0, result.stderr)
        obj = self.parse_stdout_json(result)
        self.assert_envelope(obj, ok=True, command="validate")
        self.assertEqual(obj["data"]["segments_count"], 2)
        self.assertFalse(obj["data"]["write_performed"])
        self.assertEqual(
            [step["step"] for step in obj["process"]],
            ["parse_args", "load_input", "build_calendar", "validate_ics", "no_write", "emit_json"],
        )

    def test_invalid_alarm_returns_machine_readable_validation_error(self) -> None:
        source = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        source["alarms_minutes"] = ["abc"]
        source["booking_reference"] = "SECRET1"
        source["passengers"] = ["Private Passenger"]
        with tempfile.TemporaryDirectory() as td:
            input_path = Path(td) / "bad-alarm.json"
            input_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            result = self.run_cli("--json", "validate", "--input", str(input_path))

        self.assertEqual(result.returncode, 2)
        obj = self.parse_stdout_json(result)
        self.assert_envelope(obj, ok=False, command="validate")
        self.assertEqual(obj["error"]["code"], "validation_error")
        self.assertIn("alarm", obj["error"]["message"].lower())
        combined_output = result.stdout + result.stderr
        self.assertNotIn("SECRET1", combined_output)
        self.assertNotIn("Private Passenger", combined_output)
    def test_json_usage_error_still_returns_machine_readable_envelope(self) -> None:
        result = self.run_cli("--json", "validate")

        self.assertEqual(result.returncode, 2)
        obj = self.parse_stdout_json(result)
        self.assert_envelope(obj, ok=False, command="validate")
        self.assertEqual(obj["error"]["code"], "usage_error")
        self.assertIn("--input", obj["error"]["message"])
        self.assertNotIn("usage:", result.stderr.lower())

    def test_legacy_make_writes_private_ics_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "legacy-trip.ics"
            old_umask = os.umask(0o022)
            try:
                result = subprocess.run(
                    [sys.executable, str(MAKE), "--input", str(TEMPLATE), "--output", str(output)],
                    cwd=ROOT,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    text=True,
                    capture_output=True,
                    timeout=20,
                )
            finally:
                os.umask(old_umask)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.exists())
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)

    def test_legacy_aeroflot_helper_writes_private_artifacts_without_network(self) -> None:
        spec = importlib.util.spec_from_file_location("aeroflot_pnr_to_itinerary_test", AEROFLOT)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        fake_response = {
            "pnr_locator": "ABC123",
            "passengers": [
                {
                    "first_name": "Ivan",
                    "last_name": "Ivanov",
                    "ticketing_documents": {"tickets": [{"number": "5552400000000"}]},
                }
            ],
            "legs": [
                {
                    "segments": [
                        {
                            "origin": {"airport_code": "SVO", "city_name": "Москва", "terminal_code": "B"},
                            "destination": {"airport_code": "LED", "city_name": "Санкт-Петербург", "terminal_code": "1"},
                            "departure": "2026-06-01 09:15:00",
                            "arrival": "2026-06-01 10:45:00",
                            "airline_code": "SU",
                            "airline_name": "Аэрофлот",
                            "flight_number": "1234",
                            "status_code": "HK",
                            "cabin_name": "Эконом",
                        }
                    ]
                }
            ],
        }
        original_fetch = module.fetch_aeroflot_pnr
        module.fetch_aeroflot_pnr = lambda _locator, _key: fake_response
        with tempfile.TemporaryDirectory() as td:
            output_json = Path(td) / "aeroflot.json"
            output_ics = Path(td) / "aeroflot.ics"
            old_umask = os.umask(0o022)
            try:
                rc = module.main(
                    [
                        "--pnr-locator",
                        "ABC123",
                        "--pnr-key",
                        "a" * 64,
                        "--output-json",
                        str(output_json),
                        "--output-ics",
                        str(output_ics),
                    ]
                )
            finally:
                os.umask(old_umask)
                module.fetch_aeroflot_pnr = original_fetch

            self.assertEqual(rc, 0)
            self.assertEqual(stat.S_IMODE(output_json.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(output_ics.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main(verbosity=2)
