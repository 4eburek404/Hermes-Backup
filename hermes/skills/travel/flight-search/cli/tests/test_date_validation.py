from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from flights_cli.domain.normalize import numeric_or_none, parse_iso_date
from flights_cli.errors import CliError
from helpers import PROJECT, TEST_ENV


class DateValidationTests(unittest.TestCase):
    def test_parse_iso_date_rejects_past_dates_with_future_occurrence_hint(
        self,
    ) -> None:
        with self.assertRaises(CliError) as ctx:
            parse_iso_date("2025-09-17", "depart-date", today=date(2026, 5, 10))

        self.assertEqual(ctx.exception.error_type, "validation_error")
        self.assertEqual(
            ctx.exception.details,
            {
                "field": "depart-date",
                "reason": "past_date",
                "value": "2025-09-17",
                "today": "2026-05-10",
                "suggested_date": "2026-09-17",
            },
        )

    def test_parse_iso_date_allows_today_and_future_dates(self) -> None:
        today = date(2026, 5, 10)

        self.assertEqual(
            parse_iso_date("2026-05-10", "depart-date", today=today), today
        )
        self.assertEqual(
            parse_iso_date("2026-09-17", "depart-date", today=today), date(2026, 9, 17)
        )

    def test_json_cli_returns_validation_error_for_past_departure_date(self) -> None:
        request = {
            "schema_version": "flight_search_request.v3",
            "origin": "SVX",
            "destination": "LON",
            "depart_date": "2000-09-17",
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            request_path = Path(tmp_dir) / "flight-search-request.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "flights_cli",
                    "--json",
                    "diagnose",
                    "plan",
                    "--request",
                    str(request_path),
                ],
                cwd=PROJECT,
                env=TEST_ENV,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, "")
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["type"], "validation_error")
        self.assertEqual(payload["error"]["details"]["reason"], "past_date")
        self.assertEqual(payload["error"]["details"]["value"], "2000-09-17")


class NumericNormalizationTests(unittest.TestCase):
    def test_accepts_finite_non_negative_numbers(self) -> None:
        cases = [
            (41441, 41441),
            (41441.0, 41441),
            (41441.5, 41441.5),
            ("41 441", 41441),
            ("41\u00a0441", 41441),
            ("41\u202f441", 41441),
            ("41441.50", 41441.5),
            ("41441,50", 41441.5),
            ("+41441", 41441),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(numeric_or_none(value), expected)

    def test_rejects_unsafe_or_ambiguous_values(self) -> None:
        values = [
            None,
            True,
            False,
            -1,
            -0.5,
            "-1",
            "",
            "not-a-number",
            "1,000",
            "1.2.3",
            "1,2.3",
            "NaN",
            "Infinity",
            float("nan"),
            float("inf"),
            {},
            [],
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertIsNone(numeric_or_none(value))


if __name__ == "__main__":
    unittest.main()
