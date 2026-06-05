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
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
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

    def import_cli_module(self):
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
            return module
        finally:
            sys.path[:] = old_path

    def import_script_module(self, filename: str, module_name: str | None = None):
        script_dir = str((ROOT / "scripts").resolve())
        old_path = list(sys.path)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        try:
            spec = importlib.util.spec_from_file_location(
                module_name or f"{Path(filename).stem}_test",
                ROOT / "scripts" / filename,
            )
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            sys.path[:] = old_path

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

    def assert_matches_cli_schema(self, obj: dict) -> None:
        from jsonschema import Draft202012Validator

        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(obj), key=lambda error: list(error.path))
        self.assertEqual(
            [],
            [f"{'/'.join(map(str, error.absolute_path))}: {error.message}" for error in errors],
        )

    def assert_envelope(self, obj: dict, *, ok: bool, command: str) -> None:
        self.assert_matches_cli_schema(obj)
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
        self.assertGreaterEqual(set(obj["data"]["commands"]), {"doctor", "validate", "make", "build", "aeroflot", "ural", "utair", "redwings"})
        contract = obj["data"].get("agent_contract")
        self.assertIsInstance(contract, dict)
        self.assertEqual([step["id"] for step in contract["normal_steps"]], ["collect_source", "run_one_command", "verify", "deliver"])
        self.assertEqual({item["command"] for item in contract["dispatch_matrix"]}, {"build"})
        self.assertEqual({item["route"] for item in contract["dispatch_matrix"]}, {"auto", "make", "aeroflot", "ural", "utair", "redwings"})
        auto_entry = next(item for item in contract["dispatch_matrix"] if item["route"] == "auto")
        self.assertEqual(auto_entry["argv_template"][:3], ["--json", "build", "auto"])
        aeroflot_entry = next(item for item in contract["dispatch_matrix"] if item["route"] == "aeroflot")
        self.assertEqual(aeroflot_entry["argv_template"][:3], ["--json", "build", "aeroflot"])
        for entry in contract["dispatch_matrix"]:
            self.assertNotIn("--output-json", entry["argv_template"])
            self.assertNotIn("--output-ics", entry["argv_template"])
        self.assertIn("no_full_booking_urls", contract["privacy"]["chat_summary_must_omit"])
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
        self.assertIn("build", properties["command"]["enum"])
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

    def test_make_ics_uses_compact_russian_event_content(self) -> None:
        source = {
            "schema_version": "flight-calendar-ics-itinerary.v1",
            "calendar_name": "Flights",
            "booking_reference": "18GHI4",
            "passengers": ["Орлов Константин"],
            "links": ["https://carrier.example/manage/18GHI4"],
            "flights": [
                {
                    "carrier": "Авиакомпания",
                    "flight_number": "SU1234",
                    "departure": {
                        "airport": "SVO",
                        "city": "Москва",
                        "local": "2026-06-08T14:40",
                        "tz": "Europe/Moscow",
                    },
                    "arrival": {
                        "airport": "SVX",
                        "city": "Екатеринбург",
                        "local": "2026-06-08T19:10",
                        "tz": "Asia/Yekaterinburg",
                    },
                    "ticket_number": "55583566629584",
                    "aircraft": "Boeing 737",
                    "cabin": "Эконом",
                    "fare": "Оптимум",
                    "notes": "Лишнее описание не должно попасть в календарь",
                    "status": "confirmed",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            input_path = Path(td) / "compact.json"
            output_path = Path(td) / "compact.ics"
            input_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")

            result = self.run_cli("--json", "make", "--input", str(input_path), "--output", str(output_path), "--no-alarms")

            self.assertEqual(result.returncode, 0, result.stderr)
            unfolded_ics = output_path.read_text(encoding="utf-8").replace("\r\n ", "").replace("\n ", "")
            self.assertIn(
                "SUMMARY:Орлов Константин 08.06 Москва - Екатеринбург 14:40 19:10",
                unfolded_ics,
            )
            self.assertIn(
                "DESCRIPTION:PNR: 18GHI4\\n"
                "Билет: 555 83566629584\\n"
                "08.06 Москва -> Екатеринбург 14:40 19:10\\n"
                "Самолет: Boeing 737\\n"
                "Бронирование: https://carrier.example/manage/18GHI4",
                unfolded_ics,
            )
            for verbose_label in ["Flight:", "Route:", "Departure local:", "Arrival local:", "Cabin:", "Fare:", "Notes:"]:
                self.assertNotIn(verbose_label, unfolded_ics)

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
            for private_value in ["ABC123", "Ivanov Ivan", "5552400000000", "pnrKey"]:
                self.assertNotIn(private_value, combined_output)

    def test_build_make_creates_private_bundle_and_saved_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td) / "bundle"
            old_umask = os.umask(0o022)
            try:
                result = self.run_cli(
                    "--json",
                    "build",
                    "make",
                    "--input",
                    str(TEMPLATE),
                    "--output-dir",
                    str(output_dir),
                    "--no-alarms",
                )
            finally:
                os.umask(old_umask)

            self.assertEqual(result.returncode, 0, result.stderr)
            obj = self.parse_stdout_json(result)
            self.assert_envelope(obj, ok=True, command="build")
            self.assertEqual(obj["data"]["route"], "make")
            self.assertEqual(obj["data"]["output_dir"], str(output_dir))
            self.assertEqual(obj["data"]["json_path"], str(output_dir / "itinerary.json"))
            self.assertEqual(obj["data"]["ics_path"], str(output_dir / "flights.ics"))
            self.assertEqual(obj["data"]["envelope_path"], str(output_dir / "envelope.json"))
            self.assertEqual(obj["data"]["verification"]["ok"], True)
            self.assertEqual(obj["data"]["verification"]["event_count"], obj["data"]["segments_count"])
            self.assertTrue(output_dir.is_dir())
            self.assertEqual(stat.S_IMODE(output_dir.stat().st_mode), 0o700)
            for artifact in [output_dir / "itinerary.json", output_dir / "flights.ics", output_dir / "envelope.json"]:
                self.assertTrue(artifact.exists(), artifact)
                self.assertEqual(stat.S_IMODE(artifact.stat().st_mode), 0o600, artifact)
            saved_envelope = json.loads((output_dir / "envelope.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_envelope, obj)
            ics_text = (output_dir / "flights.ics").read_text(encoding="utf-8")
            self.assertIn("BEGIN:VCALENDAR", ics_text)
            self.assertEqual(ics_text.count("BEGIN:VEVENT"), obj["data"]["segments_count"])
            self.assertTrue(all(line.endswith("Z") for line in ics_text.splitlines() if line.startswith(("DTSTART:", "DTEND:"))))
            self.assertIn("create_output_bundle", [step["step"] for step in obj["process"]])
            self.assertIn("verify_bundle", [step["step"] for step in obj["process"]])
            self.assertIn("write_envelope", [step["step"] for step in obj["process"]])
            combined_output = result.stdout + result.stderr
            for private_value in ["ABC123", "Ivanov Ivan", "5552400000000", "pnrKey"]:
                self.assertNotIn(private_value, combined_output)

    def test_build_route_parser_accepts_private_url_file_without_output_flags(self) -> None:
        module = self.import_cli_module()
        parser = module.build_parser()

        args = parser.parse_args(["build", "redwings", "--url-file", "/tmp/source.txt"])

        self.assertEqual(args.command, "build")
        self.assertEqual(args.route, "redwings")
        self.assertEqual(args.url_file, Path("/tmp/source.txt"))
        self.assertFalse(hasattr(args, "output_json"))
        self.assertFalse(hasattr(args, "output_ics"))

    def test_build_route_parser_accepts_auto_for_cli_owned_route_inference(self) -> None:
        module = self.import_cli_module()
        parser = module.build_parser()

        args = parser.parse_args(["build", "auto", "--url-file", "/tmp/source.txt"])

        self.assertEqual(args.command, "build")
        self.assertEqual(args.route, "auto")
        self.assertEqual(args.url_file, Path("/tmp/source.txt"))

    def test_build_auto_infers_make_from_canonical_itinerary_input(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td) / "auto-make-bundle"

            result = self.run_cli(
                "--json",
                "build",
                "auto",
                "--input",
                str(TEMPLATE),
                "--output-dir",
                str(output_dir),
                "--no-alarms",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            obj = self.parse_stdout_json(result)
            self.assert_envelope(obj, ok=True, command="build")
            self.assertEqual(obj["data"]["route"], "make")
            self.assertEqual(obj["data"]["route_detection"]["mode"], "auto")
            self.assertEqual(obj["data"]["route_detection"]["route"], "make")
            self.assertIn("input_kind:canonical_itinerary_json", obj["data"]["route_detection"]["evidence"])
            self.assertTrue((output_dir / "flights.ics").exists())
            self.assertIn("infer_route", [step["step"] for step in obj["process"]])

    def test_build_auto_infers_aeroflot_from_private_url_file_without_doctor(self) -> None:
        module = self.import_cli_module()
        original_command = getattr(module, "command_aeroflot")
        calls: list[argparse.Namespace] = []

        def fake_command_aeroflot(args: argparse.Namespace, process: list[dict]) -> tuple[int, dict]:
            calls.append(args)
            itinerary = json.loads(TEMPLATE.read_text(encoding="utf-8"))
            ics_text, summaries = module.make_flight_ics.build_calendar(itinerary, no_alarms=True)
            module.secure_write_text(args.output_json, json.dumps(itinerary, ensure_ascii=False, indent=2) + "\n")
            module.secure_write_text(args.output_ics, ics_text)
            module.add_step(process, "fake_fetch_aeroflot_pnr")
            module.add_step(process, "write_json", artifact="json", mode="0600")
            module.add_step(process, "write_ics", artifact="ics", mode="0600")
            return 0, {
                "segments_count": len(summaries),
                "segments": [module.safe_segment_summary(item) for item in summaries],
                "json_path": str(args.output_json),
                "ics_path": str(args.output_ics),
                "write_performed": True,
            }

        setattr(module, "command_aeroflot", fake_command_aeroflot)
        try:
            with tempfile.TemporaryDirectory() as td:
                output_dir = Path(td) / "auto-aeroflot-bundle"
                url_file = Path(td) / "source-url.txt"
                private_key = "a" * 64
                url_file.write_text(
                    f"https://www.aeroflot.ru/RU-ru/pnr/?pnrKey={private_key}&pnrLocator=ABC123\n",
                    encoding="utf-8",
                )
                args = argparse.Namespace(
                    command="build",
                    route="auto",
                    input=None,
                    url=None,
                    url_file=url_file,
                    pnr_locator=None,
                    pnr_key=None,
                    pnr=None,
                    rloc=None,
                    last_name=None,
                    first_name=None,
                    access_code=None,
                    output_dir=output_dir,
                    tz=[],
                    no_alarms=True,
                    frontend_base=None,
                    graphql_endpoint=None,
                )
                process: list[dict] = []

                rc, data = module.command_build(args, process)

                self.assertEqual(rc, 0)
                self.assertEqual(calls[0].url, f"https://www.aeroflot.ru/RU-ru/pnr/?pnrKey={private_key}&pnrLocator=ABC123")
                self.assertEqual(data["route"], "aeroflot")
                self.assertEqual(data["route_detection"]["route"], "aeroflot")
                self.assertEqual(data["route_detection"]["confidence"], 1.0)
                self.assertIn("host:aeroflot.ru", data["route_detection"]["evidence"])
                self.assertIn("query_field:pnrKey", data["route_detection"]["evidence"])
                self.assertIn("query_field:pnrLocator", data["route_detection"]["evidence"])
                self.assertNotIn("doctor", [step["step"] for step in process])
                safe_output = json.dumps(data, ensure_ascii=False) + json.dumps(process, ensure_ascii=False)
                for private_value in [private_key, "ABC123"]:
                    self.assertNotIn(private_value, safe_output)
        finally:
            setattr(module, "command_aeroflot", original_command)

    def test_build_auto_rejects_redwings_order_page_without_leaking_order_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            output_dir = Path(td) / "auto-redwings-order"
            url_file = Path(td) / "source-url.txt"
            url_file.write_text("https://flyredwings.com/booking/#/booking/ORDER123/order\n", encoding="utf-8")

            result = self.run_cli("--json", "build", "auto", "--url-file", str(url_file), "--output-dir", str(output_dir))

            self.assertEqual(result.returncode, 2)
            obj = self.parse_stdout_json(result)
            self.assert_envelope(obj, ok=False, command="build")
            self.assertEqual(obj["error"]["code"], "route_input_insufficient")
            self.assertIn("direct find link", obj["error"]["message"])
            self.assertIn("infer_route", [step["step"] for step in obj["process"]])
            self.assertNotIn("ORDER123", result.stdout + result.stderr)

    def test_build_auto_rejects_ambiguous_route_specific_args_without_private_values(self) -> None:
        result = self.run_cli(
            "--json",
            "build",
            "auto",
            "--pnr",
            "ABC123",
            "--rloc",
            "ZZ9ZZZ",
            "--last-name",
            "DOE",
        )

        self.assertEqual(result.returncode, 2)
        obj = self.parse_stdout_json(result)
        self.assert_envelope(obj, ok=False, command="build")
        self.assertEqual(obj["error"]["code"], "route_ambiguous")
        self.assertEqual(obj["error"]["safe_candidates"], ["ural", "utair"])
        self.assertIn("explicit route", obj["error"]["required_disambiguation"][0])
        for private_value in ["ABC123", "ZZ9ZZZ", "DOE"]:
            self.assertNotIn(private_value, result.stdout + result.stderr)

    def test_build_auto_locks_known_utair_host_before_generic_pnr_last_name_fields(self) -> None:
        module = self.import_cli_module()
        args = argparse.Namespace(
            route="auto",
            input=None,
            url="https://booking.utair.ru/order-manage?pnr=UT1234&lastName=DOE",
            url_file=None,
            pnr_locator=None,
            pnr_key=None,
            pnr=None,
            rloc=None,
            last_name=None,
            access_code=None,
        )

        detection = module.infer_build_route(args)

        self.assertEqual(detection["route"], "utair")
        self.assertEqual(detection["mode"], "auto")
        self.assertIn("host:utair.ru", detection["evidence"])
        self.assertIn("query_field:pnr", detection["evidence"])
        self.assertIn("query_field:lastName", detection["evidence"])
        self.assertNotIn("UT1234", json.dumps(detection, ensure_ascii=False))
        self.assertNotIn("DOE", json.dumps(detection, ensure_ascii=False))

    def test_build_auto_known_ural_host_with_utair_only_fields_fails_before_wrong_dispatch(self) -> None:
        module = self.import_cli_module()
        args = argparse.Namespace(
            route="auto",
            input=None,
            url="https://service.uralairlines.ru/?rloc=ZZ9ZZZ&last_name=DOE",
            url_file=None,
            pnr_locator=None,
            pnr_key=None,
            pnr=None,
            rloc=None,
            last_name=None,
            access_code=None,
        )

        with self.assertRaises(module.CliFailure) as raised:
            module.infer_build_route(args)

        self.assertEqual(raised.exception.code, "route_input_insufficient")
        self.assertEqual(raised.exception.details["route"], "ural")
        safe_failure = raised.exception.args[0] + json.dumps(raised.exception.details, ensure_ascii=False)
        for private_value in ["ZZ9ZZZ", "DOE"]:
            self.assertNotIn(private_value, safe_failure)

    def test_build_auto_unknown_host_generic_pnr_last_name_is_ambiguous(self) -> None:
        result = self.run_cli(
            "--json",
            "build",
            "auto",
            "--url",
            "https://example.com/manage?pnr=ABC123&lastName=DOE",
        )

        self.assertEqual(result.returncode, 2)
        obj = self.parse_stdout_json(result)
        self.assert_envelope(obj, ok=False, command="build")
        self.assertEqual(obj["error"]["code"], "route_ambiguous")
        self.assertEqual(obj["error"]["safe_candidates"], ["ural", "utair"])
        for private_value in ["ABC123", "DOE"]:
            self.assertNotIn(private_value, result.stdout + result.stderr)

    def test_build_auto_tracking_wrapper_with_multiple_known_hosts_is_ambiguous(self) -> None:
        result = self.run_cli(
            "--json",
            "build",
            "auto",
            "--url",
            "https://tracker.example/click?u=https%3A%2F%2Fwww.aeroflot.ru%2FRU-ru%2Fpnr%2F%3FpnrKey%3DKEY123%26pnrLocator%3DAF1234&next=https%3A%2F%2Fbooking.utair.ru%2Forder-manage%3Frloc%3DUT1234%26last_name%3DDOE",
        )

        self.assertEqual(result.returncode, 2)
        obj = self.parse_stdout_json(result)
        self.assert_envelope(obj, ok=False, command="build")
        self.assertEqual(obj["error"]["code"], "route_ambiguous")
        self.assertEqual(obj["error"]["safe_candidates"], ["aeroflot", "utair"])
        for private_value in ["KEY123", "AF1234", "UT1234", "DOE"]:
            self.assertNotIn(private_value, result.stdout + result.stderr)

    def test_build_route_wraps_carrier_command_with_bundle_paths_and_url_file(self) -> None:
        module = self.import_cli_module()
        original_command = getattr(module, "command_redwings")
        calls: list[argparse.Namespace] = []

        def fake_command_redwings(args: argparse.Namespace, process: list[dict]) -> tuple[int, dict]:
            calls.append(args)
            itinerary = json.loads(TEMPLATE.read_text(encoding="utf-8"))
            ics_text, summaries = module.make_flight_ics.build_calendar(itinerary, no_alarms=True)
            module.secure_write_text(args.output_json, json.dumps(itinerary, ensure_ascii=False, indent=2) + "\n")
            module.secure_write_text(args.output_ics, ics_text)
            module.add_step(process, "fake_fetch_redwings_order")
            module.add_step(process, "write_json", artifact="json", mode="0600")
            module.add_step(process, "write_ics", artifact="ics", mode="0600")
            return 0, {
                "segments_count": len(summaries),
                "segments": [module.safe_segment_summary(item) for item in summaries],
                "json_path": str(args.output_json),
                "ics_path": str(args.output_ics),
                "write_performed": True,
            }

        setattr(module, "command_redwings", fake_command_redwings)
        try:
            with tempfile.TemporaryDirectory() as td:
                output_dir = Path(td) / "redwings-bundle"
                url_file = Path(td) / "source-url.txt"
                url_file.write_text("https://flyredwings.com/booking/#/find/AB12CD/EMAILKEY123/Submit\n", encoding="utf-8")
                args = argparse.Namespace(
                    command="build",
                    route="redwings",
                    url=None,
                    url_file=url_file,
                    pnr=None,
                    access_code=None,
                    output_dir=output_dir,
                    tz=[],
                    no_alarms=True,
                    graphql_endpoint=None,
                )
                process: list[dict] = []

                rc, data = module.command_build(args, process)

                self.assertEqual(rc, 0)
                self.assertEqual(calls[0].url, "https://flyredwings.com/booking/#/find/AB12CD/EMAILKEY123/Submit")
                self.assertEqual(calls[0].output_json, output_dir / "itinerary.json")
                self.assertEqual(calls[0].output_ics, output_dir / "flights.ics")
                self.assertEqual(data["route"], "redwings")
                self.assertEqual(data["output_dir"], str(output_dir))
                self.assertEqual(data["json_path"], str(output_dir / "itinerary.json"))
                self.assertEqual(data["ics_path"], str(output_dir / "flights.ics"))
                self.assertEqual(data["envelope_path"], str(output_dir / "envelope.json"))
                self.assertEqual(data["verification"]["ok"], True)
                self.assertEqual(stat.S_IMODE((output_dir / "itinerary.json").stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE((output_dir / "flights.ics").stat().st_mode), 0o600)
                self.assertFalse((output_dir / "envelope.json").exists(), "main() writes the final envelope after command_build returns")
                safe_output = json.dumps(data, ensure_ascii=False) + json.dumps(process, ensure_ascii=False)
                for private_value in ["AB12CD", "EMAILKEY123", "Ivanov Ivan", "5552400000000"]:
                    self.assertNotIn(private_value, safe_output)
        finally:
            setattr(module, "command_redwings", original_command)

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

    def test_direct_make_script_writes_private_ics_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "direct-trip.ics"
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

    def test_provider_timezone_map_uses_skill_bundled_travelpayouts_catalog_without_local_fallback(self) -> None:
        module = self.import_cli_module()
        catalog_path = ROOT / "assets" / "travelpayouts" / "airport_timezones.json"

        catalog = module.load_travelpayouts_airport_timezones()
        document = module.load_travelpayouts_airport_timezone_document()
        tz_map = module.build_timezone_map({"KUF": "Asia/Shanghai"})

        self.assertTrue(catalog_path.exists())
        self.assertLess(catalog_path.stat().st_size, 1_000_000)
        self.assertEqual(set(document), {"schema_version", "source", "source_files", "timezones"})
        self.assertNotIn("city_code", catalog_path.read_text(encoding="utf-8"))
        self.assertGreater(len(catalog), 1000)
        self.assertEqual(catalog["KUF"], "Europe/Samara")
        self.assertEqual(catalog["SVX"], "Asia/Yekaterinburg")
        self.assertEqual(tz_map["KUF"], "Asia/Shanghai")
        self.assertEqual(tz_map["SVX"], "Asia/Yekaterinburg")

        with tempfile.TemporaryDirectory() as td:
            sentinel_catalog = Path(td) / "airport_timezones.json"
            sentinel_catalog.write_text(
                json.dumps(
                    {
                        "schema_version": "travelpayouts-airport-timezones.v1",
                        "source": "test-sentinel-catalog",
                        "source_files": ["test-fixture"],
                        "timezones": {"KUF": "Asia/Tokyo", "SVX": "Pacific/Auckland"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            sentinel_tz_map = module.build_timezone_map({"KUF": "Europe/Samara"}, catalog_path=sentinel_catalog)

        self.assertEqual(sentinel_tz_map["SVX"], "Pacific/Auckland")
        self.assertEqual(sentinel_tz_map["KUF"], "Europe/Samara")
        self.assertNotIn("SVO", sentinel_tz_map)

    def test_aeroflot_parser_accepts_spa_fragment_deeplink(self) -> None:
        module = self.import_script_module("aeroflot_pnr_to_itinerary.py", "aeroflot_pnr_to_itinerary_test")
        key = "a" * 128
        url = f"https://www.aeroflot.ru/sb/pnr/app/ru-ru#/pnr?pnr_key={key}&pnr_locator=ABC123"

        locator, parsed_key, booking_url = module.parse_pnr_source(url, None, None)

        self.assertEqual(locator, "ABC123")
        self.assertEqual(parsed_key, key)
        self.assertEqual(booking_url, url)

    def test_aeroflot_name_search_generates_deeplink_without_browser_automation(self) -> None:
        module = self.import_script_module("aeroflot_pnr_to_itinerary.py", "aeroflot_pnr_to_itinerary_test")
        calls: list[dict] = []

        def fake_post(payload: dict, *, timeout: int = 45, referer: str | None = None) -> dict:
            calls.append({"payload": payload.copy(), "timeout": timeout, "referer": referer})
            return {"success": True, "data": {"pnr_locator": payload["pnr_locator"], "pnr_key": "b" * 128}}

        original_post = getattr(module, "post_aeroflot_pnr_json", None)
        setattr(module, "post_aeroflot_pnr_json", fake_post)
        try:
            locator, key, booking_url = module.fetch_aeroflot_pnr_key_by_name(
                "abc123",
                "Ivanov",
                first_name="",
                timeout=7,
            )
        finally:
            if original_post is None:
                delattr(module, "post_aeroflot_pnr_json")
            else:
                setattr(module, "post_aeroflot_pnr_json", original_post)

        self.assertEqual(locator, "ABC123")
        self.assertEqual(key, "b" * 128)
        self.assertEqual(
            booking_url,
            "https://www.aeroflot.ru/sb/pnr/app/ru-ru#/pnr?"
            + "pnr_key="
            + "b" * 128
            + "&pnr_locator=ABC123",
        )
        self.assertEqual(
            calls,
            [
                {
                    "payload": {
                        "pnr_locator": "ABC123",
                        "last_name": "Ivanov",
                        "first_name": "",
                        "lang": "ru",
                        "country": "ru",
                    },
                    "timeout": 7,
                    "referer": "https://www.aeroflot.ru/sb/pnr/app/ru-ru#/search",
                }
            ],
        )

    def test_aeroflot_name_search_retries_with_first_name_when_surname_is_ambiguous(self) -> None:
        module = self.import_script_module("aeroflot_pnr_to_itinerary.py", "aeroflot_pnr_to_itinerary_test")
        calls: list[dict] = []

        def fake_post(payload: dict, *, timeout: int = 45, referer: str | None = None) -> dict:
            calls.append(payload.copy())
            if len(calls) == 1:
                return {"success": False, "error": {"type": "PassengerAmbiguous"}}
            return {"success": True, "data": {"pnr_locator": payload["pnr_locator"], "pnr_key": "c" * 128}}

        original_post = getattr(module, "post_aeroflot_pnr_json", None)
        setattr(module, "post_aeroflot_pnr_json", fake_post)
        try:
            locator, key, booking_url = module.fetch_aeroflot_pnr_key_by_name(
                "ABC123",
                "Ivanov",
                first_name="Ivan",
            )
        finally:
            if original_post is None:
                delattr(module, "post_aeroflot_pnr_json")
            else:
                setattr(module, "post_aeroflot_pnr_json", original_post)

        self.assertEqual(locator, "ABC123")
        self.assertEqual(key, "c" * 128)
        self.assertIn("#/pnr?", booking_url)
        self.assertEqual(calls[0]["first_name"], "")
        self.assertEqual(calls[1]["first_name"], "Ivan")

    def test_aeroflot_cli_accepts_locator_and_surname_without_existing_pnr_key(self) -> None:
        module = self.import_cli_module()
        parser = module.build_parser()

        args = parser.parse_args(
            [
                "aeroflot",
                "--pnr-locator",
                "ABC123",
                "--last-name",
                "Ivanov",
                "--output-json",
                "/tmp/aeroflot.json",
            ]
        )

        self.assertEqual(args.pnr_locator, "ABC123")
        self.assertEqual(args.last_name, "Ivanov")
        self.assertIsNone(args.pnr_key)

    def test_aeroflot_command_uses_timezone_catalog_for_saved_itinerary(self) -> None:
        module = self.import_cli_module()
        fake_response = {
            "pnr_locator": "ABC123",
            "passengers": [{"first_name": "Ivan", "last_name": "Ivanov"}],
            "legs": [
                {
                    "segments": [
                        {
                            "origin": {"airport_code": "KUF", "city_name": "Самара"},
                            "destination": {"airport_code": "SVX", "city_name": "Екатеринбург"},
                            "departure": "2026-06-01 09:15:00",
                            "arrival": "2026-06-01 10:45:00",
                            "airline_code": "SU",
                            "airline_name": "Аэрофлот",
                            "flight_number": "1234",
                            "status_code": "HK",
                        }
                    ]
                }
            ],
        }
        original_fetch = module.aeroflot.fetch_aeroflot_pnr
        original_catalog = module.airport_catalog.load_airport_timezones
        module.aeroflot.fetch_aeroflot_pnr = lambda _locator, _key: fake_response
        module.airport_catalog.load_airport_timezones = lambda catalog_path=None: {"KUF": "Asia/Tokyo", "SVX": "Asia/Tokyo"}
        try:
            with tempfile.TemporaryDirectory() as td:
                output_json = Path(td) / "aeroflot.json"
                output_ics = Path(td) / "aeroflot.ics"
                args = argparse.Namespace(
                    url=None,
                    pnr_locator="ABC123",
                    pnr_key="a" * 64,
                    last_name=None,
                    first_name=None,
                    output_json=output_json,
                    output_ics=output_ics,
                    tz=[],
                    no_alarms=True,
                )
                process: list[dict] = []

                rc, data = module.command_aeroflot(args, process)

                self.assertEqual(rc, 0)
                saved_itinerary = json.loads(output_json.read_text(encoding="utf-8"))
                self.assertEqual(saved_itinerary["flights"][0]["departure"]["tz"], "Asia/Tokyo")
                self.assertEqual(saved_itinerary["flights"][0]["arrival"]["tz"], "Asia/Tokyo")
                timezone_step = next(step for step in process if step["step"] == "load_timezone_map")
                self.assertEqual(timezone_step["defaults_count"], 0)
                self.assertEqual(timezone_step["catalog_timezones_count"], 2)
                self.assertEqual(data["segments"][0]["route"], "KUF->SVX")
                ics_text = output_ics.read_text(encoding="utf-8")
                self.assertIn("DTSTART:20260601T001500Z", ics_text)
                self.assertIn("DTEND:20260601T014500Z", ics_text)
        finally:
            module.aeroflot.fetch_aeroflot_pnr = original_fetch
            module.airport_catalog.load_airport_timezones = original_catalog

    def test_direct_aeroflot_helper_writes_private_artifacts_without_network(self) -> None:
        module = self.import_script_module("aeroflot_pnr_to_itinerary.py", "aeroflot_pnr_to_itinerary_test")

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
                            "origin": {"airport_code": "KUF", "city_name": "Самара", "terminal_code": "1"},
                            "destination": {"airport_code": "SVX", "city_name": "Екатеринбург", "terminal_code": "1"},
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
        original_catalog = module.airport_catalog.load_airport_timezones
        module.fetch_aeroflot_pnr = lambda _locator, _key: fake_response
        module.airport_catalog.load_airport_timezones = lambda catalog_path=None: {"KUF": "Asia/Tokyo", "SVX": "Asia/Tokyo"}
        with tempfile.TemporaryDirectory() as td:
            output_json = Path(td) / "aeroflot.json"
            output_ics = Path(td) / "aeroflot.ics"
            old_umask = os.umask(0o022)
            try:
                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
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
                module.airport_catalog.load_airport_timezones = original_catalog

            self.assertEqual(rc, 0)
            combined_output = stdout.getvalue() + stderr.getvalue()
            for private_value in ["ABC123", "Ivan", "Ivanov", "5552400000000"]:
                self.assertNotIn(private_value, combined_output)
            self.assertEqual(stat.S_IMODE(output_json.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(output_ics.stat().st_mode), 0o600)
            saved_itinerary = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(saved_itinerary["schema_version"], "flight-calendar-ics-itinerary.v1")
            self.assertEqual(saved_itinerary["passengers"], ["Ivanov Ivan"])
            self.assertEqual(saved_itinerary["flights"][0]["departure"]["tz"], "Asia/Tokyo")
            self.assertEqual(saved_itinerary["flights"][0]["arrival"]["tz"], "Asia/Tokyo")

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
        original_catalog = module.airport_catalog.load_airport_timezones
        module.redwings.fetch_redwings_order = fake_fetch
        module.airport_catalog.load_airport_timezones = lambda catalog_path=None: {"KUF": "Asia/Tokyo", "SVX": "Asia/Tokyo"}
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
                self.assertEqual(saved_itinerary["flights"][0]["departure"]["tz"], "Asia/Tokyo")
                self.assertEqual(saved_itinerary["flights"][0]["arrival"]["tz"], "Asia/Tokyo")
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
                self.assertIn("DTSTART:20260602T232500Z", ics_text)
                self.assertIn("DTEND:20260603T015500Z", ics_text)
                unfolded_ics = ics_text.replace("\r\n ", "").replace("\n ", "")
                self.assertIn("AB12CD", unfolded_ics)
                self.assertIn("DOE JANE", unfolded_ics)
                self.assertIn("921 8844512345", unfolded_ics)
                self.assertIn("Самолет: Sukhoi Superjet", unfolded_ics)
                self.assertNotIn("Багаж 10 кг", unfolded_ics)
        finally:
            module.redwings.fetch_redwings_order = original_fetch
            module.airport_catalog.load_airport_timezones = original_catalog

    def test_ural_url_parser_decodes_tracking_redirect_without_local_env(self) -> None:
        module = self.import_script_module("ural_airlines_to_itinerary.py", "ural_airlines_to_itinerary_test")

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
        original_catalog = module.airport_catalog.load_airport_timezones
        module.ural.fetch_ural_reservation = fake_fetch
        module.airport_catalog.load_airport_timezones = lambda catalog_path=None: {"SVX": "Asia/Tokyo", "DME": "Asia/Tokyo"}
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
                self.assertEqual(saved_itinerary["passengers"], ["DOE JANE"])
                self.assertEqual(saved_itinerary["flights"][0]["departure"]["tz"], "Asia/Tokyo")
                self.assertEqual(saved_itinerary["flights"][0]["arrival"]["tz"], "Asia/Tokyo")
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
            module.airport_catalog.load_airport_timezones = original_catalog

    def test_utair_url_parser_handles_cyrillic_surname(self) -> None:
        module = self.import_script_module("utair_to_itinerary.py", "utair_to_itinerary_test")

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

        original_fetch_token = module.utair.fetch_utair_token
        original_fetch_orders = module.utair.fetch_utair_orders
        original_catalog = module.airport_catalog.load_airport_timezones
        module.utair.fetch_utair_token = lambda: "fake-token"
        module.utair.fetch_utair_orders = fake_fetch
        module.airport_catalog.load_airport_timezones = lambda catalog_path=None: {"SVX": "Asia/Tokyo", "KUF": "Asia/Tokyo"}
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
                self.assertEqual(calls[0]["token"], "fake-token")
                self.assertTrue(output_json.exists())
                self.assertTrue(output_ics.exists())
                self.assertEqual(stat.S_IMODE(output_json.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(output_ics.stat().st_mode), 0o600)
                saved_itinerary = json.loads(output_json.read_text(encoding="utf-8"))
                self.assertEqual(saved_itinerary["schema_version"], "flight-calendar-ics-itinerary.v1")
                self.assertEqual(saved_itinerary["passengers"], ["DOE JANE"])
                self.assertEqual(saved_itinerary["flights"][0]["departure"]["tz"], "Asia/Tokyo")
                self.assertEqual(saved_itinerary["flights"][0]["arrival"]["tz"], "Asia/Tokyo")
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
                for private_value in ["ZZ9ZZZ", "DOE", "JANE", "2980000000000", "fake-token"]:
                    self.assertNotIn(private_value, safe_output)
                ics_text = output_ics.read_text(encoding="utf-8")
                self.assertIn("BEGIN:VCALENDAR", ics_text)
                self.assertEqual(ics_text.count("BEGIN:VEVENT"), 1)
                self.assertIn("DTSTART:20260610T025000Z", ics_text)
                self.assertIn("DTEND:20260610T033000Z", ics_text)
                unfolded_ics = ics_text.replace("\r\n ", "").replace("\n ", "")
                self.assertIn("ZZ9ZZZ", unfolded_ics)
                self.assertIn("DOE JANE", unfolded_ics)
                self.assertIn("298 0000000000", unfolded_ics)
        finally:
            module.utair.fetch_utair_token = original_fetch_token
            module.utair.fetch_utair_orders = original_fetch_orders
            module.airport_catalog.load_airport_timezones = original_catalog

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
            "Authorization: Bearer secret-token ticket=2980000000000"
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
