from __future__ import annotations

import contextlib
import io
import re
import unittest

from helpers import PROJECT


def _dash(*parts: str) -> str:
    return "-".join(parts)


def _command_label(*parts: str) -> str:
    return " ".join(parts)


def _snake(*parts: str) -> str:
    return "_".join(parts)


REMOVED_COMMANDS = {
    _command_label("route", "plan"): [
        "--json",
        "route",
        "plan",
        "SVX",
        "LON",
        "--depart-date",
        "2026-07-20",
    ],
    _command_label("route", _dash("live", "assemble")): [
        "--json",
        "route",
        _dash("live", "assemble"),
        "SVX",
        "LON",
        "--depart-date",
        "2026-07-20",
    ],
    "kb-search": ["--json", "kb-search", "SVX", "MOW", "--depart-date", "2026-07-19"],
    "kb-roundtrip": [
        "--json",
        "kb-roundtrip",
        "SVX",
        "BJS",
        "--depart-date",
        "2026-08-01",
        "--return-date",
        "2026-08-08",
    ],
    "fli-search": ["--json", "fli-search", "IST", "LHR", "--depart-date", "2026-07-20"],
    "fli-dates": [
        "--json",
        "fli-dates",
        "IST",
        "LHR",
        "--from-date",
        "2026-07-20",
        "--to-date",
        "2026-07-22",
    ],
}


def docs_text() -> str:
    paths = [
        PROJECT.parent / "SKILL.md",
        PROJECT / "README.md",
        *(PROJECT.parent / "references").glob("*.md"),
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


class FinalCommandSmokeTests(unittest.TestCase):
    def test_removed_commands_fail_parser(self) -> None:
        from flights_cli.cli import build_parser

        parser = build_parser()
        for label, argv in REMOVED_COMMANDS.items():
            with (
                self.subTest(label=label),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                parser.parse_args(argv)

    def test_active_docs_do_not_reference_removed_command_forms(self) -> None:
        text = docs_text()
        forbidden_patterns = {
            _command_label("route", "plan"): r"\b" + "route" + r"\s+" + "plan" + r"\b",
            _command_label("route", _dash("live", "assemble")): r"\b"
            + "route"
            + r"\s+"
            + _dash("live", "assemble")
            + r"\b",
            _command_label("route", _dash("kb", "assemble")): r"\b"
            + "route"
            + r"\s+"
            + _dash("kb", "assemble")
            + r"\b",
            "top-level kb-search": r"(?<!diagnose\s)\bkb-search\b",
            "top-level kb-roundtrip": r"(?<!diagnose\s)\bkb-roundtrip\b",
            "top-level fli-search": r"(?<!diagnose\s)\bfli-search\b",
            "top-level fli-dates": r"(?<!diagnose\s)\bfli-dates\b",
        }
        for label, pattern in forbidden_patterns.items():
            with self.subTest(label=label):
                self.assertIsNone(re.search(pattern, text))

    def test_source_tree_has_no_stale_legacy_command_references(self) -> None:
        forbidden = [
            _command_label("route", _dash("live", "assemble")),
            _command_label("route", _dash("kb", "assemble")),
            _command_label("route", "plan"),
            _snake("command", "route", "live", "assemble"),
            _snake("command", "route", "plan"),
            _snake("build", "route", "plan"),
            _snake("live", "segment", "command"),
            _command_label("flights", "--json", _dash("kb", "search")),
            _command_label("flights", "--json", _dash("fli", "search")),
        ]
        matches: list[str] = []
        for path in PROJECT.parent.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in forbidden:
                if needle in text:
                    matches.append(f"{path.relative_to(PROJECT.parent)}: {needle}")
        self.assertEqual(matches, [])

    def test_search_request_remains_single_canonical_path(self) -> None:
        text = docs_text()
        self.assertIn("python3 -m flights_cli --json search --request", text)
        self.assertIn("python3 -m flights_cli --json diagnose plan --request", text)
        self.assertNotIn("route assemble", text)
        self.assertIn("route rank", text)
        self.assertIn("route validate", text)


if __name__ == "__main__":
    unittest.main()
