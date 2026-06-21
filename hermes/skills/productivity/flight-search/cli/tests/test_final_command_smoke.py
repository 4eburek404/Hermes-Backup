from __future__ import annotations

import argparse
import contextlib
import io
import re
import unittest

from flights_cli.cli import build_parser

from helpers import PROJECT


DOCS_COMMANDS = {
    "search --request": ["--json", "search", "--request", "/tmp/flight-search-request.json"],
    "diagnose plan --request": ["--json", "diagnose", "plan", "--request", "/tmp/flight-search-request.json"],
    "maint doctor": ["--json", "maint", "doctor"],
    "maint check": ["--json", "maint", "check"],
    "cities search": ["--json", "cities", "search", "Yekaterinburg"],
    "airports explain": ["--json", "airports", "explain", "SVX", "MOW"],
}

DEV_DIAGNOSTIC_COMMANDS = {
    "route assemble": ["--json", "route", "assemble", "--input", "segment-results.json"],
    "route rank": ["--json", "route", "rank", "--input", "candidates.json"],
    "route validate": ["--json", "route", "validate", "--input", "itinerary.json"],
}

REMOVED_COMMANDS = {
    "route plan": ["--json", "route", "plan", "SVX", "LON", "--depart-date", "2026-07-20"],
    "route live-assemble": ["--json", "route", "live-assemble", "SVX", "LON", "--depart-date", "2026-07-20"],
    "kb-search": ["--json", "kb-search", "SVX", "MOW", "--depart-date", "2026-07-19"],
    "kb-roundtrip": ["--json", "kb-roundtrip", "SVX", "BJS", "--depart-date", "2026-08-01", "--return-date", "2026-08-08"],
    "fli-search": ["--json", "fli-search", "IST", "LHR", "--depart-date", "2026-07-20"],
    "fli-dates": ["--json", "fli-dates", "IST", "LHR", "--from-date", "2026-07-20", "--to-date", "2026-07-22"],
}


def docs_text() -> str:
    paths = [
        PROJECT.parent / "SKILL.md",
        PROJECT / "README.md",
        *(PROJECT.parent / "references").glob("*.md"),
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


class FinalCommandSmokeTests(unittest.TestCase):
    def parse(self, argv: list[str]) -> argparse.Namespace:
        return build_parser().parse_args(argv)

    def test_docs_command_examples_parse(self) -> None:
        for label, argv in DOCS_COMMANDS.items():
            with self.subTest(label=label):
                parsed = self.parse(argv)
                self.assertEqual(parsed.command_name, label.split(" --request", 1)[0])
                self.assertTrue(callable(parsed.func))

    def test_diagnostic_dev_commands_parse(self) -> None:
        for label, argv in DEV_DIAGNOSTIC_COMMANDS.items():
            with self.subTest(label=label):
                parsed = self.parse(argv)
                self.assertEqual(parsed.command_name, label)
                self.assertTrue(callable(parsed.func))

    def test_removed_commands_fail_parser(self) -> None:
        parser = build_parser()
        for label, argv in REMOVED_COMMANDS.items():
            with self.subTest(label=label), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parser.parse_args(argv)

    def test_active_docs_do_not_reference_removed_command_forms(self) -> None:
        text = docs_text()
        forbidden_patterns = {
            "route plan": r"\broute\s+plan\b",
            "route live-assemble": r"\broute\s+live-assemble\b",
            "route kb-assemble": r"\broute\s+kb-assemble\b",
            "top-level kb-search": r"(?<!diagnose\s)\bkb-search\b",
            "top-level kb-roundtrip": r"(?<!diagnose\s)\bkb-roundtrip\b",
            "top-level fli-search": r"(?<!diagnose\s)\bfli-search\b",
            "top-level fli-dates": r"(?<!diagnose\s)\bfli-dates\b",
        }
        for label, pattern in forbidden_patterns.items():
            with self.subTest(label=label):
                self.assertIsNone(re.search(pattern, text))

    def test_search_request_remains_single_golden_path(self) -> None:
        text = docs_text()
        self.assertIn("python3 -m flights_cli --json search --request", text)
        self.assertIn("python3 -m flights_cli --json diagnose plan --request", text)
        self.assertIn("route assemble", text)
        self.assertIn("route rank", text)
        self.assertIn("route validate", text)


if __name__ == "__main__":
    unittest.main()
