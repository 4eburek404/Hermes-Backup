from __future__ import annotations

import json
import subprocess
import sys
import unittest
from datetime import date

from flights_cli.domain.normalize import parse_iso_date
from flights_cli.errors import CliError
from helpers import PROJECT, TEST_ENV


class DateValidationTests(unittest.TestCase):
    def test_parse_iso_date_rejects_past_dates_with_future_occurrence_hint(self) -> None:
        with self.assertRaises(CliError) as ctx:
            parse_iso_date("2025-09-17", "depart-date", today=date(2026, 5, 10))

        self.assertEqual(ctx.exception.error_type, "validation_error")
        self.assertEqual(
            str(ctx.exception),
            "depart-date is in the past: 2025-09-17. Today is 2026-05-10. Did you mean 2026-09-17?",
        )

    def test_parse_iso_date_allows_today_and_future_dates(self) -> None:
        today = date(2026, 5, 10)

        self.assertEqual(parse_iso_date("2026-05-10", "depart-date", today=today), today)
        self.assertEqual(parse_iso_date("2026-09-17", "depart-date", today=today), date(2026, 9, 17))

    def test_json_cli_returns_validation_error_for_past_departure_date(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "flights_cli",
                "--json",
                "route",
                "plan",
                "SVX",
                "LON",
                "--depart-date",
                "2000-09-17",
            ],
            cwd=PROJECT,
            env=TEST_ENV,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")
        payload = json.loads(proc.stderr)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["type"], "validation_error")
        self.assertIn("depart-date is in the past: 2000-09-17", payload["error"]["message"])
        self.assertIn("Did you mean", payload["error"]["message"])


if __name__ == "__main__":
    unittest.main()
