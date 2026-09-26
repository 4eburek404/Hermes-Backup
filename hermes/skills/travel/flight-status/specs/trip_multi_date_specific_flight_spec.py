#!/usr/bin/env python3
"""Executable CLI specification for selecting an operation by date.

A saved real Trip.com response contains SU1524 operations for both Sep 25 and
Sep 26, 2026. The CLI must return the requested operation regardless of its
position in the page; a date absent from the page must remain a mismatch.

Run from the skill root:
    python3 specs/trip_multi_date_specific_flight_spec.py

Only the external page fetch is replaced. CLI handling and normalization remain
production behavior.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "trip_board.py"
FIXTURE = ROOT / "specs/fixtures/trip/trip_com_su1524_multi_date.html"


def load_cli():
    spec = importlib.util.spec_from_file_location("trip_board", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_cli(module, operating_date: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        mock.patch.object(module, "fetch_specific_flight_page", return_value=FIXTURE.read_text(encoding="utf-8")),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        try:
            code = module.main(["--flight", "SU1524", "--date", operating_date, "--json"])
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, stdout.getvalue(), stderr.getvalue()


class TripMultiDateSpecificFlightSpecification(unittest.TestCase):
    def test_requested_operation_is_selected_and_absent_date_is_not_substituted(self) -> None:
        cli = load_cli()
        code, stdout, stderr = run_cli(cli, "2026-09-26")
        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["date"], "2026-09-26")
        self.assertEqual(len(payload["rows"]), 1)
        self.assertEqual(
            payload["rows"][0],
            {
                "flight_number": "SU1524",
                "departure_airport": "SVO",
                "arrival_airport": "RGK",
                "status": "Diverted",
                "scheduled": {"departure": "00:10", "arrival": "08:35"},
                "current": {"departure": "00:34", "arrival": "09:02"},
            },
        )

        code, stdout, stderr = run_cli(cli, "2026-09-27")
        self.assertEqual(code, 2, stdout + stderr)
        self.assertEqual(stderr, "")
        self.assertEqual(
            json.loads(stdout),
            {"ok": False, "error": {"code": "trip_operating_date_mismatch", "detail": None}},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
