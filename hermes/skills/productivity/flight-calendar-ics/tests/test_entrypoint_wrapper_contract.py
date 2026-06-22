#!/usr/bin/env python3
"""Thin public entrypoint contracts for flight-calendar-ics."""
from __future__ import annotations

import importlib.util
import unittest

from helpers import CLI, ScriptPathMixin

COMMAND_SURFACE_ARGV = {
    "build auto": "--json build auto --input templates/aeroflot-itinerary.example.json",
    "diagnose doctor": "--json diagnose doctor",
    "diagnose validate": "--json diagnose validate --input templates/aeroflot-itinerary.example.json",
    "diagnose route-detect": "--json diagnose route-detect --input templates/aeroflot-itinerary.example.json",
    "diagnose bundle-check": "--json diagnose bundle-check --bundle-dir .",
    "diagnose privacy-check": "--json diagnose privacy-check --bundle-dir .",
    "diagnose carrier-probe": "--json diagnose carrier-probe aeroflot --url https://example.invalid/booking",
    "diagnose timezone inspect": "--json diagnose timezone inspect",
    "build make": "--json build make --input templates/aeroflot-itinerary.example.json",
    "build aeroflot": "--json build aeroflot --pnr-locator ABC123 --last-name TEST",
    "build ural": "--json build ural --pnr ABC123 --last-name TEST",
    "build utair": "--json build utair --rloc ABC123 --last-name TEST",
    "build redwings": "--json build redwings --access-key SECRET",
    "maint doctor": "--json maint doctor",
    "maint contracts": "--json maint contracts",
    "maint source-runtime diff": "--json maint source-runtime diff",
    "maint source-runtime-sync": "--json maint source-runtime-sync",
    "maint refs registry-check": "--json maint refs registry-check",
    "maint clean --dry-run": "--json maint clean --dry-run",
    "maint audit": "--json maint audit",
    "maint timezone-catalog inspect": "--json maint timezone-catalog inspect",
}

ACTION_COMMANDS = {
    "diagnose timezone inspect",
    "maint source-runtime diff",
    "maint refs registry-check",
    "maint timezone-catalog inspect",
}


class EntrypointWrapperContractTests(ScriptPathMixin, unittest.TestCase):
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
        from flight_calendar.contracts import COMMAND_SURFACES, build_command_registry
        from flight_calendar.parser import build_parser

        parser = build_parser()
        registry = build_command_registry()

        for surface, commands in COMMAND_SURFACES.items():
            self.assertTrue(registry[surface], f"registry surface {surface} should not be empty")
            for command in commands:
                with self.subTest(surface=surface, command=command):
                    args = parser.parse_args(COMMAND_SURFACE_ARGV[command].split())
                    namespace = vars(args)
                    self.assertNotIn("func", namespace)
                    self.assertIsNotNone(args.command)
                    if args.command == "build":
                        self.assertIn("route", namespace)
                    if args.command in {"diagnose", "maint"}:
                        self.assertIn("subcommand", namespace)
                    if command in ACTION_COMMANDS:
                        self.assertIn("action", namespace)


if __name__ == "__main__":
    unittest.main(verbosity=2)
