from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from flights_cli.cli import build_parser, normalize_global_json
from flights_cli.env import load_env_file

from helpers import PROJECT, TEST_ENV


class CliContractTests(unittest.TestCase):
    def test_route_commands_default_same_airport_minimum_is_120(self) -> None:
        parser = build_parser()
        cases = [
            ["route", "plan", "SVX", "LON", "--depart-date", "2026-07-20"],
            ["route", "validate"],
            ["route", "rank"],
            ["route", "assemble"],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertEqual(args.min_same_airport_min, 120)
                self.assertEqual(args.min_cross_airport_min, 300)
        assemble_args = parser.parse_args(["route", "assemble"])
        self.assertEqual(assemble_args.limit_per_pair, 10)

    def test_su_flights_legacy_command_is_removed(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as ctx:
            build_parser().parse_args(["su-flights", "SVX", "SVO", "--depart-date", "2026-07-19"])

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("invalid choice", stderr.getvalue())

    def test_load_env_file_reads_hermes_dotenv_without_overriding(self) -> None:
        old_token = os.environ.pop("TRAVELPAYOUTS_TOKEN", None)
        old_marker = os.environ.pop("TRAVELPAYOUTS_MARKER", None)
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                env_path = Path(tmp_dir) / ".env"
                env_path.write_text("TRAVELPAYOUTS_TOKEN=file-token\nTRAVELPAYOUTS_MARKER=file-marker\n", encoding="utf-8")
                loaded = load_env_file(env_path)
                self.assertEqual(os.environ["TRAVELPAYOUTS_TOKEN"], "file-token")
                self.assertEqual(os.environ["TRAVELPAYOUTS_MARKER"], "file-marker")
                self.assertEqual(loaded, {"TRAVELPAYOUTS_TOKEN", "TRAVELPAYOUTS_MARKER"})

                os.environ["TRAVELPAYOUTS_TOKEN"] = "external-token"
                loaded_again = load_env_file(env_path)
                self.assertEqual(os.environ["TRAVELPAYOUTS_TOKEN"], "external-token")
                self.assertEqual(loaded_again, set())
        finally:
            if old_token is not None:
                os.environ["TRAVELPAYOUTS_TOKEN"] = old_token
            else:
                os.environ.pop("TRAVELPAYOUTS_TOKEN", None)
            if old_marker is not None:
                os.environ["TRAVELPAYOUTS_MARKER"] = old_marker
            else:
                os.environ.pop("TRAVELPAYOUTS_MARKER", None)

    def test_json_doctor_envelope(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "flights_cli", "--json", "doctor"],
            cwd=PROJECT,
            env=TEST_ENV,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "doctor")
        self.assertIn("cache_counts", payload["data"])
        self.assertEqual(payload["data"]["safety"]["travelpayouts_cached_fetch_requires"], "request search --fetch")
        self.assertEqual(payload["data"]["safety"]["live_provider_commands"], ["kb-search", "u6-prices", "route kb-assemble"])
        self.assertNotIn("live_calls_require_flag", payload["data"]["safety"])

        human_proc = subprocess.run(
            [sys.executable, "-m", "flights_cli", "doctor"],
            cwd=PROJECT,
            env=TEST_ENV,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertIn("Travelpayouts cached fetch: request search --fetch", human_proc.stdout)
        self.assertIn("provider live commands: kb-search, u6-prices, route kb-assemble", human_proc.stdout)

    def test_json_route_plan_envelope_and_repeatable_hubs(self) -> None:
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
                "2026-07-20",
                "--hub",
                "IST",
                "--hub",
                "DXB",
            ],
            cwd=PROJECT,
            env=TEST_ENV,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "route plan")
        data = payload["data"]
        self.assertEqual(data["hubs"], ["IST", "DXB"])
        self.assertEqual(data["destination_airports"], ["LHR", "LGW", "STN", "LTN"])
        self.assertEqual(data["metrics"]["segment_request_count"], 10)
        self.assertIn("warnings", data)
        self.assertNotIn("cache_age_minutes", data)

    def test_normalize_global_json_accepts_trailing_json(self) -> None:
        argv = ["flights", "route", "plan", "SVX", "LON", "--json"]
        self.assertEqual(normalize_global_json(argv), ["flights", "--json", "route", "plan", "SVX", "LON"])


if __name__ == "__main__":
    unittest.main()
