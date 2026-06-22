#!/usr/bin/env python3
"""Focused argparse contract tests for flight-calendar-ics."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import unittest
from pathlib import Path

from helpers import ScriptPathMixin


def assert_namespace_subset(
    testcase: unittest.TestCase,
    args: argparse.Namespace,
    expected: dict[str, object],
) -> None:
    actual = vars(args)
    testcase.assertNotIn("func", actual)
    for key, value in expected.items():
        testcase.assertEqual(value, actual.get(key), key)


class ParserContractTests(ScriptPathMixin, unittest.TestCase):
    def parse_args(self, *argv: str) -> argparse.Namespace:
        from flight_calendar.parser import build_parser

        return build_parser().parse_args(list(argv))

    def help_text(self, *argv: str) -> str:
        from flight_calendar.parser import build_parser

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as caught:
                build_parser().parse_args([*argv, "--help"])
        self.assertEqual(0, caught.exception.code)
        return stdout.getvalue()

    def run_main(self, *argv: str) -> tuple[int, dict[str, object]]:
        from flight_calendar import parser as parser_module

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = parser_module.main(list(argv))
        self.assertEqual("", stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertIsInstance(payload, dict)
        return exit_code, payload

    def test_namespace_shapes_preserve_dispatch_contract(self) -> None:
        cases = [
            (
                ("--json", "build", "auto", "--input", "input.json"),
                {
                    "json": True,
                    "full_envelope": False,
                    "command": "build",
                    "route": "auto",
                    "input": Path("input.json"),
                    "tz": [],
                },
            ),
            (
                ("build", "redwings", "--access-key", "SECRET"),
                {
                    "command": "build",
                    "route": "redwings",
                    "access_code": "SECRET",
                },
            ),
            (
                ("diagnose", "timezone", "inspect"),
                {
                    "command": "diagnose",
                    "subcommand": "timezone",
                    "action": "inspect",
                },
            ),
            (
                ("maint", "source-runtime", "diff"),
                {
                    "command": "maint",
                    "subcommand": "source-runtime",
                    "action": "diff",
                },
            ),
            (
                ("maint", "refs", "registry-check"),
                {
                    "command": "maint",
                    "subcommand": "refs",
                    "action": "registry-check",
                },
            ),
            (
                ("maint", "timezone-catalog", "inspect"),
                {
                    "command": "maint",
                    "subcommand": "timezone-catalog",
                    "action": "inspect",
                },
            ),
        ]

        for argv, expected in cases:
            with self.subTest(argv=argv):
                args = self.parse_args(*argv)
                assert_namespace_subset(self, args, expected)

        redwings = self.parse_args("build", "redwings", "--access-key", "SECRET")
        self.assertFalse(hasattr(redwings, "access_key"))

    def test_build_help_keeps_route_and_build_source_surface(self) -> None:
        text = self.help_text("build")

        for needle in (
            "auto",
            "make",
            "aeroflot",
            "ural",
            "utair",
            "redwings",
            "--access-key",
            "--pnr-key",
            "if not using --url/--url-file",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_diagnose_route_detect_help_keeps_diagnostic_source_surface(self) -> None:
        text = self.help_text("diagnose", "route-detect")

        for needle in ("--url", "--url-file", "--pnr-key"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        self.assertNotIn("if not using --url/--url-file", text)

    def test_maint_help_keeps_namespace_surface(self) -> None:
        text = self.help_text("maint")

        for needle in (
            "contracts",
            "doctor",
            "source-runtime-sync",
            "source-runtime",
            "refs",
            "clean",
            "audit",
            "timezone-catalog",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_missing_nested_commands_still_emit_usage_error_envelope(self) -> None:
        cases = [
            (("--json",), "unknown"),
            (("--json", "diagnose"), "diagnose"),
            (("--json", "maint"), "maint"),
            (("--json", "maint", "source-runtime"), "maint"),
            (("--json", "maint", "refs"), "maint"),
            (("--json", "maint", "timezone-catalog"), "maint"),
            (("--json", "diagnose", "timezone"), "diagnose"),
        ]

        for argv, command in cases:
            with self.subTest(argv=argv):
                exit_code, payload = self.run_main(*argv)
                self.assertEqual(2, exit_code)
                self.assertEqual(False, payload["ok"])
                self.assertEqual(command, payload["command"])
                self.assertEqual("usage_error", payload["error"]["code"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
