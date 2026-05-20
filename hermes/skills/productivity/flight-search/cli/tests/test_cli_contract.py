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

from jsonschema import Draft202012Validator

from flights_cli.cli import apply_agent_brief_output, apply_agent_mode_defaults, build_parser, normalize_global_json
from flights_cli.config import DEFAULT_ROUTE_HUBS
from flights_cli.env import load_env_file

from helpers import PROJECT, TEST_ENV


def load_doctor_envelope_schema() -> dict:
    schema_rel = (
        Path("hermes")
        / "skills"
        / "software-development"
        / "skill-audit-and-improvement"
        / "schemas"
        / "cli-doctor-envelope.v1.schema.json"
    )
    for base in (PROJECT, *PROJECT.parents):
        candidate = base / schema_rel
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise AssertionError(f"doctor envelope schema not found from {PROJECT}")


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

    def test_u6_prices_standalone_probe_is_removed(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as ctx:
            build_parser().parse_args(["u6-prices", "SVX", "IST", "--from-date", "2026-07-19"])

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("invalid choice", stderr.getvalue())

    def test_travelpayouts_price_search_commands_are_removed(self) -> None:
        removed_commands = [
            ["request", "search", "SVX", "IST", "--depart-date", "2026-07-19"],
            ["request", "prices-for-dates", "SVX", "IST", "--departure-at", "2026-07-19"],
            ["request", "grouped-prices", "SVX", "IST", "--departure-at", "2026-07"],
            ["results", "parse", "--input", "tests/fixtures/svx-ist.raw.json"],
        ]
        for argv in removed_commands:
            with self.subTest(argv=argv):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as ctx:
                    build_parser().parse_args(argv)
                self.assertEqual(ctx.exception.code, 2)

    def test_subprocess_test_env_disables_bytecode_writes(self) -> None:
        self.assertEqual(TEST_ENV["PYTHONDONTWRITEBYTECODE"], "1")

    def test_load_env_file_reads_hermes_dotenv_without_overriding(self) -> None:
        old_travelpayouts_auth = os.environ.pop("TRAVELPAYOUTS_TOKEN", None)
        old_marker = os.environ.pop("TRAVELPAYOUTS_MARKER", None)
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                env_path = Path(tmp_dir) / ".env"
                env_path.write_text(
                    "\n".join(["TRAVELPAYOUTS_" + "TOKEN=placeholder", "TRAVELPAYOUTS_MARKER=placeholder"]) + "\n",
                    encoding="utf-8",
                )
                loaded = load_env_file(env_path)
                self.assertEqual(os.environ["TRAVELPAYOUTS_TOKEN"], "placeholder")
                self.assertEqual(os.environ["TRAVELPAYOUTS_MARKER"], "placeholder")
                self.assertEqual(loaded, {"TRAVELPAYOUTS_TOKEN", "TRAVELPAYOUTS_MARKER"})

                os.environ["TRAVELPAYOUTS_TOKEN"] = "external-token"
                loaded_again = load_env_file(env_path)
                self.assertEqual(os.environ["TRAVELPAYOUTS_TOKEN"], "external-token")
                self.assertEqual(loaded_again, set())
        finally:
            if old_travelpayouts_auth is not None:
                os.environ["TRAVELPAYOUTS_TOKEN"] = old_travelpayouts_auth
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
        doctor_schema = load_doctor_envelope_schema()
        Draft202012Validator.check_schema(doctor_schema)
        Draft202012Validator(doctor_schema).validate(payload)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "doctor")
        self.assertEqual(payload["issues"], [])
        self.assertEqual(payload["data"]["cli"], {"name": "flights-cli", "version": "0.10.3"})
        self.assertEqual(payload["data"]["skill"], {"name": "flight-search", "version": "0.10.3"})
        self.assertIn("cache_counts", payload["data"])
        self.assertNotIn("cached_fetch_default", payload["data"])
        self.assertEqual(payload["data"]["safety"]["travelpayouts_usage"], "static_catalog_only")
        self.assertFalse(payload["data"]["safety"]["travelpayouts_price_search_enabled"])
        self.assertNotIn("travelpayouts_cached_fetch_requires", payload["data"]["safety"])
        self.assertEqual(payload["data"]["safety"]["live_provider_commands"], ["kb-search", "fli-search", "fli-dates", "route kb-assemble", "route live-assemble"])
        self.assertEqual(payload["data"]["safety"]["legacy_debug_commands"], [])
        self.assertFalse(payload["data"]["runtime_evidence_policy"]["retry_policy"]["active_retry"])
        self.assertEqual(payload["data"]["runtime_evidence_policy"]["request_deduplication"]["scope"], "in_process_identical_segment_probes")
        self.assertNotIn("live_calls_require_flag", payload["data"]["safety"])
        self.assertEqual([item["code"] for item in payload["data"]["default_route_hubs"]], list(DEFAULT_ROUTE_HUBS))
        self.assertNotIn("routes", payload["data"]["cache_counts"])

        human_proc = subprocess.run(
            [sys.executable, "-m", "flights_cli", "doctor"],
            cwd=PROJECT,
            env=TEST_ENV,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertIn("flights 0.10.3 (skill flight-search 0.10.3)", human_proc.stdout)
        self.assertIn("Travelpayouts usage: static catalogs only", human_proc.stdout)
        self.assertNotIn("legacy Travelpayouts cached fetch", human_proc.stdout)
        self.assertIn("main live commands: kb-search, fli-search, fli-dates, route kb-assemble, route live-assemble", human_proc.stdout)
        self.assertNotIn("legacy debug commands", human_proc.stdout)
        self.assertIn("default hubs: IST, DXB, DOH", human_proc.stdout)

    def test_auto_hubs_flag_is_removed(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as ctx:
            build_parser().parse_args(["route", "plan", "SVX", "LON", "--depart-date", "2026-07-20", "--auto-hubs"])

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("unrecognized arguments: --auto-hubs", stderr.getvalue())

    def test_route_plan_direct_only_flag_is_removed(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as ctx:
            build_parser().parse_args(["route", "plan", "SVX", "LON", "--depart-date", "2026-07-20", "--direct-only"])

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("unrecognized arguments: --direct-only", stderr.getvalue())

    def test_agent_mode_sets_compact_live_assembly_defaults(self) -> None:
        args = build_parser().parse_args(
            ["route", "kb-assemble", "SVX", "DEL", "--depart-date", "2026-06-01", "--agent-mode"]
        )

        apply_agent_mode_defaults(args)

        self.assertTrue(args.agent_report)
        self.assertEqual(args.include_candidates, 0)
        self.assertEqual(args.include_ranked_candidates, 5)
        self.assertEqual(args.include_rejected_pairs, 5)
        self.assertEqual(args.include_segment_results, 0)
        self.assertEqual(args.max_candidates, 10)
        self.assertEqual(args.aggregate_control_limit, 10)

    def test_agent_mode_preserves_compact_carrier_aggregate_default(self) -> None:
        args = build_parser().parse_args(
            [
                "route",
                "kb-assemble",
                "SVX",
                "DEL",
                "--depart-date",
                "2026-06-01",
                "--agent-mode",
                "--aggregate-control-carrier",
                "SU",
            ]
        )

        apply_agent_mode_defaults(args)

        self.assertEqual(args.aggregate_control_limit, 10)

    def test_agent_brief_implies_agent_mode_and_trims_json_payload(self) -> None:
        args = build_parser().parse_args(
            ["route", "kb-assemble", "SVX", "DEL", "--depart-date", "2026-06-01", "--agent-brief"]
        )

        apply_agent_mode_defaults(args)
        trimmed = apply_agent_brief_output(
            args,
            {
                "agent_report": {"answer_lines": ["ok"]},
                "ranked": [{"id": "noisy"}],
                "candidates": [{"id": "raw"}],
            },
        )

        self.assertTrue(args.agent_mode)
        self.assertTrue(args.agent_report)
        self.assertEqual(trimmed, {"agent_report": {"answer_lines": ["ok"]}})

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
        self.assertNotIn("manual_links", data)
        self.assertNotIn("manual_direct_links", data["metrics"].get("without_cli", {}))
        self.assertIn("warnings", data)
        self.assertNotIn("cache_age_minutes", data)

    def test_normalize_global_json_accepts_trailing_json(self) -> None:
        argv = ["flights", "route", "plan", "SVX", "LON", "--json"]
        self.assertEqual(normalize_global_json(argv), ["flights", "--json", "route", "plan", "SVX", "LON"])


if __name__ == "__main__":
    unittest.main()
