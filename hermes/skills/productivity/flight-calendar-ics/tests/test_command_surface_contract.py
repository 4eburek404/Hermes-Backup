#!/usr/bin/env python3
"""Command surface contract tests for flight-calendar-ics.

These tests lock the single command truth table: the production happy path is
``build auto``; diagnostics and maintenance live under their namespaces; legacy
root commands are removed and must be rejected by the CLI.
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CLI = SCRIPTS / "flight_calendar_ics.py"
SCHEMA = ROOT / "schemas" / "cli-envelope.v1.schema.json"
REMOVED_ROOT_COMMANDS = {"validate", "make", "aeroflot", "ural", "utair", "redwings"}


class CommandSurfaceContractTests(unittest.TestCase):
    maxDiff = None

    def import_contracts(self):
        old_path = list(sys.path)
        script_dir = str(SCRIPTS.resolve())
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        try:
            return importlib.import_module("flight_calendar.contracts")
        finally:
            sys.path[:] = old_path

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

    def test_contract_registry_lists_current_wire_contracts(self) -> None:
        contracts = self.import_contracts()

        self.assertEqual(contracts.SCHEMA_VERSION, "flight-calendar-ics-cli.v1")
        self.assertEqual(contracts.BUNDLE_ROUTES, ["make", "aeroflot", "ural", "utair", "redwings"])
        self.assertEqual(contracts.BUILD_ROUTE_CHOICES, ["auto", "make", "aeroflot", "ural", "utair", "redwings"])
        self.assertEqual(contracts.COMMANDS, ["doctor", "build", "diagnose", "maint"])
        self.assertEqual(contracts.CONTRACT_REGISTRY["schema_version"], contracts.SCHEMA_VERSION)
        self.assertEqual(contracts.CONTRACT_REGISTRY["wire_commands"], contracts.COMMANDS)
        self.assertEqual(
            contracts.CONTRACT_REGISTRY["cli_envelope"],
            {
                "schema_version": "flight-calendar-ics-cli.v1",
                "schema_path": "schemas/cli-envelope.v1.schema.json",
            },
        )
        self.assertEqual(contracts.CONTRACT_REGISTRY["command_registry"], contracts.COMMAND_SURFACES)
        agent_contract = contracts.build_agent_contract()
        self.assertEqual([step["id"] for step in agent_contract["normal_steps"]], ["collect_source", "run_one_command", "verify", "deliver"])
        self.assertEqual({item["command"] for item in agent_contract["dispatch_matrix"]}, {"build"})
        self.assertEqual({item["route"] for item in agent_contract["dispatch_matrix"]}, {"auto", "make", "aeroflot", "ural", "utair", "redwings"})
        self.assertEqual(agent_contract["failure_path"]["route_switch_rule"], "do_not_switch_route_without_new_evidence")
        self.assertEqual(agent_contract["failure_path"]["diagnostics_trigger"], "build_auto_failed_or_user_requested_diagnostics")
        self.assertIn("diagnose route-detect", agent_contract["diagnostics"]["commands"])
        self.assertIn("maint refs registry-check", agent_contract["maintenance"]["commands"])
        self.assertIn("data.agent_handoff.ready=true", agent_contract["verification"]["envelope"])
        self.assertIn("data.agent_handoff.artifact_inspection_required=false", agent_contract["verification"]["envelope"])
        self.assertIn("data.agent_handoff.safe_summary.vevent_count", agent_contract["verification"]["reporting_fields"])
        self.assertIn("no_generated_ics_dump", agent_contract["privacy"]["chat_summary_must_omit"])

    def test_command_surfaces_classify_build_auto_as_production(self) -> None:
        contracts = self.import_contracts()
        surfaces = contracts.COMMAND_SURFACES

        self.assertEqual(set(surfaces), {"production", "diagnostic", "maintenance"})
        self.assertIn("build auto", surfaces["production"])
        self.assertNotIn("doctor", surfaces["production"])
        self.assertNotIn("validate", surfaces["production"])
        self.assertNotIn("make", surfaces["production"])

    def test_legacy_root_commands_are_removed_and_rejected(self) -> None:
        contracts = self.import_contracts()
        all_surface_commands = {cmd for cmds in contracts.COMMAND_SURFACES.values() for cmd in cmds}

        self.assertTrue(REMOVED_ROOT_COMMANDS.isdisjoint(all_surface_commands))
        self.assertTrue(REMOVED_ROOT_COMMANDS.isdisjoint(set(contracts.COMMANDS)))
        for legacy in sorted(REMOVED_ROOT_COMMANDS):
            with self.subTest(command=legacy):
                result = self.run_cli("--json", legacy)
                self.assertNotEqual(result.returncode, 0, f"root '{legacy}' must be rejected")

    def test_cli_envelope_schema_accepts_diagnose_and_maint_namespaces(self) -> None:
        command_registry = {
            "production": ["build auto"],
            "diagnostic": ["diagnose doctor"],
            "maintenance": ["maint contracts"],
        }
        for command, surface in [("diagnose", "diagnostic"), ("maint", "maintenance")]:
            envelope = {
                "schema_version": "flight-calendar-ics-cli.v1",
                "ok": True,
                "command": command,
                "process": [{"step": "parse_args", "status": "ok"}],
                "data": {
                    "commands": [command],
                    "surface": surface,
                    "subcommand": "contracts",
                    "command_registry": command_registry,
                },
            }
            with self.subTest(command=command):
                self.assert_matches_cli_schema(envelope)

    def test_cli_envelope_schema_accepts_code_owned_agent_handoff_for_build(self) -> None:
        envelope = {
            "schema_version": "flight-calendar-ics-cli.v1",
            "ok": True,
            "command": "build",
            "process": [{"step": "parse_args", "status": "ok"}],
            "data": {
                "segments_count": 1,
                "route": "make",
                "output_dir": "/tmp/flight-ics.synthetic",
                "json_path": "/tmp/flight-ics.synthetic/itinerary.json",
                "ics_path": "/tmp/flight-ics.synthetic/flights.ics",
                "envelope_path": "/tmp/flight-ics.synthetic/envelope.json",
                "write_performed": True,
                "verification": {
                    "ok": True,
                    "event_count": 1,
                    "utc_datetime_count": 2,
                    "placeholder_free": True,
                    "private_modes": {"json": "600", "ics": "600"},
                },
                "agent_handoff": {
                    "ready": True,
                    "media": "MEDIA:/tmp/flight-ics.synthetic/flights.ics",
                    "artifact_inspection_required": False,
                    "verification_source": "flight_calendar.bundle.verify_bundle_artifacts",
                    "safe_summary": {
                        "route": "make",
                        "route_detection_mode": "auto",
                        "segments_count": 1,
                        "verification_ok": True,
                        "vevent_count": 1,
                        "ics_mode": "0600",
                    },
                },
            },
        }

        self.assert_matches_cli_schema(envelope)

    def test_doctor_reports_classified_surfaces_without_requiring_doctor_for_happy_path(self) -> None:
        result = self.run_cli("--json", "doctor")

        self.assertEqual(result.returncode, 0, result.stderr)
        obj = self.parse_stdout_json(result)
        self.assert_matches_cli_schema(obj)
        self.assertEqual(obj["schema_version"], "flight-calendar-ics-cli.v1")
        self.assertTrue(obj["ok"])
        self.assertEqual(obj["command"], "doctor")
        self.assertEqual(obj["data"]["schema_version"], "flight-calendar-ics-cli.v1")

        registry = obj["data"].get("command_registry")
        self.assertIsInstance(registry, dict)
        self.assertEqual(set(registry), {"production", "diagnostic", "maintenance"})
        self.assertIn("build auto", registry["production"])
        self.assertTrue(REMOVED_ROOT_COMMANDS.isdisjoint(set(registry["production"])))

        contract = obj["data"].get("agent_contract")
        self.assertIsInstance(contract, dict)
        self.assertEqual([step["id"] for step in contract["normal_steps"]], ["collect_source", "run_one_command", "verify", "deliver"])
        self.assertEqual({item["command"] for item in contract["dispatch_matrix"]}, {"build"})
        self.assertIn("auto", {item["route"] for item in contract["dispatch_matrix"]})
        self.assertEqual(contract["failure_path"]["diagnostics_trigger"], "build_auto_failed_or_user_requested_diagnostics")
        self.assertIn("read_json_error_code", contract["failure_path"]["steps"])
        self.assertEqual(contract["maintenance"]["runtime_sync_requires_approval"], True)
        serialized_happy_path = json.dumps(
            {
                "normal_steps": contract["normal_steps"],
                "dispatch_matrix": contract["dispatch_matrix"],
            },
            ensure_ascii=False,
        )
        self.assertNotIn("doctor", serialized_happy_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
