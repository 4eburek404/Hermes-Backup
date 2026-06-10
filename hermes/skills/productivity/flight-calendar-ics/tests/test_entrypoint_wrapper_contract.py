#!/usr/bin/env python3
"""Thin public entrypoint contracts for flight-calendar-ics."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CLI = SCRIPTS / "flight_calendar_ics.py"


class EntrypointWrapperContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_path = list(sys.path)
        script_dir = str(SCRIPTS.resolve())
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)

    def tearDown(self) -> None:
        sys.path[:] = self._old_path

    def import_cli_module(self):
        spec = importlib.util.spec_from_file_location("flight_calendar_ics_wrapper_contract", CLI)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_public_entrypoint_delegates_main_to_parser_package(self) -> None:
        wrapper = self.import_cli_module()
        from flight_calendar import parser as parser_module

        self.assertIs(wrapper.main, parser_module.main)
        self.assertIs(wrapper.build_parser, parser_module.build_parser)
        self.assertEqual(parser_module.PUBLIC_ENTRYPOINT.name, "flight_calendar_ics.py")

    def test_wrapper_file_is_small_entrypoint_contract(self) -> None:
        wrapper_lines = CLI.read_text(encoding="utf-8").splitlines()

        self.assertLessEqual(len(wrapper_lines), 80)

    def test_parser_surfaces_cover_contract_registry_commands(self) -> None:
        from flight_calendar.contracts import build_command_registry
        from flight_calendar.parser import build_parser

        parser = build_parser()
        samples = {
            "production": ["--json build auto --input templates/aeroflot-itinerary.example.json"],
            "diagnostic": [
                "--json diagnose doctor",
                "--json diagnose validate --input templates/aeroflot-itinerary.example.json",
                "--json diagnose route-detect --input templates/aeroflot-itinerary.example.json",
                "--json diagnose timezone inspect",
            ],
            "maintenance": [
                "--json maint doctor",
                "--json maint contracts",
                "--json maint source-runtime diff",
                "--json maint source-runtime-sync",
                "--json maint refs registry-check",
                "--json maint clean --dry-run",
                "--json maint audit",
                "--json maint timezone-catalog inspect",
            ],
        }
        registry = build_command_registry()

        for surface, commands in samples.items():
            self.assertTrue(registry[surface], f"registry surface {surface} should not be empty")
            for command in commands:
                with self.subTest(surface=surface, command=command):
                    args = parser.parse_args(command.split())
                    self.assertIsNotNone(args.command)


if __name__ == "__main__":
    unittest.main(verbosity=2)
