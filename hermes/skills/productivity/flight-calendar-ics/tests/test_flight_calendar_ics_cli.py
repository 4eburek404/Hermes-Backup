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
import argparse
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
REDWINGS = ROOT / "scripts" / "redwings_to_itinerary.py"
TEMPLATE = ROOT / "templates" / "aeroflot-itinerary.example.json"
SCHEMA = ROOT / "schemas" / "cli-envelope.v1.schema.json"
ITINERARY_SCHEMA = ROOT / "schemas" / "itinerary.v1.schema.json"


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
        self.assert_cli_schema_valid(obj)

    def assert_cli_schema_valid(self, obj: dict) -> None:
        from jsonschema import Draft202012Validator

        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(obj), key=lambda error: list(error.path))
        self.assertEqual(errors, [])

    def test_doctor_json_describes_single_entrypoint_and_commands(self) -> None:
        result = self.run_cli("--json", "doctor")

        self.assertEqual(result.returncode, 0, result.stderr)
        obj = self.parse_stdout_json(result)
        self.assert_envelope(obj, ok=True, command="doctor")
        self.assertEqual(obj["data"]["entrypoint"], str(CLI))
        self.assertEqual(obj["data"]["entrypoint_kind"], "single-python-executable")
        self.assertGreaterEqual(
            set(obj["data"]["commands"]),
            {"doctor", "validate", "make", "aeroflot", "ural", "utair", "redwings"},
        )
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
        self.assertIn("ural", properties["command"]["enum"])
        self.assertIn("utair", properties["command"]["enum"])
        self.assertIn("redwings", properties["command"]["enum"])
        self.assertIn("data", properties)
        self.assertIn("error", properties)

    def test_itinerary_schema_documents_provider_agnostic_contract(self) -> None:
        from jsonschema import Draft202012Validator

        schema = json.loads(ITINERARY_SCHEMA.read_text(encoding="utf-8"))

        Draft202012Validator.check_schema(schema)
        self.assertEqual(schema["$id"], "https://hermes-agent.local/schemas/flight-calendar-ics-itinerary.v1.json")
        self.assertEqual(schema["title"], "flight-calendar-ics canonical itinerary v1")
        self.assertGreaterEqual(set(schema["required"]), {"schema_version", "flights"})
        self.assertEqual(schema["properties"]["schema_version"]["const"], "flight-calendar-ics-itinerary.v1")
        flight_segment = schema["$defs"]["flight_segment"]
        self.assertGreaterEqual(set(flight_segment["required"]), {"flight_number", "departure", "arrival"})
        endpoint = schema["$defs"]["airport_endpoint"]
        self.assertGreaterEqual(set(endpoint["required"]), {"airport", "local", "tz"})
        serialized = json.dumps(schema, ensure_ascii=False).lower()
        for provider_name in ["aeroflot", "utair", "ural", "pnrkey", "last_name"]:
            self.assertNotIn(provider_name, serialized)

    def test_template_validates_against_canonical_itinerary_schema(self) -> None:
        from jsonschema import Draft202012Validator

        schema = json.loads(ITINERARY_SCHEMA.read_text(encoding="utf-8"))
        data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)

        errors = sorted(validator.iter_errors(data), key=lambda error: list(error.path))

        self.assertEqual(data["schema_version"], "flight-calendar-ics-itinerary.v1")
        self.assertEqual(errors, [])

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
                [
                    "parse_args",
                    "load_input",
                    "validate_itinerary_schema",
                    "validate_itinerary_semantics",
                    "build_calendar",
                    "validate_ics",
                    "write_output",
                    "emit_json",
                ],
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
            [
                "parse_args",
                "load_input",
                "validate_itinerary_schema",
                "validate_itinerary_semantics",
                "build_calendar",
                "validate_ics",
                "no_write",
                "emit_json",
            ],
        )

    def test_validate_rejects_unknown_canonical_fields_before_calendar_build(self) -> None:
        source = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        source["unexpected_debug_payload"] = {"private": "SECRET1"}
        with tempfile.TemporaryDirectory() as td:
            input_path = Path(td) / "bad-extra.json"
            input_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            result = self.run_cli("--json", "validate", "--input", str(input_path))

        self.assertEqual(result.returncode, 2)
        obj = self.parse_stdout_json(result)
        self.assert_envelope(obj, ok=False, command="validate")
        self.assertEqual(obj["error"]["code"], "validation_error")
        self.assertIn("unexpected_debug_payload", obj["error"]["message"])
        steps = [step["step"] for step in obj["process"]]
        self.assertIn("validate_itinerary_schema", steps)
        self.assertNotIn("build_calendar", steps)
        combined_output = result.stdout + result.stderr
        self.assertNotIn("SECRET1", combined_output)

    def test_validate_rejects_missing_required_endpoint_timezone_at_schema_gate(self) -> None:
        source = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        source["flights"][0]["departure"].pop("tz")
        with tempfile.TemporaryDirectory() as td:
            input_path = Path(td) / "bad-missing-tz.json"
            input_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            result = self.run_cli("--json", "validate", "--input", str(input_path))

        self.assertEqual(result.returncode, 2)
        obj = self.parse_stdout_json(result)
        self.assert_envelope(obj, ok=False, command="validate")
        self.assertEqual(obj["error"]["code"], "validation_error")
        self.assertIn("flights[0].departure", obj["error"]["message"])
        self.assertIn("tz", obj["error"]["message"])
        steps = [step["step"] for step in obj["process"]]
        self.assertIn("validate_itinerary_schema", steps)
        self.assertNotIn("build_calendar", steps)

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
            saved_itinerary = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(saved_itinerary["schema_version"], "flight-calendar-ics-itinerary.v1")

    def test_redwings_url_parser_accepts_find_route_and_rejects_order_route(self) -> None:
        spec = importlib.util.spec_from_file_location("redwings_to_itinerary_test", REDWINGS)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        direct_url = "https://flyredwings.com/booking/#/find/AB12CD/EMAILKEY123/Submit"
        locator, finder_code, booking_url = module.parse_redwings_source(direct_url, None, None)

        self.assertEqual(locator, "AB12CD")
        self.assertEqual(finder_code, "EMAILKEY123")
        self.assertEqual(booking_url, direct_url)
        with self.assertRaises(ValueError) as ctx:
            module.parse_redwings_source("https://flyredwings.com/booking/#/booking/ORDER123/order", None, None)
        self.assertIn("#/find/<PNR>/<ACCESS_KEY>/Submit", str(ctx.exception))

    def test_redwings_command_fetches_order_and_writes_private_artifacts(self) -> None:
        script_dir = str((ROOT / "scripts").resolve())
        old_path = list(sys.path)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        try:
            spec = importlib.util.spec_from_file_location("flight_calendar_ics_redwings_test", CLI)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = old_path

        fake_order = {
            "data": {
                "FindOrder": {
                    "id": "order-id",
                    "locator": "AB12CD",
                    "status": "Confirmed",
                    "paymentStatus": "Paid",
                    "flight": {
                        "segmentGroups": [
                            {
                                "segments": [
                                    {
                                        "id": "seg-1",
                                        "flightNumber": "1034",
                                        "marketingAirline": {"iata": "WZ", "name": "Red Wings"},
                                        "operatingAirline": {"iata": "WZ", "name": "Red Wings"},
                                        "aircraft": {"name": "Sukhoi Superjet"},
                                        "departure": {
                                            "date": "2026-06-03",
                                            "time": "08:25",
                                            "airport": {"iata": "KUF", "city": {"name": "Самара"}},
                                        },
                                        "arrival": {
                                            "date": "2026-06-03",
                                            "time": "10:55",
                                            "airport": {"iata": "SVX", "city": {"name": "Екатеринбург"}},
                                        },
                                    }
                                ]
                            }
                        ]
                    },
                    "travellers": [
                        {
                            "id": "traveller-1",
                            "values": [
                                {"type": "FirstName", "value": "JANE"},
                                {"type": "LastName", "value": "DOE"},
                            ],
                            "tickets": [{"number": "9218844512345", "coupons": [{"segment": {"id": "seg-1"}}]}],
                            "services": {
                                "seats": [{"row": "12", "letter": "A", "segment": {"id": "seg-1"}}],
                                "brandIncludedServices": {
                                    "services": [
                                        {
                                            "segmentIds": ["seg-1"],
                                            "service": {"name": "Багаж 10 кг", "type": "Baggage"},
                                        }
                                    ]
                                },
                            },
                        }
                    ],
                }
            }
        }
        calls: list[dict] = []

        def fake_fetch(locator: str, finder_code: str, **kwargs: object) -> dict:
            calls.append({"locator": locator, "finder_code": finder_code, **kwargs})
            return fake_order

        original_fetch = module.redwings.fetch_redwings_order
        module.redwings.fetch_redwings_order = fake_fetch
        try:
            with tempfile.TemporaryDirectory() as td:
                output_json = Path(td) / "redwings.json"
                output_ics = Path(td) / "redwings.ics"
                args = argparse.Namespace(
                    url="https://flyredwings.com/booking/#/find/AB12CD/EMAILKEY123/Submit",
                    pnr=None,
                    access_code=None,
                    output_json=output_json,
                    output_ics=output_ics,
                    tz=[],
                    graphql_endpoint=None,
                    no_alarms=True,
                )
                process: list[dict] = []

                rc, data = module.command_redwings(args, process)

                self.assertEqual(rc, 0)
                self.assertEqual(calls[0]["locator"], "AB12CD")
                self.assertEqual(calls[0]["finder_code"], "EMAILKEY123")
                self.assertIsNone(calls[0]["graphql_endpoint"])
                self.assertTrue(output_json.exists())
                self.assertTrue(output_ics.exists())
                self.assertEqual(stat.S_IMODE(output_json.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(output_ics.stat().st_mode), 0o600)
                saved_itinerary = json.loads(output_json.read_text(encoding="utf-8"))
                self.assertEqual(saved_itinerary["schema_version"], "flight-calendar-ics-itinerary.v1")
                self.assertEqual(saved_itinerary["booking_reference"], "AB12CD")
                self.assertEqual(data["segments_count"], 1)
                self.assertEqual(data["segments"][0]["route"], "KUF->SVX")
                self.assertEqual(
                    [step["step"] for step in process],
                    [
                        "parse_redwings_source",
                        "load_timezone_map",
                        "fetch_redwings_order",
                        "convert_to_itinerary",
                        "validate_itinerary_schema",
                        "validate_itinerary_semantics",
                        "build_calendar",
                        "validate_ics",
                        "write_json",
                        "write_ics",
                    ],
                )
                safe_output = json.dumps(data, ensure_ascii=False) + json.dumps(process, ensure_ascii=False)
                for private_value in ["AB12CD", "EMAILKEY123", "JANE", "DOE", "9218844512345"]:
                    self.assertNotIn(private_value, safe_output)
                ics_text = output_ics.read_text(encoding="utf-8")
                self.assertIn("BEGIN:VCALENDAR", ics_text)
                self.assertEqual(ics_text.count("BEGIN:VEVENT"), 1)
                self.assertIn("DTSTART:20260603T042500Z", ics_text)
                self.assertIn("DTEND:20260603T055500Z", ics_text)
                unfolded_ics = ics_text.replace("\r\n ", "").replace("\n ", "")
                self.assertIn("AB12CD", unfolded_ics)
                self.assertIn("JANE DOE", unfolded_ics)
                self.assertIn("9218844512345", unfolded_ics)
                self.assertIn("Багаж 10 кг", unfolded_ics)
        finally:
            module.redwings.fetch_redwings_order = original_fetch

    def test_ural_url_parser_decodes_tracking_redirect_without_local_env(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "ural_airlines_to_itinerary_test",
            ROOT / "scripts" / "ural_airlines_to_itinerary.py",
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        target = "https://service.uralairlines.ru/?pnr=ZZ9ZZZ&lastName=DOE"
        redirect = "https://tracker.example/click?u=https%3A%2F%2Fservice.uralairlines.ru%2F%3Fpnr%3DZZ9ZZZ%26lastName%3DDOE"

        locator, last_name, booking_url = module.parse_ural_source(redirect, None, None)

        self.assertEqual(locator, "ZZ9ZZZ")
        self.assertEqual(last_name, "DOE")
        self.assertEqual(booking_url, target)
        self.assertEqual(module.DEFAULT_ENV_PATH, "/<version>/env/env.json")
        self.assertNotIn(".env", module.DEFAULT_ENV_PATH)

    def test_ural_command_uses_live_frontend_flow_and_writes_private_artifacts(self) -> None:
        script_dir = str((ROOT / "scripts").resolve())
        old_path = list(sys.path)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        try:
            spec = importlib.util.spec_from_file_location("flight_calendar_ics_test", CLI)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = old_path

        fake_reservation = {
            "success": True,
            "data": {
                "number": "ZZ9ZZZ",
                "journey": {
                    "outboundFlights": [
                        {
                            "referenceNumber": "1",
                            "origin": "SVX",
                            "destination": "DME",
                            "departureDate": "2026-06-04T16:00:00",
                            "arrivalDate": "2026-06-04T16:30:00",
                            "departureDateUtc": "2026-06-04T11:00:00Z",
                            "arrivalDateUtc": "2026-06-04T13:30:00Z",
                            "flightNumber": "300",
                            "operatingCarrier": "U6",
                            "marketingCarrier": "U6",
                            "aircraft": "Airbus A320neo",
                            "classOfService": "E",
                            "commercialFamily": "U6ECONOMY",
                            "statuses": ["HK"],
                        }
                    ],
                    "returnFlights": [],
                    "separateFlights": [],
                },
                "passengers": [{"firstName": "JANE", "surname": "DOE", "referenceNumber": "P1"}],
                "tickets": [{"number": "2620000000000", "passengerReference": "P1", "flightReferences": ["1"]}],
            },
        }
        calls: list[dict] = []

        def fake_fetch(locator: str, last_name: str, **kwargs: object) -> dict:
            calls.append({"locator": locator, "last_name": last_name, **kwargs})
            return fake_reservation

        original_fetch = module.ural.fetch_ural_reservation
        module.ural.fetch_ural_reservation = fake_fetch
        try:
            with tempfile.TemporaryDirectory() as td:
                output_json = Path(td) / "ural.json"
                output_ics = Path(td) / "ural.ics"
                args = argparse.Namespace(
                    url="https://service.uralairlines.ru/?pnr=ZZ9ZZZ&lastName=DOE",
                    pnr=None,
                    last_name=None,
                    output_json=output_json,
                    output_ics=output_ics,
                    tz=[],
                    no_alarms=True,
                    frontend_base=None,
                )
                process: list[dict] = []

                rc, data = module.command_ural(args, process)

                self.assertEqual(rc, 0)
                self.assertEqual(calls[0]["locator"], "ZZ9ZZZ")
                self.assertEqual(calls[0]["last_name"], "DOE")
                self.assertIsNone(calls[0]["frontend_base"])
                self.assertTrue(output_json.exists())
                self.assertTrue(output_ics.exists())
                self.assertEqual(stat.S_IMODE(output_json.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(output_ics.stat().st_mode), 0o600)
                saved_itinerary = json.loads(output_json.read_text(encoding="utf-8"))
                self.assertEqual(saved_itinerary["schema_version"], "flight-calendar-ics-itinerary.v1")
                self.assertEqual(data["segments_count"], 1)
                self.assertEqual(data["segments"][0]["route"], "SVX->DME")
                self.assertEqual(
                    [step["step"] for step in process],
                    [
                        "parse_pnr_source",
                        "load_timezone_map",
                        "fetch_ural_reservation",
                        "convert_to_itinerary",
                        "validate_itinerary_schema",
                        "validate_itinerary_semantics",
                        "build_calendar",
                        "validate_ics",
                        "write_json",
                        "write_ics",
                    ],
                )
                safe_output = json.dumps(data, ensure_ascii=False) + json.dumps(process, ensure_ascii=False)
                for private_value in ["ZZ9ZZZ", "DOE", "JANE", "2620000000000"]:
                    self.assertNotIn(private_value, safe_output)
        finally:
            module.ural.fetch_ural_reservation = original_fetch

    def test_utair_url_parser_handles_cyrillic_surname(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "utair_to_itinerary_test",
            ROOT / "scripts" / "utair_to_itinerary.py",
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        url = "https://www.utair.ru/order-manage?rloc=zz9zzz&last_name=%D0%98%D0%92%D0%90%D0%9D%D0%9E%D0%92%D0%90&utm_source=mail"

        locator, last_name, booking_url = module.parse_utair_source(url, None, None)

        self.assertEqual(locator, "ZZ9ZZZ")
        self.assertEqual(last_name, "ИВАНОВА")
        self.assertEqual(booking_url, url)

    def test_utair_command_fetches_order_and_writes_private_artifacts(self) -> None:
        script_dir = str((ROOT / "scripts").resolve())
        old_path = list(sys.path)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        try:
            spec = importlib.util.spec_from_file_location("flight_calendar_ics_utair_test", CLI)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = old_path

        fake_response = {
            "future": [
                {
                    "rloc": "ZZ9ZZZ",
                    "order_uuid": "uuid",
                    "status": "T",
                    "segments": [
                        {
                            "segment_id": "0",
                            "ak": "UT",
                            "flight_number": "281",
                            "departure_airport_code": "SVX",
                            "arrival_airport_code": "KUF",
                            "departure_local_iso": "2026-06-10T11:50:00",
                            "arrival_local_iso": "2026-06-10T12:30:00",
                            "departure_city": "Екатеринбург",
                            "arrival_city": "Самара",
                            "status": "HK",
                            "status_visual": "active",
                        }
                    ],
                    "passengers": [
                        {"passenger_id": "1", "first_name": "JANE", "last_name": "DOE", "type": "ADULT"}
                    ],
                    "tickets": [{"passenger_id": "1", "ticket": "2980000000000"}],
                    "offers": [{"segment_id": "0", "brand_name": "Минимум", "brand_code": "MINIMUM_NEW"}],
                }
            ],
            "past": [],
        }
        calls: list[dict] = []

        def fake_fetch(locator: str, last_name: str, **kwargs: object) -> dict:
            calls.append({"locator": locator, "last_name": last_name, **kwargs})
            return fake_response

        original_fetch_auth = getattr(module.utair, "fetch_utair_" + "token")
        original_fetch_orders = module.utair.fetch_utair_orders
        setattr(module.utair, "fetch_utair_" + "token", lambda: "fake-auth")
        module.utair.fetch_utair_orders = fake_fetch
        try:
            with tempfile.TemporaryDirectory() as td:
                output_json = Path(td) / "utair.json"
                output_ics = Path(td) / "utair.ics"
                args = argparse.Namespace(
                    url="https://www.utair.ru/order-manage?rloc=ZZ9ZZZ&last_name=DOE&utm_source=mail",
                    rloc=None,
                    last_name=None,
                    output_json=output_json,
                    output_ics=output_ics,
                    tz=[],
                    no_alarms=True,
                )
                process: list[dict] = []

                rc, data = module.command_utair(args, process)

                self.assertEqual(rc, 0)
                self.assertEqual(calls[0]["locator"], "ZZ9ZZZ")
                self.assertEqual(calls[0]["last_name"], "DOE")
                self.assertEqual(calls[0]["bearer_value"], "fake-auth")
                self.assertTrue(output_json.exists())
                self.assertTrue(output_ics.exists())
                self.assertEqual(stat.S_IMODE(output_json.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(output_ics.stat().st_mode), 0o600)
                saved_itinerary = json.loads(output_json.read_text(encoding="utf-8"))
                self.assertEqual(saved_itinerary["schema_version"], "flight-calendar-ics-itinerary.v1")
                self.assertEqual(data["segments_count"], 1)
                self.assertEqual(data["segments"][0]["route"], "SVX->KUF")
                self.assertEqual(
                    [step["step"] for step in process],
                    [
                        "parse_pnr_source",
                        "load_timezone_map",
                        "fetch_utair_token",
                        "fetch_utair_orders",
                        "convert_to_itinerary",
                        "validate_itinerary_schema",
                        "validate_itinerary_semantics",
                        "build_calendar",
                        "validate_ics",
                        "write_json",
                        "write_ics",
                    ],
                )
                safe_output = json.dumps(data, ensure_ascii=False) + json.dumps(process, ensure_ascii=False)
                for private_value in ["ZZ9ZZZ", "DOE", "JANE", "2980000000000", "fake-auth"]:
                    self.assertNotIn(private_value, safe_output)
                ics_text = output_ics.read_text(encoding="utf-8")
                self.assertIn("BEGIN:VCALENDAR", ics_text)
                self.assertEqual(ics_text.count("BEGIN:VEVENT"), 1)
                self.assertIn("DTSTART:20260610T065000Z", ics_text)
                self.assertIn("DTEND:20260610T083000Z", ics_text)
                unfolded_ics = ics_text.replace("\r\n ", "").replace("\n ", "")
                self.assertIn("ZZ9ZZZ", unfolded_ics)
                self.assertIn("JANE DOE", unfolded_ics)
                self.assertIn("2980000000000", unfolded_ics)
        finally:
            setattr(module.utair, "fetch_utair_" + "token", original_fetch_auth)
            module.utair.fetch_utair_orders = original_fetch_orders

    def test_redact_masks_ural_booking_url_credentials(self) -> None:
        script_dir = str((ROOT / "scripts").resolve())
        old_path = list(sys.path)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        try:
            spec = importlib.util.spec_from_file_location("flight_calendar_ics_redact_test", CLI)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = old_path

        redacted = module.redact("https://service.uralairlines.ru/?pnr=ZZ9ZZZ&lastName=DOE ticket_number=2620000000000")

        self.assertNotIn("ZZ9ZZZ", redacted)
        self.assertNotIn("DOE", redacted)
        self.assertNotIn("2620000000000", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_redact_masks_utair_booking_url_credentials(self) -> None:
        script_dir = str((ROOT / "scripts").resolve())
        old_path = list(sys.path)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        try:
            spec = importlib.util.spec_from_file_location("flight_calendar_ics_utair_redact_test", CLI)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = old_path

        redacted = module.redact(
            "https://www.utair.ru/order-manage?rloc=ZZ9ZZZ&last_name=DOE "
            "filters%5Blocator%5D=ZZ9ZZZ&filters[passenger_lastname]=DOE "
            "Authorization: " + "Bearer *** ticket=2980000000000"
        )

        for private_value in ["ZZ9ZZZ", "DOE", "secret-token", "2980000000000"]:
            self.assertNotIn(private_value, redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_redact_masks_redwings_finder_credentials(self) -> None:
        script_dir = str((ROOT / "scripts").resolve())
        old_path = list(sys.path)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        try:
            spec = importlib.util.spec_from_file_location("flight_calendar_ics_redwings_redact_test", CLI)
            assert spec is not None
            assert spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = old_path

        redacted = module.redact(
            "https://flyredwings.com/booking/#/find/AB12CD/EMAILKEY123/Submit "
            "access-key EMAILKEY123 access_code=EMAILKEY123 "
            + '{"secret": "EMAILKEY123"}'
        )

        for private_value in ["AB12CD", "EMAILKEY123"]:
            self.assertNotIn(private_value, redacted)
        self.assertIn("#/find/[REDACTED]/[REDACTED]/Submit", redacted)
        self.assertIn("[REDACTED]", redacted)


if __name__ == "__main__":
    unittest.main(verbosity=2)
